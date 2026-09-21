"""The signal panel: look-ahead audit, units, and the missing-data rules (Phase 10).

The first test is the audit's core, run permanently: perturb every input after a
cut-off date and require every panel value dated on or before it to be bit-identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.strategy.signals import (
    build_signal_panel, signal_statistics, spot_anchored_front, vrp,
)


def _inputs(n=1600, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    x[:22] = np.log(1e-4)
    for t in range(22, n):
        x[t] = -0.35 + 0.35 * x[t - 1] + 0.35 * x[t - 5:t].mean() \
            + 0.26 * x[t - 22:t].mean() + 0.3 * rng.normal()
    idx = pd.bdate_range("2004-01-05", periods=n)
    rv = pd.Series(np.exp(x), index=idx)
    vol = 100 * np.sqrt(252 * rv.rolling(10, min_periods=1).mean())
    vix = vol * rng.uniform(0.9, 1.4, n)
    curve = pd.DataFrame({
        "vix": vix, "vix3m": vix * rng.uniform(0.85, 1.15, n),
        "cm30": vix * rng.uniform(0.9, 1.1, n), "cm90": vix * rng.uniform(0.95, 1.2, n),
        "f1": vix * 1.05, "days_to_exp1": rng.integers(3, 36, n).astype(float),
    }, index=idx)
    curve.loc[curve["days_to_exp1"] > 30, "cm30"] = np.nan     # the real curve's gap
    return rv, curve


KW = dict(horizon=21, train_min=400, refit_every=21)


def test_no_panel_value_depends_on_later_inputs():
    rv, curve = _inputs()
    base, _ = build_signal_panel(rv, curve, **KW)
    cut = rv.index[1200]
    rng = np.random.default_rng(1)
    rv2, curve2 = rv.copy(), curve.copy()
    later = rv.index > cut
    rv2[later] *= rng.uniform(3.0, 30.0, later.sum())
    for c in curve2.columns:
        curve2.loc[later, c] = curve2.loc[later, c] * rng.uniform(0.5, 2.0, later.sum())
    alt, _ = build_signal_panel(rv2, curve2, **KW)
    pd.testing.assert_frame_equal(base.loc[:cut], alt.loc[:cut], check_exact=True)
    assert not base.loc[cut:].iloc[1:].equals(alt.loc[cut:].iloc[1:]), \
        "the perturbation must actually change something after the cut-off"


def test_panel_holds_no_realised_outcome():
    rv, curve = _inputs(900)
    panel, har = build_signal_panel(rv, curve, **KW)
    assert not any("realised" in c or "future" in c for c in panel.columns)
    assert har.realised.notna().any()


def test_vrp_units_by_hand():
    """VIX 20 -> 0.04 annualised variance; a daily forecast of 1e-4 -> 0.0252."""
    v = vrp(pd.Series([20.0]), pd.Series([1e-4]))
    assert v.iloc[0] == pytest.approx(0.04 - 0.0252, abs=1e-15)


def test_panel_vrp_is_vix_squared_minus_annualised_forecast():
    rv, curve = _inputs(900)
    p, _ = build_signal_panel(rv, curve, **KW)
    ok = p["vrp"].notna()
    assert np.allclose(p.loc[ok, "vrp"],
                       (p.loc[ok, "vix"] / 100) ** 2 - 252 * p.loc[ok, "har_forecast"],
                       rtol=0, atol=1e-15)


def test_spot_anchor_fills_only_the_gap_and_interpolates_from_zero_maturity():
    idx = pd.bdate_range("2020-01-01", periods=3)
    cm = pd.Series([20.0, np.nan, np.nan], index=idx)
    spot = pd.Series([18.0, 18.0, 18.0], index=idx)
    f1 = pd.Series([21.0, 21.0, 21.0], index=idx)
    tau = pd.Series([25.0, 35.0, 28.0], index=idx)
    out, flag = spot_anchored_front(cm, spot, f1, tau)
    assert out.iloc[0] == 20.0 and not flag.iloc[0]
    assert out.iloc[1] == pytest.approx(18.0 + 3.0 * 30 / 35) and flag.iloc[1]
    assert np.isnan(out.iloc[2]) and not flag.iloc[2], \
        "a gap with a contract inside 30 days is a data problem, not something to fill"


def test_missing_inputs_give_no_position_rather_than_a_default():
    rv, curve = _inputs(900)
    rv = rv.drop(rv.index[700])                  # equity market shut, futures open
    p, _ = build_signal_panel(rv, curve, **KW)
    d = curve.index[700]
    assert np.isnan(p.loc[d, "vrp"]) and np.isnan(p.loc[d, "signal"])
    assert p.loc[d, "binding"] == "undefined"


def test_binding_categories_partition_the_off_days():
    rv, curve = _inputs(1200)
    p, _ = build_signal_panel(rv, curve, **KW)
    d = p.dropna(subset=["signal"])
    assert ((d["binding"] == "none") == (d["signal"] == 1)).all()
    st = signal_statistics(p, start=d.index[0]).set_index("statistic")["fraction"]
    off = sum(st[f"off, binding constraint: {b}"] for b in ("contango", "vrp", "both"))
    assert off + st["combined on (invested)"] == pytest.approx(1.0)
