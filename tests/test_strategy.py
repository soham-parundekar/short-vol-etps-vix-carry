"""Tests for signals, sizing and the backtest engine.

The two that matter most:

``test_engine_lag_prevents_the_leak`` builds weights that *use the same day's return*
and shows that the engine's one-day lag destroys the resulting (enormous) Sharpe
ratio. That is both a correctness test and the calibration for the deliberately
leaky variant reported in the robustness section.

``test_no_lookahead_in_strategy_returns`` perturbs the index after a cut-off date and
requires every earlier strategy return to be bit-identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.etp.mechanics import etp_nav
from svcarry.strategy.backtest import buy_and_hold_etp, run_backtest
from svcarry.strategy.signals import combine_signals, contango_signal, vrp, vrp_signal
from svcarry.strategy.sizing import (
    ewma_vol,
    realised_vol,
    stress_loss,
    stress_move,
    target_weight,
)


def _idx(n, start="2010-01-04"):
    return pd.bdate_range(start, periods=n)


def _index_returns(n=1500, seed=0, mu=-0.002, sigma=0.04):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mu, sigma, n), index=_idx(n), name="ret")


# ------------------------------------------------------------------- signals
def test_contango_signal_thresholds_and_nan_propagation():
    s = pd.Series([0.85, 0.95, 1.00, 1.15, np.nan], index=_idx(5))
    sig = contango_signal(s, threshold=1.0)
    assert list(sig.iloc[:4]) == [1.0, 1.0, 0.0, 0.0]
    assert np.isnan(sig.iloc[4])


def test_vrp_units_and_sign():
    iv = pd.Series([20.0, 15.0], index=_idx(2))            # VIX points
    rv = pd.Series([0.0001, 0.0009], index=_idx(2))        # daily variance
    v = vrp(iv, rv)
    assert v.iloc[0] == pytest.approx(0.20 ** 2 - 0.0001 * 252)
    assert v.iloc[0] > 0                                    # premium being paid
    assert v.iloc[1] < 0                                    # realised exceeds implied
    assert list(vrp_signal(v)) == [1.0, 0.0]


def test_combine_signals_rules_and_missing():
    a = pd.Series([1.0, 1.0, 0.0, np.nan], index=_idx(4))
    b = pd.Series([1.0, 0.0, 0.0, 1.0], index=_idx(4))
    assert list(combine_signals({"a": a, "b": b}, "all").iloc[:3]) == [1.0, 0.0, 0.0]
    assert list(combine_signals({"a": a, "b": b}, "any").iloc[:3]) == [1.0, 1.0, 0.0]
    assert combine_signals({"a": a, "b": b}, "mean").iloc[1] == pytest.approx(0.5)
    assert np.isnan(combine_signals({"a": a, "b": b}, "all").iloc[3])
    with pytest.raises(ValueError):
        combine_signals({"a": a}, "k")


# -------------------------------------------------------------------- sizing
def test_realised_and_ewma_vol_are_backward_looking():
    r = _index_returns(400, seed=1)
    rv = realised_vol(r, window=21)
    d = rv.index[100]
    manual = r.loc[:d].iloc[-21:].std(ddof=1) * np.sqrt(252)
    assert rv.loc[d] == pytest.approx(manual, rel=1e-12)
    assert ewma_vol(r).iloc[-1] > 0


def test_stress_move_floors_at_the_historical_event():
    q = pd.Series([0.30, 0.50, 1.40], index=_idx(3))
    sm = stress_move(q, historical_floor=0.96)
    assert list(sm) == [0.96, 0.96, 1.40]
    assert stress_move(None, 0.96) == 0.96


def test_stress_loss_is_linear_in_size():
    assert float(stress_loss(0.5, 0.96)) == pytest.approx(0.48)
    assert float(stress_loss(0.25, 1.60)) == pytest.approx(0.40)


def test_stress_budget_binds_exactly_when_volatility_targeting_would_be_largest():
    """The point of the whole sizing section, as a test."""
    vol = pd.Series([0.10, 0.30, 0.80], index=_idx(3))      # calm -> stressed
    tw = target_weight(vol, vol_target=0.15, stress=0.96,
                       max_stress_loss=0.20, max_weight=1.0)
    # crash budget allows 0.20 / 0.96 = 0.208 regardless of how quiet it is
    assert tw["w_stress_budget"].iloc[0] == pytest.approx(0.20833333, rel=1e-6)
    assert tw["weight"].iloc[0] == pytest.approx(0.20833333, rel=1e-6)
    assert tw["binding"].iloc[0] == "stress_budget"
    # in the calm state, pure vol targeting would have wanted 1.5x -> capped
    assert tw["w_vol_target"].iloc[0] == pytest.approx(1.5)
    # once volatility is high the vol target is the binding constraint
    assert tw["binding"].iloc[2] == "vol_target"


def test_signal_off_produces_zero_weight():
    vol = pd.Series([0.30] * 4, index=_idx(4))
    sig = pd.Series([1.0, 0.0, 1.0, np.nan], index=_idx(4))
    tw = target_weight(vol, vol_target=0.15, stress=0.96, signal=sig)
    assert tw["weight"].iloc[1] == 0.0
    assert tw["binding"].iloc[1] == "signal_off"
    assert np.isnan(tw["weight"].iloc[3]) or tw["weight"].iloc[3] == 0.0


# ------------------------------------------------------------------ backtest
def test_backtest_accounting_identity():
    r = _index_returns(300, seed=2)
    w = pd.Series(0.5, index=r.index)
    a = pd.Series(0.00002, index=r.index)
    p = pd.Series(15.0, index=r.index)
    bt = run_backtest(r, w, price_level=p, accrual=a, signal_lag=1, cost_ticks=1.0,
                      drift_turnover=False)
    t = r.index[50]
    expected = 0.00002 - 0.5 * r.loc[t]        # no target change after the first day
    assert bt.returns.loc[t] == pytest.approx(expected, rel=1e-12)
    assert bt.costs.loc[t] == pytest.approx(0.0, abs=1e-15)


def test_constant_weight_still_trades_the_drift_back_to_target():
    """A short at 0.5 that loses 10% on the index is 0.5*1.1/0.95 = 0.579 of equity
    the next morning; holding 0.5 means buying back 0.079."""
    idx = _idx(4)
    r = pd.Series([0.0, 0.10, 0.0, 0.0], index=idx)
    w = pd.Series(0.5, index=idx)
    bt = run_backtest(r, w, cost_bps=0.0, signal_lag=1)
    drifted = 0.5 * 1.10 / (1.0 - 0.5 * 0.10)
    assert bt.turnover.iloc[2] == pytest.approx(drifted - 0.5, rel=1e-12)
    assert bt.components["turnover_target"].iloc[2] == 0.0


def test_leaving_and_re_entering_through_a_gap_is_charged():
    idx = _idx(8)
    r = pd.Series(0.0, index=idx)
    w = pd.Series([0.4, 0.4, np.nan, np.nan, 0.4, 0.4, 0.4, 0.4], index=idx)
    bt = run_backtest(r, w, cost_bps=100.0, signal_lag=1)
    assert bt.costs.iloc[3] == pytest.approx(0.4 * 0.01)      # exit into the gap
    assert bt.costs.iloc[5] == pytest.approx(0.4 * 0.01)      # re-entry after it
    assert bt.settings["n_days_weight_missing_after_start"] == 2


def test_roll_is_charged_on_both_legs():
    idx = _idx(5)
    r = pd.Series(0.0, index=idx)
    w = pd.Series(0.5, index=idx)
    roll = pd.Series([0.0, 0.05, 0.05, 0.05, 0.05], index=idx)
    bt = run_backtest(r, w, cost_bps=100.0, signal_lag=1, roll_fraction=roll)
    assert bt.components["cost_roll"].iloc[3] == pytest.approx(2 * 0.5 * 0.05 * 0.01)


def test_a_position_on_a_day_with_no_index_return_raises():
    idx = _idx(6)
    r = pd.Series([0.01, 0.01, np.nan, 0.01, 0.01, 0.01], index=idx)
    with pytest.raises(ValueError, match="no index return"):
        run_backtest(r, pd.Series(0.3, index=idx), cost_bps=0.0, signal_lag=1)
    flat = pd.Series([0.3, np.nan, 0.3, 0.3, 0.3, 0.3], index=idx)
    run_backtest(r, flat, cost_bps=0.0, signal_lag=1)          # flat that day: fine


def test_backtest_charges_costs_on_turnover_only():
    r = _index_returns(10, seed=3)
    w = pd.Series([0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=r.index)
    p = pd.Series(20.0, index=r.index)
    bt = run_backtest(r, w, price_level=p, signal_lag=1, cost_ticks=2.0, tick_size=0.05,
                      drift_turnover=False)
    k = 2.0 * 0.05 / 20.0                        # 50 bp per unit turnover
    charged = bt.costs[bt.costs > 0]
    assert len(charged) == 2                     # one entry, one exit
    assert charged.iloc[0] == pytest.approx(k, rel=1e-12)


def test_negative_signal_lag_is_rejected():
    r = _index_returns(50)
    with pytest.raises(ValueError):
        run_backtest(r, pd.Series(1.0, index=r.index), cost_bps=0, signal_lag=-1)


def test_engine_lag_prevents_the_leak():
    """Weights built from the same day's return must not pay off once lagged."""
    r = _index_returns(3000, seed=4, mu=0.0)
    foresight = (r < 0).astype(float)            # short only on days the index falls
    honest = run_backtest(r, foresight, cost_bps=0.0, signal_lag=1)
    leaky = run_backtest(r, foresight, cost_bps=0.0, signal_lag=0)
    sr = lambda s: s.mean() / s.std(ddof=1) * np.sqrt(252)
    # Shorting only on down days pays |r| half the time and nothing otherwise, so the
    # leaked Sharpe is about 0.4 / 0.583 per day ~ 11 annualised. Anything in that
    # region is an impossible ratio and a clear signature of same-day information.
    assert sr(leaky.returns) > 8.0
    assert abs(sr(honest.returns)) < 1.0         # correctly lagged, it is worth nothing


def test_no_lookahead_in_strategy_returns():
    r = _index_returns(2000, seed=5)
    cut = r.index[1200]
    vol = realised_vol(r, 21)
    w = target_weight(vol, vol_target=0.15, stress=0.96)["weight"]
    base = run_backtest(r, w, cost_bps=5.0, signal_lag=1)

    r2 = r.copy()
    rng = np.random.default_rng(0)
    m = r2.index > cut
    r2[m] = r2[m] + rng.normal(0, 0.5, int(m.sum()))
    vol2 = realised_vol(r2, 21)
    w2 = target_weight(vol2, vol_target=0.15, stress=0.96)["weight"]
    alt = run_backtest(r2, w2, cost_bps=5.0, signal_lag=1)

    common = base.returns.index[base.returns.index <= cut]
    assert len(common) > 500
    assert np.array_equal(
        base.returns.reindex(common).to_numpy(),
        alt.returns.reindex(common).to_numpy(),
    )


def test_days_with_no_weight_earn_the_collateral_only():
    r = _index_returns(50, seed=6)
    w = pd.Series(np.nan, index=r.index)
    a = pd.Series(0.0001, index=r.index)
    bt = run_backtest(r, w, cost_bps=0.0, accrual=a, signal_lag=1)
    assert bt.returns.dropna().eq(0.0001).all()
    assert bt.settings["n_days"] == 50
    assert bt.settings["n_days_invested"] == 0


def test_buy_and_hold_benchmark_matches_the_nav_recursion():
    r = _index_returns(500, seed=7)
    bh = buy_and_hold_etp(r, leverage=-1.0, fee=0.0135)
    nav = etp_nav(r, leverage=-1.0, fee=0.0135, initial=1.0)
    assert bh.equity.iloc[-1] == pytest.approx(nav["nav"].iloc[-1], rel=1e-12)


def test_slice_rebases_equity():
    r = _index_returns(500, seed=8)
    bt = run_backtest(r, pd.Series(0.3, index=r.index), cost_bps=0.0, signal_lag=1)
    sub = bt.slice(r.index[100], r.index[300])
    assert len(sub.returns) == 201
    assert sub.equity.iloc[0] == pytest.approx(1.0 + sub.returns.iloc[0], rel=1e-12)
