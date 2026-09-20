#!/usr/bin/env python3
"""Download every dataset the project needs.

Run once; everything is cached on disk with a provenance manifest, so re-running is
cheap and idempotent. Nothing downstream in the repository reaches the network.

    python scripts/fetch_data.py                 # everything
    python scripts/fetch_data.py --only futures  # one group
    python scripts/fetch_data.py --force         # ignore the cache

Groups
------
futures   per-contract Cboe VX settlement history (one file per monthly expiry)
indices   Cboe VIX, VIX3M, VIX9D, VIX6M, VVIX, PUT, BXM
prices    ETP and equity OHLCV (Yahoo Finance, falling back to Stooq)
rates     FRED Treasury bill series
filings   SEC EDGAR primary documents listed in config/filings.yaml

Exit status is non-zero if any group failed outright, so this is safe to use in a
Makefile.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from svcarry.config import load_config
from svcarry.data import cboe, edgar, fred, prices
from svcarry.data.http import read_manifest

GROUPS = ("futures", "indices", "prices", "rates", "filings")


def run_futures(cfg, force: bool) -> dict:
    start = cfg.dotted("sample.start")
    end = cfg.dotted("sample.end") or pd.Timestamp.today().normalize()
    # Reach one year beyond the sample end so the second-month contract always exists.
    log = cboe.download_vx_contracts(start, pd.Timestamp(end) + pd.DateOffset(years=1),
                                     force=force)
    counts = log["status"].value_counts().to_dict()
    return {"group": "futures", "n_contracts": len(log), **counts}


def run_indices(cfg, force: bool) -> dict:
    got, missing = [], []
    for name in cboe.CBOE_INDICES:
        res = cboe.download_cboe_index(name, force=force)
        (got if res is not None else missing).append(name)
    return {"group": "indices", "downloaded": got, "missing": missing}


def run_prices(cfg, force: bool) -> dict:
    start = cfg.dotted("sample.start")
    rows = []
    for sym in prices.SYMBOLS:
        # Products launched later still get the full window requested; the provider
        # simply returns a shorter series, which is the honest representation of
        # the product's actual life.
        rows.append(prices.download_prices(sym, start="2004-01-01", force=force))
        time.sleep(0.2)
    ok = [r["symbol"] for r in rows if r.get("provider")]
    bad = {r["symbol"]: r.get("errors") for r in rows if not r.get("provider")}
    return {"group": "prices", "ok": ok, "failed": bad}


def run_rates(cfg, force: bool) -> dict:
    got, missing = [], []
    for sid in fred.FRED_SERIES:
        try:
            fred.download_fred(sid, force=force)
            got.append(sid)
        except Exception as exc:
            missing.append({sid: str(exc)[:160]})
    return {"group": "rates", "downloaded": got, "failed": missing}


def run_filings(cfg, force: bool) -> dict:
    df = edgar.download_filings(force=force)
    return {"group": "filings", "n": len(df),
            "status": df["status"].value_counts().to_dict()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=GROUPS, default=list(GROUPS))
    ap.add_argument("--force", action="store_true", help="ignore cached copies")
    args = ap.parse_args()

    cfg = load_config()
    runners = {
        "futures": run_futures, "indices": run_indices, "prices": run_prices,
        "rates": run_rates, "filings": run_filings,
    }

    summary, failures = [], []
    for g in args.only:
        print(f"\n=== {g} " + "=" * (60 - len(g)))
        t0 = time.time()
        try:
            rec = runners[g](cfg, args.force)
            rec["seconds"] = round(time.time() - t0, 1)
            summary.append(rec)
            print(json.dumps(rec, indent=1, default=str))
        except Exception as exc:
            failures.append(g)
            print(f"FAILED: {type(exc).__name__}: {exc}")

    man = read_manifest()
    total_bytes = sum(v.get("bytes", 0) for v in man.values())
    print(
        f"\n=== manifest ===\n{len(man)} files, {total_bytes/1e6:.1f} MB, "
        f"recorded in data/raw/_manifest.json"
    )
    out = Path(__file__).resolve().parents[1] / "data" / "raw" / "_fetch_summary.json"
    out.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    if failures:
        print(f"\nFAILED GROUPS: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
