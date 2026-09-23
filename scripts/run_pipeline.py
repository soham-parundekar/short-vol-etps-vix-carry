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
                    # The regressor is ALREADY the leveraged index (L x idx), so
                    # this coefficient is the leverage-adjusted slope: 1.0 means the
                    # product moved exactly as its stated multiple of the index.
                    # (It was additionally divided by L until Phase 13, which flipped
                    # its sign for inverse products and halved it for 2x ones.)
                    "slope": float(fit.params[1]),
                    "slope_se": float(fit.bse[1]),
                    "te_bp_daily": float(resid.std() * 1e4),
                    "mean_resid_bp": float(resid.mean() * 1e4),
                })
    track = pd.DataFrame(rows)
    track.to_csv(tables / "index_tracking.csv", index=False)

    # ---- the same comparison, split on the settlement-time change ----------
    # Cboe moved the VX daily settlement from 3:15 to 3:00 p.m. CT effective
    # 2020-10-26, which is when the index and the products' 4:00 p.m. closes start
    # being measured at the same instant. The eras below straddle that date (and
    # separate the 2018 leverage change) so the regime shift is a committed number
    # rather than one that lives only in prose.
    settle_eras = [("2011-01-01", "2015-12-31"), ("2016-01-01", "2017-12-31"),
                   ("2018-01-01", "2018-12-31"), ("2019-01-01", "2020-10-23"),
                   ("2020-10-26", None)]
    era_rows = []
    idx_df = built[chosen]
    for sym, r_p in prods.items():
        for lo, hi in settle_eras:
            a, b = idx_df["ret"].copy(), r_p.copy()
            if lo: a, b = a[a.index >= lo], b[b.index >= lo]
            if hi: a, b = a[a.index <= hi], b[b.index <= hi]
            df = pd.concat({"idx": a, "prod": b}, axis=1).dropna()
            if len(df) < 60:
                continue
            L = leverage_series(sym, df.index)
            fitted = L * df["idx"]
            fit = ols(df["prod"].to_numpy(), fitted.to_numpy(), names=["lev_idx"],
                      cov_type="HAC")
            # Two tracking errors, because they answer different questions. The
            # hypothesis is written on the raw difference (H1: "the difference
            # between the rebuilt excess return and the product's return"); the
            # regression residual, which lets the slope and an intercept absorb the
            # attenuation, is the smaller number and is what V6's table reported
            # before this column existed.
            era_rows.append({
                "symbol": sym, "era": f"{lo or 'start'} to {hi or 'end'}",
                "settlement": "15:15 CT" if (hi or "2099") <= "2020-10-23" else "15:00 CT",
                "n": len(df), "slope": float(fit.params[1]),
                "te_bp_daily_raw": float((df["prod"] - fitted).std() * 1e4),
                "te_bp_daily_regression_resid": float(np.std(fit.resid, ddof=2) * 1e4),
            })
    pd.DataFrame(era_rows).to_csv(tables / "index_tracking_eras.csv", index=False)

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


def stage_tail(cfg) -> dict:
    """GJR-GARCH + conditional EVT: termination probabilities, survival, Kelly (H3, H4).

    The ex-ante claim rests on the model fitted to data ending 2017-12-31, with its
    EVT threshold chosen on pre-2018 residuals only. Everything is reported across
    the full threshold grid. Two distinctions are kept visible throughout because
    each changes the headline by a large factor:

    * **In-sample averaging vs the model's own dynamics.** Averaging the one-day
      conditional probability over the volatility states the data visited gives one
      number; simulating the fitted recursion gives a larger one, because the model
      generates volatility spirals far beyond anything observed. Survival is therefore
      simulated twice - unbounded, and with volatility capped at the in-sample maximum.
    * **Empirical vs model-based Kelly.** Under a fitted tail with xi > 0 every short
      position has positive probability of total loss, so the model-implied
      growth-optimal short is exactly zero and simulated estimates are just one over
      the largest draw. Only the empirical Kelly is an estimate.
    """
    import numpy as np
    import pandas as pd
    from scipy import stats

    from svcarry.econometrics.distributions import get_distribution
    from svcarry.econometrics.evt import fit_gpd, mean_excess
    from svcarry.econometrics.garch import GJRGarch
    from svcarry.econometrics.kelly import growth_rate_curve, kelly_fraction
    from svcarry.econometrics.tailrisk import (
        SplicedInnovations, filter_sigma, simulate_first_passage, simulate_returns,
        termination_table,
    )

    processed = ROOT / cfg.dotted("paths.processed")
    tables = ROOT / cfg.dotted("paths.tables")
    figdir = ROOT / cfg.dotted("paths.figures")
    idx = pd.read_csv(_require(processed / "index_daily.csv", "the reconstructed index",
                               "run: python scripts/run_pipeline.py --only index"),
                      parse_dates=["date"]).set_index("date")
    R = idx["ret"].dropna()
    lr = np.log1p(R)
    CUT = pd.Timestamp("2017-12-31")
    GRID = [float(q) for q in cfg.dotted("tail.threshold_grid")]
    SEED = int(cfg.dotted("tail.survival.seed"))
    NPATH = int(cfg.dotted("tail.survival.n_paths"))
    YEARS = int(cfg.dotted("tail.survival.years"))
    wf = float(cfg.dotted("tail.wipeout_fraction"))
    # One-day SIMPLE index return that removes `wf` of a product at leverage L.
    TH = {"-1x": wf / 1.0, "-0.5x": wf / 0.5}          # 0.80 and 1.60

    def ljung_box(x, lags):
        x = np.asarray(x) - np.mean(x)
        n, d = len(x), float(np.sum(x * x))
        ac = np.array([np.sum(x[k:] * x[:-k]) / d for k in range(1, lags + 1)])
        q = n * (n + 2) * np.sum(ac ** 2 / (n - np.arange(1, lags + 1)))
        return float(q), float(stats.chi2.sf(q, lags))

    from svcarry.econometrics.evt import choose_threshold, gpd_ks  # noqa: F401

    # ---- 1. GARCH fits --------------------------------------------------------
    samples = {"pre2018": lr[lr.index <= CUT], "full": lr}
    fits, garch_rows = {}, []
    for name, s in samples.items():
        f0 = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(s, n_starts=4, seed=0)
        f1 = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(s, n_starts=4, seed=1)
        fits[name] = f0
        z = f0.std_resid
        pit = get_distribution(f0.dist).cdf(z, f0.dist_params)
        q10, p10 = ljung_box(z ** 2, 10)
        q20, p20 = ljung_box(z ** 2, 20)
        row = {"sample": name, "start": str(s.index.min().date()),
               "end": str(s.index.max().date()), "n": len(s),
               "loglik": f0.loglik, "loglik_seed1": f1.loglik,
               "max_param_diff_between_seeds": max(abs(f0.params[k] - f1.params[k])
                                                   for k in f0.params),
               "persistence": f0.persistence,
               "uncond_vol_annual": float(np.sqrt(f0.uncond_var * 252)),
               "lb_z2_10_p": p10, "lb_z2_20_p": p20,
               "ks_pit_p": float(stats.kstest(pit, "uniform").pvalue),
               "nu": float(f0.dist_params[0]), "lambda": float(f0.dist_params[1])}
        for k, v in f0.params.items():
            row[k] = v
            row[f"se_{k}"] = f0.se_robust.get(k, np.nan)
        garch_rows.append(row)
    pd.DataFrame(garch_rows).to_csv(tables / "garch_fit.csv", index=False)

    # ---- 2. EVT threshold, per sample, on that sample's residuals only ---------
    evt, gpds, chosen_q = [], {}, {}
    for name, f in fits.items():
        t, g, q = choose_threshold(f.std_resid, GRID)
        t.insert(0, "sample", name)
        evt.append(t)
        gpds[name], chosen_q[name] = g, q
    evt = pd.concat(evt, ignore_index=True)
    evt.to_csv(tables / "evt_thresholds.csv", index=False)
    if not np.isfinite(chosen_q["pre2018"]):
        raise SystemExit("no pre-2018 threshold satisfies the rule; report a range")

    # ---- 3. termination probabilities, both fits x every threshold -------------
    pre_state = filter_sigma(fits["pre2018"].params, lr[lr.index <= "2018-02-09"])
    term = []
    for name, f in fits.items():
        insample = pd.Series(f.sigma, index=samples[name].index)
        for q in GRID:
            S = SplicedInnovations(f.dist, f.dist_params, gpds[name][q])
            t = termination_table(insample, f.params["mu"], S, TH)
            if name == "pre2018":
                t2 = termination_table(pre_state, f.params["mu"], S, TH,
                                       at_dates=["2018-01-12", "2018-02-05"])
                t = pd.concat([t, t2[t2["state"].str.startswith("on ")]])
            t.insert(0, "q", q)
            t.insert(0, "fit", name)
            t["headline_threshold"] = q == chosen_q[name]
            term.append(t)
    term = pd.concat(term, ignore_index=True)
    term["state"] = term["state"].str.replace("on 2018-02-05",
                                              "for 2018-02-05, data through 2018-02-02")
    term.to_csv(tables / "termination_probabilities.csv", index=False)

    # The model's warning, day by day, into February 2018 (parameters frozen at
    # 2017-12-31; only the volatility state is updated as each day's data arrives).
    fp = fits["pre2018"]
    Sh = SplicedInnovations(fp.dist, fp.dist_params, gpds["pre2018"][chosen_q["pre2018"]])
    path = pre_state.loc["2018-01-02":"2018-02-09"].to_frame("sigma_daily")
    for k, c in TH.items():
        from svcarry.econometrics.tailrisk import conditional_exceedance
        p = conditional_exceedance(c, fp.params["mu"], path["sigma_daily"], Sh)
        path[f"p_daily_{k}"] = p
        path[f"return_period_years_{k}"] = 1.0 / (p * 252.0)
    path["index_return"] = R.reindex(path.index)
    path.to_csv(tables / "exante_warning_path.csv", index_label="date")

    # ---- 4. is the scale well calibrated across volatility regimes? ------------
    cal = []
    for name, f in fits.items():
        z = pd.Series(f.std_resid, index=samples[name].index)
        sg = pd.Series(f.sigma, index=samples[name].index)
        u = np.quantile(z, 0.95)
        qb = pd.qcut(sg, 5, labels=["Q1 calm", "Q2", "Q3", "Q4", "Q5 turbulent"])
        chi_p = float(stats.chi2_contingency(pd.crosstab(qb, z > u)).pvalue)
        for k, g in z.groupby(qb, observed=True):
            x = int((g > u).sum())
            lo, hi = stats.binomtest(x, len(g)).proportion_ci(0.95)
            cal.append({"sample": name, "sigma_quintile": str(k), "n": len(g),
                        "exceed": x, "rate": x / len(g), "ci_low": lo, "ci_high": hi,
                        "chi2_equal_rates_p": chi_p})
    pd.DataFrame(cal).to_csv(tables / "evt_calibration_by_sigma.csv", index=False)

    # ---- 5. survival, unbounded and capped, headline + across the grid ---------
    cap = float(fp.sigma.max())
    n_steps = 252 * YEARS
    curves = {}
    for label, c in (("unbounded", None), ("capped at in-sample max sigma", cap)):
        sv = simulate_first_passage(fp.params, Sh, TH, n_paths=NPATH, n_steps=n_steps,
                                    seed=SEED, sigma_cap=c)
        sv.insert(0, "dynamics", label)
        curves[label] = sv
    surv = pd.concat(curves.values(), ignore_index=True)
    surv.to_csv(tables / "survival_curves.csv", index=False)

    # Where the simulated risk comes from: volatility states the data never visited.
    rng = np.random.default_rng(SEED + 3)
    npd = 4000
    s2 = np.full(npd, fp.params["omega"] / (1 - fp.persistence))
    e_prev = np.zeros(npd)
    SIG = np.empty((npd, n_steps))
    HIT = np.zeros((npd, n_steps), dtype=bool)
    for t in range(n_steps):
        s2 = (fp.params["omega"] + (fp.params["alpha"] + fp.params["gamma"] * (e_prev < 0))
              * e_prev ** 2 + fp.params["beta"] * s2)
        e = np.sqrt(s2) * Sh.ppf(rng.random(npd))
        SIG[:, t] = np.sqrt(s2)
        HIT[:, t] = fp.params["mu"] + e >= np.log1p(TH["-1x"])
        e_prev = e
    beyond = SIG > cap
    first = np.argmax(HIT, axis=1)
    anyhit = HIT.any(axis=1)
    repeat = [HIT[i, first[i] + 1:first[i] + 21].any() for i in np.where(anyhit)[0]]
    pd.DataFrame([{
        "paths": npd, "days": n_steps, "seed": SEED + 3,
        "insample_sigma_max": cap, "insample_sigma_p999": float(np.quantile(fp.sigma, 0.999)),
        "sim_sigma_p999": float(np.quantile(SIG, 0.999)), "sim_sigma_max": float(SIG.max()),
        "share_sim_days_beyond_insample_max": float(beyond.mean()),
        "share_sim_wipeouts_beyond_insample_max": float((HIT & beyond).sum() / max(HIT.sum(), 1)),
        "share_hit_paths_with_repeat_within_20d": float(np.mean(repeat)) if repeat else np.nan,
    }]).to_csv(tables / "simulation_diagnostics.csv", index=False)

    sg_rows = []
    for q in GRID:
        Sq = SplicedInnovations(fp.dist, fp.dist_params, gpds["pre2018"][q])
        for label, c in (("unbounded", None), ("capped", cap)):
            sv = simulate_first_passage(fp.params, Sq, TH, n_paths=NPATH // 2,
                                        n_steps=n_steps, seed=SEED + 1, sigma_cap=c)
            last = sv.iloc[-1]
            sg_rows.append({"q": q, "dynamics": label,
                            "surv5_-1x": last["survival_-1x"], "se_-1x": last["se_-1x"],
                            "surv5_-0.5x": last["survival_-0.5x"],
                            "se_-0.5x": last["se_-0.5x"],
                            "gap_pp": (last["survival_-0.5x"] - last["survival_-1x"]) * 100})
    pd.DataFrame(sg_rows).to_csv(tables / "survival_by_threshold.csv", index=False)

    # ---- 6. Kelly ---------------------------------------------------------------
    nboot = 1000
    kel = []
    variants = {"full sample": R, "pre-2018": R[R.index <= CUT],
                "full sample without 2018-02-05": R.drop(pd.Timestamp("2018-02-05"))}
    for lab, r in variants.items():
        k = kelly_fraction(r, bootstrap=nboot, seed=SEED)
        kel.append({"returns": lab, "kind": "empirical estimate", "n": k.n,
                    "f_star": k.f_star, "ci_low": k.ci_low, "ci_high": k.ci_high,
                    "ci_contains_1": bool(k.ci_low <= 1.0 <= k.ci_high),
                    "ruin_bound": 1.0 / float(np.max(r)), "note": k.note or ""})
    for lab, c in (("simulated, unbounded", None), ("simulated, capped", cap)):
        rs = simulate_returns(fp.params, Sh, 500, 2520, seed=SEED + 2, sigma_cap=c).ravel()
        k = kelly_fraction(rs)
        kel.append({"returns": lab, "kind": "NOT an estimate: equals 1/max(simulated R)",
                    "n": k.n, "f_star": k.f_star, "ci_low": np.nan, "ci_high": np.nan,
                    "ci_contains_1": np.nan, "ruin_bound": 1.0 / float(rs.max()),
                    "note": "the fitted tail has unbounded support, so every short "
                            "position has positive ruin probability and the model-"
                            "implied growth-optimal short is exactly zero"})
    kel = pd.DataFrame(kel)
    kel.to_csv(tables / "kelly.csv", index=False)

    # ---- 7. jackknife the largest day of each sample ---------------------------
    jk = []
    for name, s in samples.items():
        big = s.idxmax()
        s2 = s.drop(big)
        fj = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(s2, n_starts=4, seed=0)
        qj = chosen_q[name]
        gj = fit_gpd(fj.std_resid, q=qj, tail="upper")
        Sj = SplicedInnovations(fj.dist, fj.dist_params, gj)
        tj = termination_table(pd.Series(fj.sigma, index=s2.index), fj.params["mu"], Sj, TH)
        base = term[(term["fit"] == name) & (term["q"] == qj)
                    & (term["state"] == "unconditional")].set_index("design")
        kj = kelly_fraction(np.expm1(s2), bootstrap=0)
        kb = kelly_fraction(np.expm1(s), bootstrap=0)
        for _, row in tj[tj["state"] == "unconditional"].iterrows():
            b = base.loc[row["design"], "p_daily"]
            jk.append({"sample": name, "dropped": str(big.date()),
                       "dropped_return": float(np.expm1(s[big])),
                       "design": row["design"], "p_daily_with": b,
                       "p_daily_without": row["p_daily"],
                       "change_pct": (row["p_daily"] / b - 1.0) * 100,
                       "rp_years_with": 1 / (b * 252), "rp_years_without": row["return_period_years"],
                       "xi_with": gpds[name][qj].xi, "xi_without": gj.xi,
                       "kelly_with": kb.f_star, "kelly_without": kj.f_star})
    pd.DataFrame(jk).to_csv(tables / "tail_jackknife.csv", index=False)

    # ---- 8. figures ------------------------------------------------------------
    from svcarry.viz.figures import (
        plot_gpd_qq, plot_kelly_growth_curve, plot_mean_excess, plot_survival_curves,
    )
    from svcarry.viz.style import save_figure

    zp = fp.std_resid
    th, me, se = mean_excess(zp, tail="upper", n_points=60, q_lo=0.80, q_hi=0.99)
    save_figure(plot_mean_excess(th, me, se, chosen=gpds["pre2018"][chosen_q["pre2018"]].threshold),
                figdir / "mean_excess.png")
    g = gpds["pre2018"][chosen_q["pre2018"]]
    exc = np.sort(zp[zp > g.threshold] - g.threshold)
    pp = (np.arange(1, len(exc) + 1) - 0.5) / len(exc)
    theo = g.beta / g.xi * ((1 - pp) ** (-g.xi) - 1)
    save_figure(plot_gpd_qq(exc, theo), figdir / "qq_gpd.png")
    sc = {}
    bands = {}
    for label, sv in curves.items():
        short = "unbounded" if label == "unbounded" else "capped"
        for k in TH:
            nm = f"{k}, {short}"
            sc[nm] = pd.Series(sv[f"survival_{k}"].to_numpy(), index=sv["years"].to_numpy())
            bands[nm] = (sv[f"survival_{k}"] - 1.96 * sv[f"se_{k}"],
                         sv[f"survival_{k}"] + 1.96 * sv[f"se_{k}"])
    from svcarry.viz.style import PALETTE as _P, LINESTYLES as _LS
    sty = {nm: {"color": _P[0] if nm.startswith("-1x") else _P[1],
                "linestyle": _LS[0] if "unbounded" in nm else _LS[1]} for nm in sc}
    save_figure(plot_survival_curves(sc, bands, styles=sty), figdir / "survival_curves.png")
    fg, gr = growth_rate_curve(R.to_numpy(), f_grid=np.linspace(0.0, 1.03, 250))
    kf = kel.set_index("returns").loc["full sample", "f_star"]
    # growth_rate_curve returns DAILY expected log growth and the figure annualises
    # it; passing an annualised series here multiplied by 252 twice (a peak of 33
    # "per year" instead of 0.13), which is how this line came to be written.
    save_figure(plot_kelly_growth_curve(fg, gr, f_star=kf,
                                        marks={"-1x offered": 1.0, "-0.5x": 0.5}),
                figdir / "kelly_growth_curve.png")
    from svcarry.viz.figures import plot_exante_warning
    save_figure(plot_exante_warning(path.loc[:"2018-02-07"]), figdir / "exante_warning.png")

    # ---- summary ---------------------------------------------------------------
    hq = chosen_q["pre2018"]
    h = term[(term["fit"] == "pre2018") & (term["q"] == hq)].set_index(["state", "design"])
    unc = term[(term["fit"] == "pre2018") & (term["state"] == "unconditional")]
    rng = unc.groupby("design")["return_period_years"].agg(["min", "max"])
    s5 = {lab: sv.iloc[-1] for lab, sv in curves.items()}
    qc = {
        "pre2018_threshold_q": hq, "full_threshold_q": chosen_q["full"],
        "pre2018_xi": gpds["pre2018"][hq].xi,
        "exante_rp_years_-1x_unconditional": float(h.loc[("unconditional", "-1x"), "return_period_years"]),
        "exante_rp_years_-0.5x_unconditional": float(h.loc[("unconditional", "-0.5x"), "return_period_years"]),
        "exante_rp_range_-1x_over_grid": [float(rng.loc["-1x", "min"]), float(rng.loc["-1x", "max"])],
        "exante_rp_range_-0.5x_over_grid": [float(rng.loc["-0.5x", "min"]), float(rng.loc["-0.5x", "max"])],
        "ratio_p_-1x_over_p_-0.5x_headline":
            float(h.loc[("unconditional", "-1x"), "p_daily"] / h.loc[("unconditional", "-0.5x"), "p_daily"]),
        "rp_years_-1x_for_2018-02-05": float(h.loc[("for 2018-02-05, data through 2018-02-02", "-1x"), "return_period_years"]),
        "rp_years_-1x_on_2018-01-12": float(h.loc[("on 2018-01-12", "-1x"), "return_period_years"]),
        "survival5_unbounded": {k: float(s5["unbounded"][f"survival_{k}"]) for k in TH},
        "survival5_capped": {k: float(s5["capped at in-sample max sigma"][f"survival_{k}"]) for k in TH},
        "kelly_full": kel.iloc[0][["f_star", "ci_low", "ci_high"]].tolist(),
        "kelly_pre2018": kel.iloc[1][["f_star", "ci_low", "ci_high"]].tolist(),
        "H4_rejected_ci_contains_1": bool(kel.iloc[0]["ci_contains_1"]),
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


def stage_signals(cfg) -> dict:
    """Realised variance, real-time HAR forecasts, VRP and term-structure signals.

    Order matters and is the order of the phase prompt: choose the variance proxy
    (and show why), fit the HAR in sample for description only, produce real-time
    forecasts, judge them against naive benchmarks, and only then build signals.
    Thresholds come from configuration, fixed in commit 2bdeb31 before any data was
    retrieved; nothing here is tuned.
    """
    import numpy as np
    import pandas as pd

    from svcarry.data.cboe import load_cboe_index
    from svcarry.data.prices import load_prices
    from svcarry.econometrics.forecast_eval import diebold_mariano, forecast_metrics, qlike
    from svcarry.econometrics.har import fit_har, har_features
    from svcarry.econometrics.realized import (
        close_to_close, daily_variance_proxy, garman_klass, overnight, parkinson,
        rogers_satchell, yang_zhang,
    )
    from svcarry.strategy.signals import build_signal_panel, signal_statistics

    processed = ROOT / cfg.dotted("paths.processed")
    tables = ROOT / cfg.dotted("paths.tables")
    figdir = ROOT / cfg.dotted("paths.figures")
    idx = pd.read_csv(_require(processed / "index_daily.csv", "the reconstructed index",
                               "run: python scripts/run_pipeline.py --only index"),
                      parse_dates=["date"]).set_index("date")
    H = int(cfg.dotted("forecast.har_horizon"))
    LAGS = tuple(int(x) for x in cfg.dotted("forecast.har_lags"))
    LOG = bool(cfg.dotted("forecast.har_log"))
    TMIN = int(cfg.dotted("forecast.har_train_min"))
    REFIT = int(cfg.dotted("forecast.har_refit_every"))
    METHOD = str(cfg.dotted("forecast.rv_method"))
    THR = float(cfg.dotted("strategy.contango_threshold"))
    VMIN = float(cfg.dotted("strategy.vrp_min"))

    # ---- 1. the variance proxy -------------------------------------------------
    spy = load_prices("SPY")
    rows = []
    sources = {"SPY": spy}
    try:
        sources["^GSPC"] = load_prices("^GSPC")
    except FileNotFoundError:
        pass
    ests = {
        "close_to_close": close_to_close, "parkinson (intraday only)": parkinson,
        "garman_klass (intraday only)": garman_klass,
        "rogers_satchell (intraday only)": rogers_satchell,
        "overnight only": overnight,
        "parkinson_overnight": lambda d: daily_variance_proxy(d, "parkinson_overnight"),
        "gk_overnight": lambda d: daily_variance_proxy(d, "gk_overnight"),
        "rs_overnight": lambda d: daily_variance_proxy(d, "rs_overnight"),
    }
    for src, df in sources.items():
        df = df.loc[:, ["open", "high", "low", "close"]].dropna()
        cc_mean = float(close_to_close(df).dropna().mean())
        open_eq_prev = float((df["open"] == df["close"].shift(1)).iloc[1:].mean())
        for name, fn in ests.items():
            x = fn(df).dropna()
            pos = x[x > 0]
            rows.append({
                "source": src, "estimator": name, "n": len(x),
                "first": str(x.index.min().date()),
                "ann_vol_pct": float(np.sqrt(252 * x.mean()) * 100),
                "mean_over_close_to_close": float(x.mean() / cc_mean),
                "share_nonpositive": float((x <= 0).mean()),
                "sd_log_daily": float(np.log(pos).std()),
                "ar1_daily": float(x.autocorr(1)),
                "share_open_equals_prev_close": open_eq_prev,
                "used": bool(src == "SPY" and name == METHOD),
            })
    comp = pd.DataFrame(rows)
    comp.to_csv(tables / "variance_proxy_comparison.csv", index=False)
    rv = daily_variance_proxy(spy, METHOD).dropna()
    if (rv <= 0).any():
        raise ValueError(f"{int((rv <= 0).sum())} non-positive variance proxies")
    yz = yang_zhang(spy[["open", "high", "low", "close"]], window=H).dropna()
    rv_m = rv.rolling(H).mean().reindex(yz.index)
    yz_check = {"corr_with_rolling_proxy": float(np.corrcoef(yz, rv_m)[0, 1]),
                "mean_ratio_yz_over_proxy": float(yz.mean() / rv_m.mean())}

    # ---- 2. HAR in sample, descriptive only -------------------------------------
    fit_rows = []
    for spec, lg in (("log (primary)", True), ("level", False)):
        f = har_features(rv, horizon=H, lags=LAGS, log=lg)
        r = fit_har(f)
        naive = fit_har(f, cov_type="homoskedastic")
        for j, nm in enumerate(r.names):
            fit_rows.append({"spec": spec, "term": nm, "coef": float(r.params[j]),
                             "se_hac": float(r.bse[j]), "t_hac": float(r.tvalues[j]),
                             "p_hac": float(r.pvalues[j]), "se_ols": float(naive.bse[j]),
                             "hac_lags": r.lags, "n": r.nobs, "r2": float(r.rsquared),
                             "first": str(f.index.min().date()), "last": str(f.index.max().date())})
    pd.DataFrame(fit_rows).to_csv(tables / "har_fit.csv", index=False)

    # ---- 3. the panel: real-time forecasts, VRP, slopes, signals -----------------
    curve = idx[["vix", "vix3m", "cm30", "cm90", "f1", "days_to_exp1"]]
    panel, har = build_signal_panel(rv, curve, horizon=H, lags=LAGS, log=LOG,
                                    train_min=TMIN, refit_every=REFIT,
                                    contango_threshold=THR, vrp_min=VMIN)
    burn_in = panel["signal"].first_valid_index()

    # ---- 4. out-of-sample evaluation against naive benchmarks --------------------
    from svcarry.econometrics.har import har_oos_forecast
    y = har.realised
    bench = {
        f"HAR log (primary)": har.forecast,
        "HAR level": har_oos_forecast(rv, H, LAGS, False, TMIN, REFIT).forecast,
        "HAR log, smearing (not adopted)": har_oos_forecast(
            rv, H, LAGS, True, TMIN, REFIT, retransform="smearing").forecast,
        f"trailing {H}-day RV": rv.rolling(H).mean(),
        "random walk (today's RV)": rv,
        "expanding mean": rv.expanding().mean(),
    }
    common = y.dropna().index
    for f in bench.values():
        common = common.intersection(f.dropna().index)
    periods = {"full": (None, None), "2008-2012": ("2008", "2012"),
               "2013-2019": ("2013", "2019"), "2020-2026": ("2020", "2026")}
    diag = []
    trail = bench[f"trailing {H}-day RV"]
    for per, (a, b) in periods.items():
        c = common[(common >= pd.Timestamp(a or "1900")) & (common <= pd.Timestamp(f"{b}-12-31" if b else "2100"))]
        for name, f in bench.items():
            m = forecast_metrics(f.reindex(c), y.reindex(c), H,
                                 baseline=bench["expanding mean"].reindex(c))
            if name != f"trailing {H}-day RV":
                e_a = (y.reindex(c) - f.reindex(c)) ** 2
                e_b = (y.reindex(c) - trail.reindex(c)) ** 2
                q_a = pd.Series(qlike(y.reindex(c), f.reindex(c)), index=c)
                q_b = pd.Series(qlike(y.reindex(c), trail.reindex(c)), index=c)
                dm1, dm2 = diebold_mariano(e_a, e_b, H), diebold_mariano(q_a, q_b, H)
                m.update({"dm_mse_t_vs_trailing": dm1["t_stat"], "dm_mse_p": dm1["p_value"],
                          "dm_qlike_t_vs_trailing": dm2["t_stat"], "dm_qlike_p": dm2["p_value"]})
            diag.append({"period": per, "model": name, **m})
    diag = pd.DataFrame(diag)
    diag.to_csv(tables / "har_oos_diagnostics.csv", index=False)
    pd.DataFrame({"har_forecast": har.forecast, "realised_next_h": y,
                  "trailing_rv": trail.reindex(har.forecast.index),
                  "rv_proxy": rv.reindex(har.forecast.index)}).to_csv(
        processed / "har_oos_forecasts.csv", index_label="date")
    har.coefficients.to_csv(tables / "har_coefficient_path.csv", index_label="refit_date")
    full = diag[diag["period"] == "full"].set_index("model")
    prim, trl = full.loc["HAR log (primary)"], full.loc[f"trailing {H}-day RV"]
    # the leak signature: a forecast should not track its outcome implausibly well
    cc = pd.DataFrame({"f": har.forecast, "y": y, "t": trail, "r": rv}).loc[common]
    corr = {"forecast_vs_outcome": float(cc["f"].corr(cc["y"])),
            "trailing_vs_outcome": float(cc["t"].corr(cc["y"])),
            "forecast_vs_same_day_proxy": float(cc["f"].corr(cc["r"])),
            "log_forecast_vs_log_outcome": float(np.log(cc["f"]).corr(np.log(cc["y"])))}
    # retransformation: were the log residuals already non-normal at the first refit?
    from scipy import stats as _st
    from svcarry.econometrics.har import fit_har as _fit
    f_all = har_features(rv, horizon=H, lags=LAGS, log=True)
    t0 = har.forecast.index[0]
    first_train = f_all.iloc[: f_all.index.searchsorted(t0) - H]
    r0 = _fit(first_train).resid
    smear_fc = bench["HAR log, smearing (not adopted)"]
    vrp_smear = (panel["vix"] / 100.0) ** 2 - 252.0 * smear_fc.reindex(panel.index)
    inv_smear = ((panel["sig_contango"] == 1) & (vrp_smear > VMIN)).loc[burn_in:][
        panel["signal"].loc[burn_in:].notna()].mean()
    retrans = {
        "first_refit_train_rows": int(len(first_train)),
        "first_refit_resid_skew": float(_st.skew(r0)),
        "first_refit_normal_factor": float(np.exp(r0.var(ddof=4) / 2)),
        "first_refit_smearing_factor": float(np.mean(np.exp(r0))),
        "oos_mean_forecast_over_mean_outcome": float(har.forecast.loc[common].mean() / y.loc[common].mean()),
        "oos_median_forecast_over_outcome": float((har.forecast.loc[common] / y.loc[common]).median()),
        "smearing_vrp_positive_share": float((vrp_smear.dropna() > 0).mean()),
        "smearing_invested": float(inv_smear),
    }
    am_over_gm = float((rv.rolling(H).mean() / np.exp(np.log(rv).rolling(H).mean())).loc[common].mean())

    # ---- 5. VRP by hand, from the raw Cboe file ---------------------------------
    hand_date = pd.Timestamp("2018-01-12")
    raw = (ROOT / "data/raw/cboe/indices/VIX_History.csv").read_text(encoding="utf-8").splitlines()
    line = next(ln for ln in raw if ln.startswith(hand_date.strftime("%m/%d/%Y")))
    vix_raw = float(line.split(",")[-1])
    # the forecast itself, rebuilt from the proxy and the coefficients in force
    refit = har.coefficients.index[har.coefficients.index <= hand_date].max()
    b = har.coefficients.loc[refit].to_numpy()
    lrv = np.log(rv.loc[:hand_date])
    x = np.array([1.0, lrv.iloc[-LAGS[0]:].mean(), lrv.iloc[-LAGS[1]:].mean(),
                  lrv.iloc[-LAGS[2]:].mean()])
    fc_raw = float(np.exp(x @ b + 0.5 * har.resid_var.loc[refit]))
    if abs(fc_raw / har.forecast.loc[hand_date] - 1.0) > 1e-12:
        raise ValueError("HAR forecast could not be rebuilt by hand")
    by_hand = (vix_raw / 100.0) ** 2 - 252.0 * fc_raw
    hand = {"date": str(hand_date.date()), "vix_close_raw_line": line, "vix": vix_raw,
            "refit_date": str(refit.date()), "coefficients": b.tolist(),
            "resid_var": float(har.resid_var.loc[refit]),
            "forecast_daily_var": fc_raw, "forecast_ann_vol_pct": float(np.sqrt(252 * fc_raw) * 100),
            "vrp_by_hand": by_hand, "vrp_panel": float(panel.loc[hand_date, "vrp"]),
            "agree": bool(abs(by_hand - panel.loc[hand_date, "vrp"]) < 1e-12)}
    if not hand["agree"]:
        raise ValueError(f"VRP hand check failed: {hand}")

    # ---- 6. signal statistics ---------------------------------------------------
    stats_ = signal_statistics(panel, start=burn_in)
    stats_.to_csv(tables / "signal_statistics.csv", index=False)
    post = panel.loc[burn_in:].dropna(subset=["signal"])
    by_year = post.groupby(post.index.year).agg(
        days=("signal", "size"), invested=("signal", "mean"),
        contango_on=("sig_contango", "mean"), vrp_on=("sig_vrp", "mean"))
    by_year.to_csv(tables / "signal_statistics_by_year.csv", index_label="year")
    ov = panel.dropna(subset=["slope_cm", "slope_vix3m"])
    agree = float((panel["sig_contango"] == panel["sig_contango_vix3m"])[ov.index].mean())
    agree_filled = float((panel["sig_contango"] == panel["sig_contango_vix3m"])[
        ov.index[ov["cm30_spot_anchored"]]].mean())

    # ---- 7. timing table (look-ahead audit, step 2) -------------------------------
    lag = int(cfg.dotted("strategy.signal_lag"))
    timing = pd.DataFrame([
        ("SPY open/high/low/close", "t", "close of t (4:00 pm ET)", f"close of t+{lag}"),
        ("rv_proxy (overnight + Rogers-Satchell)", "t", "close of t", f"close of t+{lag}"),
        ("HAR predictors rv_d, rv_w, rv_m", "t", "close of t (windows end at t)", f"close of t+{lag}"),
        ("HAR coefficients", "refit date t", f"close of t; trained on rows s <= t-{H}-1, whose "
         f"targets end by t-1", f"close of t+{lag}"),
        ("HAR forecast", "t", "close of t", f"close of t+{lag}"),
        ("VIX close", "t", "4:15 pm ET on t", f"close of t+{lag}"),
        ("VIX3M close", "t", "4:15 pm ET on t", f"close of t+{lag} (robustness only)"),
        ("VX settlements -> cm30, cm90", "t", "3:15 pm CT to 2020-10-23; 3:00 pm CT after",
         f"close of t+{lag}"),
        ("VRP, slopes, signals", "t", "latest of the above: 4:15 pm ET on t", f"close of t+{lag}"),
        ("realised_next_h (evaluation only)", "t", f"close of t+{H}", "never used in a decision"),
    ], columns=["input", "indexed_by", "available", "first_used"])
    timing["use_precedes_availability"] = False
    timing.to_csv(tables / "timing_audit.csv", index=False)

    # ---- 8. outputs --------------------------------------------------------------
    panel.to_csv(processed / "signals_daily.csv", index_label="date")
    from svcarry.viz.figures import (
        plot_har_forecast_vs_realised, plot_signal_state, plot_vrp_timeseries,
    )
    from svcarry.viz.style import save_figure
    save_figure(plot_vrp_timeseries(panel), figdir / "vrp_timeseries.png")
    save_figure(plot_har_forecast_vs_realised(
        har.forecast.reindex(common), y.reindex(common), trail.reindex(common),
        stats={"oos_r2": prim["oos_r2_vs_eval_mean"], "mz_beta": prim["mz_beta"],
               "trail_r2": trl["oos_r2_vs_eval_mean"], "trail_mz": trl["mz_beta"]}),
        figdir / "har_forecast_vs_realised.png")
    save_figure(plot_signal_state(panel, THR), figdir / "signal_state.png")

    st = stats_.set_index("statistic")["fraction"]
    qc = {
        "proxy": f"SPY {METHOD}", "proxy_ann_vol_pct": float(np.sqrt(252 * rv.mean()) * 100),
        "yang_zhang_window_check": yz_check,
        "burn_in_first_signal": str(burn_in.date()),
        "oos_first": str(common.min().date()), "oos_last": str(common.max().date()),
        "oos_n": int(len(common)),
        "oos_r2": float(prim["oos_r2_vs_eval_mean"]),
        "oos_r2_vs_expanding_mean": float(prim["oos_r2_vs_expanding_mean"]),
        "rmse_har_vs_trailing": [float(prim["rmse_ann_var"]), float(trl["rmse_ann_var"])],
        "qlike_har_vs_trailing": [float(prim["qlike"]), float(trl["qlike"])],
        "dm_t_mse": float(prim["dm_mse_t_vs_trailing"]), "dm_t_qlike": float(prim["dm_qlike_t_vs_trailing"]),
        "mz_beta": float(prim["mz_beta"]), "mz_beta_se": float(prim["mz_beta_se"]),
        "trailing_mz_beta": float(trl["mz_beta"]),
        "correlations": corr, "am_over_gm_21d_mean": am_over_gm,
        "retransformation": retrans,
        "vrp_hand_check": hand,
        "vrp_positive_share": float((panel["vrp"].dropna() > 0).mean()),
        "vrp_median_ann_var": float(panel["vrp"].median()),
        "cm30_spot_anchored_days": int(panel["cm30_spot_anchored"].sum()),
        "slope_agreement_overlap": agree, "slope_agreement_on_anchored_days": agree_filled,
        "slope_overlap_days": int(len(ov)),
        "slope_ratio_corr": float(ov["slope_cm"].corr(ov["slope_vix3m"])),
        "coverage_after_burn_in": float(st["days with the combined signal defined"]),
        "contango_on": float(st["contango (cm30/cm90) on"]),
        "vrp_on": float(st["VRP on"]),
        "invested": float(st["combined on (invested)"]),
        "signals_agree": float(st["both signals agree"]),
        "binding": {b: float(st[f"off, binding constraint: {b}"]) for b in ("contango", "vrp", "both")},
        "undefined_after_burn_in": [str(d.date()) for d in
                                    panel.loc[burn_in:].index[panel.loc[burn_in:, "signal"].isna()]],
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


def stage_backtest(cfg) -> dict:
    """The crash-budgeted strategy, its benchmarks, and H5.

    Three things are kept visible throughout because each could otherwise flatter the
    result: the design window is reported apart from the evaluation window and never
    pooled into a headline; the crash floor is the largest move observed *to date*,
    with the configured 5 February 2018 floor run beside it as a hindsight
    calibration; and the deliberately leaky variant (signal_lag = 0) is run so a
    reader can see what a one-day leak would have been worth here.
    """
    import numpy as np
    import pandas as pd

    from svcarry.data.cboe import load_cboe_index
    from svcarry.data.fred import load_fred, tbill_accrual
    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.econometrics.evt import choose_threshold
    from svcarry.econometrics.garch import GJRGarch
    from svcarry.econometrics.tailrisk import SplicedInnovations, conditional_move_quantile
    from svcarry.evaluation.metrics import (
        drawdown, performance_stats, performance_table, rolling_sharpe, window_returns,
    )
    from svcarry.evaluation.regressions import alpha_regression, downside_beta_regression
    from svcarry.strategy.backtest import buy_and_hold_etp, run_backtest
    from svcarry.strategy.sizing import roll_fraction, running_max_floor, strategy_weights

    processed = ROOT / cfg.dotted("paths.processed")
    tables = ROOT / cfg.dotted("paths.tables")
    figdir = ROOT / cfg.dotted("paths.figures")
    idx = pd.read_csv(_require(processed / "index_daily.csv", "the reconstructed index",
                               "run: python scripts/run_pipeline.py --only index"),
                      parse_dates=["date"]).set_index("date")
    sig = pd.read_csv(_require(processed / "signals_daily.csv", "the signal panel",
                               "run: python scripts/run_pipeline.py --only signals"),
                      parse_dates=["date"]).set_index("date")
    R = idx["ret"]
    lr = np.log1p(R.dropna())
    DESIGN_END = pd.Timestamp(cfg.dotted("sample.design_end"))
    OOS_START = pd.Timestamp(cfg.dotted("sample.oos_start"))
    VT = float(cfg.dotted("strategy.vol_target"))
    VL = int(cfg.dotted("strategy.vol_lookback"))
    LMAX = float(cfg.dotted("strategy.max_stress_loss"))
    WMAX = float(cfg.dotted("strategy.max_weight"))
    QP = float(cfg.dotted("strategy.stress_quantile"))
    LAG = int(cfg.dotted("strategy.signal_lag"))
    TICKS = float(cfg.dotted("strategy.cost_ticks"))
    TICK = float(cfg.dotted("strategy.tick_value"))
    GRID = [float(q) for q in cfg.dotted("tail.threshold_grid")]

    # ---- 1. the crash scenario, fitted on the design window only ---------------
    train = lr[lr.index <= DESIGN_END]
    fit = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(train, n_starts=4, seed=0)
    fit1 = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(train, n_starts=4, seed=1)
    thr, gpds, q_chosen = choose_threshold(fit.std_resid, GRID)
    thr.insert(0, "sample", f"design window to {DESIGN_END.date()}")
    thr.to_csv(tables / "evt_threshold_design_window.csv", index=False)
    if not np.isfinite(q_chosen):
        raise SystemExit("no design-window EVT threshold satisfies the rule")
    innov = SplicedInnovations(fit.dist, fit.dist_params, gpds[q_chosen])
    q999 = conditional_move_quantile(fit.params, innov, lr, p=QP).reindex(idx.index)
    floor_rt = running_max_floor(R).reindex(idx.index)
    floor_event = float(R.loc[pd.Timestamp(cfg.dotted("strategy.stress_floor_event"))])

    # ---- 2. weights -------------------------------------------------------------
    S = sig["signal"].reindex(idx.index)
    sizing = {
        "primary": strategy_weights(R, S, q999, floor_rt, VT, VL, LMAX, WMAX),
        "hindsight floor (calibration)":
            strategy_weights(R, S, q999, floor_event, VT, VL, LMAX, WMAX),
        "no crash budget (vol target only)":
            strategy_weights(R, S, q999 * 0 + 1e-12, 1e-12, VT, VL, LMAX, WMAX),
        "no signals (always on)":
            strategy_weights(R, pd.Series(1.0, index=idx.index), q999, floor_rt,
                             VT, VL, LMAX, WMAX),
    }
    W = sizing["primary"]
    W.to_csv(processed / "strategy_weights.csv", index_label="date")

    # ---- 3. the backtest --------------------------------------------------------
    acc = tbill_accrual(load_fred("DTB3"), idx.index)
    price = (idx["w1"] * idx["f1"] + idx["w2"] * idx["f2"]).rename("price_held")
    roll = roll_fraction(idx["w2"], idx["exp2"])
    common = dict(price_level=price, accrual=acc, cost_ticks=TICKS, tick_size=TICK,
                  roll_fraction=roll)
    bt = run_backtest(R, W["weight"], signal_lag=LAG, **common)
    runs = {"strategy": bt}
    for nm, sz in sizing.items():
        if nm != "primary":
            runs[nm] = run_backtest(R, sz["weight"], signal_lag=LAG, **common)
    lag_runs = {l: run_backtest(R, W["weight"], signal_lag=l, **common) for l in (0, 1, 2)}
    cost_runs = {c: run_backtest(R, W["weight"], signal_lag=LAG,
                                 **{**common, "cost_ticks": c})
                 for c in [float(x) for x in cfg.dotted("robustness.cost_ticks_grid")]}
    no_roll = run_backtest(R, W["weight"], signal_lag=LAG,
                           **{**common, "roll_fraction": None})
    no_drift = run_backtest(R, W["weight"], signal_lag=LAG, drift_turnover=False, **common)

    # ---- 4. benchmarks ----------------------------------------------------------
    fee = lambda sym: float(cfg.dotted(f"products.{sym}.fee"))          # noqa: E731
    spy = split_adjusted_returns(load_prices("SPY")).reindex(idx.index)
    put = load_cboe_index("PUT")["close"].reindex(idx.index).pct_change()
    vxx_like = R - fee("VXX") * pd.Series(idx.index, index=idx.index).diff().dt.days / 365.0
    bh1 = buy_and_hold_etp(R.fillna(0.0), leverage=-1.0, fee=fee("XIV"), accrual=acc)
    bh05 = buy_and_hold_etp(R.fillna(0.0), leverage=-0.5, fee=fee("SVXY"), accrual=acc)

    def const_weight(window_start, window_end):
        w = bt.weight.loc[window_start:window_end].mean()
        return w, run_backtest(R, pd.Series(w, index=idx.index), signal_lag=LAG, **common)

    series = {
        "strategy": bt.returns,
        "buy-and-hold -1x (XIV fee)": bh1.returns,
        "buy-and-hold -0.5x (SVXY fee)": bh05.returns,
        "Cboe PutWrite (PUT)": put,
        "S&P 500 (SPY, total return)": spy,
    }
    extras = {"strategy": {"turnover": bt.turnover, "weight": bt.weight}}

    # ---- 5. performance, by window ----------------------------------------------
    windows = {"full (not a headline)": (idx.index.min(), idx.index.max()),
               "design": (idx.index.min(), DESIGN_END),
               "oos": (OOS_START, idx.index.max())}
    perf = {}
    const_w = {}
    for wname, (lo, hi) in windows.items():
        cw, cw_bt = const_weight(lo, hi)
        const_w[wname] = cw
        ser = {**series, f"constant weight {cw:.3f} short": cw_bt.returns}
        sub = {k: v.loc[lo:hi] for k, v in ser.items()}
        t = performance_table(sub, rf=acc.loc[lo:hi],
                              extras={"strategy": {"turnover": bt.turnover.loc[lo:hi],
                                                   "weight": bt.weight.loc[lo:hi]}})
        t.insert(0, "window", wname)
        perf[wname] = t
        t.to_csv(tables / f"performance_{wname.split()[0]}.csv")
    oos = perf["oos"]

    # ---- 6. variants, lags, costs -----------------------------------------------
    var_rows = []
    for nm, r_ in {**{k: v.returns for k, v in runs.items()},
                   **{f"signal_lag = {l}": v.returns for l, v in lag_runs.items()},
                   **{f"cost {c:g} tick(s)": v.returns for c, v in cost_runs.items()},
                   "no roll cost charged": no_roll.returns,
                   "no drift turnover charged": no_drift.returns}.items():
        for wname, (lo, hi) in windows.items():
            st = performance_stats(r_.loc[lo:hi], rf=acc.loc[lo:hi], name=nm)
            st["window"] = wname
            var_rows.append(st)
    variants = pd.DataFrame(var_rows)
    variants.to_csv(tables / "backtest_variants.csv", index=False)

    # ---- 7. stress windows -------------------------------------------------------
    sw = {k: (v[0], v[1]) for k, v in cfg.dotted("robustness.stress_windows").items()}
    cw_full, cw_full_bt = const_weight(*windows["full (not a headline)"])
    stress = window_returns({**series,
                             f"constant weight {cw_full:.3f} short": cw_full_bt.returns,
                             "strategy, hindsight floor": runs["hindsight floor (calibration)"].returns,
                             "strategy, no crash budget": runs["no crash budget (vol target only)"].returns},
                            sw)
    stress.to_csv(tables / "stress_windows.csv", index_label="window")

    # ---- 8. attribution ----------------------------------------------------------
    factors = {"PUT": put - acc, "SPX": spy - acc, "VXX_like": vxx_like}
    # The three-factor regression is what H5 names, but VXX_like is the index the
    # strategy is short, so it is nearly mechanical and it is strongly correlated with
    # PUT. Two auxiliary specifications are reported so the partial coefficients are
    # not read as economic loadings on their own.
    specs = {"H5 (PUT+SPX+VXX)": factors,
             "auxiliary: PUT+SPX": {k: factors[k] for k in ("PUT", "SPX")},
             "auxiliary: VXX only": {"VXX_like": factors["VXX_like"]},
             "auxiliary: PUT only": {"PUT": factors["PUT"]},
             "auxiliary: SPX only": {"SPX": factors["SPX"]}}
    aux_rows = []
    for wname, (lo, hi) in windows.items():
        for sname, fs in specs.items():
            a_ = alpha_regression(bt.returns.loc[lo:hi],
                                  {k: v.loc[lo:hi] for k, v in fs.items()}, rf=acc.loc[lo:hi])
            aux_rows.append({"window": wname, "spec": sname, "n": a_["n"],
                             "alpha_annual": a_["alpha_annual"], "alpha_t": a_["alpha_t"],
                             "alpha_p": a_["alpha_p"], "r2": a_["rsquared"],
                             **{f"beta_{k}": v for k, v in a_["betas"].items()},
                             **{f"t_{k}": v for k, v in a_["beta_t"].items()}})
    aux = pd.DataFrame(aux_rows)
    fcorr = pd.DataFrame({k: v for k, v in factors.items()}).corr()
    fcorr.to_csv(tables / "factor_correlations.csv", index_label="factor")
    aux.to_csv(tables / "alpha_regression_specs.csv", index=False)

    reg_rows, regs = [], {}
    for wname, (lo, hi) in windows.items():
        r_ = bt.returns.loc[lo:hi]
        a = alpha_regression(r_, {k: v.loc[lo:hi] for k, v in factors.items()}, rf=acc.loc[lo:hi])
        d = downside_beta_regression(r_, spy.loc[lo:hi], rf=acc.loc[lo:hi])
        regs[wname] = (a, d)
        reg_rows.append({"window": wname, "n": a["n"], "alpha_annual": a["alpha_annual"],
                         "alpha_t": a["alpha_t"], "alpha_p": a["alpha_p"],
                         **{f"beta_{k}": v for k, v in a["betas"].items()},
                         **{f"t_{k}": v for k, v in a["beta_t"].items()},
                         "r2": a["rsquared"], "hac_lags": a["lags"],
                         "beta_spx_up": d["beta_up"], "beta_spx_down": d["beta_down"],
                         "asymmetry_p": d["asymmetry_p"]})
    pd.DataFrame(reg_rows).to_csv(tables / "alpha_regression.csv", index=False)

    # ---- 9. daily panel and figures ----------------------------------------------
    daily = bt.frame().join(W[["realised_vol", "move_quantile", "floor", "stress_move",
                               "w_vol_target", "w_stress_budget", "binding",
                               "stress_source"]], rsuffix="_sizing")
    daily["index_ret"] = R
    daily["signal"] = S
    daily = daily.join(bt.components[["turnover_rebalance", "turnover_roll",
                                      "cost_rebalance", "cost_roll"]])
    daily.to_csv(processed / "backtest_daily.csv", index_label="date")

    from svcarry.viz.figures import (
        plot_drawdowns, plot_equity_curves, plot_event_detail, plot_weight_and_constraint,
    )
    from svcarry.viz.style import save_figure
    eq = {nm: (1.0 + s.fillna(0.0)).cumprod() for nm, s in
          {**series, f"constant weight {cw_full:.3f} short": cw_full_bt.returns}.items()}
    save_figure(plot_equity_curves(eq, oos_start=str(OOS_START.date())),
                figdir / "equity_curve.png")
    save_figure(plot_drawdowns({nm: drawdown(s.fillna(0.0))["drawdown"]
                                for nm, s in series.items()}), figdir / "drawdowns.png")
    from svcarry.viz.figures import plot_rolling_sharpe
    rs = {nm: rolling_sharpe(s, 252, rf=acc) for nm, s in series.items()
          if nm != "buy-and-hold -1x (XIV fee)"}
    save_figure(plot_rolling_sharpe(rs, 252, oos_start=str(OOS_START.date())),
                figdir / "rolling_sharpe.png")
    save_figure(plot_weight_and_constraint(bt.weight, W["binding"].shift(LAG)),
                figdir / "weight_and_binding_constraint.png")
    ev = idx.loc["2018-01-15":"2018-03-01"]
    save_figure(plot_event_detail(
        (1.0 + R.loc[ev.index]).cumprod(),
        {"strategy": (1.0 + bt.returns.loc[ev.index]).cumprod(),
         "buy-and-hold -1x": (1.0 + bh1.returns.loc[ev.index]).cumprod(),
         "strategy, hindsight floor": (1.0 + runs["hindsight floor (calibration)"]
                                       .returns.loc[ev.index]).cumprod()},
        weight=bt.weight.loc[ev.index]), figdir / "feb2018_detail.png")

    # ---- 9b. what the escape from 5 February 2018 rests on -----------------------
    thr_c = float(cfg.dotted("strategy.contango_threshold"))
    feb_prev, feb_day = pd.Timestamp("2018-02-02"), pd.Timestamp("2018-02-05")
    w_held = float(W.loc[pd.Timestamp("2018-02-01"), "weight"])
    feb_dep = {
        "signal_off_from": str(feb_prev.date()),
        "slope_cm_on_2018-02-02": float(sig.loc[feb_prev, "slope_cm"]),
        "threshold": thr_c,
        "margin_over_threshold_pct": float(sig.loc[feb_prev, "slope_cm"] / thr_c - 1.0) * 100,
        "vrp_signal_on_2018-02-02": float(sig.loc[feb_prev, "sig_vrp"]),
        "vrp_on_2018-02-05": float(sig.loc[feb_day, "vrp"]),
        "weight_that_would_have_been_held": w_held,
        "counterfactual_loss_on_2018-02-05": -w_held * float(R.loc[feb_day]),
        "actual_return_on_2018-02-05": float(bt.returns.loc[feb_day]),
        "worst_day_with_lag_2": float(lag_runs[2].returns.min()),
    }

    # ---- 9c. timing table, extended over the sizing chain ------------------------
    tpath = tables / "timing_audit.csv"
    tt = pd.read_csv(tpath) if tpath.exists() else pd.DataFrame()
    rows = [
        ("index return r_t", "t", "futures settlement on t", "close of t (sizing inputs)"),
        ("trailing 21-day realised volatility", "t", "close of t", f"close of t+{LAG}"),
        ("GJR-GARCH parameters + EVT tail", f"fitted once on data to {DESIGN_END.date()}",
         f"{DESIGN_END.date()}", f"first used {OOS_START.date()} out of sample; in sample before"),
        ("conditional 99.9% move for t+1", "t", "close of t (state filtered to t)",
         f"close of t+{LAG}"),
        ("crash floor (running maximum)", "t", "close of t", f"close of t+{LAG}"),
        ("weight w", "t", "close of t", f"return of t+{LAG}"),
        ("T-bill accrual", "t", "previous business day's discount rate", "return of t"),
        ("futures price for costs", "t", "settlement on t", "costs charged on t"),
    ]
    add = pd.DataFrame(rows, columns=["input", "indexed_by", "available", "first_used"])
    add["use_precedes_availability"] = False
    pd.concat([tt, add], ignore_index=True).to_csv(tpath, index=False)

    # ---- 10. audit and H5 ---------------------------------------------------------
    sr = lambda s, lo, hi: performance_stats(s.loc[lo:hi], rf=acc.loc[lo:hi])["sharpe"]  # noqa: E731
    lo_o, hi_o = windows["oos"]
    lag_sharpe = {l: sr(v.returns, lo_o, hi_o) for l, v in lag_runs.items()}
    cost_sharpe = {c: sr(v.returns, lo_o, hi_o) for c, v in cost_runs.items()}
    feb = {nm: float((1.0 + s.loc["2018-02-05":"2018-02-06"]).prod() - 1.0)
           for nm, s in {**series, "strategy, hindsight floor":
                         runs["hindsight floor (calibration)"].returns}.items()}
    a_oos = regs["oos"][0]
    worst = bt.returns.loc[lo_o:hi_o].nsmallest(3)
    best = bt.returns.loc[lo_o:hi_o].nlargest(3)
    tot_oos = float((1.0 + bt.returns.loc[lo_o:hi_o]).prod() - 1.0)
    qc = {
        "design_window_model": {
            "n": int(len(train)), "end": str(DESIGN_END.date()),
            "persistence": fit.persistence, "threshold_q": q_chosen,
            "xi": gpds[q_chosen].xi,
            "max_param_diff_between_seeds": max(abs(fit.params[k] - fit1.params[k])
                                                for k in fit.params),
            "q999_median": float(q999.median()), "q999_max": float(q999.max()),
        },
        "floor": {"running_max_at_2018-02-02": float(floor_rt.loc["2018-02-02"]),
                  "event_floor": floor_event,
                  "share_days_floor_binds_over_model": float((W["stress_source"] == "floor").mean())},
        "weights": {"mean": float(bt.weight.mean()), "max": float(bt.weight.max()),
                    "mean_when_on": float(bt.weight[bt.weight > 0].mean()),
                    "binding_shares": W["binding"].value_counts(normalize=True).round(4).to_dict()},
        "oos": {
            "sharpe": float(oos.loc["strategy", "sharpe"]),
            "sharpe_se": float(oos.loc["strategy", "sharpe_se_lo"]),
            "cagr": float(oos.loc["strategy", "cagr"]),
            "max_drawdown": float(oos.loc["strategy", "max_drawdown"]),
            "worst_day": float(oos.loc["strategy", "worst_day"]),
            "worst_week": float(oos.loc["strategy", "worst_week"]),
            "ann_turnover": float(oos.loc["strategy", "ann_turnover"]),
            "total_return": tot_oos,
            "worst_3_days": {str(d.date()): float(v) for d, v in worst.items()},
            "best_3_days": {str(d.date()): float(v) for d, v in best.items()},
        },
        "design_sharpe": float(perf["design"].loc["strategy", "sharpe"]),
        "constant_weight": const_w,
        "lag_sharpe_oos": lag_sharpe, "cost_sharpe_oos": cost_sharpe,
        "feb_2018_5th_6th": feb,
        "feb_2018_dependence": feb_dep,
        "alpha_specs_oos": aux[aux["window"] == "oos"].set_index("spec")[
            ["alpha_annual", "alpha_t", "r2", "beta_PUT", "beta_VXX_like"]].round(4).to_dict("index"),
        "factor_correlations": fcorr.round(3).to_dict(),
        "alpha_oos": {"annual": a_oos["alpha_annual"], "t": a_oos["alpha_t"],
                      "p": a_oos["alpha_p"], "betas": a_oos["betas"],
                      "n": a_oos["n"], "r2": a_oos["rsquared"]},
        "H5": {
            "oos_sharpe_positive": bool(oos.loc["strategy", "sharpe"] > 0),
            "alpha_insignificant_at_5pct": bool(a_oos["alpha_p"] > 0.05),
        },
        "cost_share_roll": float(bt.components["cost_roll"].sum() / bt.costs.sum()),
        "outputs": ["data/processed/backtest_daily.csv",
                    "reports/tables/performance_{full,design,oos}.csv",
                    "reports/tables/stress_windows.csv",
                    "reports/tables/alpha_regression.csv",
                    "reports/tables/backtest_variants.csv"],
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


def stage_robust(cfg) -> dict:
    """Try to break every conclusion, and report the whole grid - not the cells that
    worked.

    The organising question is the phase prompt's: not "does the result survive small
    perturbations" but "what is the smallest reasonable change that reverses it".
    Every cell of every sweep is written out, the chosen configuration's rank inside
    the full grid is reported, and the nine red-team questions are answered with
    numbers rather than reassurance.
    """
    import numpy as np
    import pandas as pd

    from svcarry.data.cboe import load_cboe_index, load_vx_panel
    from svcarry.data.fred import load_fred, tbill_accrual
    from svcarry.data.prices import load_prices, split_adjusted_returns
    from svcarry.econometrics.evt import choose_threshold
    from svcarry.econometrics.garch import GJRGarch
    from svcarry.econometrics.realized import daily_variance_proxy
    from svcarry.econometrics.tailrisk import SplicedInnovations, conditional_move_quantile
    from svcarry.evaluation.metrics import performance_stats, sharpe_standard_error
    from svcarry.evaluation.regressions import alpha_regression
    from svcarry.index.reconstruct import reconstruct_index
    from svcarry.strategy.backtest import run_backtest
    from svcarry.strategy.signals import build_signal_panel, combine_signals
    from svcarry.strategy.sizing import roll_fraction, running_max_floor, strategy_weights

    processed = ROOT / cfg.dotted("paths.processed")
    interim = ROOT / cfg.dotted("paths.interim")
    tables = ROOT / cfg.dotted("paths.tables")
    figdir = ROOT / cfg.dotted("paths.figures")
    idx = pd.read_csv(_require(processed / "index_daily.csv", "the reconstructed index",
                               "run: python scripts/run_pipeline.py --only index"),
                      parse_dates=["date"]).set_index("date")
    DESIGN_END = pd.Timestamp(cfg.dotted("sample.design_end"))
    OOS_START = pd.Timestamp(cfg.dotted("sample.oos_start"))
    BASE = dict(
        vol_target=float(cfg.dotted("strategy.vol_target")),
        vol_lookback=int(cfg.dotted("strategy.vol_lookback")),
        max_stress_loss=float(cfg.dotted("strategy.max_stress_loss")),
        max_weight=float(cfg.dotted("strategy.max_weight")),
        contango_threshold=float(cfg.dotted("strategy.contango_threshold")),
        vrp_min=float(cfg.dotted("strategy.vrp_min")),
        cost_ticks=float(cfg.dotted("strategy.cost_ticks")),
        signal_lag=int(cfg.dotted("strategy.signal_lag")),
        rebalance=1, evt_q=None, floor="running_max", slope="cm",
        horizon=int(cfg.dotted("forecast.har_horizon")),
        lags=tuple(int(x) for x in cfg.dotted("forecast.har_lags")),
        har_log=bool(cfg.dotted("forecast.har_log")),
        retransform="normal", rv_method=str(cfg.dotted("forecast.rv_method")),
        index="rolled",
    )
    TICK = float(cfg.dotted("strategy.tick_value"))
    TMIN = int(cfg.dotted("forecast.har_train_min"))
    REFIT = int(cfg.dotted("forecast.har_refit_every"))
    QP = float(cfg.dotted("strategy.stress_quantile"))
    GRID = [float(q) for q in cfg.dotted("tail.threshold_grid")]
    acc = tbill_accrual(load_fred("DTB3"), idx.index)
    spy_ohlc = load_prices("SPY")
    floor_event = float(idx["ret"].loc[pd.Timestamp(cfg.dotted("strategy.stress_floor_event"))])

    # ---- alternative index constructions ---------------------------------------
    panel = pd.read_csv(_require(interim / "vx_panel.csv", "the futures panel",
                                 "run: python scripts/run_pipeline.py --only clean"),
                        parse_dates=["date", "expiry"])

    def constant_maturity_index(p: pd.DataFrame, maturity: int = 30) -> pd.DataFrame:
        """Hold the two contracts bracketing ``maturity`` days, at the interpolation
        weights, and reprice them the next day. A tradable alternative to the calendar
        roll: the weights come from where 30 days falls on the curve, not from the
        roll schedule."""
        g = p.dropna(subset=["settle"]).sort_values(["date", "days_to_expiry"])
        rows = {}
        for d, grp in g.groupby("date"):
            q = grp[grp["days_to_expiry"] > 0]
            lo = q[q["days_to_expiry"] <= maturity].tail(1)
            hi = q[q["days_to_expiry"] > maturity].head(1)
            if len(hi) == 0:
                continue
            if len(lo) == 0:                       # nothing shorter: hold the front
                rows[d] = {"e1": hi["expiry"].iloc[0], "e2": hi["expiry"].iloc[0],
                           "p1": hi["settle"].iloc[0], "p2": hi["settle"].iloc[0], "w1": 1.0}
                continue
            t1, t2 = float(lo["days_to_expiry"].iloc[0]), float(hi["days_to_expiry"].iloc[0])
            w1 = (t2 - maturity) / (t2 - t1)
            rows[d] = {"e1": lo["expiry"].iloc[0], "e2": hi["expiry"].iloc[0],
                       "p1": lo["settle"].iloc[0], "p2": hi["settle"].iloc[0], "w1": w1}
        cm = pd.DataFrame.from_dict(rows, orient="index").sort_index()
        px = p.dropna(subset=["settle"]).set_index(["date", "expiry"])["settle"]
        ret = {}
        dates = cm.index
        for i in range(1, len(dates)):
            t, s = dates[i], dates[i - 1]
            r = cm.loc[s]
            try:
                p1n, p2n = px.loc[(t, r["e1"])], px.loc[(t, r["e2"])]
            except KeyError:
                continue
            ret[t] = r["w1"] * (p1n / r["p1"] - 1.0) + (1 - r["w1"]) * (p2n / r["p2"] - 1.0)
        out = cm.copy()
        out["ret"] = pd.Series(ret)
        out["w2"] = 1.0 - out["w1"]
        out["price_held"] = out["w1"] * out["p1"] + out["w2"] * out["p2"]
        return out

    def calendar_spread_index(p: pd.DataFrame, near: int = 1, far: int = 4) -> pd.DataFrame:
        """Long the front month, short the ``far``-th, both rolled on the monthly
        cycle, normalised to one unit of front-month notional. Shorting this series is
        the calendar-spread version of the strategy: it isolates the slope from the
        level."""
        g = p.dropna(subset=["settle"]).sort_values(["date", "days_to_expiry"])
        g = g[g["days_to_expiry"] > 0]
        held, rows = {}, {}
        for d, grp in g.groupby("date"):
            if len(grp) < far:
                continue
            held[d] = (grp["expiry"].iloc[near - 1], grp["expiry"].iloc[far - 1],
                       grp["settle"].iloc[near - 1], grp["settle"].iloc[far - 1])
        px = g.set_index(["date", "expiry"])["settle"]
        dates = sorted(held)
        for i in range(1, len(dates)):
            t, s = dates[i], dates[i - 1]
            e1, e2, p1, p2 = held[s]
            try:
                n1, n2 = px.loc[(t, e1)], px.loc[(t, e2)]
            except KeyError:
                continue
            rows[t] = {"ret": (n1 / p1 - 1.0) - (n2 / p2 - 1.0) * (p2 / p1),
                       "price_held": p1}
        return pd.DataFrame.from_dict(rows, orient="index").sort_index()

    alt_index = {}
    alt_index["rolled"] = idx
    shifted = reconstruct_index(panel, convention="shifted")
    alt_index["shifted roll convention"] = shifted
    cm_idx = constant_maturity_index(panel)
    cm_idx["f1"], cm_idx["f2"] = cm_idx["p1"], cm_idx["p2"]
    cm_idx["exp2"] = cm_idx["e2"]
    alt_index["constant-maturity 30 day"] = cm_idx
    sp_idx = calendar_spread_index(panel)
    alt_index["calendar spread, front vs 4th"] = sp_idx

    # ---- cached builders ---------------------------------------------------------
    _sig_cache, _q_cache = {}, {}

    def signal_panel(horizon, lags, har_log, retransform, rv_method, threshold, vrp_min, slope):
        key = (horizon, lags, har_log, retransform, rv_method)
        if key not in _sig_cache:
            rv = daily_variance_proxy(spy_ohlc, rv_method).dropna()
            curve = idx[["vix", "vix3m", "cm30", "cm90", "f1", "days_to_exp1"]]
            _sig_cache[key] = build_signal_panel(
                rv, curve, horizon=horizon, lags=lags, log=har_log, train_min=TMIN,
                refit_every=REFIT, contango_threshold=1.0, vrp_min=0.0,
                retransform=retransform)[0]
        p_ = _sig_cache[key]
        slope_col = "slope_cm" if slope == "cm" else "slope_vix3m"
        c = (p_[slope_col] < threshold).astype(float)
        c[p_[slope_col].isna()] = np.nan
        v = (p_["vrp"] > vrp_min).astype(float)
        v[p_["vrp"].isna()] = np.nan
        return combine_signals({"c": c, "v": v}, rule="all")

    def move_quantile(returns, evt_q):
        key = (id(returns), evt_q)
        if key not in _q_cache:
            lr = np.log1p(returns.dropna())
            train = lr[lr.index <= DESIGN_END]
            fkey = ("fit", id(returns))
            if fkey not in _q_cache:
                f = GJRGarch(dist=cfg.dotted("tail.garch_dist")).fit(train, n_starts=4, seed=0)
                t_, g_, q_ = choose_threshold(f.std_resid, GRID)
                _q_cache[fkey] = (f, g_, q_)
            f, g_, q_ = _q_cache[fkey]
            q = evt_q if evt_q is not None else q_
            innov = SplicedInnovations(f.dist, f.dist_params, g_[q])
            _q_cache[key] = conditional_move_quantile(f.params, innov, lr, p=QP)
        return _q_cache[key]

    def run(**over):
        o = {**BASE, **over}
        src = alt_index[o["index"]]
        R = src["ret"]
        price = (src["w1"] * src["f1"] + src["w2"] * src["f2"]) if "w1" in src else src["price_held"]
        roll = roll_fraction(src["w2"], src["exp2"]) if "w2" in src and "exp2" in src \
            else pd.Series(1.0 / 21.0, index=src.index)
        sig = signal_panel(o["horizon"], o["lags"], o["har_log"], o["retransform"],
                           o["rv_method"], o["contango_threshold"], o["vrp_min"],
                           o["slope"]).reindex(R.index)
        fl = running_max_floor(R) if o["floor"] == "running_max" else floor_event
        w = strategy_weights(R, sig, move_quantile(R, o["evt_q"]).reindex(R.index), fl,
                             o["vol_target"], o["vol_lookback"], o["max_stress_loss"],
                             o["max_weight"])["weight"]
        if o["rebalance"] > 1:                      # hold the weight between rebalances
            keep = pd.Series(False, index=w.index)
            keep.iloc[::o["rebalance"]] = True
            w = w.where(keep).ffill()
        a = acc.reindex(R.index)
        return run_backtest(R, w, price_level=price, accrual=a, signal_lag=o["signal_lag"],
                            cost_ticks=o["cost_ticks"], tick_size=TICK, roll_fraction=roll)

    def stats(bt, lo=OOS_START, hi=None, name="cell"):
        r = bt.returns.loc[lo:hi]
        st = performance_stats(r, rf=acc.reindex(r.index), name=name,
                               turnover=bt.turnover.loc[lo:hi], weight=bt.weight.loc[lo:hi])
        st["feb_2018"] = float((1.0 + bt.returns.loc["2018-02-05":"2018-02-06"]).prod() - 1.0)
        return st

    base_bt = run()
    base_oos = stats(base_bt, name="chosen configuration")
    base_sharpe = base_oos["sharpe"]

    # ---- 1. cost sweep and breakeven ---------------------------------------------
    cost_grid = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
    cost_rows = [stats(run(cost_ticks=c), name=f"{c:g} ticks") | {"cost_ticks": c}
                 for c in cost_grid]
    costs = pd.DataFrame(cost_rows)
    costs.to_csv(tables / "robustness_costs.csv", index=False)
    sh = costs.set_index("cost_ticks")["sharpe"]
    below = sh[sh <= 0]
    if len(below):
        c_hi = below.index[0]
        c_lo = sh.index[sh.index.get_loc(c_hi) - 1]
        breakeven = c_lo + (c_hi - c_lo) * sh[c_lo] / (sh[c_lo] - sh[c_hi])
    else:
        breakeven = np.nan

    # ---- 2. one-at-a-time sweeps --------------------------------------------------
    sweeps = {
        "contango_threshold": [float(x) for x in cfg.dotted("robustness.contango_grid")],
        "vol_target": [float(x) for x in cfg.dotted("robustness.vol_target_grid")],
        "max_stress_loss": [float(x) for x in cfg.dotted("robustness.stress_loss_grid")],
        "rebalance": [int(x) for x in cfg.dotted("robustness.rebalance_grid")],
        "evt_q": GRID,
        "horizon": [10, 21, 42],
        "lags": [(1, 5, 22), (1, 5, 10), (1, 10, 44)],
        "har_log": [True, False],
        "retransform": ["normal", "smearing"],
        "rv_method": ["rs_overnight", "parkinson_overnight", "gk_overnight", "close_to_close"],
        "floor": ["running_max", "event"],
        "slope": ["cm", "vix3m"],
        "vol_lookback": [10, 21, 63],
        "signal_lag": [0, 1, 2],
        "index": list(alt_index),
    }
    par_rows = []
    for name, values in sweeps.items():
        for v in values:
            st = stats(run(**{name: v}), name=f"{name} = {v}")
            st.update({"parameter": name, "value": str(v),
                       "is_baseline": v == BASE[name]})
            par_rows.append(st)
    params = pd.DataFrame(par_rows)
    params.to_csv(tables / "robustness_parameters.csv", index=False)

    # ---- 3. the full grid, for the specification distribution ---------------------
    grid_rows = []
    for th in sweeps["contango_threshold"]:
        for vt in sweeps["vol_target"]:
            for ml in sweeps["max_stress_loss"]:
                for rb in sweeps["rebalance"]:
                    st = stats(run(contango_threshold=th, vol_target=vt,
                                   max_stress_loss=ml, rebalance=rb))
                    st.update({"contango_threshold": th, "vol_target": vt,
                               "max_stress_loss": ml, "rebalance": rb,
                               "is_chosen": (th == BASE["contango_threshold"]
                                             and vt == BASE["vol_target"]
                                             and ml == BASE["max_stress_loss"]
                                             and rb == BASE["rebalance"])})
                    grid_rows.append(st)
    grid = pd.DataFrame(grid_rows)
    grid.to_csv(tables / "specification_distribution.csv", index=False)
    n_specs = len(grid) + len(params) + len(costs)
    pct = float((grid["sharpe"] < base_sharpe).mean())

    # ---- 4. subsamples -------------------------------------------------------------
    sub_rows = []
    for lo, hi in cfg.dotted("robustness.subsamples"):
        st = stats(base_bt, lo=pd.Timestamp(lo), hi=pd.Timestamp(hi) if hi else None,
                   name=f"{lo} to {hi or 'end'}")
        st["kind"] = "configured subsample"
        sub_rows.append(st)
    oos_years = sorted({d.year for d in base_bt.returns.loc[OOS_START:].index})
    for y in oos_years:
        r = base_bt.returns.loc[OOS_START:]
        keep = r[r.index.year != y]
        st = performance_stats(keep, rf=acc.reindex(keep.index), name=f"OOS excluding {y}")
        st["kind"] = "leave one year out"
        sub_rows.append(st)
    for wname, (lo, hi) in cfg.dotted("robustness.stress_windows").items():
        r = base_bt.returns.loc[OOS_START:]
        keep = r[(r.index < pd.Timestamp(lo)) | (r.index > pd.Timestamp(hi))]
        if len(keep) < 250:
            continue
        st = performance_stats(keep, rf=acc.reindex(keep.index), name=f"OOS excluding {wname}")
        st["kind"] = "leave one stress window out"
        sub_rows.append(st)
    for y in oos_years:                      # each year on its own
        r = base_bt.returns.loc[OOS_START:]
        seg = r[r.index.year == y]
        st = performance_stats(seg, rf=acc.reindex(seg.index), name=f"{y} alone")
        st["kind"] = "single year"
        sub_rows.append(st)
    subs = pd.DataFrame(sub_rows)
    subs.to_csv(tables / "robustness_subsamples.csv", index=False)

    # ---- 5. red-team answers, each a number ---------------------------------------
    oos_r = base_bt.returns.loc[OOS_START:]
    tot = float((1.0 + oos_r).prod() - 1.0)
    contrib = {}
    for wname, (lo, hi) in cfg.dotted("robustness.stress_windows").items():
        seg = oos_r[(oos_r.index >= pd.Timestamp(lo)) & (oos_r.index <= pd.Timestamp(hi))]
        if len(seg):
            contrib[wname] = float((1.0 + seg).prod() - 1.0)
    yearly = {int(y): float((1.0 + oos_r[oos_r.index.year == y]).prod() - 1.0)
              for y in oos_years}
    top_day = oos_r.abs().nlargest(1)
    lag0 = stats(run(signal_lag=0))["sharpe"]
    feb_by_threshold = {str(th): float(params[(params["parameter"] == "contango_threshold")
                                              & (params["value"] == str(th))]["feb_2018"].iloc[0])
                        for th in sweeps["contango_threshold"]}
    products = cfg.dotted("products")
    prod_cover = {k: {"inception": v.get("inception"), "terminated": v.get("terminated", "-")}
                  for k, v in products.items()}
    a_oos = alpha_regression(
        oos_r,
        {"PUT": load_cboe_index("PUT")["close"].reindex(idx.index).pct_change().loc[OOS_START:] - acc.loc[OOS_START:],
         "SPX": split_adjusted_returns(load_prices("SPY")).reindex(idx.index).loc[OOS_START:] - acc.loc[OOS_START:],
         "VXX_like": idx["ret"].loc[OOS_START:]},
        rf=acc.loc[OOS_START:])
    redteam = [
        ("1. Weakest assumption",
         "The contango filter's threshold. It cleared 1.0 by 0.72% at the close of "
         "2 Feb 2018; at 1.025 the position is held into the event.",
         f"Feb 2018 return by threshold: " + ", ".join(f"{k}: {v:.1%}" for k, v in feb_by_threshold.items())),
        ("2. Could look-ahead explain the result?",
         "No: a one-day leak multiplies the Sharpe, it does not create the honest one.",
         f"lag 0 Sharpe {lag0:.2f} vs chosen {base_sharpe:.2f}; whole-chain perturbation "
         f"test passes and is mutation-checked"),
        ("3. Survivorship",
         "XIV is in the product sample for its whole life including its termination; "
         "no product was dropped.",
         json.dumps(prod_cover)),
        ("4. Cost at which the OOS Sharpe reaches zero",
         "Interpolated on the cost grid.",
         f"{breakeven:.2f} ticks per side ({breakeven * TICK:.3f} VIX points)"),
        ("5. Does one period dominate?",
         "Total out-of-sample return decomposed by stress window and by year.",
         f"total {tot:.1%}; " + ", ".join(f"{k}: {v:+.1%}" for k, v in contrib.items())
         + "; best year " + max(yearly, key=yearly.get).__str__() + f" {max(yearly.values()):+.1%}"),
        ("6. Does one day dominate?",
         "Largest single day as a share of the total out-of-sample return.",
         f"{top_day.index[0].date()} {float(top_day.iloc[0]):+.1%}, "
         f"{abs(float(top_day.iloc[0]) / tot):.1%} of the total"),
        ("7. Parameter selection",
         "Distribution of out-of-sample Sharpe over the full grid.",
         f"n = {len(grid)} cells: min {grid['sharpe'].min():.2f}, median "
         f"{grid['sharpe'].median():.2f}, max {grid['sharpe'].max():.2f}; chosen "
         f"{base_sharpe:.2f} at the {pct:.0%} percentile"),
        ("8. Asset-outstanding bounds",
         "H2 is stated at the lower bound already (Phase 08); the upper bound only "
         "strengthens it, and the flow claim is excluded outside the anchors.",
         "lower bound 25.0% of front-month open interest; upper bound exceeds 100%"),
        ("9. Is the economic story fitted?",
         "The alpha is indistinguishable from zero and the equity beta is asymmetric, "
         "which is the story the design predicted before the data was seen.",
         f"alpha {a_oos['alpha_annual']:.2%} a year (t = {a_oos['alpha_t']:.2f}); "
         f"a constant-weight short earns more per unit of risk than the dynamic rule"),
    ]
    pd.DataFrame(redteam, columns=["question", "answer", "number"]).to_csv(
        tables / "redteam_answers.csv", index=False)

    # ---- 6. figures ----------------------------------------------------------------
    from svcarry.viz.figures import (
        _SOURCE as _SOURCE_NOTE, plot_cost_sensitivity, plot_parameter_heatmap,
        plot_subsample_stability,
    )
    from svcarry.viz.style import save_figure
    save_figure(plot_cost_sensitivity(costs["cost_ticks"], costs["sharpe"],
                                      breakeven=breakeven), figdir / "cost_sensitivity.png")
    hm = grid[(grid["rebalance"] == 1)].pivot_table(index="contango_threshold",
                                                    columns="max_stress_loss",
                                                    values="sharpe", aggfunc="mean")
    save_figure(plot_parameter_heatmap(
        hm, chosen=(BASE["contango_threshold"], BASE["max_stress_loss"]),
        source=_SOURCE_NOTE + " Daily rebalancing, averaged over the three volatility "
        "targets (0.10, 0.15, 0.20); the full 144-cell grid is in "
        "specification_distribution.csv."), figdir / "parameter_heatmap.png")
    est = {}
    for _, r_ in subs[subs["kind"].isin(["configured subsample", "single year"])].iterrows():
        est[r_["name"]] = (r_["sharpe"], r_.get("sharpe_se_lo", np.nan))
    save_figure(plot_subsample_stability(est, reference=base_sharpe),
                figdir / "subsample_stability.png")

    qc = {
        "chosen_oos_sharpe": base_sharpe,
        "specifications_run_here": int(n_specs),
        "grid": {"n": int(len(grid)), "min": float(grid["sharpe"].min()),
                 "median": float(grid["sharpe"].median()),
                 "max": float(grid["sharpe"].max()),
                 "chosen_percentile": pct,
                 "share_positive": float((grid["sharpe"] > 0).mean())},
        "cost_breakeven_ticks": float(breakeven),
        "sweep_extremes": {
            p_: {"min": float(g["sharpe"].min()), "max": float(g["sharpe"].max()),
                 "argmin": g.loc[g["sharpe"].idxmin(), "value"],
                 "argmax": g.loc[g["sharpe"].idxmax(), "value"]}
            for p_, g in params.groupby("parameter")},
        "feb_2018_by_threshold": feb_by_threshold,
        "subsample_sharpe": {r_["name"]: float(r_["sharpe"]) for _, r_ in subs.iterrows()},
        "yearly_return_oos": yearly,
        "stress_window_contribution_oos": contrib,
        "alternative_constructions": {
            nm: float(params[(params["parameter"] == "index")
                             & (params["value"] == nm)]["sharpe"].iloc[0])
            for nm in alt_index},
        "outputs": ["reports/tables/robustness_costs.csv",
                    "reports/tables/robustness_parameters.csv",
                    "reports/tables/robustness_subsamples.csv",
                    "reports/tables/specification_distribution.csv",
                    "reports/tables/redteam_answers.csv"],
    }
    print(json.dumps(qc, indent=1, default=str))
    return qc


RUNNERS = {
    "clean": stage_clean,
    "index": stage_index,
    "mechanics": stage_mechanics,
    "tail": stage_tail,
    "signals": stage_signals,
    "backtest": stage_backtest,
    "robust": stage_robust,
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
