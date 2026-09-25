"""Bounding each product's net assets through time.

Why this is its own module
--------------------------
Assets outstanding is the weakest input in the project and the rebalancing-flow
estimate is *linear* in it, so an asset series wrong by a factor of two makes the
headline claim wrong by a factor of two. No free source gives a clean daily
shares-outstanding history for these products over the whole sample.

What is available is a set of **directly disclosed anchors** - the ProShares Trust II
10-K states each fund's net assets, shares outstanding and per-share NAV at four
year-ends, and its cover page gives the share count at one further date. Between
anchors the share count is unknown, so this module produces an upper and a lower
bound rather than a series, and the flow result is stated as the band those bounds
imply. Outside the anchored window nothing is claimed at all: those dates are marked
``extrapolated`` and the pipeline excludes them from the headline.

Working in adjusted share units
-------------------------------
These products reverse-split constantly - UVXY thirteen times in the sample - so a
raw share count at one date is not comparable to a raw share count at another. Net
assets are invariant, though, and so is the product of adjusted shares and adjusted
price:

    assets(t) = raw_shares(t) x raw_price(t) = adj_shares(t) x adj_price(t)

with ``adj_shares(t) = raw_shares(t) * prod(k for splits after t)`` and the adjusted
price divided by the same factor. Everything below is in adjusted units, which makes
the interpolation between anchors meaningful.

The bounding assumption, stated plainly
---------------------------------------
Between two anchors the share count is taken to lie between the two anchor values.
That is an assumption, not a deduction: creations and redemptions could in principle
have carried the count outside that range and back. It is the weakest assumption that
yields a usable band, it is exactly right at every anchor, and it is recorded in
``docs/limitations.md`` as something a subscription data source with daily shares
outstanding would remove.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "cumulative_split_factor",
    "adjusted_shares",
    "load_anchors",
    "asset_bounds",
]


def cumulative_split_factor(splits: pd.Series, dates) -> pd.Series:
    """For each date, the product of split ratios for splits occurring **after** it.

    A 2-for-1 forward split is reported as ``2.0`` and doubles the share count; a
    1-for-4 reverse is reported as ``0.25`` and quarters it. So a share count
    observed before those events is expressed in today's basis by multiplying by
    this factor, and a price observed then is divided by it - which is exactly the
    convention :func:`svcarry.data.prices.split_adjusted_returns` uses.
    """
    idx = pd.DatetimeIndex(dates)
    out = pd.Series(1.0, index=idx)
    if splits is None or len(splits) == 0:
        return out
    for d, k in pd.Series(splits).items():
        out.loc[idx < pd.Timestamp(d)] *= float(k)
    return out


def adjusted_shares(raw_shares, dates, splits: pd.Series) -> pd.Series:
    """Raw share counts restated in the current (fully split-adjusted) share basis."""
    f = cumulative_split_factor(splits, dates)
    return pd.Series(np.asarray(raw_shares, dtype=float), index=f.index) * f


def load_anchors(path) -> pd.DataFrame:
    """Read the disclosed-anchor table, ignoring its provenance header."""
    df = pd.read_csv(path, comment="#")
    df["date"] = pd.to_datetime(df["date"])
    for c in ("nav_usd", "shares_outstanding", "nav_per_share"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def asset_bounds(
    anchors: pd.DataFrame,
    adj_price: pd.Series,
    splits: pd.Series,
    tolerance: float = 0.05,
) -> pd.DataFrame:
    """Lower, central and upper net-asset series for one product.

    ``anchors`` are that product's rows from the anchor table; ``adj_price`` is its
    split-adjusted closing price; ``splits`` its recorded split events.

    Returns a frame indexed by the price dates with

    ``assets_lower, assets_central, assets_upper``  in dollars
    ``adj_shares_*``                                the underlying share paths
    ``is_anchor``                                   True on a disclosed date
    ``extrapolated``                                True outside the anchored window,
                                                    where nothing is claimed

    Raises if a disclosed anchor does not lie inside its own band, or if an anchor's
    two independent statements of the share count - ``nav_usd / price`` and
    ``shares_outstanding`` restated for splits - disagree by more than ``tolerance``.
    That second check is the useful one: it tests the price series and the split
    handling against the filing, and it is how a mis-signed split factor would be
    caught here rather than downstream.
    """
    px = pd.Series(adj_price).astype(float).dropna()
    px = px[~px.index.duplicated(keep="last")].sort_index()
    a = anchors.dropna(subset=["date"]).sort_values("date").copy()

    # --- anchor share counts in adjusted units -------------------------------
    #
    # A trap worth naming, because it is invisible until something is cross-checked.
    # A 10-K restates BOTH its share counts and its per-share NAVs onto one share
    # basis - the filing's own - so the figure it prints for 2014 is already
    # expressed in the shares of 2017. Re-applying the splits that fall between 2014
    # and the filing date therefore counts them twice. The symptom is a share count
    # wrong by exactly the product of the intervening split ratios, which for UVXY is
    # a factor of 1,900.
    #
    # The fix is to avoid split arithmetic wherever the filing gives net assets:
    # ``net assets / adjusted price`` is exact and needs no basis at all, because
    # dollars are dollars. Splits are only needed for an anchor that states a share
    # count and no value, and there the count is scaled against the nearest anchor
    # from the same filing - valid precisely because no split intervenes, which is
    # asserted rather than assumed.
    # A fund strikes NAV only on trading days, so a disclosure "as of 31 December"
    # that falls on a weekend is the NAV struck at the preceding session's close.
    # Each anchor is therefore placed on that session. Without this, the two
    # year-end anchors that fall on weekends (2016-12-31, 2017-12-31) were not in
    # the price index at all, and the bracketing check below skipped them in
    # silence - half the anchors unverified while the check reported success.
    def _session(d):
        prior = px.index[px.index <= d]
        return prior.max() if len(prior) else pd.NaT

    a["disclosed_date"] = a["date"]
    a["date"] = [_session(d) for d in a["date"]]
    a = a.dropna(subset=["date"])
    a["px_at_anchor"] = [float(px.at[d]) for d in a["date"]]
    a["S"] = a["nav_usd"] / a["px_at_anchor"]

    # Consistency check across anchors that DO state net assets: the ratio of the
    # filing's share count to the adjusted share count must be one constant, because
    # every row of the filing is on the same basis. A row restated differently - or a
    # mis-signed split factor in the price series - breaks this.
    valued = a["S"].notna() & a["shares_outstanding"].notna()
    basis_factor = np.nan
    if valued.any():
        basis = a.loc[valued, "S"] / a.loc[valued, "shares_outstanding"]
        # One valued anchor fixes the basis; the consistency check needs two.
        if valued.sum() >= 2 and float(basis.max() / basis.min() - 1.0) > tolerance:
            raise ValueError(
                "the filing's share counts are not on a single basis relative to the "
                f"price series (ratios {basis.to_dict()}); either an anchor is "
                "restated differently or the split adjustment is wrong"
            )
        basis_factor = float(basis.median())

    # Anchors that give a share count but no value: scale on the common basis, after
    # checking no split falls between this anchor and the valued ones it relies on.
    need = a["S"].isna() & a["shares_outstanding"].notna()
    if need.any():
        if not np.isfinite(basis_factor):
            raise ValueError("cannot place a shares-only anchor without a valued one")
        sp = pd.Series(splits) if splits is not None else pd.Series(dtype=float)
        lo_d, hi_d = a.loc[valued, "date"].max(), a.loc[need, "date"].max()
        between = [d for d in sp.index if lo_d < pd.Timestamp(d) <= hi_d]
        if between:
            raise ValueError(
                f"a split occurs between the valued anchors and a shares-only anchor "
                f"({between}); the common-basis scaling is not valid there"
            )
        a.loc[need, "S"] = a.loc[need, "shares_outstanding"] * basis_factor

    a = a.dropna(subset=["S"])
    if len(a) < 2:
        raise ValueError("need at least two usable anchors to bound assets")

    idx = px.index
    t = idx.to_julian_date().to_numpy()
    ta = pd.DatetimeIndex(a["date"]).to_julian_date().to_numpy()
    Sa = a["S"].to_numpy(dtype=float)

    central = np.interp(t, ta, Sa)
    prev = pd.Series(Sa, index=pd.DatetimeIndex(a["date"])).reindex(idx, method="ffill")
    nxt = pd.Series(Sa, index=pd.DatetimeIndex(a["date"])).reindex(idx, method="bfill")
    prev = prev.fillna(Sa[0]).to_numpy()
    nxt = nxt.fillna(Sa[-1]).to_numpy()

    lower_S = np.minimum(prev, nxt)
    upper_S = np.maximum(prev, nxt)

    out = pd.DataFrame(
        {
            "adj_price": px.to_numpy(),
            "adj_shares_lower": lower_S,
            "adj_shares_central": central,
            "adj_shares_upper": upper_S,
        },
        index=idx,
    )
    for k in ("lower", "central", "upper"):
        out[f"assets_{k}"] = out[f"adj_shares_{k}"] * out["adj_price"]

    out["is_anchor"] = out.index.isin(pd.DatetimeIndex(a["date"]))
    out["extrapolated"] = (out.index < a["date"].min()) | (out.index > a["date"].max())

    # --- every disclosed anchor must fall inside its own band (docs/methodology.md M4) ---
    for _, row in a.iterrows():
        d = pd.Timestamp(row["date"])
        if d not in out.index:        # cannot happen now anchors sit on sessions
            raise ValueError(f"anchor {row['disclosed_date'].date()} has no session")
        lo, hi = out.at[d, "assets_lower"], out.at[d, "assets_upper"]
        disclosed = row["nav_usd"] if np.isfinite(row["nav_usd"]) else row["S"] * out.at[d, "adj_price"]
        if not (lo * (1 - 1e-6) <= disclosed <= hi * (1 + 1e-6)):
            raise ValueError(
                f"disclosed net assets on {d.date()} ({disclosed:,.0f}) fall outside "
                f"the band [{lo:,.0f}, {hi:,.0f}] - the bound is wrong"
            )
    return out
