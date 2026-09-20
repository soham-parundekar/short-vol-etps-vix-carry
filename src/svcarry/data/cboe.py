"""Cboe data: VIX futures settlement history and Cboe index history.

Two families of file are used, both published by Cboe without registration.

**Per-contract futures history.**
``https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_<settlement>.csv``
returns the complete daily history of a single VX contract, keyed by its final
settlement date, with columns

    Trade Date, Futures, Open, High, Low, Close, Settle, Change, Total Volume,
    EFP, Open Interest

Requesting by settlement date rather than by trade date means the number of
requests scales with the number of *contracts* (roughly twelve a year) rather than
the number of trading days, and the resulting panel is naturally organised the way
the index reconstruction needs it. The settlement dates themselves come from
:mod:`svcarry.index.calendar`, which derives them from the contract specification -
the file names are never guessed by scraping a directory listing.

**Index history.**
``https://cdn.cboe.com/api/global/us_indices/daily_prices/<NAME>_History.csv`` with
``DATE, OPEN, HIGH, LOW, CLOSE`` (single-column ``DATE, <NAME>`` for some of the
strategy benchmark indices).

Only monthly VX contracts are downloaded. Cboe also lists weekly VX expiries, but
the S&P short-term index is defined on the monthly cycle, and mixing weeklies into
the front-two-contract panel would change what is being reconstructed.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import load_config
from ..index.calendar import MONTH_CODES, vix_settlement_dates
from .http import fetch

__all__ = [
    "VX_URL",
    "LEGACY_VX_URL",
    "INDEX_URL",
    "legacy_vx_url",
    "download_vx_contracts",
    "load_vx_panel",
    "download_cboe_index",
    "load_cboe_index",
    "CBOE_INDICES",
]

VX_URL = (
    "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/"
    "VX_{settlement}.csv"
)

#: Cboe serves the modern per-expiry files only for contracts expiring from roughly
#: January 2013 onward. Earlier contracts live in a legacy archive keyed by the CME
#: month code and a two-digit year rather than by settlement date, and dated
#: MM/DD/YYYY rather than ISO. Both are downloaded into the same local naming scheme
#: (``VX_<settlement>.csv``) so that nothing downstream needs to know which endpoint
#: served a given contract; which one did is recorded in the raw manifest.
LEGACY_VX_URL = (
    "https://cdn.cboe.com/resources/futures/archive/volume-and-price/"
    "CFE_{code}{yy}_VX.csv"
)


def legacy_vx_url(settlement) -> str:
    """Legacy archive URL for the contract expiring in ``settlement``'s month.

    A VX contract's final settlement date always falls inside its own expiry month,
    so the month code and year come directly from the settlement date.
    """
    s = pd.Timestamp(settlement)
    return LEGACY_VX_URL.format(code=MONTH_CODES[s.month], yy=f"{s.year % 100:02d}")
INDEX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"

#: Cboe index series used in this project, with what each is for.
CBOE_INDICES = {
    "VIX": "30-day implied volatility of SPX options; the short leg of the VRP",
    "VIX3M": "93-day implied volatility; the VIX/VIX3M ratio is the term-structure signal",
    "VIX9D": "9-day implied volatility; robustness on the slope definition",
    "VIX6M": "6-month implied volatility; robustness on the slope definition",
    "VVIX": "volatility of VIX; used to describe the 5 Feb 2018 environment",
    "PUT": "Cboe S&P 500 PutWrite Index; the option-selling benchmark",
    "BXM": "Cboe S&P 500 BuyWrite Index; secondary option-selling benchmark",
}

_VX_COLUMNS = {
    "Trade Date": "date",
    "Futures": "contract",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Settle": "settle",
    "Change": "change",
    "Total Volume": "volume",
    "EFP": "efp",
    "Open Interest": "open_interest",
}


def _raw_dir() -> Path:
    return load_config().get_path("paths.raw")


def download_vx_contracts(
    start, end, force: bool = False, verbose: bool = True
) -> pd.DataFrame:
    """Download every monthly VX contract whose settlement falls in ``[start, end]``.

    Returns a log DataFrame with one row per contract: the settlement date, whether
    the file was already cached, its size and hash, or the reason it was skipped.
    Contracts that 404 are recorded rather than raising, because the very earliest
    and the not-yet-listed expiries legitimately have no file.
    """
    settles = vix_settlement_dates(start, end)
    out_dir = _raw_dir() / "cboe" / "vx"
    rows = []
    for s in settles:
        tag = s.strftime("%Y-%m-%d")
        dest = out_dir / f"VX_{tag}.csv"

        # Modern per-expiry endpoint first, legacy archive as a fallback. The two
        # cover different eras (roughly 2013 onward, and 2004-2013 respectively),
        # so a failure on one is expected rather than exceptional.
        res, source, detail = None, None, None
        for label, url in (("modern", VX_URL.format(settlement=tag)),
                           ("legacy", legacy_vx_url(s))):
            try:
                res = fetch(url, dest, force=force, allow_missing=True)
            except Exception as exc:
                detail = f"{label}: {type(exc).__name__}: {str(exc)[:120]}"
                res = None
            if res is not None:
                source = label
                break

        if res is None:
            rows.append(dict(settlement=s, status="unavailable",
                             detail=detail or "not served by either endpoint"))
            if verbose:
                print(f"  VX_{tag}.csv  unavailable ({detail or '404 on both'})")
            continue

        rows.append(
            dict(settlement=s, status="cached" if res.from_cache else "downloaded",
                 source=source, bytes=res.n_bytes, sha256=res.sha256[:12],
                 path=str(dest))
        )
        if verbose and not res.from_cache:
            print(f"  VX_{tag}.csv  {res.n_bytes:,} bytes  [{source}]")

    log = pd.DataFrame(rows)
    if verbose and len(log):
        print(log["status"].value_counts().to_string())
        if "source" in log.columns:
            print(log["source"].value_counts(dropna=True).to_string())
    return log


def _parse_vx_file(path: Path, settlement: pd.Timestamp) -> pd.DataFrame:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    # Some files carry a leading blank line or a stray BOM.
    df = pd.read_csv(io.StringIO(raw), skip_blank_lines=True)
    df = df.rename(columns={c: _VX_COLUMNS.get(c.strip(), c.strip()) for c in df.columns})
    missing = {"date", "settle"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing expected columns {missing}")

    # The two Cboe endpoints date their rows differently: the modern per-expiry files
    # use ISO (2018-02-05), the legacy archive uses US order (02/05/2018). Parse each
    # with an explicit format rather than letting pandas infer, because inference on a
    # file whose first rows happen to be ambiguous (03/04/2013) would silently swap
    # day and month for part of the sample.
    raw_dates = df["date"].astype(str).str.strip()
    fmt = "%m/%d/%Y" if raw_dates.str.contains("/").mean() > 0.5 else "%Y-%m-%d"
    df["date"] = pd.to_datetime(raw_dates, format=fmt, errors="coerce")
    n_unparsed = int(df["date"].isna().sum())
    if n_unparsed:
        # Fall back only for the stragglers, and only after the deterministic pass.
        df.loc[df["date"].isna(), "date"] = pd.to_datetime(
            raw_dates[df["date"].isna()], errors="coerce"
        )
    df = df.dropna(subset=["date"])
    for c in ("open", "high", "low", "close", "settle", "change", "volume",
              "efp", "open_interest"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["expiry"] = settlement
    keep = [c for c in ["date", "expiry", "contract", "open", "high", "low", "close",
                        "settle", "volume", "open_interest"] if c in df.columns]
    return df[keep]


def load_vx_panel(start=None, end=None, verbose: bool = False) -> pd.DataFrame:
    """Assemble every cached VX contract file into one long panel.

    Returns columns ``date, expiry, settle, open, high, low, close, volume,
    open_interest, days_to_expiry``, sorted by ``date`` then ``expiry``, with
    duplicates removed and zero settlement prices treated as missing.

    Data-quality decisions made here, all of them logged in ``docs/methodology.md``:

    * ``settle == 0`` is a placeholder Cboe uses on days a contract had no activity
      before listing; it is set to NaN rather than carried, because a zero price
      would silently produce a -100% return in the index reconstruction.
    * Rows dated after a contract's own settlement date are dropped (they appear in
      a handful of files as trailing artefacts).
    * Nothing is forward-filled at this stage. Gap handling is the cleaning step's
      job and is done where it can be documented and tested.
    """
    cfg = load_config()
    start = start or cfg.dotted("sample.start")
    end = end or (cfg.dotted("sample.end") or pd.Timestamp.today().normalize())
    d = _raw_dir() / "cboe" / "vx"
    files = sorted(d.glob("VX_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"no VX contract files in {d}; run scripts/fetch_data.py first"
        )
    frames = []
    for f in files:
        settlement = pd.Timestamp(f.stem.split("_")[1])
        try:
            frames.append(_parse_vx_file(f, settlement))
        except Exception as exc:
            if verbose:
                print(f"  skipping {f.name}: {exc}")
    panel = pd.concat(frames, ignore_index=True)

    panel.loc[panel["settle"] <= 0, "settle"] = np.nan
    for c in ("open", "high", "low", "close"):
        if c in panel.columns:
            panel.loc[panel[c] <= 0, c] = np.nan

    panel = panel[panel["date"] <= panel["expiry"]]
    panel = panel.drop_duplicates(subset=["date", "expiry"], keep="last")
    panel = panel.sort_values(["date", "expiry"]).reset_index(drop=True)
    panel["days_to_expiry"] = (panel["expiry"] - panel["date"]).dt.days

    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    return panel[(panel["date"] >= lo) & (panel["date"] <= hi)].reset_index(drop=True)


def download_cboe_index(name: str, force: bool = False, max_age_days: float = 1.0):
    """Download one Cboe index history CSV."""
    if name not in CBOE_INDICES:
        raise ValueError(f"unknown Cboe index {name!r}; known: {sorted(CBOE_INDICES)}")
    url = INDEX_URL.format(name=name)
    dest = _raw_dir() / "cboe" / "indices" / f"{name}_History.csv"
    return fetch(url, dest, force=force, max_age_days=max_age_days, allow_missing=True)


def load_cboe_index(name: str) -> pd.DataFrame:
    """Load a cached Cboe index CSV into a tidy frame indexed by date.

    Handles both the OHLC layout (``DATE, OPEN, HIGH, LOW, CLOSE``) and the
    close-only layout (``DATE, <NAME>``) that the strategy benchmark indices use.
    """
    path = _raw_dir() / "cboe" / "indices" / f"{name}_History.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run scripts/fetch_data.py first")
    text = path.read_text(encoding="utf-8", errors="replace")
    # A few of these files carry descriptive preamble lines before the header.
    lines = text.splitlines()
    hdr = next(
        (i for i, ln in enumerate(lines) if ln.strip().upper().startswith("DATE")), 0
    )
    df = pd.read_csv(io.StringIO("\n".join(lines[hdr:])))
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if list(df.columns) == [name.lower()]:
        df = df.rename(columns={name.lower(): "close"})
    df = df[~df.index.duplicated(keep="last")]
    return df
