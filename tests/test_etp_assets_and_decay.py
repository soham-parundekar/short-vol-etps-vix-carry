"""Tests for asset bounding and the decay-regression diagnostics (Phase 08).

Two of these guard against a trap that was actually fallen into: a 10-K restates its
share counts and per-share NAVs onto the filing's own share basis, so re-applying the
splits that fall between an early anchor and the filing date counts them twice. For
UVXY that is an error of a factor of about 1,900, and the only thing that caught it
was requiring two independent statements of the same share count to agree.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.etp.assets import asset_bounds, cumulative_split_factor
from svcarry.etp.mechanics import (
    block_influence,
    decay_blocks,
    decay_regression,
    identity_approximation_error,
    theoretical_decay,
)


# ------------------------------------------------------------------ split factors
def test_split_factor_direction():
    """A 2-for-1 forward split doubles an EARLIER share count in today's basis; a
    1-for-4 reverse quarters it. Dates on or after a split are unaffected by it."""
    splits = pd.Series({pd.Timestamp("2020-06-01"): 2.0,
                        pd.Timestamp("2021-06-01"): 0.25})
    f = cumulative_split_factor(splits, ["2020-01-01", "2020-06-01", "2021-01-01",
                                         "2022-01-01"])
    assert f.tolist() == pytest.approx([0.5, 0.25, 0.25, 1.0])


# ------------------------------------------------------------------ asset bounds
def _prices(start="2015-01-01", end="2016-12-31", level=10.0):
    idx = pd.bdate_range(start, end)
    return pd.Series(level, index=idx, dtype=float)


def _anchors(rows):
    df = pd.DataFrame(rows, columns=["symbol", "date", "nav_usd", "shares_outstanding"])
    df["date"] = pd.to_datetime(df["date"])
    df["nav_per_share"] = np.nan
    return df


def test_bounds_bracket_every_anchor_exactly():
    px = _prices()
    a = _anchors([("X", "2015-01-02", 100.0, 10.0),
                  ("X", "2015-12-31", 300.0, 30.0),
                  ("X", "2016-12-30", 200.0, 20.0)])
    b = asset_bounds(a, px, pd.Series(dtype=float))
    for d, nav in (("2015-01-02", 100.0), ("2015-12-31", 300.0), ("2016-12-30", 200.0)):
        d = pd.Timestamp(d)
        assert b.at[d, "assets_lower"] == pytest.approx(nav)
        assert b.at[d, "assets_upper"] == pytest.approx(nav)


def test_bounds_between_anchors_span_the_endpoints():
    px = _prices()
    a = _anchors([("X", "2015-01-02", 100.0, 10.0), ("X", "2015-12-31", 300.0, 30.0)])
    b = asset_bounds(a, px, pd.Series(dtype=float))
    mid = b.loc["2015-06-01":"2015-06-30"]
    assert np.allclose(mid["assets_lower"].to_numpy(), 100.0)
    assert np.allclose(mid["assets_upper"].to_numpy(), 300.0)
    assert ((mid["assets_central"] > 100.0) & (mid["assets_central"] < 300.0)).all()


def test_dates_outside_the_anchors_are_flagged_not_claimed():
    px = _prices()
    a = _anchors([("X", "2015-03-02", 100.0, 10.0), ("X", "2015-09-01", 200.0, 20.0)])
    b = asset_bounds(a, px, pd.Series(dtype=float))
    assert b.loc["2015-01-02", "extrapolated"]
    assert not b.loc["2015-06-01", "extrapolated"]
    assert b.loc["2016-06-01", "extrapolated"]


def test_inconsistent_share_basis_raises():
    """Two valued anchors whose share counts imply different bases relative to the
    price series - the signature of a mis-restated anchor or a wrong split factor."""
    px = _prices()
    a = _anchors([("X", "2015-01-02", 100.0, 10.0),      # basis 10/10  = 1.0
                  ("X", "2015-12-31", 300.0, 60.0)])     # basis 30/60  = 0.5
    with pytest.raises(ValueError, match="single basis"):
        asset_bounds(a, px, pd.Series(dtype=float))


def test_shares_only_anchor_across_a_split_raises():
    px = _prices()
    a = _anchors([("X", "2015-01-02", 100.0, 10.0),
                  ("X", "2015-06-01", np.nan, 25.0)])
    splits = pd.Series({pd.Timestamp("2015-03-02"): 2.0})
    with pytest.raises(ValueError, match="split occurs between"):
        asset_bounds(a, px, splits)


def test_shares_only_anchor_is_placed_on_the_common_basis():
    px = _prices()
    a = _anchors([("X", "2015-01-02", 100.0, 10.0),
                  ("X", "2015-06-01", np.nan, 25.0)])
    b = asset_bounds(a, px, pd.Series(dtype=float))
    assert b.at[pd.Timestamp("2015-06-01"), "assets_central"] == pytest.approx(250.0)


# ------------------------------------------------------------- decay diagnostics
def _synthetic(L, n=21 * 40, vol=0.04, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    r = pd.Series(rng.normal(0.0, vol, n), index=idx)
    p = L * r                       # a perfect daily-rebalanced product, no fee
    return p, r


def test_decay_blocks_are_what_the_regression_fits():
    from svcarry.econometrics.hac import ols
    p, r = _synthetic(-1.0)
    B = decay_blocks(p, r, -1.0, 21)
    f = ols(B["y"].to_numpy(), B["x"].to_numpy(), names=["rv"], cov_type="HC1")
    res = decay_regression(p, r, leverage=-1.0, horizon=21)
    assert float(f.params[1]) == pytest.approx(res.slope, abs=1e-12)


@pytest.mark.parametrize("L", [-1.0, -0.5, 1.5, 2.0])
def test_perfect_product_recovers_theoretical_slope(L):
    p, r = _synthetic(L)
    res = decay_regression(p, r, leverage=L, horizon=21)
    assert res.slope == pytest.approx(theoretical_decay(L), abs=0.08)


def test_block_influence_finds_a_planted_outlier():
    p, r = _synthetic(-1.0)
    k = 21 * 20 + 5
    r.iloc[k] = 0.96                 # a 5 February 2018-sized day
    p.iloc[k] = -0.33                # and a product that did not keep up that day
    inf = block_influence(p, r, -1.0, 21)
    top = pd.Timestamp(inf.iloc[0]["end"])
    assert r.index[21 * 20] <= top <= r.index[21 * 21 - 1]
    assert abs(inf.iloc[0]["delta"]) > 5 * abs(inf.iloc[1]["delta"])


def test_identity_is_exact_in_the_small_return_limit():
    r = pd.Series(np.full(21, 1e-5))
    e = identity_approximation_error(-1.0, r)
    assert abs(e["error_pp"]) < 1e-6


def test_identity_error_is_large_at_a_96_percent_day():
    r = pd.Series([0.01] * 10 + [0.961] + [-0.2596] + [0.0] * 9)
    e = identity_approximation_error(-1.0, r)
    assert e["exact"] == pytest.approx(float(np.prod(1.0 - r.to_numpy()) - 1.0))
    assert e["error_pp"] > 15.0
