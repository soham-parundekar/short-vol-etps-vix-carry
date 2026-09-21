"""Reconstruction of the S&P 500 VIX Short-Term Futures Index from raw futures data.

What the index is
-----------------
A long position in the two nearest monthly VIX futures, rolled continuously so that
the weighted average time to maturity stays near one month. Each day a fraction of
the near contract is sold and the same notional bought in the next contract; over a
roll period the portfolio migrates entirely from one to the other. The index is
*excess return*: it reflects the return on the futures position only, with the
total-return version adding a Treasury-bill accrual on the notional.

Daily return
------------
Writing ``w1, w2`` for the roll weights set at the close of ``t-1`` and ``F1, F2``
for the settlement prices of the two contracts *held at that time*,

    TDWI_{t-1} = w1_{t-1} F1_{t-1} + w2_{t-1} F2_{t-1}
    TDWO_t     = w1_{t-1} F1_t     + w2_{t-1} F2_t
    r_t        = TDWO_t / TDWI_{t-1} - 1

The subtlety that makes or breaks a reconstruction is the phrase *held at that
time*. On the day after a settlement the labels "first month" and "second month"
point at different contracts than they did the day before, so a naive
``F1.pct_change()`` silently computes the return between two *different* contracts
and books the calendar spread as a price move. This module therefore looks up the
expiry pair recorded for ``t-1`` and prices exactly those two contracts on both
days.

Why reconstruct at all
----------------------
The published index level is not freely available as a long history, but more
importantly the reconstruction is what makes the rest of the project possible: it
gives an index series that extends before the products existed, that is not
contaminated by product fees, and whose inputs (each contract's settlement price,
volume and open interest) are visible. The reconstruction is validated against the
traded products in ``docs/validation.md``; that comparison is the check that the
roll convention and the calendar are right.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import load_config
from .calendar import build_roll_calendar

__all__ = [
    "build_curve",
    "roll_weights",
    "reconstruct_index",
    "constant_maturity_curve",
    "carry_measures",
]


def build_curve(panel: pd.DataFrame, price_col: str = "settle") -> pd.DataFrame:
    """Pivot the long futures panel into a date x expiry price matrix."""
    wide = panel.pivot_table(index="date", columns="expiry", values=price_col,
                             aggfunc="last")
    return wide.sort_index().sort_index(axis=1)


def roll_weights(roll_cal: pd.DataFrame, convention: str = "sp_dji") -> pd.DataFrame:
    """Weights on the near and far contract for each date.

    ``sp_dji``   ``w1 = dr / dt``, the S&P Dow Jones Indices definition, where ``dr``
                 is the number of business days remaining in the roll period after
                 today and ``dt`` the total number in the period.
    ``shifted``  ``w1 = (dr + 1) / dt``. Identical in structure but advanced by one
                 business day; vendors differ on whether the roll trade is booked at
                 the close of the settlement date or of the following day.

    Both are produced so that the choice can be made on evidence (tracking error
    against the traded products) rather than on assertion.
    """
    dr, dt = roll_cal["dr"].astype(float), roll_cal["dt"].astype(float)
    if convention == "sp_dji":
        w1 = dr / dt
    elif convention == "shifted":
        w1 = (dr + 1.0) / dt
    else:
        raise ValueError(f"unknown roll convention {convention!r}")
    w1 = w1.clip(0.0, 1.0)
    return pd.DataFrame({"w1": w1, "w2": 1.0 - w1}, index=roll_cal.index)


def reconstruct_index(
    panel: pd.DataFrame,
    convention: str | None = None,
    price_col: str = "settle",
    tbill_accrual: pd.Series | None = None,
    base_level: float = 100_000.0,
    start=None,
    end=None,
) -> pd.DataFrame:
    """Rebuild the short-term VIX futures index from the contract panel.

    Returns a DataFrame indexed by date with

    ``f1, f2``            settlement prices of the contracts held *that* day
    ``exp1, exp2``        their expiries
    ``w1, w2``            roll weights applied at that day's close
    ``ret``               excess (futures-only) daily simple return
    ``level_er``          excess-return index level, based at ``base_level``
    ``ret_tr, level_tr``  total-return versions, if a T-bill accrual is supplied
    ``n_missing``         contracts with no usable settlement price that day

    Days on which either held contract has no settlement price produce ``NaN``
    returns rather than a forward-filled zero. Those days are reported, not hidden:
    a reconstruction that silently prints 0% on a data gap would understate
    volatility and flatter every risk statistic downstream.
    """
    cfg = load_config()
    convention = convention or cfg.dotted("index.roll_convention")
    start = pd.Timestamp(start or panel["date"].min())
    end = pd.Timestamp(end or panel["date"].max())

    # The index's business days are the days the futures market actually traded, so
    # the roll's business-day counts are taken from the panel itself rather than from
    # a derived calendar that could disagree with it. This matters on the handful of
    # sessions where CFE traded while the equity market was shut.
    cal = build_roll_calendar(start, end, business_days=panel["date"].unique())
    cal = cal.loc[cal.index.isin(panel["date"].unique())]
    if cal.empty:
        raise ValueError("no overlap between the futures panel and the roll calendar")
    w = roll_weights(cal, convention)

    curve = build_curve(panel, price_col=price_col)
    dates = cal.index

    exp1 = cal["near_expiry"]
    exp2 = cal["far_expiry"]

    def _price(d: pd.Timestamp, e: pd.Timestamp) -> float:
        try:
            return float(curve.at[d, e])
        except KeyError:
            return np.nan

    f1 = pd.Series([_price(d, exp1[d]) for d in dates], index=dates, name="f1")
    f2 = pd.Series([_price(d, exp2[d]) for d in dates], index=dates, name="f2")

    # Return from t-1 to t on the contracts that were held at t-1.
    prev = dates[:-1]
    cur = dates[1:]
    tdwi = np.full(len(dates), np.nan)
    tdwo = np.full(len(dates), np.nan)
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        e1, e2 = exp1[d0], exp2[d0]
        p1_0, p2_0 = _price(d0, e1), _price(d0, e2)
        p1_1, p2_1 = _price(d1, e1), _price(d1, e2)
        ww1, ww2 = float(w.at[d0, "w1"]), float(w.at[d0, "w2"])
        tdwi[i] = ww1 * p1_0 + ww2 * p2_0
        tdwo[i] = ww1 * p1_1 + ww2 * p2_1

    with np.errstate(invalid="ignore", divide="ignore"):
        ret = tdwo / tdwi - 1.0
    ret = pd.Series(ret, index=dates, name="ret")

    out = pd.DataFrame(
        {
            "f1": f1, "f2": f2,
            "exp1": exp1.reindex(dates), "exp2": exp2.reindex(dates),
            "w1": w["w1"], "w2": w["w2"],
            "dr": cal["dr"], "dt": cal["dt"],
            "days_to_exp1": (exp1.reindex(dates) - pd.Series(dates, index=dates)).dt.days,
            "days_to_exp2": (exp2.reindex(dates) - pd.Series(dates, index=dates)).dt.days,
            "ret": ret,
        }
    )
    out["n_missing"] = out[["f1", "f2"]].isna().sum(axis=1)

    lvl = (1.0 + out["ret"].fillna(0.0)).cumprod() * base_level
    lvl[out["ret"].isna() & (out.index != out.index[0])] = np.nan
    out["level_er"] = lvl.ffill()

    if tbill_accrual is not None:
        accr = tbill_accrual.reindex(out.index)
        out["accrual"] = accr
        out["ret_tr"] = out["ret"] + accr
        out["level_tr"] = (1.0 + out["ret_tr"].fillna(0.0)).cumprod() * base_level

    out.attrs["convention"] = convention
    out.attrs["price_col"] = price_col
    out.attrs["n_days_missing_price"] = int((out["n_missing"] > 0).sum())
    return out


def constant_maturity_curve(
    panel: pd.DataFrame, maturities=(30, 60, 90, 120, 150, 180),
    price_col: str = "settle", min_open_interest: int | None = None,
) -> pd.DataFrame:
    """Linear interpolation of the futures curve at fixed calendar-day maturities.

    For each date the available (days-to-expiry, price) pairs are interpolated at the
    requested horizons. Points beyond the longest listed contract are left as ``NaN``
    rather than extrapolated: an extrapolated 180-day VIX future is a modelling
    choice, not an observation, and treating it as data would quietly contaminate the
    term-structure statistics.
    """
    p = panel.dropna(subset=[price_col]).copy()
    if min_open_interest is not None and "open_interest" in p.columns:
        p = p[p["open_interest"].fillna(0) >= min_open_interest]
    rows = {}
    for d, grp in p.groupby("date"):
        g = grp[grp["days_to_expiry"] > 0].sort_values("days_to_expiry")
        if len(g) < 2:
            continue
        x = g["days_to_expiry"].to_numpy(dtype=float)
        y = g[price_col].to_numpy(dtype=float)
        vals = {}
        for m in maturities:
            vals[f"cm{m}"] = np.interp(m, x, y) if (x.min() <= m <= x.max()) else np.nan
        vals["n_contracts"] = len(g)
        rows[d] = vals
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def carry_measures(
    index_df: pd.DataFrame, vix: pd.Series | None = None,
    vix3m: pd.Series | None = None, cm: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Term-structure and carry statistics.

    ``carry_log``      ``ln(F2/F1) / (tau2 - tau1)``, the log slope per calendar day
                       between the two held contracts. Negative in contango, which is
                       the state that pays a short-volatility position.
    ``basis_f1_vix``   ``F1 / VIX - 1``, how far the front future sits above spot.
    ``slope_vix3m``    ``VIX / VIX3M``. Below one means the implied-volatility curve
                       is upward sloping. The strategy's robustness variant.
    ``slope_cm``       ``cm30 / cm90`` from the interpolated futures curve, available
                       from 2008 where VIX3M starts only in September 2009. The
                       strategy's primary slope measure is built from this, with the
                       gaps after some expiries filled in
                       :func:`svcarry.strategy.signals.spot_anchored_front`; this
                       column is left unfilled.

    Every column is computed from data observable at that day's close, so the
    strategy code can lag them by one day without further thought.
    """
    out = pd.DataFrame(index=index_df.index)
    tau1 = index_df["days_to_exp1"].astype(float)
    tau2 = index_df["days_to_exp2"].astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["carry_log"] = np.log(index_df["f2"] / index_df["f1"]) / (tau2 - tau1)
        out["spread_f2_f1"] = index_df["f2"] - index_df["f1"]
    if vix is not None:
        v = vix.reindex(out.index)
        out["vix"] = v
        out["basis_f1_vix"] = index_df["f1"] / v - 1.0
        if vix3m is not None:
            v3 = vix3m.reindex(out.index)
            out["vix3m"] = v3
            out["slope_vix3m"] = v / v3
    if cm is not None:
        c = cm.reindex(out.index)
        if {"cm30", "cm90"} <= set(c.columns):
            out["slope_cm"] = c["cm30"] / c["cm90"]
        for col in c.columns:
            out[col] = c[col]
    return out
