"""Tests for the VIX futures index reconstruction.

The panel used here is synthetic, built on the real settlement calendar, so the
correct index return is known analytically. The most important test is
``test_no_spurious_return_when_contracts_roll``: it builds a panel in which every
individual contract's price is constant through time but the curve is steeply
upward sloping, so a naive "front-month percentage change" reconstruction books a
large fake loss on every roll date while the correct construction returns exactly
zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.index.calendar import build_roll_calendar, trading_days, vix_settlement_dates
from svcarry.index.reconstruct import (
    build_curve,
    carry_measures,
    constant_maturity_curve,
    reconstruct_index,
    roll_weights,
)


def _panel(start="2015-01-02", end="2016-12-30", price_fn=None):
    """Synthetic VX panel: every monthly contract priced by ``price_fn(date, expiry)``."""
    days = trading_days(start, end)
    settles = vix_settlement_dates(start, pd.Timestamp(end) + pd.DateOffset(years=1))
    if price_fn is None:
        price_fn = lambda d, e: 15.0
    rows = []
    for d in days:
        nxt = [s for s in settles if s >= d][:6]
        for e in nxt:
            rows.append(
                dict(date=d, expiry=e, settle=float(price_fn(d, e)),
                     open_interest=5000, volume=1000,
                     days_to_expiry=int((e - d).days))
            )
    return pd.DataFrame(rows)


def test_flat_curve_gives_zero_return():
    p = _panel()
    idx = reconstruct_index(p)
    r = idx["ret"].dropna()
    assert len(r) > 400
    assert np.abs(r).max() < 1e-12, r.abs().max()


def test_no_spurious_return_when_contracts_roll():
    """Steep contango, each contract's own price constant -> index return is zero.

    A reconstruction that differences the *front-month price series* instead of the
    *held contracts* would print a large negative return on every settlement date.
    """
    # price depends only on the expiry, not on the trade date: a fixed term structure
    p = _panel(price_fn=lambda d, e: 12.0 + 0.9 * ((e.year - 2015) * 12 + e.month))
    idx = reconstruct_index(p)
    r = idx["ret"].dropna()
    assert np.abs(r).max() < 1e-12, r.abs().max()

    # demonstrate that the naive alternative really would be wrong
    naive = idx["f1"].pct_change().dropna()
    assert naive.abs().max() > 0.02, "synthetic curve is not steep enough to be a test"


def test_parallel_price_move_passes_through_exactly():
    """If both held contracts rise x%, the index must return exactly x%."""
    days = list(trading_days("2016-01-04", "2016-03-31"))
    bump = {d: 1.0 + 0.003 * i for i, d in enumerate(days)}
    p = _panel("2016-01-04", "2016-03-31",
               price_fn=lambda d, e: 15.0 * bump[d])
    idx = reconstruct_index(p)
    r = idx["ret"].dropna()
    expect = pd.Series(
        [bump[days[i]] / bump[days[i - 1]] - 1.0 for i in range(1, len(days))],
        index=days[1:],
    ).reindex(r.index)
    assert np.nanmax(np.abs(r - expect)) < 1e-12


def test_roll_weights_sum_to_one_and_are_bounded():
    cal = build_roll_calendar("2012-01-03", "2020-12-31")
    for conv in ("sp_dji", "shifted"):
        w = roll_weights(cal, conv)
        assert np.allclose(w["w1"] + w["w2"], 1.0)
        assert w["w1"].between(0.0, 1.0).all()


def test_unknown_convention_raises():
    cal = build_roll_calendar("2016-01-04", "2016-06-30")
    with pytest.raises(ValueError):
        roll_weights(cal, "whatever")


def test_held_contracts_change_only_on_settlement_dates():
    p = _panel("2016-01-04", "2016-12-30")
    idx = reconstruct_index(p)
    changed = idx["exp1"] != idx["exp1"].shift(1)
    change_dates = set(idx.index[changed][1:])
    settles = set(vix_settlement_dates("2016-01-04", "2016-12-30"))
    # every change of front contract must be a settlement date or the day after one
    for d in change_dates:
        prev = idx.index[idx.index.get_loc(d) - 1]
        assert (d in settles) or (prev in settles), d


def test_missing_settlement_prices_produce_nan_not_zero():
    """A contract with no settlement price must give NaN, never a silent 0%."""
    p = _panel("2016-01-04", "2016-06-30")
    victim = pd.Timestamp("2016-03-15")
    p.loc[p["date"] == victim, "settle"] = np.nan
    idx = reconstruct_index(p)
    assert np.isnan(idx.loc[victim, "ret"])            # cannot price today
    nxt = idx.index[idx.index.get_loc(victim) + 1]
    assert np.isnan(idx.loc[nxt, "ret"])               # nor the move out of it
    assert idx.attrs["n_days_missing_price"] >= 1
    # the level series must not invent a return over the gap
    assert idx.loc[victim, "level_er"] == pytest.approx(
        idx.loc[idx.index[idx.index.get_loc(victim) - 1], "level_er"]
    )


def test_constant_maturity_interpolation_is_exact_on_a_linear_curve():
    p = _panel("2016-01-04", "2016-06-30",
               price_fn=lambda d, e: 14.0 + 0.02 * (e - d).days)
    cm = constant_maturity_curve(p, maturities=(30, 60, 90))
    d = cm.index[20]
    assert cm.loc[d, "cm30"] == pytest.approx(14.0 + 0.02 * 30, abs=1e-9)
    assert cm.loc[d, "cm90"] == pytest.approx(14.0 + 0.02 * 90, abs=1e-9)


def test_constant_maturity_does_not_extrapolate():
    p = _panel("2016-01-04", "2016-03-31")
    cm = constant_maturity_curve(p, maturities=(5, 30, 400))
    assert cm["cm400"].isna().all()       # beyond the longest listed contract
    assert cm["cm30"].notna().mean() > 0.9


def test_carry_is_negative_in_contango():
    p = _panel("2016-01-04", "2016-12-30",
               price_fn=lambda d, e: 14.0 + 0.03 * (e - d).days)
    idx = reconstruct_index(p)
    cm = constant_maturity_curve(p, maturities=(30, 90))
    car = carry_measures(idx, cm=cm)
    # upward-sloping curve -> F2 > F1 -> positive log slope; the short position earns it
    assert (car["carry_log"].dropna() > 0).mean() > 0.99
    assert (car["slope_cm"].dropna() < 1.0).mean() > 0.99


def test_total_return_adds_the_accrual():
    p = _panel("2016-01-04", "2016-06-30")
    days = trading_days("2016-01-04", "2016-06-30")
    accr = pd.Series(0.0001, index=days)
    idx = reconstruct_index(p, tbill_accrual=accr)
    d = idx.index[10]
    assert idx.loc[d, "ret_tr"] == pytest.approx(idx.loc[d, "ret"] + 0.0001, abs=1e-15)
    assert idx["level_tr"].iloc[-1] > idx["level_er"].iloc[-1]


def test_build_curve_pivot_shape():
    p = _panel("2016-01-04", "2016-03-31")
    c = build_curve(p)
    assert c.index.is_monotonic_increasing
    assert c.columns.is_monotonic_increasing
    assert c.notna().sum(axis=1).min() >= 2
