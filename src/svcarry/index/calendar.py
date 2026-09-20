"""US equity/derivatives trading calendar and the Cboe VIX futures expiry calendar.

Why this module exists
----------------------
The reconstruction of the S&P 500 VIX Short-Term Futures Index depends entirely on
knowing, for every trading day, (a) which two VIX futures contracts are the "first"
and "second" month and (b) how many business days remain in the current roll period.
Both quantities are functions of the Cboe VIX futures *final settlement date*, which
is defined by contract specification rather than by any data field we can download.

Getting this calendar wrong is the single most common source of silent error in VIX
index reconstruction: a one-day misalignment of the roll shifts weights by 1/dt
(typically 1/21 ~ 4.8%) every day of the sample and shows up as a small but
systematic tracking error against the traded products.

Contract specification (Cboe)
-----------------------------
"The final settlement date for a contract with the 'VX' ticker symbol is on the
Wednesday that is 30 days prior to the third Friday of the calendar month
immediately following the month in which the contract expires."

If that Wednesday, or the Friday 30 days later (the SPX option expiration used to
compute the settlement value), is a Cboe/NYSE holiday, the final settlement date is
the business day immediately preceding that Wednesday.

Holiday rules implemented
-------------------------
Standard NYSE/Cboe holiday schedule, with observance shifting (Saturday -> preceding
Friday, Sunday -> following Monday), Good Friday computed from the Gregorian Easter
algorithm, Juneteenth added from 2022, plus the handful of ad-hoc closures that fall
inside a plausible sample window. Ad-hoc closures are listed explicitly rather than
inferred, so that the assumption is auditable.

Everything here is pure-Python/NumPy and is exercised by ``tests/test_calendar.py``
against independently known settlement dates.
"""

from __future__ import annotations

import datetime as _dt
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "easter_sunday",
    "CFE_ONLY_SESSIONS",
    "us_market_holidays",
    "trading_days",
    "is_trading_day",
    "vix_settlement_date",
    "vix_settlement_dates",
    "build_roll_calendar",
    "MONTH_CODES",
    "CODE_TO_MONTH",
]

# CME/Cboe single-letter month codes used in the Cboe historical futures files,
# e.g. "G (Feb 2018)" -> February 2018 expiry.
#: Public view of the equity-closed / futures-open sessions.
CFE_ONLY_SESSIONS: tuple[str, ...] = (
    "2015-04-03", "2018-12-05", "2025-01-09",
)

MONTH_CODES: dict[int, str] = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
CODE_TO_MONTH: dict[str, int] = {v: k for k, v in MONTH_CODES.items()}

# Ad-hoc, non-recurring US market closures. Only full-day closures matter for us.
# Source: NYSE historical closings.
#: Days the equity market was closed but Cboe Futures Exchange held a session.
#: These are not guesses: each was identified because the downloaded VX contract
#: files contain settlement prices and non-zero volume on that date while the NYSE
#: calendar calls it a holiday. Using the equity calendar for the futures panel
#: would silently drop these sessions and shift the roll business-day counts around
#: them.
#:   2015-04-03  Good Friday; CFE held a session around the March employment report
#:   2018-12-05  national day of mourning, President G.H.W. Bush (NYSE shut, CFE open)
#:   2025-01-09  national day of mourning, President Carter (NYSE shut, CFE open)
_CFE_ONLY_SESSIONS: tuple[str, ...] = (
    "2015-04-03",
    "2018-12-05",
    "2025-01-09",
)

_AD_HOC_CLOSURES: tuple[str, ...] = (
    "2004-06-11",  # National day of mourning, President Reagan
    "2007-01-02",  # National day of mourning, President Ford
    "2012-10-29",  # Hurricane Sandy
    "2012-10-30",  # Hurricane Sandy
    "2018-12-05",  # National day of mourning, President G.H.W. Bush
    "2025-01-09",  # National day of mourning, President Carter
)


def easter_sunday(year: int) -> _dt.date:
    """Gregorian Easter Sunday (Anonymous / Meeus-Jones-Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month = (h + lam - 7 * m + 114) // 31
    day = ((h + lam - 7 * m + 114) % 31) + 1
    return _dt.date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    """n-th ``weekday`` (Mon=0) of ``month``; n negative counts from the end."""
    if n > 0:
        first = _dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + _dt.timedelta(days=offset + 7 * (n - 1))
    last_day = (
        _dt.date(year + (month == 12), (month % 12) + 1, 1) - _dt.timedelta(days=1)
    )
    offset = (last_day.weekday() - weekday) % 7
    return last_day - _dt.timedelta(days=offset + 7 * (-n - 1))


def _observed(d: _dt.date) -> _dt.date | None:
    """NYSE observance rule for fixed-date holidays.

    The rule is: a holiday falling on a Saturday is observed on the preceding
    Friday, **unless that Friday is the last trading day of the calendar year**, and
    a holiday falling on a Sunday is observed on the following Monday.

    The exception matters and is easy to miss. When 1 January falls on a Saturday the
    preceding Friday is 31 December, so the exchange does *not* close: it stays open
    on 31 December 2010 and 31 December 2021, both of which this project's futures
    data confirms were full trading sessions. An implementation without the carve-out
    marks those two days as holidays, which shifts every business-day count in the
    surrounding roll periods.

    Returns ``None`` when the holiday produces no closure at all.
    """
    if d.weekday() == 5:                      # Saturday
        friday = d - _dt.timedelta(days=1)
        if friday.month == 12 and friday.day == 31:
            return None                       # last trading day of the year: open
        return friday
    if d.weekday() == 6:                      # Sunday -> following Monday
        return d + _dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def us_market_holidays(start_year: int = 2003, end_year: int = 2035,
                       market: str = "nyse") -> frozenset[_dt.date]:
    """Full-day closures between ``start_year`` and ``end_year`` inclusive.

    ``market="nyse"`` gives the equity-market calendar, which is what the S&P 500
    OHLC data follows. ``market="cfe"`` gives the Cboe Futures Exchange calendar,
    which differs on a handful of days when CFE held a session while the equity
    market was shut - see :data:`_CFE_ONLY_SESSIONS`.
    """
    days: set[_dt.date] = set()

    def _add(d: _dt.date | None) -> None:
        if d is not None:
            days.add(d)

    for y in range(start_year, end_year + 1):
        _add(_observed(_dt.date(y, 1, 1)))                          # New Year's Day
        _add(_nth_weekday(y, 1, 0, 3))                              # MLK Jr Day
        _add(_nth_weekday(y, 2, 0, 3))                              # Washington's Birthday
        _add(easter_sunday(y) - _dt.timedelta(days=2))              # Good Friday
        _add(_nth_weekday(y, 5, 0, -1))                             # Memorial Day
        if y >= 2022:
            _add(_observed(_dt.date(y, 6, 19)))                     # Juneteenth
        _add(_observed(_dt.date(y, 7, 4)))                          # Independence Day
        _add(_nth_weekday(y, 9, 0, 1))                              # Labor Day
        _add(_nth_weekday(y, 11, 3, 4))                             # Thanksgiving
        _add(_observed(_dt.date(y, 12, 25)))                        # Christmas
    for iso in _AD_HOC_CLOSURES:
        days.add(_dt.date.fromisoformat(iso))
    if market == "cfe":
        days -= {_dt.date.fromisoformat(x) for x in _CFE_ONLY_SESSIONS}
    return frozenset(days)


def is_trading_day(d, market: str = "nyse") -> bool:
    """True if ``d`` is a weekday and not a full-day closure for ``market``."""
    d = pd.Timestamp(d).date()
    return d.weekday() < 5 and d not in us_market_holidays(market=market)


def trading_days(start, end, market: str = "nyse") -> pd.DatetimeIndex:
    """All trading days in ``[start, end]`` inclusive for ``market``.

    ``market="cfe"`` is the right calendar for anything derived from the VIX futures
    panel; ``market="nyse"`` for anything derived from equity prices.
    """
    rng = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D")
    hol = us_market_holidays(market=market)
    mask = np.array([(ts.weekday() < 5) and (ts.date() not in hol) for ts in rng])
    return pd.DatetimeIndex(rng[mask])


def _prev_trading_day(d: _dt.date, market: str = "cfe") -> _dt.date:
    while not is_trading_day(d, market=market):
        d -= _dt.timedelta(days=1)
    return d


def vix_settlement_date(year: int, month: int) -> pd.Timestamp:
    """Final settlement date of the VX contract *expiring* in ``year``-``month``.

    Implements the contract spec directly: the Wednesday 30 days before the third
    Friday of the *following* calendar month, pulled back to the previous business
    day if that Wednesday or the reference Friday is a holiday.
    """
    nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
    third_friday = _nth_weekday(nxt_y, nxt_m, 4, 3)
    settle = third_friday - _dt.timedelta(days=30)
    # By construction ``settle`` is a Wednesday; verify rather than assume.
    if settle.weekday() != 2:
        raise AssertionError(f"expected Wednesday, got {settle} ({settle.weekday()})")
    hol = us_market_holidays(market="cfe")
    if (third_friday in hol) or (settle in hol):
        settle = _prev_trading_day(settle - _dt.timedelta(days=1))
    return pd.Timestamp(settle)


def vix_settlement_dates(start, end) -> pd.DatetimeIndex:
    """All monthly VIX futures settlement dates whose value falls in ``[start, end]``."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    out: list[pd.Timestamp] = []
    y, m = start.year - 1, 1
    while y < end.year + 2:
        out.append(vix_settlement_date(y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    idx = pd.DatetimeIndex(sorted(out))
    return idx[(idx >= start) & (idx <= end)]


def build_roll_calendar(start, end, business_days=None, market: str = "cfe") -> pd.DataFrame:
    """Per-trading-day roll state for the S&P short-term VIX futures index.

    The index holds the two nearest monthly VX contracts and shifts weight from the
    near contract to the far contract linearly in *business days* across the roll
    period.

    Definitions follow the S&P Dow Jones Indices methodology:

    * A roll period begins on a VIX futures settlement date and runs up to, but
      excluding, the next settlement date.
    * ``dt`` = number of business days in the current roll period (from and including
      the settlement date that starts it, to but excluding the next settlement date).
    * ``dr`` = number of business days remaining, counted from the day *after* ``t``
      up to but excluding the next settlement date.
    * ``w1 = dr / dt`` on the near contract, ``w2 = 1 - w1`` on the far contract.

    On the settlement date itself ``dr = dt - 1``... note that different vendors
    implement the boundary with an off-by-one in either direction. Rather than
    asserting one convention is correct, this function returns the business-day
    counts and lets :mod:`svcarry.index.reconstruct` build weights under both the
    ``dr/dt`` and ``(dr+1)/dt`` conventions; the empirically correct one is selected
    by tracking-error validation against the traded products and the choice is
    recorded in ``docs/validation.md``.

    Returns
    -------
    DataFrame indexed by trading day with columns:
        ``near_expiry``      settlement date of the front contract held
        ``far_expiry``       settlement date of the second contract held
        ``roll_start``       settlement date that opened the current roll period
        ``roll_end``         settlement date that closes it (= ``near_expiry``)
        ``dt``               business days in the roll period
        ``dr``               business days remaining after today
        ``is_settlement``    True on a VIX futures settlement date
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if business_days is not None:
        # The caller supplies the days the index is actually computed on - in
        # practice, the dates present in the futures panel. Preferred over any
        # derived calendar, because it cannot disagree with the data.
        bd = pd.DatetimeIndex(pd.Series(pd.DatetimeIndex(business_days)).sort_values().unique())
        days = bd[(bd >= start) & (bd <= end)]
    else:
        days = trading_days(start, end, market=market)
    settles = vix_settlement_dates(start - pd.Timedelta(days=120), end + pd.Timedelta(days=400))
    settles = pd.DatetimeIndex(sorted(set(settles)))

    # Business-day ordinal for fast counting. Built on the same day set as `days`,
    # extended at both ends so the roll periods at the sample boundaries are countable.
    pad = trading_days(start - pd.Timedelta(days=200), end + pd.Timedelta(days=500),
                       market=market)
    if business_days is not None:
        all_days = pd.DatetimeIndex(sorted(set(pad[(pad < days.min()) | (pad > days.max())])
                                           | set(days)))
    else:
        all_days = pad
    ordinal = pd.Series(np.arange(len(all_days)), index=all_days)

    rows = []
    for d in days:
        # Roll period containing d: [s_k, s_{k+1}) where s_k <= d < s_{k+1}.
        pos = settles.searchsorted(d, side="right") - 1
        if pos < 0 or pos + 2 >= len(settles):
            continue
        roll_start = settles[pos]
        roll_end = settles[pos + 1]
        # On a settlement date the expiring contract has rolled off: the period that
        # *starts* today is the one we are in.
        near_expiry = roll_end
        far_expiry = settles[pos + 2]
        dt_ = int(ordinal.get(roll_end, np.nan) - ordinal.get(roll_start, np.nan))
        dr_ = int(ordinal.get(roll_end, np.nan) - ordinal.get(d, np.nan)) - 1
        rows.append(
            dict(
                date=d,
                near_expiry=near_expiry,
                far_expiry=far_expiry,
                roll_start=roll_start,
                roll_end=roll_end,
                dt=dt_,
                dr=dr_,
                is_settlement=bool(d in set(settles)),
            )
        )
    out = pd.DataFrame(rows).set_index("date")
    if not out.empty:
        bad = out[(out["dt"] <= 0) | (out["dr"] < 0) | (out["dr"] >= out["dt"])]
        if len(bad):
            raise ValueError(
                f"roll calendar produced {len(bad)} rows with invalid dr/dt; "
                f"first offender:\n{bad.head(1)}"
            )
    return out
