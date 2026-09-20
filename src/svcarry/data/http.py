"""Polite, cached HTTP retrieval with a provenance manifest.

Every byte that enters this project arrives through :func:`fetch`. That buys three
things that matter for a research repository:

* **Provenance.** Each download is recorded in ``data/raw/_manifest.json`` with its
  URL, retrieval timestamp, byte count and SHA-256. A reader can therefore verify
  that the file in front of them is the file that was downloaded, and re-running the
  pipeline months later makes any silent vendor revision visible as a hash change.
* **Reproducibility without hammering the source.** Responses are cached on disk;
  re-running an analysis does not re-download anything unless ``force=True`` or the
  cache has expired.
* **Courtesy.** A descriptive User-Agent with a contact address (required by SEC
  EDGAR, good manners everywhere else), a minimum interval between requests to the
  same host, and exponential backoff on 429/5xx.

Nothing here attempts to bypass authentication, paywalls or anti-bot measures; if a
source refuses access the failure is raised and recorded rather than worked around.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests

from ..config import PROJECT_ROOT, load_config

__all__ = ["fetch", "FetchResult", "manifest_path", "read_manifest", "verify_manifest"]

_MIN_INTERVAL = {"www.sec.gov": 0.15, "cdn.cboe.com": 0.10, "default": 0.05}
_last_request: dict[str, float] = {}
_session: requests.Session | None = None


@dataclass
class FetchResult:
    path: Path
    url: str
    from_cache: bool
    status: int | None
    sha256: str
    n_bytes: int


def _user_agent() -> str:
    try:
        contact = load_config().dotted("project.contact")
    except Exception:
        contact = "academic research"
    return f"svcarry/0.1 ({contact})"


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": _user_agent(),
                "Accept": "text/csv,application/json,text/html,*/*",
                "Accept-Encoding": "gzip, deflate",
            }
        )
        _session = s
    return _session


def _throttle(host: str) -> None:
    gap = _MIN_INTERVAL.get(host, _MIN_INTERVAL["default"])
    last = _last_request.get(host)
    if last is not None:
        wait = gap - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
    _last_request[host] = time.time()


def manifest_path() -> Path:
    p = PROJECT_ROOT / "data" / "raw" / "_manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_manifest() -> dict:
    mp = manifest_path()
    if mp.exists():
        with open(mp, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _write_manifest(entries: dict) -> None:
    with open(manifest_path(), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=1, sort_keys=True)


def fetch(
    url: str,
    dest: str | Path,
    force: bool = False,
    max_age_days: float | None = None,
    retries: int = 4,
    timeout: float = 60.0,
    allow_missing: bool = False,
    params: dict | None = None,
) -> FetchResult | None:
    """Download ``url`` to ``dest`` unless a fresh cached copy exists.

    Parameters
    ----------
    dest
        Destination path, absolute or relative to the project root.
    force
        Re-download even if a cached copy exists.
    max_age_days
        Treat a cached copy older than this as stale. ``None`` means never stale,
        which is the right default for fixed historical files (an expired VIX
        futures contract's settlement history does not change).
    allow_missing
        Return ``None`` on a 404 instead of raising. Used when probing for files
        that may legitimately not exist (e.g. a contract that never listed).
    """
    dest = Path(dest)
    if not dest.is_absolute():
        dest = PROJECT_ROOT / dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        stale = False
        if max_age_days is not None:
            age_days = (time.time() - dest.stat().st_mtime) / 86400.0
            stale = age_days > max_age_days
        if not stale:
            raw = dest.read_bytes()
            return FetchResult(dest, url, True, None, hashlib.sha256(raw).hexdigest(), len(raw))

    host = urlparse(url).netloc
    sess = _get_session()
    last_exc: Exception | None = None
    for attempt in range(retries):
        _throttle(host)
        try:
            resp = sess.get(url, timeout=timeout, params=params)
        except Exception as exc:                      # network-level failure
            last_exc = exc
            time.sleep(min(2.0 ** attempt, 20.0))
            continue
        if resp.status_code == 404 and allow_missing:
            return None
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2.0 ** attempt, 20.0))
            last_exc = RuntimeError(f"HTTP {resp.status_code} from {url}")
            continue
        resp.raise_for_status()
        content = resp.content
        dest.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()

        entries = read_manifest()
        entries[str(dest.relative_to(PROJECT_ROOT))] = {
            "url": resp.url,
            "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": resp.status_code,
            "bytes": len(content),
            "sha256": digest,
            "content_type": resp.headers.get("Content-Type", ""),
        }
        _write_manifest(entries)
        return FetchResult(dest, resp.url, False, resp.status_code, digest, len(content))

    raise RuntimeError(f"failed to fetch {url} after {retries} attempts") from last_exc


def verify_manifest(paths: Iterable[str] | None = None) -> list[dict]:
    """Re-hash cached files and report any that no longer match the manifest."""
    entries = read_manifest()
    problems: list[dict] = []
    keys = list(entries) if paths is None else list(paths)
    for k in keys:
        rec = entries.get(k)
        p = PROJECT_ROOT / k
        if rec is None:
            problems.append({"path": k, "issue": "not in manifest"})
            continue
        if not p.exists():
            problems.append({"path": k, "issue": "file missing"})
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != rec["sha256"]:
            problems.append(
                {"path": k, "issue": "hash mismatch",
                 "expected": rec["sha256"], "found": digest}
            )
    return problems
