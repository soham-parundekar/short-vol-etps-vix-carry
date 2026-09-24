#!/usr/bin/env python3
"""Check every headline number in the write-ups against the committed tables.

Phase 13's rule is that a number in the prose must be pointable to a table. This
script is that rule, executable: it reads the tables and asserts the figures
quoted in `docs/results.md`, `reports/report.md`, `reports/summary_one_page.md`
and `README.md`. It is deliberately dumb - the expected values are written out
here, so a pipeline change that moves a number fails this check instead of
silently disagreeing with the write-up.

    python scripts/check_results_numbers.py        # exits 1 on any mismatch

Numbers quoted in the prose but not held in a table (derivations, filing
quotations, commit hashes and timestamps) are traced in `docs/validation.md` at
the section named beside them, and are out of this script's scope by design: it
checks the table-to-prose link, not the data-to-table one, which is what the
pipeline's own validation stages do.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "reports" / "tables"

fails: list[str] = []


def chk(label: str, got: float, want: float, tol: float = 0.015) -> None:
    got = float(got)
    if abs(got - want) > tol * max(abs(want), 1e-9):
        fails.append(f"{label}: table says {got:.4g}, results.md says {want:.4g}")


def main() -> int:
    e = pd.read_csv(T / "index_tracking_eras.csv")
    v = e[e["symbol"] == "VIXY"].set_index("era")
    chk("H1 tracking error 2011-2015", v.loc["2011-01-01 to 2015-12-31", "te_bp_daily_raw"], 133.2)
    chk("H1 tracking error after 2020-10-26", v.loc["2020-10-26 to end", "te_bp_daily_raw"], 31.7)
    chk("H1 slope after 2020-10-26", v.loc["2020-10-26 to end", "slope"], 0.985)

    d = pd.read_csv(T / "leverage_decay.csv")
    d = d[(d["horizon"] == 21) & (d["blocks"] == "non_overlapping")]
    g = d[(d["symbol"] == "SVXY") & (d["leverage"] == -1.0)]
    chk("decay SVXY -1x full", g[g["window"] == "full"]["slope"].iloc[0], -2.846)
    chk("decay SVXY -1x ex-Feb2018", g[g["window"] != "full"]["slope"].iloc[0], -1.087)
    u = d[(d["symbol"] == "UVXY") & (d["leverage"] == 2.0)]
    chk("decay UVXY +2x full", u[u["window"] == "full"]["slope"].iloc[0], -0.732)
    chk("decay UVXY +2x ex-Feb2018", u[u["window"] != "full"]["slope"].iloc[0], -0.946)

    f = pd.read_csv(T / "rebalancing_flows.csv", parse_dates=["date"]).set_index("date")
    chk("H2 contracts 2018-02-05", f.loc["2018-02-05", "contracts_lower"], 55690, 1e-3)
    chk("H2 share of front-month OI", f.loc["2018-02-05", "share_oi_front_lower"], 0.250)
    dl = pd.read_csv(T / "delevering_counterfactual.csv")
    dl = dl[dl["bound"] == "lower"].iloc[0]
    chk("de-levering contracts", dl["contracts_after"], 20884, 1e-3)
    chk("de-levering share", dl["share_oi_front_after"], 0.094)

    # H2's strength claim, which the final audit (F-A2) found wrong in five documents:
    # "4 of 10 days" was really 3, because 2017-08-10 sits at 9.97% and printed as
    # "10.0%". It lived only in prose, which is why it survived four phases. It is a
    # table-derived number now, so it cannot drift again without failing here.
    win = f.loc["2016-01-01":"2018-12-31"]
    top = win["index_return"].nlargest(10)
    over_lower = int((win.loc[top.index, "share_oi_front_lower"] > 0.10).sum())
    both_below = int(((win.loc[top.index, "share_oi_front_lower"] <= 0.10)
                      & (win.loc[top.index, "share_oi_front_upper"] <= 0.10)).sum())
    chk("H2 days over 10% at the lower bound", over_lower, 3, 0.0)
    chk("H2 days below 10% at BOTH bounds (would reject)", both_below, 0, 0.0)
    chk("H2 marginal day 2016-01-07", f.loc["2016-01-07", "share_oi_front_lower"], 0.1018)
    chk("H2 marginal day 2016-06-13", f.loc["2016-06-13", "share_oi_front_lower"], 0.1023)
    chk("H2 the day that does NOT clear 10%",
        f.loc["2017-08-10", "share_oi_front_lower"], 0.0997)

    t = pd.read_csv(T / "termination_probabilities.csv")
    t = t[(t["fit"] == "pre2018") & (t["headline_threshold"])].set_index(["state", "design"])
    chk("H3 unconditional -1x return period", t.loc[("unconditional", "-1x"), "return_period_years"], 78.9)
    chk("H3 calm -1x return period", t.loc[("calm (lowest 20% of sigma)", "-1x"), "return_period_years"], 2835)
    chk("H3 5 Feb 2018 return period",
        t.loc[("for 2018-02-05, data through 2018-02-02", "-1x"), "return_period_years"], 12.8)
    chk("H3 probability ratio -1x / -0.5x",
        t.loc[("unconditional", "-1x"), "p_daily"] / t.loc[("unconditional", "-0.5x"), "p_daily"], 8.7)

    sv = pd.read_csv(T / "survival_curves.csv")
    last = sv.groupby("dynamics").tail(1).set_index("dynamics")
    cap = [i for i in last.index if i != "unbounded"][0]
    chk("survival -1x unbounded", last.loc["unbounded", "survival_-1x"], 0.811)
    chk("survival -0.5x unbounded", last.loc["unbounded", "survival_-0.5x"], 0.937)
    chk("survival -1x capped", last.loc[cap, "survival_-1x"], 0.899)
    chk("survival -0.5x capped", last.loc[cap, "survival_-0.5x"], 0.986)

    k = pd.read_csv(T / "kelly.csv").set_index("returns")
    chk("H4 Kelly full sample", k.loc["full sample", "f_star"], 0.623)
    chk("H4 Kelly pre-2018", k.loc["pre-2018", "f_star"], 1.114)

    h = pd.read_csv(T / "har_oos_diagnostics.csv")
    h = h[h["period"] == "full"].set_index("model")
    chk("HAR out-of-sample R2", h.loc["HAR log (primary)", "oos_r2_vs_eval_mean"], 0.285)
    chk("HAR Mincer-Zarnowitz slope", h.loc["HAR log (primary)", "mz_beta"], 0.91)
    chk("trailing RV R2", h.loc["trailing 21-day RV", "oos_r2_vs_eval_mean"], 0.060, 0.03)
    chk("trailing RV slope", h.loc["trailing 21-day RV", "mz_beta"], 0.53)

    si = pd.read_csv(T / "signal_statistics.csv").set_index("statistic")["fraction"]
    chk("VRP on", si["VRP on"], 0.874)
    chk("contango on", si["contango (cm30/cm90) on"], 0.831)

    po = pd.read_csv(T / "performance_oos.csv", index_col=0)
    chk("H5 out-of-sample Sharpe", po.loc["strategy", "sharpe"], 0.27, 0.03)
    chk("H5 Sharpe standard error", po.loc["strategy", "sharpe_se_lo"], 0.31, 0.03)
    chk("strategy CAGR", po.loc["strategy", "cagr"], 0.050)
    chk("strategy max drawdown", po.loc["strategy", "max_drawdown"], -0.263)
    chk("strategy worst day", po.loc["strategy", "worst_day"], -0.117)
    chk("strategy worst week", po.loc["strategy", "worst_week"], -0.135)
    chk("PutWrite Sharpe", po.loc["Cboe PutWrite (PUT)", "sharpe"], 0.525)
    chk("S&P 500 Sharpe", po.loc["S&P 500 (SPY, total return)", "sharpe"], 0.745)
    cw = [i for i in po.index if i.startswith("constant")][0]
    chk("constant-weight Sharpe", po.loc[cw, "sharpe"], 0.398)
    chk("constant-weight worst day", po.loc[cw, "worst_day"], -0.166)

    bv = pd.read_csv(T / "backtest_variants.csv")
    bv = bv[bv["window"] == "oos"].set_index("name")
    chk("volatility targeting alone, Sharpe", bv.loc["no crash budget (vol target only)", "sharpe"], 0.056, 0.05)
    chk("volatility targeting alone, drawdown",
        bv.loc["no crash budget (vol target only)", "max_drawdown"], -0.432)
    chk("no signals, worst day", bv.loc["no signals (always on)", "worst_day"], -0.242)

    ar = pd.read_csv(T / "alpha_regression.csv").set_index("window")
    chk("H5 alpha", ar.loc["oos", "alpha_annual"], -0.014, 0.05)
    chk("H5 alpha t", ar.loc["oos", "alpha_t"], -0.52, 0.03)

    sp = pd.read_csv(T / "specification_distribution.csv")
    chk("grid median", sp["sharpe"].median(), 0.06, 0.06)
    chk("grid maximum", sp["sharpe"].max(), 0.53, 0.02)
    chk("grid minimum", sp["sharpe"].min(), -0.35, 0.02)
    chk("chosen percentile", (sp["sharpe"] < po.loc["strategy", "sharpe"]).mean(), 0.78, 0.02)
    chk("share of cells positive", (sp["sharpe"] > 0).mean(), 0.646)

    rp = pd.read_csv(T / "robustness_parameters.csv")
    pick = lambda p_, v_, c: float(rp[(rp["parameter"] == p_) & (rp["value"] == v_)][c].iloc[0])  # noqa: E731
    chk("threshold 1.025, Feb 2018", pick("contango_threshold", "1.025", "feb_2018"), -0.243)
    chk("weekly rebalance, Feb 2018", pick("rebalance", "5", "feb_2018"), -0.317)
    chk("weekly rebalance, worst day", pick("rebalance", "5", "worst_day"), -0.380)

    rc = pd.read_csv(T / "robustness_costs.csv").set_index("cost_ticks")["sharpe"]
    below = rc[rc <= 0]
    hi = below.index[0]
    lo = rc.index[rc.index.get_loc(hi) - 1]
    chk("cost breakeven (ticks)", lo + (hi - lo) * rc[lo] / (rc[lo] - rc[hi]), 2.05, 0.02)

    # ---- numbers first quoted in reports/report.md and reports/summary_one_page.md ----

    # Section 2: the filings. Every product term the report tabulates was matched.
    ft = pd.read_csv(T / "filing_terms.csv")
    if not bool(ft["found"].all()):
        missing = ft.loc[~ft["found"].astype(bool), "claim"].tolist()
        fails.append(f"report section 2: filing terms not found in the documents: {missing}")
    if not (ft["agrees"] != "no").all():
        fails.append("report section 2: a filing term disagrees with config")
    chk("report: number of verified filing terms", len(ft), 28, 0.0)

    # Section 3: sample span, from the index itself rather than a table.
    idx = pd.read_csv(ROOT / "data" / "processed" / "index_daily.csv", parse_dates=["date"])
    chk("report: index sessions", len(idx), 4711, 0.0)
    for label, got, want in [("first", str(idx["date"].min().date()), "2008-01-02"),
                             ("last", str(idx["date"].max().date()), "2026-09-18")]:
        if got != want:
            fails.append(f"report: sample {label} session is {got}, the write-ups say {want}")

    # Section 4.1: the roll convention was chosen on evidence, not asserted.
    rv = pd.read_csv(T / "roll_convention.csv")
    rv = rv[(rv["convention"] == "sp_dji") & (rv["symbol"] == "VIXY")].iloc[0]
    chk("report: roll-weight loading t-stat (VIXY)", rv["t_stat"], -0.61, 0.03)
    chk("report: roll-weight loading p-value (VIXY)", rv["p_value"], 0.54, 0.03)

    # Section 4.3 / 5.4: the ex-ante model, as the report states its parameters.
    gf = pd.read_csv(T / "garch_fit.csv").set_index("sample").loc["pre2018"]
    chk("report: GARCH persistence", gf["persistence"], 0.938)
    chk("report: GARCH nu", gf["nu"], 5.75)
    chk("report: GARCH lambda", gf["lambda"], 0.201)
    chk("report: GARCH alpha", gf["alpha"], 0.279)
    chk("report: GARCH gamma", gf["gamma"], -0.245)
    chk("report: GARCH beta", gf["beta"], 0.781)
    if not gf["max_param_diff_between_seeds"] < 1e-5:
        fails.append("report: the two GARCH seeds do not agree to 1e-5")

    ev = pd.read_csv(T / "evt_thresholds.csv")
    ev = ev[(ev["sample"] == "pre2018") & (ev["chosen"])].iloc[0]
    chk("report: EVT threshold quantile", ev["q"], 0.925, 1e-9)
    chk("report: EVT exceedances", ev["n_exceed"], 189, 0.0)
    chk("report: EVT shape xi", ev["xi"], 0.181)

    # Section 5.4: the warning path the report walks date by date.
    wp = pd.read_csv(T / "exante_warning_path.csv", parse_dates=["date"]).set_index("date")
    for d, want in [("2018-01-12", 3877.0), ("2018-01-29", 1941.0),
                    ("2018-02-02", 294.0), ("2018-02-05", 12.8)]:
        chk(f"report: ex-ante return period {d}", wp.loc[d, "return_period_years_-1x"], want)
    chk("report: 5 Feb morning, one in N trading days",
        1.0 / wp.loc["2018-02-05", "p_daily_-1x"], 3200, 0.02)
    chk("report: settlement-based index return 5 Feb 2018",
        wp.loc["2018-02-05", "index_return"], 0.961)

    # Section 5.4 / 8: the design gap across the whole threshold grid.
    sbt = pd.read_csv(T / "survival_by_threshold.csv")
    ratio = (pd.read_csv(T / "termination_probabilities.csv")
             .query("fit == 'pre2018' and state == 'unconditional'")
             .pivot(index="q", columns="design", values="p_daily"))
    ratio = ratio["-1x"] / ratio["-0.5x"]
    chk("report: probability ratio, grid minimum", ratio.min(), 5.3, 0.02)
    chk("report: probability ratio, grid maximum", ratio.max(), 9.4, 0.02)
    chk("report: survival gap, capped, grid maximum",
        sbt[sbt["dynamics"] == "capped"]["gap_pp"].max(), 9.43, 0.01)

    # Section 5.6: the HAR's out-of-sample correlation claim ("0.54 against 0.53").
    hf = pd.read_csv(T / "har_oos_diagnostics.csv")
    hf = hf[hf["period"] == "full"].set_index("model")
    chk("report: HAR level-spec R2", hf.loc["HAR level", "oos_r2_vs_eval_mean"], 0.053, 0.05)

    # Section 5.7 and the summary: the benchmark table the comparison rests on.
    chk("report: strategy annualised volatility", po.loc["strategy", "ann_vol"], 0.126)
    chk("report: strategy time invested", po.loc["strategy", "time_invested"], 0.726)
    chk("report: out-of-sample sessions", po.loc["strategy", "n"], 2695, 0.0)
    chk("report: buy-and-hold -1x drawdown",
        po.loc["buy-and-hold -1x (XIV fee)", "max_drawdown"], -0.992, 0.01)

    # Section 6: the red-team answers the report quotes.
    rt = pd.read_csv(T / "redteam_answers.csv").set_index("question")
    leak = [q for q in rt.index if q.startswith("2.")][0]
    if "1.12" not in str(rt.loc[leak, "number"]):
        fails.append("report section 6: the leak-calibration Sharpe is no longer 1.12")
    conc = [q for q in rt.index if q.startswith("6.")][0]
    for token in ("11.7%", "17.0%"):
        if token not in str(rt.loc[conc, "number"]):
            fails.append(f"report section 6: concentration answer no longer quotes {token}")
    per = [q for q in rt.index if q.startswith("5.")][0]
    for token in ("68.7%", "-8.9%", "-4.8%", "-3.2%", "25.5%"):
        if token not in str(rt.loc[per, "number"]):
            fails.append(f"report section 6: period answer no longer quotes {token}")

    if fails:
        print(f"{len(fails)} number(s) in the write-ups do not match the tables:")
        for line in fails:
            print("  " + line)
        return 1
    print("results.md, report.md, summary_one_page.md, README.md: every checked number matches its committed table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
