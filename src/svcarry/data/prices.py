"""Daily OHLCV for the exchange-traded products and the S&P 500.

Two free providers are supported and tried in order. Which one actually served each
symbol is recorded in the returned frame's ``.attrs['provider']`` and in the raw
manifest, because the two differ in one respect that matters:

* **Yahoo Finance** (``query2.finance.yahoo.com/v8/finance/chart``) returns raw OHLC
  plus an ``adjclose`` series and explicit split events.
* **Stooq** (``stooq.com/q/d/l``) returns OHLCV already adjusted for splits.

Splits are not a detail here. VXX and UVXY have each been reverse-split many times -
a long-volatility product that decays by 50-80% a year has to be - and an
unadjusted VXX price series shows enormous fake positive returns on split dates. Any
comparison of a reconstructed index against a traded product is meaningless unless
the split adjustment is right, so :func:`load_prices` returns both the raw and the
adjusted series and :func:`split_adjusted_returns` states which one it used.

Dividends are a non-issue for these particular products (the commodity pools and
ETNs do not distribute), but the adjustment is applied generically anyway so that
SPY and the PutWrite benchmark are handled correctly.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import load_config
from .http import fetch

__all__ = ["download_prices", "load_prices", "split_adjusted_returns", "SYMBOLS"]

YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
STOOQ_URL = "https://stooq.com/q/d/l/"

#: Symbols used in the project and why.
SYMBOLS = {
    "VXX": "iPath long 1x short-term VIX futures ETN - index tracking validation",
    "VIXY": "ProShares long 1x short-term VIX futures ETF - index tracking validation",
    "SVXY": "ProShares inverse short-term VIX futures ETF - the -1x/-0.5x survivor",
    "UVXY": "ProShares 2x/1.5x long short-term VIX futures ETF - leverage decay test",
    "SVIX": "Volatility Shares -1x short-term VIX futures ETF - post-2018 re-offering",
    "SPY": "S&P 500 ETF - OHLC for range-based realised variance and as a benchmark",
    "^GSPC": "S&P 500 index - realised variance without the ETF's dividend effects",
    "^VIX": "VIX index via the price provider - cross-check on the Cboe file",
}

_STOOQ_MAP = {"^GSPC": "^spx", "^VIX": "^vix"}


def _raw_dir() -> Path:
    return load_config().get_path("paths.raw") / "prices"


# --------------------------------------------------------------------- download
def download_prices(
    symbol: str,
    start="2004-01-01",
    end=None,
    force: bool = False,
    providers: tuple[str, ...] = ("yahoo", "stooq"),
    max_age_days: float = 1.0,
) -> dict:
    """Download one symbol, trying each provider in turn.

    Returns a record describing what happened, including the provider that served
    the data. A provider that fails (rate limit, auth wall, empty payload) is logged
    and the next one is tried; nothing here attempts to defeat an access control.
    """
    end = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()
    start = pd.Timestamp(start)
    errors: dict[str, str] = {}

    for provider in providers:
        try:
            if provider == "yahoo":
                dest = _raw_dir() / "yahoo" / f"{symbol.replace('^', '_')}.json"
                p1 = int(start.tz_localize("UTC").timestamp())
                p2 = int((end + pd.Timedelta(days=1)).tz_localize("UTC").timestamp())
                url = YAHOO_URL.format(symbol=symbol)
                res = fetch(
                    url, dest, force=force, max_age_days=max_age_days,
                    params={"period1": p1, "period2": p2, "interval": "1d",
                            "events": "div,split", "includeAdjustedClose": "true"},
                )
                payload = json.loads(dest.read_text(encoding="utf-8", errors="replace"))
                if payload.get("chart", {}).get("error"):
                    raise RuntimeError(str(payload["chart"]["error"])[:200])
                if not payload.get("chart", {}).get("result"):
                    raise RuntimeError("empty chart result")
                return {"symbol": symbol, "provider": "yahoo", "path": str(dest),
                        "bytes": res.n_bytes, "from_cache": res.from_cache}

            if provider == "stooq":
                s = _STOOQ_MAP.get(symbol, f"{symbol.lower()}.us")
                dest = _raw_dir() / "stooq" / f"{symbol.replace('^', '_')}.csv"
                res = fetch(
                    STOOQ_URL, dest, force=force, max_age_days=max_age_days,
                    params={"s": s, "i": "d",
                            "d1": start.strftime("%Y%m%d"), "d2": end.strftime("%Y%m%d")},
                )
                head = dest.read_text(encoding="utf-8", errors="replace")[:200]
                if "Date" not in head:
                    raise RuntimeError(f"unexpected payload: {head[:80]!r}")
                return {"symbol": symbol, "provider": "stooq", "path": str(dest),
                        "bytes": res.n_bytes, "from_cache": res.from_cache}
        except Exception as exc:
            errors[provider] = str(exc)[:200]
            time.sleep(0.5)

    return {"symbol": symbol, "provider": None, "errors": errors}


# ------------------------------------------------------------------------ load
def _load_yahoo(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    res = payload["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    # Yahoo timestamps are exchange-open instants; the trading *date* in New York is
    # what we need, so convert before dropping the time component.
    idx = ts.tz_convert("America/New_York").normalize().tz_localize(None)
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {k: q.get(k) for k in ("open", "high", "low", "close", "volume")}, index=idx
    )
    adj = res["indicators"].get("adjclose")
    df["adjclose"] = adj[0]["adjclose"] if adj else df["close"]
    events = res.get("events", {})
    splits = events.get("splits", {}) or {}
    sp = pd.Series(
        {pd.Timestamp(int(v["date"]), unit="s", tz="UTC")
         .tz_convert("America/New_York").normalize().tz_localize(None):
         float(v["numerator"]) / float(v["denominator"]) for v in splits.values()},
        dtype=float,
    )
    df.attrs["splits"] = sp.sort_index() if len(sp) else pd.Series(dtype=float)
    df.attrs["provider"] = "yahoo"
    return df


def _load_stooq(path: Path) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(path.read_text(encoding="utf-8", errors="replace")))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["adjclose"] = df["close"]       # Stooq series are already split-adjusted
    df.attrs["splits"] = pd.Series(dtype=float)
    df.attrs["provider"] = "stooq"
    return df


def load_prices(symbol: str, provider: str | None = None) -> pd.DataFrame:
    """Load a cached price series, preferring Yahoo if both providers are cached."""
    stem = symbol.replace("^", "_")
    y = _raw_dir() / "yahoo" / f"{stem}.json"
    s = _raw_dir() / "stooq" / f"{stem}.csv"
    order = [provider] if provider else ["yahoo", "stooq"]
    for p in order:
        if p == "yahoo" and y.exists():
            try:
                return _load_yahoo(y)
            except Exception:
                continue
        if p == "stooq" and s.exists():
            return _load_stooq(s)
    raise FileNotFoundError(
        f"no cached price file for {symbol}; run scripts/fetch_data.py first"
    )


def split_adjusted_returns(df: pd.DataFrame, prefer: str = "adjclose") -> pd.Series:
    """Daily simple returns corrected for splits and distributions.

    ``prefer='adjclose'`` uses the provider's adjusted close, which is the right
    choice when it is available and trustworthy. ``prefer='manual'`` instead rebuilds
    the adjustment from the raw close and the recorded split factors, which is used
    in ``docs/validation.md`` to confirm that the provider's adjustment agrees with
    an independent reconstruction.
    """
    if prefer == "adjclose" and "adjclose" in df.columns and df["adjclose"].notna().any():
        px = df["adjclose"].astype(float)
        return px.pct_change().rename("ret")

    px = df["close"].astype(float)
    splits: pd.Series = df.attrs.get("splits", pd.Series(dtype=float))
    factor = pd.Series(1.0, index=px.index)
    for d, ratio in splits.items():
        # a 1-for-4 reverse split arrives as numerator/denominator = 0.25
        factor.loc[factor.index < d] *= ratio
    adj = px * factor
    return adj.pct_change().rename("ret")
