#!/usr/bin/env python3
"""Check every headline number in docs/results.md against the committed tables.

Phase 13's rule is that a number in the prose must be pointable to a table. This
script is that rule, executable: it reads the tables and asserts the figures the
results document quotes. It is deliberately dumb - the expected values are written
out here, so a pipeline change that moves a number fails this check instead of
silently disagreeing with the write-up.

    python scripts/check_results_numbers.py        # exits 1 on any mismatch
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

    if fails:
        print(f"{len(fails)} number(s) in docs/results.md do not match the tables:")
        for line in fails:
            print("  " + line)
        return 1
    print("docs/results.md: every checked number matches its committed table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
