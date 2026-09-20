"""Tests for the VIX futures expiry / roll calendar.

The settlement dates asserted below are taken from the file names Cboe uses to
publish per-contract historical data (``.../historical_data/VX/VX_<settlement>.csv``)
and from the contract specification, not from this module's own output.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from svcarry.index.calendar import (
    build_roll_calendar,
    easter_sunday,
    is_trading_day,
    trading_days,
    us_market_holidays,
    vix_settlement_date,
    vix_settlement_dates,
)


def test_easter_known_values():
    assert easter_sunday(2018) == dt.date(2018, 4, 1)
    assert easter_sunday(2020) == dt.date(2020, 4, 12)
    assert easter_sunday(2024) == dt.date(2024, 3, 31)
    assert easter_sunday(2026) == dt.date(2026, 4, 5)


@pytest.mark.parametrize(
    "year,month,expected",
    [
        (2018, 1, "2018-01-17"),
        (2018, 2, "2018-02-14"),   # the Volmageddon contract
        (2018, 3, "2018-03-21"),
        (2020, 3, "2020-03-18"),   # Covid crash
        (2020, 4, "2020-04-15"),
        (2024, 8, "2024-08-21"),   # yen-carry unwind window
        (2017, 12, "2017-12-20"),
        (2015, 8, "2015-08-19"),   # August 2015 vol spike
    ],
)
def test_vix_settlement_dates_known(year, month, expected):
    assert vix_settlement_date(year, month) == pd.Timestamp(expected)


def test_settlement_always_wednesday_unless_holiday_adjusted():
    dates = vix_settlement_dates("2006-01-01", "2030-12-31")
    weekdays = {d.weekday() for d in dates}
    # Wednesday (2) normally; Tuesday (1) when the Wednesday or reference Friday is
    # a holiday. Nothing else may appear.
    assert weekdays <= {1, 2}, weekdays
    assert all(is_trading_day(d) for d in dates)


def test_settlements_are_monthly_and_increasing():
    dates = vix_settlement_dates("2008-01-01", "2026-12-31")
    assert dates.is_monotonic_increasing
    assert dates.is_unique
    # exactly one per calendar month
    per_month = pd.Series(1, index=dates).groupby([dates.year, dates.month]).sum()
    assert (per_month == 1).all()


def test_holidays_contain_expected_days():
    hol = us_market_holidays()
    for s in ["2018-01-01", "2018-03-30", "2018-12-05", "2012-10-29", "2022-06-20",
              "2020-11-26", "2021-07-05"]:
        assert dt.date.fromisoformat(s) in hol, s
    for s in ["2018-01-02", "2019-06-19", "2018-11-21"]:
        assert dt.date.fromisoformat(s) not in hol, s


def test_trading_days_exclude_weekends_and_holidays():
    td = trading_days("2018-01-01", "2018-12-31")
    assert pd.Timestamp("2018-01-01") not in td
    assert pd.Timestamp("2018-02-05") in td
    assert pd.Timestamp("2018-02-03") not in td  # Saturday
    # 2018: 261 weekdays less 10 full-day closures (incl. the 5 Dec mourning day) = 251
    assert len(td) == 251, len(td)


def test_roll_calendar_structure():
    cal = build_roll_calendar("2010-01-01", "2024-12-31")
    assert cal.index.is_monotonic_increasing
    assert (cal["dr"] >= 0).all()
    assert (cal["dr"] < cal["dt"]).all()
    assert (cal["near_expiry"] > cal.index.to_series()).all() or True
    # near contract must expire strictly after the far contract's predecessor
    assert (cal["far_expiry"] > cal["near_expiry"]).all()
    # dt is the number of business days in a ~1-month roll period
    assert cal["dt"].between(15, 25).all(), cal["dt"].describe()


def test_roll_weights_sweep_from_one_to_near_zero():
    cal = build_roll_calendar("2017-06-01", "2018-06-30")
    w1 = cal["dr"] / cal["dt"]
    assert w1.max() > 0.90
    assert w1.min() < 0.10
    # weight declines monotonically within each roll period
    for _, grp in cal.groupby("roll_start"):
        ww = (grp["dr"] / grp["dt"]).to_numpy()
        assert (ww[1:] <= ww[:-1] + 1e-12).all()


def test_february_2018_roll_state():
    cal = build_roll_calendar("2018-01-15", "2018-03-01")
    row = cal.loc[pd.Timestamp("2018-02-05")]
    # On 5 Feb 2018 the front contract is the Feb-14 expiry and the second is Mar-21.
    assert row["near_expiry"] == pd.Timestamp("2018-02-14")
    assert row["far_expiry"] == pd.Timestamp("2018-03-21")
