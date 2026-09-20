"""SEC EDGAR: archive the product filings the project's terms are taken from.

The project's claims about product terms - the daily leverage, the fee, the
acceleration clause, the change from -1x to -0.5x - are only as good as their
sources. This module downloads the primary documents into ``references/filings/``
and writes a machine-readable index, so that a reader can check any stated term
against the filing rather than against this repository's prose.

EDGAR's fair-access policy requires a descriptive User-Agent with a contact address
and asks for no more than ten requests a second; :mod:`svcarry.data.http` supplies
the header and throttles below that limit. No authentication, no paywall, nothing to
circumvent - these documents are public.

The filing list lives in ``config/filings.yaml`` rather than in code, so that adding
a source is a data change and the bibliography can be generated from it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from ..config import PROJECT_ROOT, load_config
from .http import fetch

__all__ = ["load_filing_list", "download_filings", "company_submissions", "filing_index"]

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_LIST = PROJECT_ROOT / "config" / "filings.yaml"


def _filings_dir() -> Path:
    return load_config().get_path("paths.filings")


def load_filing_list() -> list[dict]:
    with open(FILING_LIST, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["filings"]


def download_filings(force: bool = False, verbose: bool = True) -> pd.DataFrame:
    """Download every filing listed in ``config/filings.yaml``."""
    rows = []
    for spec in load_filing_list():
        dest = _filings_dir() / spec["local_name"]
        try:
            res = fetch(spec["url"], dest, force=force, allow_missing=True)
        except Exception as exc:
            rows.append({**spec, "status": "error", "detail": str(exc)[:200]})
            continue
        if res is None:
            rows.append({**spec, "status": "missing (404)"})
            continue
        rows.append({
            **spec,
            "status": "cached" if res.from_cache else "downloaded",
            "bytes": res.n_bytes,
            "sha256": res.sha256,
        })
        if verbose and not res.from_cache:
            print(f"  {spec['local_name']}  {res.n_bytes:,} bytes")
    df = pd.DataFrame(rows)
    idx = _filings_dir() / "_index.json"
    idx.write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    return df


def company_submissions(cik: int, force: bool = False) -> dict:
    """Fetch an issuer's EDGAR submission history (used to locate 10-K filings)."""
    dest = load_config().get_path("paths.raw") / "edgar" / f"CIK{cik:010d}.json"
    fetch(SUBMISSIONS_URL.format(cik=cik), dest, force=force, max_age_days=7.0)
    return json.loads(dest.read_text(encoding="utf-8", errors="replace"))


def filing_index() -> pd.DataFrame:
    """Read back the index written by :func:`download_filings`."""
    p = _filings_dir() / "_index.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found; run scripts/fetch_data.py first")
    return pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
