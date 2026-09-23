#!/usr/bin/env python3
"""Regenerate every figure in the report from committed data.

    python scripts/make_figures.py              # all of them
    python scripts/make_figures.py --list       # name, question, inputs
    python scripts/make_figures.py --only survival_curves cost_sensitivity
    python scripts/make_figures.py --index      # rewrite docs/figure_index.md

Each entry below is a figure, the **question it answers**, and the committed files it
reads. A figure with no question does not belong in the report, so the registry is
also the check: anything that cannot be given a question here is deleted rather than
kept because the data existed.

Most inputs are committed (`data/processed/*.csv`, `reports/tables/*.csv`). Three
figures need what cannot be committed: the traded products' price history, which
`docs/data_sources.md` explains is reproduced by `scripts/fetch_data.py` rather than
redistributed, and the GARCH residuals, which are refitted here in a few seconds from
the committed index. Those are marked `raw` and `refit` in the listing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from svcarry.config import load_config          # noqa: E402
from svcarry.viz import figures as F            # noqa: E402
from svcarry.viz.style import save_figure       # noqa: E402

CFG = load_config()
PROC = ROOT / CFG.dotted("paths.processed")
TAB = ROOT / CFG.dotted("paths.tables")
FIG = ROOT / CFG.dotted("paths.figures")


def _read(path: Path, **kw) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(
            f"\nMissing input: {path.relative_to(ROOT)}\n"
            f"  -> run the pipeline stage that produces it "
            f"(python scripts/run_pipeline.py --list)\n"
        )
    return pd.read_csv(path, **kw)


def _dated(path: Path) -> pd.DataFrame:
    return _read(path, parse_dates=["date"]).set_index("date")


def _index() -> pd.DataFrame:
    return _dated(PROC / "index_daily.csv")


def _stress_windows() -> dict:
    return {k: (v[0], v[1]) for k, v in CFG.dotted("robustness.stress_windows").items()}


# ----------------------------------------------------------------- reconstruction
def fig_index_vs_products():
    from svcarry.data.prices import load_prices, split_adjusted_returns

    idx = _index()
    lvl = idx["level_er"]
    prods = {}
    for sym in ("VIXY", "VXX"):
        r = split_adjusted_returns(load_prices(sym)).reindex(idx.index)
        prods[sym] = (1.0 + r.fillna(0.0)).cumprod().where(r.notna().cummax())
    vixy = split_adjusted_returns(load_prices("VIXY")).reindex(idx.index)
    resid = (vixy - idx["ret"]).dropna()
    return F.plot_index_vs_products(lvl, prods, residual=resid)


def fig_term_structure():
    cm = _dated(PROC / "curve_constant_maturity.csv")
    sig = _dated(PROC / "signals_daily.csv")
    return F.plot_term_structure(cm, slope=sig["slope_cm"],
                                 threshold=float(CFG.dotted("strategy.contango_threshold")))


# --------------------------------------------------------------------- mechanics
def _decay_results():
    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.etp.mechanics import decay_regression

    idx = _index()["ret"]
    out = {}
    for sym in ("VIXY", "SVXY", "UVXY"):
        L = float(CFG.dotted(f"products.{sym}.leverage"))
        after = CFG.dotted(f"products.{sym}.leverage_after", None)
        when = CFG.dotted(f"products.{sym}.leverage_change_date", None)
        r = split_adjusted_returns(load_prices(sym))
        df = pd.DataFrame({"p": r}).join(idx.rename("i"), how="inner").dropna()
        if after is not None and when:
            df = df[df.index < pd.Timestamp(when)]       # the first leverage regime
        out[f"{sym} ({L:+g}x)"] = decay_regression(df["p"], df["i"], leverage=L,
                                                   horizon=21)
    return out


def fig_decay_regression():
    return F.plot_decay_regression(_decay_results())


def fig_decay_blocks():
    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.etp.mechanics import decay_blocks, theoretical_decay

    idx = _index()["ret"]
    break_date = pd.Timestamp(CFG.dotted("products.SVXY.leverage_change_date"))
    panels = []
    for sym, L, lo, hi, flag in (
        ("SVXY", -1.0, None, break_date - pd.Timedelta(days=1), "2018-02-07"),
        ("SVXY", -0.5, break_date, None, None),
        ("UVXY", 2.0, None, break_date - pd.Timedelta(days=1), "2018-02-07"),
        ("UVXY", 1.5, break_date, None, None),
    ):
        r = split_adjusted_returns(load_prices(sym))
        d = pd.DataFrame({"p": r}).join(idx.rename("i"), how="inner").dropna()
        if lo is not None:
            d = d[d.index >= lo]
        if hi is not None:
            d = d[d.index <= hi]
        era = "before" if hi is not None else "after"
        panels.append({"title": f"{sym} at {L:+g}x ({era} {break_date:%-d %b %Y})",
                       "blocks": decay_blocks(d["p"], d["i"], L, 21),
                       "theory": theoretical_decay(L), "flag": flag})
    return F.plot_decay_blocks(panels)


def fig_flow_vs_open_interest():
    fl = _dated(TAB / "rebalancing_flows.csv")
    return F.plot_flow_vs_open_interest(fl["share_oi_front_lower"],
                                        fl["share_oi_front_upper"])


def fig_product_assets_with_anchors():
    b = _dated(PROC / "product_assets_bounds.csv")
    anchors = _read(ROOT / "data/reference/product_asset_anchors.csv",
                    comment="#", parse_dates=["date"])
    bounds = {s: g.drop(columns=["symbol"]) for s, g in b.groupby("symbol")}
    return F.plot_asset_bounds({s: bounds[s] for s in ("SVXY", "UVXY", "VIXY")
                                if s in bounds}, anchors)


# -------------------------------------------------------------------------- tail
def _pre2018_fit():
    from svcarry.econometrics.garch import GJRGarch

    lr = np.log1p(_index()["ret"].dropna())
    return GJRGarch(dist=CFG.dotted("tail.garch_dist")).fit(
        lr[lr.index <= "2017-12-31"], n_starts=4, seed=0)


def fig_mean_excess():
    from svcarry.econometrics.evt import mean_excess

    z = _pre2018_fit().std_resid
    th, me, se = mean_excess(z, tail="upper", n_points=60, q_lo=0.80, q_hi=0.99)
    grid = _read(TAB / "evt_thresholds.csv")
    ch = grid[(grid["sample"] == "pre2018") & (grid["chosen"])]
    return F.plot_mean_excess(th, me, se,
                              chosen=float(ch["threshold"].iloc[0]) if len(ch) else None)


def fig_qq_gpd():
    from svcarry.econometrics.evt import fit_gpd

    z = _pre2018_fit().std_resid
    grid = _read(TAB / "evt_thresholds.csv")
    q = float(grid[(grid["sample"] == "pre2018") & (grid["chosen"])]["q"].iloc[0])
    g = fit_gpd(z, q=q, tail="upper")
    exc = np.sort(z[z > g.threshold] - g.threshold)
    pp = (np.arange(1, len(exc) + 1) - 0.5) / len(exc)
    theo = g.beta / g.xi * ((1 - pp) ** (-g.xi) - 1)
    return F.plot_gpd_qq(exc, theo)


def fig_shape_across_thresholds():
    grid = _read(TAB / "evt_thresholds.csv")
    pre = grid[grid["sample"] == "pre2018"]
    ch = pre[pre["chosen"]]
    return F.plot_shape_across_thresholds(
        pre, chosen=float(ch["q"].iloc[0]) if len(ch) else None)


def fig_survival_curves():
    from svcarry.viz.style import LINESTYLES, PALETTE

    sv = _read(TAB / "survival_curves.csv")
    curves, bands, styles = {}, {}, {}
    for dyn, g in sv.groupby("dynamics"):
        short = "unbounded" if dyn == "unbounded" else "capped"
        for k in ("-1x", "-0.5x"):
            nm = f"{k}, {short}"
            curves[nm] = pd.Series(g[f"survival_{k}"].to_numpy(),
                                   index=g["years"].to_numpy())
            bands[nm] = (g[f"survival_{k}"] - 1.96 * g[f"se_{k}"],
                         g[f"survival_{k}"] + 1.96 * g[f"se_{k}"])
            styles[nm] = {"color": PALETTE[0] if k == "-1x" else PALETTE[1],
                          "linestyle": LINESTYLES[0] if short == "unbounded" else LINESTYLES[1]}
    return F.plot_survival_curves(curves, bands, styles=styles)


def fig_kelly_growth_curve():
    from svcarry.econometrics.kelly import growth_rate_curve

    R = _index()["ret"].dropna().to_numpy()
    f, g = growth_rate_curve(R, f_grid=np.linspace(0.0, 1.03, 250))
    k = _read(TAB / "kelly.csv").set_index("returns")
    return F.plot_kelly_growth_curve(f, g, f_star=float(k.loc["full sample", "f_star"]),
                                     marks={"-1x offered": 1.0, "-0.5x": 0.5})


def fig_exante_warning():
    path = _dated(TAB / "exante_warning_path.csv")
    return F.plot_exante_warning(path.loc[:"2018-02-07"])


# ---------------------------------------------------------------------- signals
def fig_vrp_timeseries():
    return F.plot_vrp_timeseries(_dated(PROC / "signals_daily.csv"))


def fig_har_forecast_vs_realised():
    h = _dated(PROC / "har_oos_forecasts.csv").dropna()
    d = _read(TAB / "har_oos_diagnostics.csv")
    d = d[d["period"] == "full"].set_index("model")
    stats = {"oos_r2": float(d.loc["HAR log (primary)", "oos_r2_vs_eval_mean"]),
             "mz_beta": float(d.loc["HAR log (primary)", "mz_beta"]),
             "trail_r2": float(d.loc["trailing 21-day RV", "oos_r2_vs_eval_mean"]),
             "trail_mz": float(d.loc["trailing 21-day RV", "mz_beta"])}
    return F.plot_har_forecast_vs_realised(h["har_forecast"], h["realised_next_h"],
                                           h["trailing_rv"], stats=stats)


def fig_signal_state():
    return F.plot_signal_state(_dated(PROC / "signals_daily.csv"),
                               threshold=float(CFG.dotted("strategy.contango_threshold")))


# --------------------------------------------------------------------- strategy
def _benchmarks() -> pd.DataFrame:
    return _dated(PROC / "benchmarks_daily.csv")


def fig_equity_curve():
    b = _benchmarks().drop(columns=["accrual"])
    eq = {nm: (1.0 + s.fillna(0.0)).cumprod() for nm, s in b.items()}
    return F.plot_equity_curves(eq, oos_start=CFG.dotted("sample.oos_start"))


def fig_drawdowns():
    from svcarry.evaluation.metrics import drawdown

    b = _benchmarks().drop(columns=["accrual", "constant weight 0.196 short"],
                           errors="ignore")
    return F.plot_drawdowns({nm: drawdown(s.fillna(0.0))["drawdown"] for nm, s in b.items()})


def fig_rolling_sharpe():
    from svcarry.evaluation.metrics import rolling_sharpe

    b = _benchmarks()
    acc = b["accrual"]
    keep = [c for c in b.columns if c not in ("accrual", "buy-and-hold -1x (XIV fee)")]
    return F.plot_rolling_sharpe({nm: rolling_sharpe(b[nm], 252, rf=acc) for nm in keep},
                                 252, oos_start=CFG.dotted("sample.oos_start"))


def fig_weight_and_binding_constraint():
    d = _dated(PROC / "backtest_daily.csv")
    lag = int(CFG.dotted("strategy.signal_lag"))
    return F.plot_weight_and_constraint(d["weight"], d["binding"].shift(lag),
                                        windows=_stress_windows())


def fig_feb2018_detail():
    from svcarry.data.prices import load_prices, split_adjusted_returns

    d = _dated(PROC / "backtest_daily.csv")
    b = _benchmarks()
    lo, hi = "2018-01-15", "2018-03-01"
    idx_level = (1.0 + d["index_ret"].loc[lo:hi].fillna(0.0)).cumprod()
    prods = {"strategy equity": (1.0 + d["ret"].loc[lo:hi]).cumprod(),
             "buy-and-hold -1x": (1.0 + b["buy-and-hold -1x (XIV fee)"].loc[lo:hi]).cumprod()}
    for sym in ("VIXY", "SVXY", "UVXY"):
        r = split_adjusted_returns(load_prices(sym)).loc[lo:hi]
        prods[f"{sym} (traded)"] = (1.0 + r).cumprod()
    return F.plot_event_detail(idx_level, prods, weight=d["weight"].loc[lo:hi],
                               lo=lo, hi=hi)


# ------------------------------------------------------------------- robustness
def fig_cost_sensitivity():
    c = _read(TAB / "robustness_costs.csv")
    sh = c.set_index("cost_ticks")["sharpe"]
    below = sh[sh <= 0]
    be = None
    if len(below):
        h = below.index[0]
        l = sh.index[sh.index.get_loc(h) - 1]
        be = l + (h - l) * sh[l] / (sh[l] - sh[h])
    return F.plot_cost_sensitivity(c["cost_ticks"], c["sharpe"], breakeven=be)


def fig_parameter_heatmap():
    g = _read(TAB / "specification_distribution.csv")
    hm = g[g["rebalance"] == 1].pivot_table(index="contango_threshold",
                                            columns="max_stress_loss",
                                            values="sharpe", aggfunc="mean")
    return F.plot_parameter_heatmap(
        hm, chosen=(float(CFG.dotted("strategy.contango_threshold")),
                    float(CFG.dotted("strategy.max_stress_loss"))),
        source=F._SOURCE + " Daily rebalancing, averaged over the three volatility "
        "targets (0.10, 0.15, 0.20); the full 144-cell grid is in "
        "specification_distribution.csv.")


def fig_specification_distribution():
    g = _read(TAB / "specification_distribution.csv")
    chosen = float(g[g["is_chosen"]]["sharpe"].iloc[0])
    return F.plot_specification_distribution(g["sharpe"], chosen=chosen)


def fig_subsample_stability():
    s = _read(TAB / "robustness_subsamples.csv")
    s = s[s["kind"].isin(["configured subsample", "single year"])]
    est = {r["name"]: (r["sharpe"], r.get("sharpe_se_lo", np.nan)) for _, r in s.iterrows()}
    g = _read(TAB / "specification_distribution.csv")
    return F.plot_subsample_stability(est, reference=float(g[g["is_chosen"]]["sharpe"].iloc[0]))


# ---------------------------------------------------------------------- registry
FIGURES = {
    "index_vs_products": (
        fig_index_vs_products,
        "Does the rebuilt index track the products it is supposed to, and how does the "
        "difference behave through time? (H1)",
        "index_daily.csv; product prices (raw)"),
    "term_structure": (
        fig_term_structure,
        "What does the futures curve look like through time, and when is it inverted "
        "enough to switch the strategy off?",
        "curve_constant_maturity.csv, signals_daily.csv"),
    "decay_regression": (
        fig_decay_regression,
        "Do the products decay at the rate the leverage identity predicts? (H2, "
        "mechanical part)",
        "index_daily.csv; product prices (raw)"),
    "decay_blocks": (
        fig_decay_blocks,
        "What do the decay regression's own observations look like, and how much of "
        "the -1x result is the single block holding 5-6 February 2018? (H2)",
        "index_daily.csv; product prices (raw)"),
    "flow_vs_open_interest": (
        fig_flow_vs_open_interest,
        "How large was mechanical rebalancing demand against the open interest that "
        "had to absorb it, at both asset bounds? (H2)",
        "rebalancing_flows.csv"),
    "product_assets_with_anchors": (
        fig_product_assets_with_anchors,
        "How wide is the band on assets outstanding between the disclosed anchors, and "
        "where are the anchors?",
        "product_assets_bounds.csv, product_asset_anchors.csv"),
    "mean_excess": (
        fig_mean_excess,
        "Where does the tail of the standardised residuals become straight - i.e. where "
        "may a GPD be fitted? (H3)",
        "index_daily.csv (GARCH refit), evt_thresholds.csv"),
    "qq_gpd": (
        fig_qq_gpd,
        "Does the fitted GPD describe the exceedances it was fitted to? (H3)",
        "index_daily.csv (GARCH refit), evt_thresholds.csv"),
    "shape_across_thresholds": (
        fig_shape_across_thresholds,
        "Does the tail-shape estimate depend on where the tail is declared to start? (H3)",
        "evt_thresholds.csv"),
    "survival_curves": (
        fig_survival_curves,
        "How much more likely was a -1x product to survive five years than a -0.5x one, "
        "under the pre-2018 model? (H3)",
        "survival_curves.csv"),
    "kelly_growth_curve": (
        fig_kelly_growth_curve,
        "Where does expected log growth peak, and how far is the offered -1x from it? (H4)",
        "index_daily.csv, kelly.csv"),
    "exante_warning": (
        fig_exante_warning,
        "What did a model fitted before the event say, day by day, going into "
        "5 February 2018? (H3)",
        "exante_warning_path.csv"),
    "vrp_timeseries": (
        fig_vrp_timeseries,
        "How large is the variance risk premium, and how often is it negative - the "
        "state in which the strategy stands aside?",
        "signals_daily.csv"),
    "har_forecast_vs_realised": (
        fig_har_forecast_vs_realised,
        "Do the real-time variance forecasts have out-of-sample skill, and is the "
        "trailing-RV benchmark worse?",
        "har_oos_forecasts.csv, har_oos_diagnostics.csv"),
    "signal_state": (
        fig_signal_state,
        "When is the strategy allowed in, and which filter keeps it out when it is not?",
        "signals_daily.csv"),
    "equity_curve": (
        fig_equity_curve,
        "How did the strategy compound against every benchmark, including the passive "
        "products it is supposed to improve on? (H5)",
        "benchmarks_daily.csv"),
    "drawdowns": (
        fig_drawdowns,
        "What did holding each of these cost at the worst moment?",
        "benchmarks_daily.csv"),
    "rolling_sharpe": (
        fig_rolling_sharpe,
        "Is the strategy's risk-adjusted return a property of the whole sample or of a "
        "few stretches? (H5)",
        "benchmarks_daily.csv"),
    "weight_and_binding_constraint": (
        fig_weight_and_binding_constraint,
        "How large was the position, and which of the three constraints set it on each "
        "day - with the stress windows shaded?",
        "backtest_daily.csv"),
    "feb2018_detail": (
        fig_feb2018_detail,
        "What happened to the index, the traded products, the strategy's exposure and "
        "its equity through the February 2018 event?",
        "backtest_daily.csv, benchmarks_daily.csv; product prices (raw)"),
    "cost_sensitivity": (
        fig_cost_sensitivity,
        "At what transaction cost does the out-of-sample Sharpe reach zero?",
        "robustness_costs.csv"),
    "parameter_heatmap": (
        fig_parameter_heatmap,
        "How does the result move across the threshold and crash-budget grid, and where "
        "does the pre-registered cell sit in it?",
        "specification_distribution.csv"),
    "specification_distribution": (
        fig_specification_distribution,
        "How much of the headline is the choice of specification? (the median cell "
        "against the chosen one)",
        "specification_distribution.csv"),
    "subsample_stability": (
        fig_subsample_stability,
        "Does the result hold in every subsample, or is it carried by particular years?",
        "robustness_subsamples.csv, specification_distribution.csv"),
}


def write_index() -> Path:
    lines = [
        "# Figure index",
        "",
        "Every figure in the report, the question it answers, and what it is built",
        "from. Regenerate all of them with `python scripts/make_figures.py`; the",
        "registry in that script is the source of this table.",
        "",
        "Inputs marked *(raw)* need the product price history, which is reproduced by",
        "`scripts/fetch_data.py` rather than redistributed (`docs/data_sources.md`);",
        "*(GARCH refit)* means the figure refits the pre-2018 model from the committed",
        "index, which takes a few seconds.",
        "",
        "| Figure | Question it answers | Built from |",
        "|---|---|---|",
    ]
    for name, (_, question, inputs) in FIGURES.items():
        lines.append(f"| `{name}.png` | {question} | {inputs} |")
    lines += [
        "",
        "## Conventions",
        "",
        "- One shared style module (`svcarry.viz.style`): the same palette, line styles,",
        "  date formatting and source note on every figure.",
        "- Colour is never the only carrier of meaning. The palette has seven hue pairs",
        "  whose luminance is within 0.07 of each other (`style.greyscale_check`), so",
        "  every multi-series figure also varies line style or marker, and the signal-",
        "  state strip puts each state in its own horizontal band.",
        "- Log scales wherever a series compounds over the full sample.",
        "- Uncertainty is drawn where it exists (simulation error bands on the survival",
        "  curves, one standard error on the EVT shape and the subsample Sharpes, the",
        "  asset-bound band on the flow figure).",
        "- No axis is truncated to exaggerate a difference; where a series is clipped to",
        "  stay legible the caption says so and counts the clipped points.",
    ]
    out = ROOT / "docs" / "figure_index.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=sorted(FIGURES))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--index", action="store_true")
    args = ap.parse_args()

    if args.list:
        for name, (_, question, inputs) in FIGURES.items():
            print(f"{name:32s} {question}\n{'':32s} inputs: {inputs}")
        return 0
    if args.index:
        print(f"wrote {write_index().relative_to(ROOT)}")
        return 0

    FIG.mkdir(parents=True, exist_ok=True)
    names = args.only or list(FIGURES)
    failed = []
    for name in names:
        builder = FIGURES[name][0]
        try:
            fig = builder()
        except SystemExit:
            raise
        except Exception as exc:                       # noqa: BLE001
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  [figures] {name:32s} FAILED  {type(exc).__name__}: {exc}")
            continue
        save_figure(fig, FIG / f"{name}.png")
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"  [figures] {name:32s} ok")
    write_index()
    if failed:
        print(f"\n{len(failed)} figure(s) failed:")
        for line in failed:
            print("  " + line)
        return 1
    print(f"\n{len(names)} figures in {FIG.relative_to(ROOT)}; index in docs/figure_index.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
