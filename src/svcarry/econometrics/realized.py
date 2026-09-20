"""Range-based daily variance estimators.

With only free daily OHLC data there is no intraday tick series, so realised
variance has to be estimated from the daily range. Range-based estimators are far
more efficient than squared close-to-close returns (Parkinson's estimator has
roughly five times the efficiency of close-to-close for the same sample), which
matters a great deal here: the variance risk premium is the difference between a
forward-looking option-implied number and a *noisy estimate* of realised variance,
and estimator noise translates one-for-one into signal noise.

Estimators implemented
----------------------
close_to_close      sum of squared log close-to-close returns (the naive benchmark)
parkinson           Parkinson (1980), high-low range, assumes no drift, no jumps
garman_klass        Garman & Klass (1980), uses OHLC, no drift, ignores overnight
rogers_satchell     Rogers & Satchell (1991), drift-independent
yang_zhang          Yang & Zhang (2000), a *multi-day window* estimator that is
                    drift-independent and handles opening jumps
daily_variance_proxy  the per-day series actually used downstream

A note on "daily Yang-Zhang"
----------------------------
The Yang-Zhang estimator is defined over a window of n days: it needs the sample
means of the overnight and open-to-close return series to form its two variance
components, so there is no single-day Yang-Zhang number. Where a daily series is
required (as an input to the HAR regression) this module uses the natural daily
decomposition that Yang-Zhang is built from,

    sigma2_t = o_t^2 + RS_t,        o_t = ln(O_t / C_{t-1}),

i.e. the overnight squared return plus the drift-independent Rogers-Satchell
intraday estimator. This is unbiased for the total (overnight plus intraday)
variance under the same assumptions, needs no window, and collapses to Yang-Zhang's
own components. The deviation from the literal Yang-Zhang formula is deliberate and
is recorded in ``docs/methodology.md``; ``yang_zhang`` itself is provided and used
for the rolling-window cross-check in ``docs/validation.md``.

All functions take a DataFrame with columns ``open``, ``high``, ``low``, ``close``
indexed by date, and return *daily* variance in squared log-return units. Use
:func:`annualize` to convert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "close_to_close",
    "parkinson",
    "garman_klass",
    "rogers_satchell",
    "yang_zhang",
    "daily_variance_proxy",
    "annualize",
    "TRADING_DAYS_PER_YEAR",
]

TRADING_DAYS_PER_YEAR = 252


def _cols(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    need = ["open", "high", "low", "close"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise KeyError(f"missing OHLC columns: {missing}")
    o, h, l, c = (df[x].astype(float) for x in need)
    bad = (h < l) | (h < o) | (h < c) | (l > o) | (l > c)
    if bool(bad.any()):
        raise ValueError(
            f"{int(bad.sum())} rows violate low <= {{open,close}} <= high; "
            f"first: {df.index[bad][0]}"
        )
    return o, h, l, c


def annualize(daily_var, periods: int = TRADING_DAYS_PER_YEAR):
    """Daily variance -> annualised variance."""
    return daily_var * periods


def close_to_close(df: pd.DataFrame) -> pd.Series:
    """Squared log close-to-close return (includes the overnight move)."""
    _, _, _, c = _cols(df)
    r = np.log(c).diff()
    return (r ** 2).rename("cc")


def parkinson(df: pd.DataFrame) -> pd.Series:
    """Parkinson (1980): (1/(4 ln 2)) * ln(H/L)^2. Intraday only, no drift."""
    _, h, l, _ = _cols(df)
    return ((np.log(h / l) ** 2) / (4.0 * np.log(2.0))).rename("parkinson")


def garman_klass(df: pd.DataFrame) -> pd.Series:
    """Garman & Klass (1980): 0.5 ln(H/L)^2 - (2 ln 2 - 1) ln(C/O)^2."""
    o, h, l, c = _cols(df)
    return (
        0.5 * np.log(h / l) ** 2 - (2.0 * np.log(2.0) - 1.0) * np.log(c / o) ** 2
    ).rename("garman_klass")


def rogers_satchell(df: pd.DataFrame) -> pd.Series:
    """Rogers & Satchell (1991): drift-independent intraday variance.

    RS_t = ln(H/O) ln(H/C) + ln(L/O) ln(L/C)
    """
    o, h, l, c = _cols(df)
    return (
        np.log(h / o) * np.log(h / c) + np.log(l / o) * np.log(l / c)
    ).rename("rogers_satchell")


def overnight(df: pd.DataFrame) -> pd.Series:
    """Squared overnight log return ln(O_t / C_{t-1})^2."""
    o, _, _, c = _cols(df)
    return (np.log(o / c.shift(1)) ** 2).rename("overnight")


def yang_zhang(df: pd.DataFrame, window: int = 21) -> pd.Series:
    """Yang & Zhang (2000) rolling-window daily-equivalent variance.

    sigma2_YZ = sigma2_open + k sigma2_close + (1 - k) sigma2_RS,
    k = 0.34 / (1.34 + (n + 1) / (n - 1)),

    where sigma2_open is the sample variance of overnight log returns
    ln(O_t / C_{t-1}), sigma2_close the sample variance of open-to-close log returns
    ln(C_t / O_t), and sigma2_RS the mean Rogers-Satchell term, all over the window.
    The result is a *per-day* variance, comparable to the other estimators here.
    """
    if window < 3:
        raise ValueError("window must be >= 3")
    o, h, l, c = _cols(df)
    o_ret = np.log(o / c.shift(1))
    c_ret = np.log(c / o)
    rs = rogers_satchell(df)

    var_o = o_ret.rolling(window).var(ddof=1)
    var_c = c_ret.rolling(window).var(ddof=1)
    mean_rs = rs.rolling(window).mean()
    k = 0.34 / (1.34 + (window + 1.0) / (window - 1.0))
    return (var_o + k * var_c + (1.0 - k) * mean_rs).rename("yang_zhang")


def daily_variance_proxy(df: pd.DataFrame, method: str = "rs_overnight") -> pd.Series:
    """The daily variance series used as the HAR dependent variable.

    ``rs_overnight`` (default)  overnight squared return + Rogers-Satchell intraday
    ``gk_overnight``            overnight squared return + Garman-Klass intraday
    ``parkinson_overnight``     overnight squared return + Parkinson intraday
    ``close_to_close``          squared close-to-close return

    Negative values (possible for Garman-Klass and Rogers-Satchell in degenerate
    bars) are *not* silently clipped: they are returned as-is and handled explicitly
    by the caller, because silent clipping biases the mean upward.
    """
    if method == "rs_overnight":
        out = overnight(df) + rogers_satchell(df)
    elif method == "gk_overnight":
        out = overnight(df) + garman_klass(df)
    elif method == "parkinson_overnight":
        out = overnight(df) + parkinson(df)
    elif method == "close_to_close":
        out = close_to_close(df)
    else:
        raise ValueError(f"unknown method {method!r}")
    return out.rename(f"rv_{method}")
