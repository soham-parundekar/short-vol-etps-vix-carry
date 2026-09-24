"""Timing alignment and the cost approximation, pinned by tests.

Everything here exists because the final audit found something that nothing checked.

*A-02 / A-05.* The look-ahead audit table used to end in
``timing["use_precedes_availability"] = False`` — a literal the project then cited as
mechanical evidence. It concealed a fifteen-minute overlap on 1,482 trading days. The
tests below require the computed table to *fail* when the extra lag is removed, so the
check can no longer pass by construction.

*The convention itself.* Three documents stated the signal-to-return lag three different
ways and no test pinned any of them. ``test_signal_date_earns_the_next_days_return``
does, end to end, on data whose answer is known by construction.

*A-03.* The engine's drift-turnover denominator is the gross return, not the net return
its docstring used to claim. The approximation is fine; the absence of a bound on it was
not. ``test_drift_denominator_approximation_is_bounded`` builds the exact sequential
series and states the tolerance.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest

from svcarry.strategy.backtest import run_backtest
from svcarry.strategy.signals import build_signal_panel
from svcarry.timing import (
    SETTLEMENT_CHANGE,
    VIX_CASH_CLOSE_ET,
    execution_strike_et,
    extra_lag_required,
    timing_audit_table,
    verify_weight_alignment,
)
import svcarry.timing as T


def _dates(n=4000, start="2008-01-02"):
    return pd.bdate_range(start, periods=n)


# --------------------------------------------------------------------- the clock rule
def test_execution_strike_moves_on_the_settlement_change_date():
    d = pd.DatetimeIndex(["2020-10-22", "2020-10-23", "2020-10-26", "2020-10-27"])
    got = execution_strike_et(d)
    assert list(got.values[:2]) == [16 * 60 + 15, 16 * 60 + 15]
    assert list(got.values[2:]) == [16 * 60, 16 * 60]


def test_a_1615_input_needs_an_extra_lag_only_from_the_change_date():
    d = _dates()
    need = extra_lag_required(VIX_CASH_CLOSE_ET, d, signal_lag=1)
    assert need.loc[d < SETTLEMENT_CHANGE].max() == 0
    assert need.loc[d >= SETTLEMENT_CHANGE].min() == 1
    assert need[need > 0].index[0] >= SETTLEMENT_CHANGE


def test_a_1600_input_never_needs_an_extra_lag():
    need = extra_lag_required(time(16, 0), _dates(), signal_lag=1)
    assert int(need.sum()) == 0


@pytest.mark.parametrize("lag", [2, 3])
def test_a_longer_lag_makes_the_time_of_day_irrelevant(lag):
    assert int(extra_lag_required(VIX_CASH_CLOSE_ET, _dates(), signal_lag=lag).sum()) == 0


def test_zero_lag_is_a_whole_day_of_look_ahead_for_every_input():
    need = extra_lag_required(time(16, 0), _dates(), signal_lag=0)
    assert int(need.min()) == 1


# ------------------------------------------------- the table must be able to say True
def test_timing_table_is_clean_as_configured():
    t = timing_audit_table(_dates(), signal_lag=1, horizon=21,
                           design_end="2015-12-31", oos_start="2016-01-01")
    assert len(t) >= 18
    assert not t["use_precedes_availability"].any()
    # and it is not clean by construction: the VIX rows do carry a real requirement
    assert t.loc[t["input"] == "VIX close", "dates_needing_extra_lag"].iloc[0] > 0
    assert t.loc[t["input"] == "VIX close", "extra_lag_applied"].iloc[0] == 1


def test_timing_table_fails_when_the_extra_lag_is_removed():
    """Mutation check: this is the defect the table used to be unable to report."""
    saved = [s["extra_lag"] for s in T._REGISTRY]
    try:
        for s in T._REGISTRY:
            s["extra_lag"] = 0
        t = timing_audit_table(_dates(), signal_lag=1, horizon=21,
                               design_end="2015-12-31", oos_start="2016-01-01")
        bad = t[t["use_precedes_availability"]]
        assert len(bad) >= 3, "a 16:15 input used same-day after the change must be flagged"
        assert set(bad["input"]) >= {"VIX close", "VRP (VIX close less HAR forecast)"}
        expected = int((_dates() >= SETTLEMENT_CHANGE).sum())
        assert expected > 0
        assert (bad["n_dates_use_precedes_availability"] == expected).all()
    finally:
        for s, v in zip(T._REGISTRY, saved):
            s["extra_lag"] = v


# ------------------------------------------------------------ the panel applies the lag
def _synthetic_panel_inputs(n=900):
    d = pd.bdate_range("2018-01-01", periods=n)
    rng = np.random.default_rng(11)
    rv = pd.Series(np.abs(rng.normal(0.0001, 0.00004, n)), index=d)
    curve = pd.DataFrame(
        {
            "vix": 16 + rng.normal(0, 2.5, n),
            "vix3m": 18 + rng.normal(0, 2.0, n),
            "cm30": 17 + rng.normal(0, 2.0, n),
            "cm90": 19 + rng.normal(0, 1.5, n),
            "f1": 17 + rng.normal(0, 2.0, n),
            "days_to_exp1": rng.integers(3, 33, n),
        },
        index=d,
    )
    return rv, curve


def test_panel_lags_vix_inputs_only_on_and_after_the_change_date():
    rv, curve = _synthetic_panel_inputs()
    p, _ = build_signal_panel(rv, curve, train_min=200, vix_extra_lag_from=SETTLEMENT_CHANGE)
    before = p.index < SETTLEMENT_CHANGE
    after = p.index >= SETTLEMENT_CHANGE
    assert before.any() and after.any(), "the sample must straddle the change date"
    # Before the change the aligned series is the raw one, NaNs included (vrp is missing
    # through the HAR burn-in, so an == comparison would be false on those rows).
    pd.testing.assert_series_equal(
        p.loc[before, "vrp_aligned"], p.loc[before, "vrp"], check_names=False)
    # From the change it is the raw series shifted one trading day.
    pd.testing.assert_series_equal(
        p.loc[after, "vrp_aligned"], p["vrp"].shift(1).loc[after], check_names=False)
    # and the shift is real: at least one row actually differs
    assert (p.loc[after, "vrp_aligned"] - p.loc[after, "vrp"]).abs().max() > 0
    assert not p.loc[before, "vix_input_lagged"].any()
    assert p.loc[after, "vix_input_lagged"].all()


def test_panel_without_the_flag_reproduces_the_pre_audit_behaviour():
    rv, curve = _synthetic_panel_inputs()
    p, _ = build_signal_panel(rv, curve, train_min=200, vix_extra_lag_from=None)
    assert (p["vrp_aligned"].fillna(-9) == p["vrp"].fillna(-9)).all()
    assert not p["vix_input_lagged"].any()


# ------------------------------------------------------- the convention, end to end
def test_signal_date_earns_the_next_days_return():
    """A signal that switches on at date d must earn the return of d+1, never of d.

    Constructed so the two are distinguishable: the index return is zero everywhere
    except on the switch date and the day after, with different values.
    """
    d = pd.bdate_range("2020-01-01", periods=12)
    r = pd.Series(0.0, index=d)
    r.iloc[5] = 0.10      # the move on the switch date itself
    r.iloc[6] = -0.20     # the move on the following day
    w_raw = pd.Series(0.0, index=d)
    w_raw.iloc[5:] = 0.5  # weight first computable at index 5
    res = run_backtest(r, w_raw, price_level=pd.Series(20.0, index=d),
                       accrual=pd.Series(0.0, index=d), signal_lag=1, cost_ticks=0.0)
    assert res.weight.iloc[5] == 0.0, "a weight computed at d cannot be held during d"
    assert res.weight.iloc[6] == 0.5
    # short of 0.5 against a -20% move on day 6 is +10%
    assert res.returns.iloc[5] == pytest.approx(0.0)
    assert res.returns.iloc[6] == pytest.approx(0.10)


def test_verify_weight_alignment_detects_a_double_shift():
    d = pd.bdate_range("2020-01-01", periods=50)
    raw = pd.Series(np.linspace(0.1, 0.6, 50), index=d)
    held = raw.shift(1).fillna(0.0)
    good = verify_weight_alignment(raw, held, signal_lag=1)
    assert good["aligned"] and good["max_abs_deviation"] < 1e-15
    bad = verify_weight_alignment(raw, raw.shift(2).fillna(0.0), signal_lag=1)
    assert not bad["aligned"]
    assert bad["max_abs_deviation"] > 1e-6


# ------------------------------------------------------------------ A-03: cost bound
def test_drift_denominator_approximation_is_bounded():
    """The engine divides the drift by the gross return; exact would be the net return.

    Exact is circular within a day, so the engine approximates. This states the price of
    that approximation instead of leaving it unmeasured: it must stay far below anything
    that could move a reported figure.
    """
    n = 2500
    d = pd.bdate_range("2010-01-04", periods=n)
    rng = np.random.default_rng(7)
    r = pd.Series(rng.normal(0.0, 0.05, n), index=d)
    w_raw = pd.Series(np.clip(0.3 + rng.normal(0, 0.1, n), 0.0, 1.0), index=d)
    price = pd.Series(np.clip(18 + rng.normal(0, 3, n), 8, None), index=d)
    acc = pd.Series(0.00008, index=d)

    res = run_backtest(r, w_raw, price_level=price, accrual=acc, signal_lag=1,
                       cost_ticks=1.0, tick_size=0.05)

    # exact sequential reference: denominator is the previous NET return
    w = w_raw.shift(1).fillna(0.0).values
    rv_ = r.fillna(0.0).values
    gross = res.gross.values
    k = (1.0 * 0.05) / price.values
    to_exact = np.zeros(n)
    net_exact = np.zeros(n)
    prev_net = 0.0
    for i in range(n):
        drift = 0.0 if i == 0 else w[i - 1] * (1 + rv_[i - 1]) / (1 + prev_net)
        to_exact[i] = abs(w[i] - drift)
        net_exact[i] = gross[i] - to_exact[i] * k[i]
        prev_net = net_exact[i]

    to_coded = (res.components["turnover_rebalance"]).values
    assert np.abs(to_coded - to_exact).max() < 5e-3
    assert np.abs(res.returns.values - net_exact).max() < 1e-4
    ann_coded = to_coded.sum() * 252 / n
    ann_exact = to_exact.sum() * 252 / n
    assert abs(ann_coded - ann_exact) < 1e-2 * max(ann_exact, 1.0)
