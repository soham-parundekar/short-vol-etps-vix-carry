# Phase 05 — Data acquisition

## 1. Objective

Build a downloader that another researcher can run to obtain exactly the data this
project used, and run it. End state: every raw file on disk, every file recorded in a
provenance manifest with its URL, retrieval time and SHA-256, and a summary of what
was fetched and what was not.

## 2. Context

Phase 04 verified the sources and their URL patterns. This phase turns them into a
pipeline. The two properties that matter are **idempotence** — re-running must not
re-download or produce a different result — and **provenance** — a reader must be able
to establish that the file in the repository is the file the source served.

## 3. Inputs

- `docs/data_sources.md` (verified patterns, rate limits, licensing)
- `config/config.yaml` → `sample.start`, `sample.end`, `project.contact`
- `config/filings.yaml`
- `svcarry.index.calendar` — the futures file names are *derived* from the contract
  specification, never scraped from a directory listing

## 4. Tasks

1. Implement the shared HTTP layer once: on-disk cache, per-host throttle, exponential
   backoff on 429/5xx, descriptive User-Agent with a contact address, and a manifest
   recording URL, UTC timestamp, status, byte count, content type and SHA-256.
2. Implement one downloader per source family, each returning a log of what it did
   rather than printing and forgetting.
3. For the futures: generate the monthly expiry dates from the calendar, request one
   file per expiry, and treat a 404 as data (the contract did not list) rather than as
   an error. Reach at least one year beyond the sample end so the second-month
   contract always exists.
4. For the prices: implement the preferred provider and a fallback, record which one
   served each symbol, and keep the raw payload rather than a parsed extract.
5. Implement `scripts/fetch_data.py` with one group per source family, `--only` and
   `--force` flags, a machine-readable summary, and a non-zero exit status on failure.
6. Run it. Record wall time, total bytes, and every failure.
7. Re-run it. Confirm nothing is re-downloaded and the manifest is unchanged.

## 5. Tools and methods

`requests` with a `Session`; `hashlib` for digests; the project's own calendar module.
No scraping of HTML listings where a structured pattern exists.

## 6. Execution instructions

Write the downloader so that failure is informative. A source that returns 403 should
produce a log entry naming the host and the status, not a stack trace three frames
deep. A source that is rate-limiting should back off, not retry immediately.

Never fabricate a payload. If a file cannot be retrieved, the pipeline records that it
could not, and every downstream phase must be able to run with that file absent or
stop with a clear message.

Store raw exactly as received. Parsing belongs to Phase 06; a downloader that parses
loses the ability to re-parse when the parse turns out to be wrong.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Coverage | one file per monthly expiry in the sample, gaps explained | a handful of pre-sample expiries missing | unexplained gaps |
| Manifest | every file present with URL, timestamp, size, SHA-256 | — | a file on disk that is not in the manifest |
| Idempotence | second run downloads nothing, manifest unchanged | — | second run changes files or hashes |
| Verification | `verify_manifest()` returns no problems | — | any hash mismatch |
| Rate limits | no 429 responses in the log | occasional 429 with successful backoff | sustained 429s |
| Payload sanity | each file parses and its date range matches Phase 04's finding | minor discrepancy, investigated | a file whose contents differ from what Phase 04 verified |

## 8. Self-review

- Does the file count match the number of monthly expiries the calendar generates?
- Does any file have a suspicious size (near-zero, or an HTML error page saved as CSV)?
- Was the raw payload stored, or a parsed extract?
- Does the pipeline silently succeed when a source is unreachable?
- Is the contact address in the User-Agent real?

## 9. Deliverables

- `src/svcarry/data/{http,cboe,prices,fred,edgar}.py`
- `scripts/fetch_data.py`
- `data/raw/**`, `data/raw/_manifest.json`, `data/raw/_fetch_summary.json`
- `references/filings/**` with `_index.json`

## 10. Git requirements

Commit the code, the manifest and the fetch summary. Do **not** commit `data/raw/**`
unless Phase 04's licensing decision permits it; the manifest plus the script is what
makes the data reproducible. Commit message states the number of files, the total
size, and the date range covered.

## 11. Completion gate

- [ ] Every source family has a downloader
- [ ] `scripts/fetch_data.py` runs end to end and exits non-zero on failure
- [ ] Manifest complete; `verify_manifest()` clean
- [ ] Second run is a no-op
- [ ] Every failure recorded with its reason
- [ ] File counts reconciled against the expiry calendar
- [ ] Raw data excluded from git per the licensing decision

## 12. Handoff

Phase 06 consumes `data/raw/**` and the manifest. It must be told which files are
known-missing and why, so that it does not interpret an absent contract as a data
quality problem.
