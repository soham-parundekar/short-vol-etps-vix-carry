"""Tests for the leveraged/inverse ETP mechanics.

Each quantity is checked against an independent construction: the NAV recursion
against a hand-written loop, the rebalancing trade against the definition of
"restore target exposure", and the decay identity against a Monte Carlo of an
exactly daily-rebalanced product.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.etp.mechanics import (
    aggregate_rebalancing_flow,
    contracts_equivalent,
    decay_regression,
    etp_nav,
    rebalancing_trade,
    theoretical_decay,
    wipeout_threshold,
)


def _idx(n, start="2010-01-04"):
    return pd.bdate_range(start, periods=n)


def test_wipeout_thresholds_match_the_proposal():
    assert wipeout_threshold(-1.0, 0.80) == pytest.approx(0.80)
    assert wipeout_threshold(-0.5, 0.80) == pytest.approx(1.60)
    assert wipeout_threshold(2.0, 0.80) == pytest.approx(-0.40)
    assert wipeout_threshold(1.5, 0.80) == pytest.approx(-0.5333333, rel=1e-6)


def test_wipeout_threshold_is_consistent_with_the_nav_recursion():
    for L in (-1.0, -0.5, 2.0, 1.5):
        r = wipeout_threshold(L, 0.80)
        assert 1.0 + L * r == pytest.approx(0.20)


def test_rebalancing_trade_direction_and_size():
    A, r = 1_000_000.0, 0.10
    assert rebalancing_trade(-1.0, A, r) == pytest.approx(2.0 * A * r)
    assert rebalancing_trade(2.0, A, r) == pytest.approx(2.0 * A * r)
    assert rebalancing_trade(-0.5, A, r) == pytest.approx(0.75 * A * r)
    assert rebalancing_trade(1.0, A, r) == pytest.approx(0.0)
    # de-levering from -1x to -0.5x cuts the trade by 62.5% for the same shock
    assert rebalancing_trade(-0.5, A, r) / rebalancing_trade(-1.0, A, r) == pytest.approx(0.375)


def test_rebalancing_trade_from_first_principles():
    """dE must be exactly the trade that restores exposure = L * assets."""
    for L in (-1.0, -0.5, 2.0, 1.5, 3.0):
        A, r = 250.0, 0.037
        assets_after = A * (1.0 + L * r)
        exposure_drifted = L * A * (1.0 + r)
        need = L * assets_after - exposure_drifted
        assert rebalancing_trade(L, A, r) == pytest.approx(need, rel=1e-12)


def test_theoretical_decay_coefficients():
    assert theoretical_decay(1.0) == pytest.approx(0.0)
    assert theoretical_decay(0.0) == pytest.approx(0.0)
    assert theoretical_decay(-1.0) == pytest.approx(-1.0)
    assert theoretical_decay(2.0) == pytest.approx(-1.0)
    assert theoretical_decay(-0.5) == pytest.approx(-0.375)
    assert theoretical_decay(1.5) == pytest.approx(-0.375)


def test_etp_nav_matches_a_manual_loop():
    rng = np.random.default_rng(0)
    n = 300
    r = pd.Series(rng.normal(0, 0.03, n), index=_idx(n))
    a = pd.Series(0.00002, index=r.index)
    out = etp_nav(r, leverage=-1.0, fee=0.0135, accrual=a, initial=100.0)
    days = pd.Series(r.index, index=r.index).diff().dt.days.fillna(1).astype(float)
    v = 100.0
    for i in range(n):
        v = v * (1 + 0.00002 - 1.0 * r.iat[i]) - v * 0.0135 * days.iat[i] / 365
    assert out["nav"].iloc[-1] == pytest.approx(v, rel=1e-12)


def test_unlevered_product_tracks_the_index_exactly():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0, 0.02, 200), index=_idx(200))
    out = etp_nav(r, leverage=1.0, fee=0.0, accrual=None, initial=1.0)
    assert out["nav"].iloc[-1] == pytest.approx(float((1 + r).prod()), rel=1e-12)


def test_inverse_product_decays_at_the_predicted_rate():
    """Zero-drift index, -1x product: NAV should shrink at roughly exp(-sigma^2 T)."""
    rng = np.random.default_rng(2)
    n, sigma = 5000, 0.04
    logret = rng.normal(-0.5 * sigma ** 2, sigma, n)   # driftless in levels
    r = pd.Series(np.expm1(logret), index=_idx(n))
    out = etp_nav(r, leverage=-1.0, fee=0.0, initial=1.0)
    realised_var = float((logret ** 2).sum())
    predicted = np.exp(-1.0 * np.log1p(r).sum() - 1.0 * realised_var)
    assert np.log(out["nav"].iloc[-1]) == pytest.approx(np.log(predicted), abs=0.35)


def test_nav_floors_at_zero_and_stays_dead():
    r = pd.Series([0.0, 0.0, 0.60, 0.10, -0.20], index=_idx(5))
    out = etp_nav(r, leverage=-2.0, fee=0.0, initial=100.0)
    assert out["nav"].iloc[2] == 0.0
    assert not out["alive"].iloc[2:].any()
    assert (out["nav"].iloc[2:] == 0.0).all()


def test_decay_regression_recovers_the_identity():
    """Build an exactly daily-rebalanced product and recover -(L^2-L)/2."""
    rng = np.random.default_rng(3)
    n = 6000
    sigma = 0.05
    logret = rng.normal(0.0, sigma, n)
    idx_ret = pd.Series(np.expm1(logret), index=_idx(n))
    for L in (-1.0, -0.5, 2.0):
        prod = etp_nav(idx_ret, leverage=L, fee=0.0, initial=1.0)
        res = decay_regression(prod["ret"], idx_ret, leverage=L, horizon=21)
        assert res.slope == pytest.approx(theoretical_decay(L), abs=0.10), res.summary()
        assert abs(res.t_vs_theory) < 4.0, res.summary()
        assert abs(res.intercept_annual) < 0.05, res.summary()


def test_decay_regression_detects_a_fee():
    rng = np.random.default_rng(4)
    n = 6000
    idx_ret = pd.Series(np.expm1(rng.normal(0.0, 0.04, n)), index=_idx(n))
    prod = etp_nav(idx_ret, leverage=-1.0, fee=0.0135, initial=1.0)
    res = decay_regression(prod["ret"], idx_ret, leverage=-1.0, horizon=21)
    assert res.intercept_annual == pytest.approx(-0.0135, abs=0.006), res.summary()


def test_contracts_equivalent_units():
    # $20m of exposure at a futures price of 20 is 1,000 contracts at $1,000/point
    assert float(contracts_equivalent(20_000_000.0, 20.0)) == pytest.approx(1000.0)


def test_aggregate_flow_shapes_and_share_of_open_interest():
    idx = _idx(50)
    assets = pd.DataFrame({"XIV": 1.5e9, "SVXY": 1.0e9, "UVXY": 5e8}, index=idx)
    r = pd.Series(np.linspace(-0.05, 0.05, 50), index=idx)
    front = pd.Series(15.0, index=idx)
    oi = pd.Series(400_000.0, index=idx)
    flows = aggregate_rebalancing_flow(
        assets, {"XIV": -1.0, "SVXY": -1.0, "UVXY": 2.0}, r, front, oi
    )
    assert {"flow_XIV", "flow_SVXY", "flow_UVXY", "flow_total", "contracts",
            "share_of_oi"} <= set(flows.columns)
    # all three designs trade the same direction as the index move
    up = flows.loc[r > 0]
    assert (up["flow_total"] > 0).all()
    assert flows["share_of_oi"].abs().max() < 1.0


def test_time_varying_leverage_is_honoured():
    idx = _idx(10)
    assets = pd.DataFrame({"SVXY": 1e9}, index=idx)
    lev = pd.DataFrame({"SVXY": [-1.0] * 5 + [-0.5] * 5}, index=idx)
    r = pd.Series(0.10, index=idx)
    flows = aggregate_rebalancing_flow(assets, lev, r, pd.Series(15.0, index=idx))
    assert flows["flow_SVXY"].iloc[0] == pytest.approx(2.0 * 1e9 * 0.10)
    assert flows["flow_SVXY"].iloc[-1] == pytest.approx(0.75 * 1e9 * 0.10)
