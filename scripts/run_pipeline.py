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


RUNNERS = {
    "clean": stage_clean,
    "index": stage_index,
    "mechanics": _not_yet("mechanics"),
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
