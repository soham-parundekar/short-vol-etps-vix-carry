"""Tests for split handling, written after two real bugs were found against live data.

Both bugs had the same character: the code produced a *plausible* series rather than
an obviously broken one, so nothing failed until the result was compared against an
independent benchmark. That is the argument for these tests existing.

Bug 1 - inverted split factor. The provider reports a 1-for-5 reverse split as
``numerator/denominator = 0.2``. The historical price must be multiplied by ``1/0.2``
to splice onto the current share count; the code multiplied by ``0.2``, which prints
a +2,400% return on the split date and mis-scales everything behind it.

Bug 2 - double adjustment. Yahoo's chart endpoint already returns split-adjusted
OHLC, so "rebuild the adjustment from raw close and the split factors" is not an
independent check, it is a second adjustment applied to an already-adjusted series.
The manual path now refuses rather than returning a wrong number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.data.prices import is_preadjusted, split_adjusted_returns


def _frame(close, adjclose=None, splits=None):
    idx = pd.bdate_range("2020-01-01", periods=len(close))
    df = pd.DataFrame({"close": close, "adjclose": adjclose if adjclose is not None else close},
                      index=idx)
    df.attrs["splits"] = (pd.Series(splits, dtype=float) if splits
                          else pd.Series(dtype=float))
    return df, idx


def test_detects_a_preadjusted_provider():
    df, _ = _frame([10.0, 11.0, 12.0, 13.0])
    assert is_preadjusted(df) is True


def test_detects_a_raw_provider():
    df, _ = _frame([10.0, 11.0, 12.0, 13.0], adjclose=[5.0, 5.5, 6.0, 13.0])
    assert is_preadjusted(df) is False


def test_manual_path_refuses_to_double_adjust():
    """The bug that made an already-adjusted series wrong a second time."""
    df, _ = _frame([10.0, 11.0, 12.0, 13.0])
    with pytest.raises(ValueError, match="already split-adjusted"):
        split_adjusted_returns(df, prefer="manual")


def test_reverse_split_factor_is_inverted_correctly():
    """A 1-for-5 reverse split must produce a zero return, not +2,400%."""
    idx = pd.bdate_range("2020-01-01", periods=4)
    split_date = idx[2]
    # raw prices: 10, 10 then the reverse split lifts the quote to 50, 50
    df = pd.DataFrame({"close": [10.0, 10.0, 50.0, 50.0],
                       "adjclose": [np.nan] * 4}, index=idx)
    df.attrs["splits"] = pd.Series({split_date: 0.2})
    r = split_adjusted_returns(df, prefer="manual")
    assert r.iloc[2] == pytest.approx(0.0, abs=1e-12), "split date must not print a return"
    assert r.iloc[1] == pytest.approx(0.0, abs=1e-12)
    assert r.iloc[3] == pytest.approx(0.0, abs=1e-12)


def test_forward_split_factor_is_inverted_correctly():
    """A 2-for-1 forward split halves the quote; the return must still be zero."""
    idx = pd.bdate_range("2020-01-01", periods=4)
    df = pd.DataFrame({"close": [100.0, 100.0, 50.0, 50.0],
                       "adjclose": [np.nan] * 4}, index=idx)
    df.attrs["splits"] = pd.Series({idx[2]: 2.0})
    r = split_adjusted_returns(df, prefer="manual")
    assert r.iloc[2] == pytest.approx(0.0, abs=1e-12)


def test_an_unadjusted_split_would_have_been_caught():
    """Guard the property directly: no post-adjustment return may exceed the raw
    move that a missed split would create."""
    idx = pd.bdate_range("2020-01-01", periods=4)
    df = pd.DataFrame({"close": [10.0, 10.0, 50.0, 50.0],
                       "adjclose": [np.nan] * 4}, index=idx)
    df.attrs["splits"] = pd.Series({idx[2]: 0.2})
    r = split_adjusted_returns(df, prefer="manual").dropna()
    assert r.abs().max() < 0.5, "a surviving split shows up as a huge single-day move"


def test_adjclose_path_is_used_when_available():
    df, _ = _frame([10.0, 20.0, 30.0], adjclose=[1.0, 2.0, 3.0])
    r = split_adjusted_returns(df, prefer="adjclose")
    assert r.iloc[1] == pytest.approx(1.0)      # 1 -> 2 on the adjusted series
