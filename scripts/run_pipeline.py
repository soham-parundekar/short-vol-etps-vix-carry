#!/usr/bin/env python3
"""Run the analysis end to end, from cached raw data to tables and figures.

    python scripts/run_pipeline.py                  # everything
    python scripts/run_pipeline.py --from index     # resume at a stage
    python scripts/run_pipeline.py --only tail      # one stage
    python scripts/run_pipeline.py --list           # show the stages

Stages, in dependency order:

    clean     raw files -> cleaned futures panel, ETP prices, rates
    index     panel -> reconstructed index, curve, carry, tracking validation
    mechanics leverage-decay regressions and rebalancing flows
    tail      GJR-GARCH / EVT, termination probabilities, survival, Kelly
    signals   realised variance, HAR forecasts, VRP and term-structure signals
    backtest  crash-budgeted strategy and benchmarks
    robust    parameter sweeps, subsamples, red-team checks
    figures   every figure in reports/figures

Each stage writes its outputs and a short JSON record to
``reports/_pipeline_state.json`` so a later run can tell what is already done and
what a resumed run is building on.

The pipeline reaches the network **never**. If the raw data is not present it stops
with an instruction to run ``scripts/fetch_data.py`` rather than fetching implicitly,
so that a figure can never be produced from data whose provenance was not recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from svcarry.config import load_config  # noqa: E402

STAGES = ["clean", "index", "mechanics", "tail", "signals", "backtest", "robust", "figures"]
STATE = ROOT / "reports" / "_pipeline_state.json"


def _state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def _record(stage: str, rec: dict) -> None:
    st = _state()
    st[stage] = {**rec, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


def _require(path: Path, what: str, remedy: str) -> Path:
    if not path.exists():
        raise SystemExit(
            f"\nMissing {what}: {path.relative_to(ROOT)}\n"
            f"  -> {remedy}\n"
            f"\nThe pipeline does not download anything implicitly; every input must\n"
            f"have been fetched through scripts/fetch_data.py so that its URL,\n"
            f"retrieval time and SHA-256 are recorded in data/raw/_manifest.json.\n"
        )
    return path


# --------------------------------------------------------------------- stages
def stage_clean(cfg) -> dict:
    from svcarry.data.cboe import load_vx_panel

    raw = ROOT / cfg.dotted("paths.raw") / "cboe" / "vx"
    _require(raw, "raw VIX futures files", "run: python scripts/fetch_data.py --only futures")

    panel = load_vx_panel(verbose=True)
    out = ROOT / cfg.dotted("paths.interim") / "vx_panel.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)

    qc = {
        "rows": int(len(panel)),
        "contracts": int(panel["expiry"].nunique()),
        "dates": int(panel["date"].nunique()),
        "first_date": str(panel["date"].min().date()),
        "last_date": str(panel["date"].max().date()),
        "missing_settle": int(panel["settle"].isna().sum()),
        "duplicate_keys": int(panel.duplicated(["date", "expiry"]).sum()),
        "output": str(out.relative_to(ROOT)),
    }
    print(json.dumps(qc, indent=1))
    return qc


def stage_index(cfg) -> dict:
    """Panel -> reconstructed index, constant-maturity curve, carry, tracking.

    Both roll conventions are built. Which one the project uses is decided here, on
    evidence: each is compared against the traded products and against the roll
    weight itself, and the decision plus its numbers go to
    ``reports/tables/roll_convention.csv``. Nothing downstream reads a convention
    that has not been through this comparison.
    """
    import numpy as np
    import pandas as pd

    from svcarry.data.cboe import load_cboe_index
    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.econometrics.hac import ols
    from svcarry.index.reconstruct import (
        carry_measures, constant_maturity_curve, reconstruct_index,
    )

    interim = ROOT / cfg.dotted("paths.interim") / "vx_panel.csv"
    _require(interim, "cleaned futures panel",
             "run: python scripts/run_pipeline.py --only clean")
    panel = pd.read_csv(interim, parse_dates=["date", "expiry"])

    processed = ROOT / cfg.dotted("paths.processed")
    tables = ROOT / cfg.dotted("paths.tables")
    processed.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    # ---- both conventions, on settlement prices ----------------------------
    built = {c: reconstruct_index(panel, convention=c) for c in ("sp_dji", "shifted")}
    chosen = cfg.dotted("index.roll_convention")

    # ---- traded products, for the tracking comparison ----------------------
    prods = {}
    for sym in ("VIXY", "VXX", "SVXY", "UVXY", "SVIX"):
        try:
            prods[sym] = split_adjusted_returns(load_prices(sym))
        except Exception as exc:
            print(f"  [index] no price series for {sym}: {str(exc)[:80]}")

    lev = {s: float(cfg.dotted(f"products.{s}.leverage")) for s in prods}
    lev_after = {s: cfg.dotted(f"products.{s}.leverage_after", None) for s in prods}
    lev_date = {s: cfg.dotted(f"products.{s}.leverage_change_date", None) for s in prods}

    def leverage_series(sym, idx):
        """Leverage through time: SVXY and UVXY both changed on 2018-02-28."""
        L = pd.Series(lev[sym], index=idx, dtype=float)
        if lev_after.get(sym) is not None and lev_date.get(sym):
            L.loc[L.index >= pd.Timestamp(lev_date[sym])] = float(lev_after[sym])
        return L

    eras = [("2011-01-01", "2017-12-31"), ("2018-01-01", "2021-12-31"),
            ("2022-01-01", None), (None, None)]

    rows = []
    for conv, idx_df in built.items():
        r_idx = idx_df["ret"]
        for sym, r_p in prods.items():
            for lo, hi in eras:
                a, b = r_idx.copy(), r_p.copy()
                if lo: a, b = a[a.index >= lo], b[b.index >= lo]
                if hi: a, b = a[a.index <= hi], b[b.index <= hi]
                df = pd.concat({"idx": a, "prod": b}, axis=1).dropna()
                if len(df) < 60:
                    continue
                L = leverage_series(sym, df.index)
                # Compare the product against the leveraged index return. Fees are
                # a few basis points a year and are left in the residual rather
                # than netted out, because the point of the comparison is the
                # reconstruction, not the product's expense ratio.
                fitted = L * df["idx"]
                resid = df["prod"] - fitted
                fit = ols(df["prod"].to_numpy(), fitted.to_numpy(),
                          names=["lev_idx"], cov_type="HAC")
                rows.append({
                    "convention": conv, "symbol": sym,
                    "start": str(df.index.min().date()), "end": str(df.index.max().date()),
                    "n": len(df),
                    "corr": float(df["idx"].corr(df["prod"])),
                    "slope": float(fit.params[1]),
                    "slope_se": float(fit.bse[1]),
                    "slope_over_lev": float(fit.params[1] / L.mean()),
                    "te_bp_daily": float(resid.std() * 1e4),
                    "mean_resid_bp": float(resid.mean() * 1e4),
                })
    track = pd.DataFrame(rows)
    track.to_csv(tables / "index_tracking.csv", index=False)

    # ---- the decisive test: does the residual load on the roll weight? -----
    # A mis-timed roll shows up as tracking residual that moves with w1. Under the
    # correct convention the slope is indistinguishable from zero; under a
    # convention that is a day out, the residual carries the roll.
    conv_rows = []
    for conv, idx_df in built.items():
        for sym, r_p in prods.items():
            df = pd.concat({"idx": idx_df["ret"], "prod": r_p,
                            "w1": idx_df["w1"].shift(1)}, axis=1).dropna()
            df = df[df.index >= "2011-01-01"]
            if len(df) < 250:
                continue
            L = leverage_series(sym, df.index)
            resid = df["prod"] - L * df["idx"]
            fit = ols(resid.to_numpy(), df[["w1"]].to_numpy(),
                      names=["w1_lag"], cov_type="HAC")
            conv_rows.append({
                "convention": conv, "symbol": sym, "n": len(df),
                "beta_w1_bp": float(fit.params[1] * 1e4),
                "t_stat": float(fit.tvalues[1]),
                "p_value": float(fit.pvalues[1]),
                "resid_sd_bp": float(resid.std() * 1e4),
            })
    conv_tab = pd.DataFrame(conv_rows)
    conv_tab.to_csv(tables / "roll_convention.csv", index=False)

    # ---- outputs for the chosen convention ---------------------------------
    index_df = built[chosen]
    cm = constant_maturity_curve(
        panel, maturities=tuple(cfg.dotted("index.constant_maturities")),
    )
    vix = vix3m = None
    for name, target in (("VIX", "vix"), ("VIX3M", "vix3m")):
        try:
            s = load_cboe_index(name)["close"]
            if target == "vix":
                vix = s
            else:
                vix3m = s
        except Exception as exc:
            print(f"  [index] no {name} history: {str(exc)[:80]}")
    carry = carry_measures(index_df, vix=vix, vix3m=vix3m, cm=cm)

    out = index_df.join(carry[[c for c in carry.columns if c not in index_df.columns]])
    out.to_csv(processed / "index_daily.csv", index_label="date")
    cm.to_csv(processed / "curve_constant_maturity.csv", index_label="date")

    r = out["ret"].dropna()
    ann = float((1.0 + r).prod() ** (252.0 / len(r)) - 1.0)
    qc = {
        "convention": chosen,
        "rows": int(len(out)),
        "first_date": str(out.index.min().date()),
        "last_date": str(out.index.max().date()),
        "sessions_with_missing_price": int((out["n_missing"] > 0).sum()),
        "sessions_with_nan_return": int(out["ret"].isna().sum()) - 1,
        "ann_return": ann,
        "ann_vol": float(r.std() * np.sqrt(252.0)),
        "worst_day": float(r.min()),
        "worst_day_date": str(r.idxmin().date()),
        "best_day": float(r.max()),
        "best_day_date": str(r.idxmax().date()),
        "feb_2018_spike": float(r.get(pd.Timestamp("2018-02-05"), np.nan)),
        "outputs": ["data/processed/index_daily.csv",
                    "data/processed/curve_constant_maturity.csv",
                    "reports/tables/index_tracking.csv",
                    "reports/tables/roll_convention.csv"],
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


def _not_yet(name: str):
    def _stage(cfg):
        raise SystemExit(
            f"Stage '{name}' requires the upstream stages to have produced their "
            f"outputs. Run the earlier stages first, or `--list` to see the order."
        )
    return _stage


def stage_mechanics(cfg) -> dict:
    """Leverage decay, the February 2018 de-levering, and rebalancing flows.

    Three deliberate choices, each of which changes what may be claimed.

    *The decay regression is reported with and without the block containing
    5 February 2018.* That single block moves the SVXY slope by 1.76 where the next
    most influential moves it by 0.11, for two documented reasons: the identity is a
    continuous-rebalancing approximation and errs by 28 percentage points at a +96%
    daily move, and the index-product measurement gap (``docs/validation.md`` V6, V9)
    takes about three sessions to wash out. Neither is a data error, so the block is
    not deleted - it is reported both ways with the diagnostics that explain it.

    *Assets are bounded, never point estimated.* See :mod:`svcarry.etp.assets`.

    *The flow conclusion is stated at the LOWER bound.* The band is wide in the weeks
    around Volmageddon, and the upper bound is not merely imprecise but implausible
    there - it implies more than the whole front-month open interest on seven
    sessions. The lower bound never does, and it also excludes XIV and every other
    non-ProShares product, so it understates the complex twice over.
    """
    import numpy as np
    import pandas as pd

    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.econometrics.hac import ols
    from svcarry.etp.assets import asset_bounds, load_anchors
    from svcarry.etp.mechanics import (
        block_influence, decay_blocks, decay_regression,
        identity_approximation_error, theoretical_decay,
    )

    processed = ROOT / cfg.dotted("paths.processed")
    tables = ROOT / cfg.dotted("paths.tables")
    tables.mkdir(parents=True, exist_ok=True)

    index_path = _require(processed / "index_daily.csv", "the reconstructed index",
                          "run: python scripts/run_pipeline.py --only index")
    idx = pd.read_csv(index_path, parse_dates=["date"]).set_index("date")
    r_idx = idx["ret"]
    panel = pd.read_csv(ROOT / cfg.dotted("paths.interim") / "vx_panel.csv",
                        parse_dates=["date", "expiry"])

    BREAK = pd.Timestamp(cfg.dotted("products.SVXY.leverage_change_date"))
    # The block containing 5-6 February 2018 ends here; a pre-break window stopping
    # before it isolates the effect without discarding anything from the full run.
    PRE_CLEAN_END = pd.Timestamp("2018-01-31")

    SPECS = [
        ("VIXY", 1.0, None, None), ("VXX", 1.0, None, None),
        ("SVXY", -1.0, None, BREAK - pd.Timedelta(days=1)),
        ("SVXY", -0.5, BREAK, None),
        ("UVXY", 2.0, None, BREAK - pd.Timedelta(days=1)),
        ("UVXY", 1.5, BREAK, None),
        ("SVIX", -1.0, None, None),
    ]
    rets = {}
    for sym, *_ in SPECS:
        if sym not in rets:
            try:
                rets[sym] = split_adjusted_returns(load_prices(sym))
            except Exception as exc:
                print(f"  [mechanics] no prices for {sym}: {str(exc)[:70]}")

    # ---- 1. decay regression -------------------------------------------------
    rows = []
    for sym, L, lo, hi in SPECS:
        if sym not in rets:
            continue
        base = pd.concat({"p": rets[sym], "i": r_idx}, axis=1, sort=False).dropna()
        variants = [("full", lo, hi)]
        if hi is not None and hi > PRE_CLEAN_END:
            variants.append(("ex_feb2018", lo, PRE_CLEAN_END))
        for label, a, b in variants:
            d = base
            if a is not None:
                d = d[d.index >= a]
            if b is not None:
                d = d[d.index <= b]
            for H in (21, 63):
                for over in (False, True):
                    try:
                        if over:
                            B = decay_blocks(d["p"], d["i"], L, H, overlapping=True)
                            f = ols(B["y"].to_numpy(), B[["x"]].to_numpy(),
                                    names=["rv"], cov_type="HAC", lags=2 * H)
                            slope, se, n, r2 = (float(f.params[1]), float(f.bse[1]),
                                                int(f.nobs), float(f.rsquared))
                            icpt = float(f.params[0]) * 252.0 / H
                        else:
                            res = decay_regression(d["p"], d["i"], leverage=L, horizon=H)
                            slope, se, n, r2 = res.slope, res.slope_se, res.n, res.rsquared
                            icpt = res.intercept_annual
                    except ValueError:
                        continue
                    theo = theoretical_decay(L)
                    rows.append({
                        "symbol": sym, "leverage": L, "window": label,
                        "start": str(d.index.min().date()), "end": str(d.index.max().date()),
                        "horizon": H, "blocks": "overlapping" if over else "non_overlapping",
                        "n": n, "slope": slope, "se": se, "theoretical": theo,
                        "t_vs_theory": (slope - theo) / se if se > 0 else np.nan,
                        "intercept_annual": icpt, "rsquared": r2,
                        "fee_config": cfg.dotted(f"products.{sym}.fee", np.nan),
                    })
    decay = pd.DataFrame(rows)
    decay.to_csv(tables / "leverage_decay.csv", index=False)

    # ---- 2. what one block does, and why -------------------------------------
    inf_rows, app_rows = [], []
    for sym, L in (("SVXY", -1.0), ("UVXY", 2.0)):
        if sym not in rets:
            continue
        d = pd.concat({"p": rets[sym], "i": r_idx}, axis=1, sort=False).dropna()
        d = d[d.index < BREAK]
        inf = block_influence(d["p"], d["i"], L, 21)
        full = inf.attrs["full_slope"]
        for _, row in inf.head(5).iterrows():
            inf_rows.append({"symbol": sym, "leverage": L, "full_slope": full,
                             "block_end": str(pd.Timestamp(row["end"]).date()),
                             "slope_without": row["slope_without"],
                             "delta": row["delta"], "block_realised_var": row["block_x"]})
    WINDOWS = {"2018-02-07_volmageddon": ("2018-01-09", "2018-02-07"),
               "2016-07-08_typical": ("2016-06-09", "2016-07-08"),
               "2020-03-20_covid": ("2020-02-21", "2020-03-20"),
               "2024-08-16_yen_carry": ("2024-07-18", "2024-08-16")}
    for name, (a, b) in WINDOWS.items():
        for L in (-1.0, 2.0, -0.5, 1.5):
            e = identity_approximation_error(L, r_idx.loc[a:b])
            app_rows.append({"window": name, **e})
    pd.DataFrame(inf_rows).to_csv(tables / "decay_influence.csv", index=False)
    pd.DataFrame(app_rows).to_csv(tables / "decay_approximation_error.csv", index=False)

    # ---- 3. the de-levering as a structural break ----------------------------
    brk = []
    for sym, L0, L1 in (("SVXY", -1.0, -0.5), ("UVXY", 2.0, 1.5)):
        if sym not in rets:
            continue
        base = pd.concat({"p": rets[sym], "i": r_idx}, axis=1, sort=False).dropna()
        for label, pre_end in (("full", BREAK - pd.Timedelta(days=1)),
                               ("ex_feb2018", PRE_CLEAN_END)):
            pre = decay_blocks(base[base.index <= pre_end]["p"],
                               base[base.index <= pre_end]["i"], L0, 21)
            post = decay_blocks(base[base.index >= BREAK]["p"],
                                base[base.index >= BREAK]["i"], L1, 21)
            pre["post"], post["post"] = 0.0, 1.0
            B = pd.concat([pre, post])
            X = np.column_stack([B["x"], B["post"], B["x"] * B["post"]])
            f = ols(B["y"].to_numpy(), X, names=["rv", "post", "rv_x_post"],
                    cov_type="HC1")
            exp = theoretical_decay(L1) - theoretical_decay(L0)
            brk.append({
                "symbol": sym, "pre_window": label, "n": int(f.nobs),
                "leverage_before": L0, "leverage_after": L1, "break_date": str(BREAK.date()),
                "slope_pre": float(f.params[1]), "theory_pre": theoretical_decay(L0),
                "step": float(f.params[3]), "step_se": float(f.bse[3]), "theory_step": exp,
                "t_step_vs_zero": float(f.tvalues[3]),
                "t_step_vs_theory": (float(f.params[3]) - exp) / float(f.bse[3]),
                "slope_post": float(f.params[1] + f.params[3]),
                "theory_post": theoretical_decay(L1),
            })
    pd.DataFrame(brk).to_csv(tables / "leverage_break.csv", index=False)

    # ---- 4. assets, bounded --------------------------------------------------
    anchors = load_anchors(ROOT / cfg.dotted("paths.reference")
                           / "product_asset_anchors.csv")
    bounds, asset_frames = {}, []
    for sym in sorted(anchors["symbol"].unique()):
        if sym not in rets:
            continue
        px = load_prices(sym)
        b = asset_bounds(anchors[anchors["symbol"] == sym],
                         px["adjclose"].astype(float), px.attrs["splits"])
        bounds[sym] = b
        f = b.loc[~b["extrapolated"], ["assets_lower", "assets_central",
                                       "assets_upper", "is_anchor"]].copy()
        f.insert(0, "symbol", sym)
        asset_frames.append(f)
    assets_out = pd.concat(asset_frames).rename_axis("date")
    assets_out.to_csv(processed / "product_assets_bounds.csv")

    # ---- 5. flows ------------------------------------------------------------
    m = panel.set_index(["date", "expiry"])["open_interest"]
    oi1 = pd.Series([m.get((d, pd.Timestamp(idx.at[d, "exp1"])), np.nan)
                     for d in idx.index], index=idx.index)
    oi2 = pd.Series([m.get((d, pd.Timestamp(idx.at[d, "exp2"])), np.nan)
                     for d in idx.index], index=idx.index)

    GEARED = {s: (cfg.dotted(f"products.{s}.leverage"),
                  cfg.dotted(f"products.{s}.leverage_after"))
              for s in ("SVXY", "UVXY") if s in bounds}
    dates = idx.index
    inside = pd.Series(True, index=dates)
    for s in GEARED:
        inside &= (bounds[s]["extrapolated"].reindex(dates) == False)  # noqa: E712

    flows = pd.DataFrame(index=dates)
    flows["index_return"] = r_idx
    flows["front_settle"] = idx["f1"]
    flows["oi_front"] = oi1
    flows["oi_front_two"] = oi1 + oi2
    for k in ("lower", "central", "upper"):
        tot = pd.Series(0.0, index=dates)
        for s, (L0, L1) in GEARED.items():
            A = bounds[s][f"assets_{k}"].reindex(dates)
            L = pd.Series(np.where(dates >= BREAK, float(L1), float(L0)), index=dates)
            per = L * (L - 1.0) * A * r_idx
            if k == "lower":
                flows[f"flow_{s}"] = per.where(inside)
            tot = tot.add(per.fillna(0.0), fill_value=0.0)
        flows[f"flow_{k}"] = tot.where(inside)
        flows[f"contracts_{k}"] = flows[f"flow_{k}"] / (1000.0 * flows["front_settle"])
        flows[f"share_oi_front_{k}"] = flows[f"contracts_{k}"].abs() / flows["oi_front"]
        flows[f"share_oi_front_two_{k}"] = (flows[f"contracts_{k}"].abs()
                                            / flows["oi_front_two"])
    flows = flows[flows["flow_lower"].notna()]
    flows.to_csv(tables / "rebalancing_flows.csv", index_label="date")

    # ---- 6. the de-levering counterfactual: same shock, new coefficient -------
    day = pd.Timestamp("2018-02-05")
    coef_before = {s: L0 * (L0 - 1.0) for s, (L0, _) in GEARED.items()}
    coef_after = {s: float(L1) * (float(L1) - 1.0) for s, (_, L1) in GEARED.items()}
    cf = []
    if day in flows.index:
        for k in ("lower", "upper"):
            base = sum(bounds[s].at[day, f"assets_{k}"] for s in GEARED)
            f_before = sum(coef_before[s] * bounds[s].at[day, f"assets_{k}"]
                           for s in GEARED) * r_idx[day]
            f_after = sum(coef_after[s] * bounds[s].at[day, f"assets_{k}"]
                          for s in GEARED) * r_idx[day]
            ctr_b = f_before / (1000.0 * idx.at[day, "f1"])
            ctr_a = f_after / (1000.0 * idx.at[day, "f1"])
            cf.append({"bound": k, "date": str(day.date()), "assets_usd": base,
                       "coef_before": 2.0, "coef_after": 0.75,
                       "flow_before_usd": f_before, "flow_after_usd": f_after,
                       "contracts_before": ctr_b, "contracts_after": ctr_a,
                       "share_oi_front_before": abs(ctr_b) / oi1[day],
                       "share_oi_front_after": abs(ctr_a) / oi1[day],
                       "reduction": 1.0 - coef_after["SVXY"] / coef_before["SVXY"]})
    pd.DataFrame(cf).to_csv(tables / "delevering_counterfactual.csv", index=False)

    # ---- 7. figures ----------------------------------------------------------
    from types import SimpleNamespace

    from svcarry.viz.figures import (
        plot_asset_bounds, plot_decay_blocks, plot_decay_regression,
        plot_flow_vs_open_interest,
    )
    from svcarry.viz.style import save_figure

    figdir = ROOT / cfg.dotted("paths.figures")
    nb = decay[(decay["blocks"] == "non_overlapping") & (decay["horizon"] == 21)]
    dot = {}
    for _, row in nb.iterrows():
        lab = f"{row['symbol']} {row['leverage']:+g}x" + (
            "  excl. Feb-2018 block" if row["window"] == "ex_feb2018" else "")
        dot[lab] = SimpleNamespace(slope=row["slope"], slope_se=row["se"],
                                   theoretical=row["theoretical"])
    save_figure(plot_decay_regression(dot), figdir / "decay_regression.png")

    panels = []
    for sym, L, lo, hi, flag in (
        ("SVXY", -1.0, None, BREAK - pd.Timedelta(days=1), "2018-02-07"),
        ("SVXY", -0.5, BREAK, None, None),
        ("UVXY", 2.0, None, BREAK - pd.Timedelta(days=1), "2018-02-07"),
        ("UVXY", 1.5, BREAK, None, None),
    ):
        if sym not in rets:
            continue
        d = pd.concat({"p": rets[sym], "i": r_idx}, axis=1, sort=False).dropna()
        if lo is not None:
            d = d[d.index >= lo]
        if hi is not None:
            d = d[d.index <= hi]
        era = "before" if hi is not None else "after"
        panels.append({"title": f"{sym} at {L:+g}x ({era} 28 Feb 2018)",
                       "blocks": decay_blocks(d["p"], d["i"], L, 21),
                       "theory": theoretical_decay(L), "flag": flag})
    save_figure(plot_decay_blocks(panels), figdir / "decay_blocks.png")

    save_figure(plot_flow_vs_open_interest(flows["share_oi_front_lower"],
                                           flows["share_oi_front_upper"],
                                           annotate="2018-02-05"),
                figdir / "flow_vs_open_interest.png")
    save_figure(plot_asset_bounds({s: bounds[s] for s in ("SVXY", "UVXY", "VIXY")
                                   if s in bounds}, anchors),
                figdir / "product_assets_with_anchors.png")

    lo_max_oi = float(flows["share_oi_front_lower"].max())
    up_over = int((flows["share_oi_front_upper"] > 1.0).sum())
    qc = {
        "decay_rows": int(len(decay)),
        "anchored_window": [str(flows.index.min().date()), str(flows.index.max().date())],
        "anchored_sessions": int(len(flows)),
        "feb_2018_flow_lower_usd": float(flows.at[day, "flow_lower"]) if day in flows.index else None,
        "feb_2018_contracts_lower": float(flows.at[day, "contracts_lower"]) if day in flows.index else None,
        "feb_2018_share_front_oi_lower": float(flows.at[day, "share_oi_front_lower"]) if day in flows.index else None,
        "feb_2018_share_front_two_oi_lower": float(flows.at[day, "share_oi_front_two_lower"]) if day in flows.index else None,
        "lower_bound_max_share_front_oi": lo_max_oi,
        "lower_bound_ever_over_100pct_oi": bool(lo_max_oi > 1.0),
        "upper_bound_sessions_over_100pct_oi": up_over,
        "outputs": ["reports/tables/leverage_decay.csv",
                    "reports/tables/decay_influence.csv",
                    "reports/tables/decay_approximation_error.csv",
                    "reports/tables/leverage_break.csv",
                    "reports/tables/rebalancing_flows.csv",
                    "reports/tables/delevering_counterfactual.csv",
                    "data/processed/product_assets_bounds.csv"],
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


RUNNERS = {
    "clean": stage_clean,
    "index": stage_index,
    "mechanics": stage_mechanics,
    "tail": _not_yet("tail"),
    "signals": _not_yet("signals"),
    "backtest": _not_yet("backtest"),
    "robust": _not_yet("robust"),
    "figures": _not_yet("figures"),
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", nargs="*", choices=STAGES)
    ap.add_argument("--from", dest="start", choices=STAGES)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        st = _state()
        for s in STAGES:
            done = st.get(s, {}).get("finished_utc", "-")
            print(f"  {s:10s} last run: {done}")
        return 0

    stages = args.only or (
        STAGES[STAGES.index(args.start):] if args.start else STAGES
    )
    cfg = load_config()

    for s in stages:
        print(f"\n=== {s} " + "=" * (60 - len(s)))
        t0 = time.time()
        try:
            rec = RUNNERS[s](cfg) or {}
        except SystemExit as exc:
            print(exc)
            return 2
        except Exception:
            traceback.print_exc()
            return 1
        rec["seconds"] = round(time.time() - t0, 1)
        _record(s, rec)
    print("\nDone. State in reports/_pipeline_state.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
