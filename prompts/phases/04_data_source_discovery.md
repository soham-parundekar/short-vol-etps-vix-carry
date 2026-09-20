# Phase 04 — Data source discovery and verification

## 1. Objective

Identify, **test** and document every dataset the design requires, before writing a
downloader against any of them. End state: `docs/data_sources.md` in which every row
describes a source that has been hit and shown to return what it claims.

## 2. Context

A data source that is easy to download is not thereby the right one. The project needs
per-contract VIX futures settlement history with open interest, Cboe index history,
ETP prices with correct split handling, a Treasury bill series on a specific quoting
convention, and SEC filings. Each has a preferred form and several inferior ones.

The failure mode to avoid: discovering in Phase 07 that the chosen price series is not
split-adjusted, or that the index history starts five years after the sample does.

## 3. Inputs

- `docs/research_design.md` §3 (the dataset table)
- Phase 01's per-host reachability findings

## 4. Tasks

1. For each dataset in the design, identify candidate sources in this order of
   preference: official API, official bulk download, public structured source,
   programmatic scraping, manual retrieval.
2. **Actually request each candidate** and record the status, the first few lines of
   the payload, and the earliest and latest dates present. A source is not verified
   until its content has been seen.
3. Resolve the URL *pattern* rather than a single URL: what varies (contract expiry,
   ticker, series id), and what the valid range of that variable is.
4. Check licensing and terms of use for each source, and decide per source whether the
   raw data may be redistributed in the repository. Record the decision and the
   reasoning.
5. Identify what each source does *not* give you: the earliest date, missing fields,
   known revisions, adjustments already applied.
6. Identify the specific hazards per dataset: split adjustment in the ETP prices,
   discount versus yield quoting in the bill series, the index history's start date,
   weekly versus monthly futures contracts.
7. Where a required series is unavailable for part of the sample, find and verify a
   substitute, and plan the overlap test that will show the two agree.
8. Write `docs/data_sources.md`.

## 5. Tools and methods

Direct HTTP requests; `svcarry.data.http.fetch` once the pattern is known. Respect
`robots.txt`, rate limits and terms. Send a descriptive User-Agent with a contact
address — SEC EDGAR requires it. Do not attempt to bypass authentication, paywalls or
anti-bot measures; if a source refuses, record the refusal and use a different source.

## 6. Execution instructions

Verify before building. One request per candidate source costs seconds; a downloader
written against an unverified assumption costs an afternoon.

Where two sources could serve, prefer the one whose provenance is clearest even if it
is harder to parse. Where a vendor has already applied an adjustment (splits,
dividends), prefer a source that exposes the raw series as well, so the adjustment can
be reproduced and checked rather than trusted.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Reachability | every source returns 200 with the expected content type | a source reachable only through a fallback provider | a source listed but never requested |
| Coverage | each series covers the sample window | a series starts late, substitute identified and verified | a gap discovered later, in a downstream phase |
| Pattern | the varying element and its valid range are documented | — | a single hard-coded URL standing in for a family |
| Licensing | redistribute/do-not-redistribute decided per source with reasoning | — | raw vendor data committed without checking |
| Hazards | split, quoting-convention and contract-type hazards named per dataset | — | any of them discovered in a later phase |

## 8. Self-review

- Has every source actually been requested, or has any been assumed from familiarity?
- For each series, what is the earliest date — and is it earlier than the sample start?
- For the ETP prices: is the series split-adjusted, and how is that going to be
  verified independently?
- For the bill series: discount rate or yield? The two differ by enough to matter in
  a total-return index.
- Are the futures files monthly expiries only, or do weekly contracts share the
  naming pattern?

## 9. Deliverables

`docs/data_sources.md`, with one section per dataset covering: source and URL pattern,
provider, variables and units, frequency, date range verified, access constraints and
licensing, required transformations, known limitations, and potential biases.

## 10. Git requirements

Commit `docs/data_sources.md` and any configuration listing sources. Do not commit
data in this phase. Commit message states how many sources were verified and names any
that could not be.

## 11. Completion gate

- [ ] Every dataset in the design has a verified source
- [ ] Every source has been requested and its payload inspected
- [ ] URL patterns and their valid ranges documented
- [ ] Licensing decision recorded per source
- [ ] Start dates checked against the sample window; substitutes verified where needed
- [ ] Per-dataset hazards named
- [ ] `docs/data_sources.md` complete

## 12. Handoff

Phase 05 consumes the verified URL patterns, the per-source rate limits and the
licensing decisions (which determine what may be cached in the repository). Phase 06
consumes the hazard list, which becomes its cleaning checklist.
