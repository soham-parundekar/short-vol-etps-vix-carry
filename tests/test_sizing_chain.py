"""The sizing chain used by the Phase 11 backtest: timing, the real-time stress floor,
the roll, and the whole chain under the look-ahead perturbation test."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.econometrics.evt import fit_gpd
from svcarry.econometrics.tailrisk import (
    SplicedInnovations, conditional_move_quantile, filter_sigma, one_step_ahead_sigma,
)
from svcarry.strategy.backtest import run_backtest
from svcarry.strategy.sizing import roll_fraction, running_max_floor, strategy_weights

PARAMS = {"mu": -0.003, "omega": 1e-4, "alpha": 0.20, "gamma": -0.15, "beta": 0.80}


def _returns(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.standard_t(4, n) * 0.035 - 0.002,
                     index=pd.bdate_range("2008-01-03", periods=n))


def _innov():
    z = np.random.default_rng(1).standard_t(5, 20000) / np.sqrt(5 / 3)
    return SplicedInnovations("skewt", np.array([5.7, 0.2]), fit_gpd(z, q=0.95, tail="upper"))


def test_one_step_ahead_sigma_is_the_next_days_filtered_sigma():
    r = np.log1p(_returns(300))
    nxt = one_step_ahead_sigma(PARAMS, r)
    cur = filter_sigma(PARAMS, r)
    assert np.allclose(nxt.iloc[:-1].to_numpy(), cur.iloc[1:].to_numpy(), rtol=0, atol=1e-15)


def test_one_step_ahead_sigma_sees_todays_return_and_nothing_later():
    r = np.log1p(_returns(300))
    k = 150
    r2 = r.copy()
    r2.iloc[k] = 0.6
    a, b = one_step_ahead_sigma(PARAMS, r), one_step_ahead_sigma(PARAMS, r2)
    assert np.array_equal(a.iloc[:k].to_numpy(), b.iloc[:k].to_numpy())
    assert b.iloc[k] > 3 * a.iloc[k]


def test_move_quantile_is_the_simple_return_at_the_conditional_quantile():
    r = np.log1p(_returns(200))
    S = _innov()
    q = conditional_move_quantile(PARAMS, S, r, p=0.999)
    sig = one_step_ahead_sigma(PARAMS, r)
    z = S.ppf(np.array([0.999]))[0]
    assert np.allclose(q, np.expm1(PARAMS["mu"] + sig * z))
    assert (q > 0).all()


def test_running_floor_only_knows_the_past():
    r = pd.Series([0.01, 0.30, -0.1, 0.05, 0.96, 0.02],
                  index=pd.bdate_range("2018-01-29", periods=6))
    f = running_max_floor(r)
    assert f.tolist() == [0.01, 0.30, 0.30, 0.30, 0.96, 0.96]


def test_roll_fraction_moves_the_whole_basket_once_per_cycle():
    idx = pd.bdate_range("2008-01-10", periods=8)
    exp2 = pd.Series(["F", "F", "F", "F", "G", "G", "G", "G"], index=idx)
    w2 = pd.Series([0.50, 0.75, 1.00, 1.00, 0.25, 0.50, 0.75, 1.00], index=idx)
    rf = roll_fraction(w2, exp2)
    assert rf.iloc[1:].tolist() == [0.25, 0.25, 0.0, 0.25, 0.25, 0.25, 0.25]


def _chain(r, sig):
    lr = np.log1p(r)
    q = conditional_move_quantile(PARAMS, _innov(), lr)
    tw = strategy_weights(r, sig, q, running_max_floor(r), vol_target=0.15,
                          max_stress_loss=0.20)
    bt = run_backtest(r, tw["weight"], cost_bps=10.0, signal_lag=1,
                      roll_fraction=pd.Series(0.05, index=r.index))
    return tw, bt


def test_whole_chain_has_no_lookahead():
    r = _returns(1500, seed=3)
    sig = pd.Series((np.random.default_rng(4).random(1500) > 0.3).astype(float),
                    index=r.index)
    tw, bt = _chain(r, sig)
    T = r.index[1000]
    r2 = r.copy()
    later = r2.index >= T
    r2[later] = r2[later] + np.random.default_rng(5).normal(0, 0.3, later.sum()).clip(-0.5)
    r2.loc[T] = 1.5          # a record day: any input that peeks one day ahead sees it
    tw2, bt2 = _chain(r2, sig)
    # the weight applied to day T was set at the close of T-1
    assert np.array_equal(bt.weight.loc[:T].to_numpy(), bt2.weight.loc[:T].to_numpy())
    before = bt.returns.index < T
    assert np.array_equal(bt.returns[before].to_numpy(), bt2.returns[before].to_numpy())
    assert np.array_equal(tw.loc[tw.index < T].to_numpy(dtype=str),
                          tw2.loc[tw2.index < T].to_numpy(dtype=str))


def test_crash_budget_caps_the_loss_on_a_move_at_the_floor():
    """Whatever the volatility estimate, a position sized under a floor of f loses at
    most max_stress_loss if the index then rises by f."""
    r = _returns(400, seed=6) * 0.2            # a very calm history
    r.iloc[-1] = 0.0
    tw = strategy_weights(r, pd.Series(1.0, index=r.index), pd.Series(0.05, index=r.index),
                          floor=0.96, vol_target=0.15, max_stress_loss=0.20)
    w = tw["weight"].iloc[-1]
    assert w * 0.96 == pytest.approx(0.20, rel=1e-12)
    assert tw["binding"].iloc[-1] == "stress_budget"


def test_missing_stress_gives_missing_weight_not_a_vol_target_weight():
    r = _returns(100, seed=7)
    q = pd.Series(0.2, index=r.index)
    q.iloc[60] = np.nan
    tw = strategy_weights(r, pd.Series(1.0, index=r.index), q, floor=0.1)
    assert np.isnan(tw["weight"].iloc[60])
    assert tw["binding"].iloc[60] == "no_estimate"
