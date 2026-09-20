"""Risk-free rates from FRED.

Two series are used.

``DTB3``   3-month Treasury bill, **secondary market discount rate**, daily.
``DGS3MO`` 3-month Treasury constant-maturity **yield**, daily.

The distinction matters. The S&P VIX futures total-return indices, and the Daily
Accrual term in the VelocityShares ETN formula, are both defined on the 91-day
Treasury bill *discount* rate, with the accrual

    TBR_t = ( 1 / (1 - (91/360) * TBAR_{t-1}) ) ^ (delta_t / 91) - 1

where ``TBAR_{t-1}`` is the previous business day's discount rate as a decimal and
``delta_t`` the number of calendar days since the previous index business day. That
is what :func:`tbill_accrual` implements, so the reconstructed total-return index
and the collateral leg of the backtest use the same convention as the products they
are being compared with, rather than a generic "cash return".
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import load_config
from .http import fetch

__all__ = ["download_fred", "load_fred", "tbill_accrual", "FRED_SERIES"]

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

FRED_SERIES = {
    "DTB3": "3-month Treasury bill secondary market discount rate (daily, % p.a.)",
    "DGS3MO": "3-month Treasury constant maturity yield (daily, % p.a.)",
    "DFF": "effective federal funds rate (daily, %) - robustness on the cash leg",
}


def _raw_dir() -> Path:
    return load_config().get_path("paths.raw") / "fred"


def download_fred(series_id: str, force: bool = False, max_age_days: float = 1.0):
    if series_id not in FRED_SERIES:
        raise ValueError(f"unknown FRED series {series_id!r}")
    dest = _raw_dir() / f"{series_id}.csv"
    return fetch(FRED_URL, dest, force=force, max_age_days=max_age_days,
                 params={"id": series_id})


def load_fred(series_id: str) -> pd.Series:
    """Load a cached FRED series as a float Series in percent per annum.

    FRED writes ``.`` for non-observations (holidays and bank closures); those become
    NaN here and are *not* filled at load time. Filling is the caller's decision and
    is done explicitly in :func:`tbill_accrual`.
    """
    path = _raw_dir() / f"{series_id}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run scripts/fetch_data.py first")
    df = pd.read_csv(io.StringIO(path.read_text(encoding="utf-8", errors="replace")))
    df.columns = [c.strip() for c in df.columns]
    date_col = df.columns[0]           # 'DATE' historically, 'observation_date' now
    val_col = [c for c in df.columns if c.upper() != date_col.upper()][0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    s = pd.to_numeric(df[val_col].replace(".", np.nan), errors="coerce")
    out = pd.Series(s.to_numpy(), index=pd.DatetimeIndex(df[date_col]), name=series_id)
    return out[~out.index.isna()].sort_index()


def tbill_accrual(
    discount_rate_pct: pd.Series, index_dates: pd.DatetimeIndex
) -> pd.Series:
    """Daily total-return accrual on 91-day Treasury bills, S&P DJI convention.

        TBR_t = ( 1 / (1 - (91/360) TBAR_{t-1}) ) ^ (delta_t / 91) - 1

    ``discount_rate_pct`` is the quoted discount rate in percent (e.g. ``4.85``).
    The previous *business day's* rate is used, which is both what the methodology
    specifies and what makes the series usable in real time: the accrual credited on
    day ``t`` is known at the close of ``t - 1``.

    Missing rates are forward-filled for up to five business days (bank holidays that
    are not exchange holidays) and the number of filled observations is attached to
    the result's ``.attrs``.
    """
    r = discount_rate_pct.reindex(
        discount_rate_pct.index.union(index_dates)
    ).sort_index()
    n_missing_before = int(r.reindex(index_dates).isna().sum())
    r = r.ffill(limit=5)
    rate = r.reindex(index_dates) / 100.0
    prev_rate = rate.shift(1)

    delta = pd.Series(index_dates, index=index_dates).diff().dt.days.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        base = 1.0 / (1.0 - (91.0 / 360.0) * prev_rate)
        accr = base ** (delta / 91.0) - 1.0
    accr = accr.rename("tbill_accrual")
    accr.attrs["n_missing_before_fill"] = n_missing_before
    accr.attrs["n_still_missing"] = int(accr.isna().sum()) - 1  # first row is NaN by design
    return accr
