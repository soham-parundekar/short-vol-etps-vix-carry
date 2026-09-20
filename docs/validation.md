# Validation record

What this file is for: every claim in this project that something is *correct* has
to point at a test that could have failed and did not. This is the register of
those tests. It is written in the order the checks run, from the calendar through
the raw files to the reconstructed index, and it records the checks that **failed**
as prominently as the ones that passed, because the failures are what changed the
code.

The standard applied throughout: a script completing is not evidence that its output
is right. Each section below states the specific proposition, the independent
quantity it was compared against, and the number that came back.

Reproduce everything here with

```
python scripts/fetch_data.py            # raw files + retrieval manifest
python scripts/run_pipeline.py --only clean index
python scripts/run_tests.py
```

---

## V1. The settlement and roll calendar

**Proposition.** `svcarry.index.calendar.vix_settlement_date` derives VIX futures
final settlement dates from the contract specification — the Wednesday thirty days
before the third Friday of the following month, pulled back to the preceding
business day when that Wednesday is an exchange holiday — without consulting any
list of dates.

**Test.** Derive every monthly settlement date from January 2008 to May 2027 and
compare the set against the set of per-contract files Cboe actually serves. The
file names are keyed by settlement date, so a calendar error shows up as a request
that 404s or a file that is never requested. Neither list was used to build the
other.

**Result.** 233 derived dates, 233 files served, zero discrepancies in either
direction.

**What this does and does not establish.** It establishes that the settlement dates
are right, which fixes the roll period boundaries. It does not establish that the
roll *weights* inside each period are right; that is V5.

### V1a. A calendar bug this check did not catch

The NYSE observance rule for a holiday falling on a Saturday is to close the
preceding Friday — **except** when that Friday is the last trading day of the year,
which stays open. The first implementation omitted the exception and closed
2010-12-31 and 2021-12-31. The settlement-date check above passed anyway, because
neither date is a settlement date.

It was caught by a different property: both dates carry settlement prices and real
volume in the futures files. A day the calendar calls closed cannot have a
settlement price. That is now a test (`tests/test_calendar.py`).

**Lesson recorded deliberately:** a check that passes is evidence about the
proposition it tests and nothing else.

---

## V2. Integrity of the raw files

**Proposition.** The files the analysis reads are byte-for-byte the files that were
downloaded from the recorded URLs.

**Test.** `svcarry.data.http` writes a manifest entry per file — source URL,
retrieval timestamp, byte count, SHA-256 — at download time. `verify_manifest()`
re-hashes every file on disk and reports any that are missing or altered. The
manifest is committed (`data/raw/_manifest.json`); the vendor data itself is not
redistributed.

**Result.** 338 recorded files. 331 verify byte-for-byte. The 7 that do not appear
locally are the SEC filings, which are still on the author's machine and have not
been staged into this environment; they are listed as missing rather than silently
passed. No file that is present differs from its recorded hash.

### V2a. A verification bug

The first run reported all 258 entries missing. The manifest had been written on
Windows, so its keys carried backslash separators, and the check ran on Linux.
Fixed by normalising to POSIX separators on both write and read. Worth recording
because the failure mode was a verifier that reported catastrophe when the data was
fine — the symmetric error to a verifier that reports success when it is not.

---

## V3. Assembling the futures panel

Three defects, all found by inspecting the assembled panel rather than by watching
the code run, and all sharing the property that the pipeline completed and produced
a plausibly-shaped frame.

### V3a. Fourteen legacy files dropped in silence

From the July-2013 expiry onward, Cboe's legacy archive prefixes each CSV with a
one-line legal disclaimer above the header. `_parse_vx_file` read that line as the
header, failed its required-column check, and `load_vx_panel` swallowed the
exception in a bare `except` that only printed under `verbose=True`.

Fixed by locating the header row explicitly. The broader fix is that a file which
cannot be parsed now **raises** by default (`strict=True`); silently continuing past
unreadable input is what allowed this to persist.

### V3b. Placeholder settlement prices winning the merge

Cboe's modern per-expiry archive publishes `Settle = 0` for every session from
**2013-01-02 to 2013-07-19** while populating `Open`, `High`, `Low`, `Close`,
`Volume` and `Open Interest` normally — 852 (date, expiry) cells across 98 sessions.

Zeros were correctly converted to NaN. But the conversion ran *after*
de-duplication, and the de-duplication rule was "the modern archive wins". So the
empty modern row beat the legacy row that carried the real price.

**Consequence before the fix:** 95 consecutive sessions, 2013-01-02 to 2013-05-17,
with **no contract priced at all**. The reconstruction returns NaN there and the
index level forward-fills across it. The index ran from 2008 to 2026 and looked
entirely normal.

Fixed by converting placeholders to NaN before de-duplicating and ordering the
preference *settlement price present first, modern archive second*. The legacy
archive supplies a price for 846 of the 852 placeholder cells (99.3%).

### V3c. The December 2012 gap

Related and found first: the modern archive truncates every contract that was
already listed on 2013-01-02 (the January-2013 contract holds 10 rows there against
275 in the legacy file), leaving 2012-12-20 to 2012-12-31 unpriced. The downloader
now fetches a legacy companion file (`VXL_<settlement>.csv`) alongside any modern
file at the boundary; 80 companions were retrieved, covering the January-2008
through August-2014 expiries, which is the full extent of the legacy archive.

### V3d. Do the tests actually catch these?

A test that passes against fixed code but would also pass against broken code is
worth nothing. Each fix was reverted in turn and the suite re-run:

| Mutation restored | Tests failing |
|---|---|
| "modern wins" de-duplication | 1 of 10 |
| header read from line 1 | 3 of 10 |
| silent skip of unparseable files | 2 of 10 |
| none (fixed code) | 0 of 10 |

**Panel after repair.** 41,872 rows, 4,711 sessions, 233 expiries, 2008-01-02 to
2026-09-18. Zero sessions with no priced contract; zero sessions with fewer than
two. Median nine contracts priced per session in every year from 2009 on.

---

## V4. Cross-validation of the two Cboe archives

**Proposition.** The modern per-expiry archive and the legacy archive are the same
price series, so splicing them does not stitch together two different definitions.

**Test.** Take every (date, expiry) cell where both archives supply a settlement
price and compare them.

**Result.** 13,127 overlapping cells spanning 2006-04-24 to 2014-08-20. **One**
disagreement: 2013-05-28, February-2014 expiry, modern 20.10 against legacy 10.25.

**Adjudication, on evidence rather than on which source is preferred.** That was the
contract's listing day — zero volume, high and low both 19.95. The rest of the curve
that session runs 15.20, 16.35, 17.20, 17.85, 18.25, 18.70, 18.90, 19.60 in monotone
contango. 20.10 continues it; 10.25 would sit 9.35 points *below* the front month at
nine months out, which no VIX futures curve does. The legacy value is a bad print.
The merge rule prefers the modern archive where both carry a price, so it resolves
this correctly, and the case is now a regression test.

---

## V5. Choosing the roll convention

Two conventions are implemented: `sp_dji` (`w1 = dr/dt`, the S&P Dow Jones Indices
definition) and `shifted` (`w1 = (dr+1)/dt`, the same weights advanced one business
day). Vendors differ on whether the roll trade is booked at the close of the
settlement date or of the following day. The choice is made on evidence, not
assertion.

**Test 1 — tracking error.** Build the index under each convention and measure the
daily tracking error against each traded product over each era.

**Result.** `sp_dji` wins **16 of 16** comparisons, by 1.27 to 7.07 basis points a
day. Unanimous, though small relative to the level of the tracking error itself.

**Test 2 — does the residual carry the roll?** A mis-timed roll leaves a residual
that moves with the roll weight. Regress the tracking residual on `w1` lagged one
day, HAC standard errors, 2011 onward.

**Result.** Under `sp_dji`, across all five products, every |t| < 1.21 and every
p ≥ 0.227. No detectable loading. Under `shifted`, the same — so this test does not
discriminate between them, but it does establish that **neither** convention leaves
roll-shaped structure in the residual.

**Decision.** `sp_dji`, on Test 1, with Test 2 confirming that the roll is not the
source of the remaining tracking error. Recorded in `config/config.yaml` as
`index.roll_convention` and in `reports/tables/roll_convention.csv`.

---

## V6. The tracking-error regime shift

This is the substantive finding of the reconstruction phase, and it began as a
hypothesis that was **rejected**.

**H1 (pre-registered in `docs/research_design.md`):** the reconstructed index tracks
the traded products to within roughly 20 bp a day throughout.

**H1 is rejected.** Daily tracking error against VIXY, de-levered:

| Era | Tracking error (bp/day) | Slope on the index |
|---|---|---|
| 2011-01 to 2015-12 | 120.6 | 0.873 |
| 2016-01 to 2017-12 | 108.4 | 0.886 |
| 2019-01 to 2020-10-23 | 137.3 | 0.958 |
| 2020-10-26 onward | 31.0 | 0.985 |

The slopes are the signature that matters. A slope below one, common across products
of *different leverage and different issuer*, is not product-specific tracking
difficulty — it is attenuation from noise in the regressor, i.e. in the
reconstructed index. Over 2011-2017, slope ÷ leverage came to 0.887 for VIXY (+1x),
0.889 for SVXY (−1x) and 0.877 for UVXY (+2x): one common factor across three
issuers and three leverages.

### Hypotheses tested and rejected

**Roll timing.** Rejected — V5, Test 2. No residual loading on the roll weight.

**Second-month staleness.** If a thinly-traded second contract were contaminating
the index, the attenuation would weaken on days when the roll weight sits mostly on
the liquid front month. Interact the index return with the lagged roll weight:
every |t| ≤ 1.10, no era. And the second month's share of front-two volume is flat
at 0.38-0.44 in every year from 2009 to 2026 — there is no liquidity shift to
explain a regime change. **Rejected.**

**Using closing prices instead of settlement prices.** Rebuilding the index on
`close` makes tracking *worse* in every era, and dramatically so after October 2020
(101-108 bp against 27-36 bp). **Rejected**, and informative — see below.

### What the evidence does support

**Non-synchronous measurement.** If the index is struck at a later instant than the
product's closing price, the missing interval appears as noise in the regressor
(attenuating the slope) and part of it arrives in the product the following day
(a positive coefficient on the lagged index). Both are present. Regressing the
de-levered product return on the index at t, t−1 and t+1, over 2011-2017:

| Product | slope at t | slope at t−1 | HAC t on t−1 |
|---|---|---|---|
| VIXY | 0.881 | 0.057 | 4.97 |
| SVXY | 0.877 | 0.066 | 4.62 |
| UVXY | 0.872 | 0.056 | 4.49 |

Year by year, the lagged loading is significant from 2011 through 2015 and
indistinguishable from zero from 2016 on.

**The dated market-structure change.** Cboe moved the VX daily settlement price
calculation from **3:15 p.m. CT to 3:00 p.m. CT effective 26 October 2020**
([Cboe notice](https://cdn.cboe.com/resources/release_notes/2020/Adjustment-of-Daily-Settlement-Time-for-Proprietary-Index-Products-Notice.pdf)).
3:00 p.m. CT is 4:00 p.m. ET — exactly when the products' consolidated closing price
is struck. Before that date the two series are measured fifteen minutes apart; after
it they are measured together.

**The break is located in the data, not assumed.** Median absolute de-levered
tracking difference over the 60 sessions before against the 60 after each candidate
date:

| Candidate break | Before (bp) | After (bp) | Ratio |
|---|---|---|---|
| 2020-09-01 | 54.1 | 31.2 | 1.74 |
| 2020-10-01 | 49.5 | 18.3 | 2.71 |
| **2020-10-26** | **51.0** | **14.5** | **3.51** |
| 2020-11-15 | 39.5 | 16.3 | 2.42 |
| 2020-12-15 | 19.2 | 17.8 | 1.08 |
| 2021-02-01 | 15.1 | 24.5 | 0.62 |

The ratio is maximised at the documented effective date and falls away on either
side. This is also why building on `close` does not help: the session continues past
4:00 p.m. ET, so the last trade never aligns with the product's close, in any era.

### What remains unexplained

The settlement-time change accounts for the largest and final step, and the lead-lag
coefficients are direct evidence of asynchronous measurement before it. It does
**not** account for everything:

* the lagged loading dies after 2015, five years before the settlement-time change;
* the contemporaneous slope improves from ~0.88 to ~0.95 around 2019, again before it.

These are stated as unexplained rather than attributed to a mechanism that has not
been demonstrated. 2018 is not usable for dating anything — the contemporaneous
slope collapses to 0.42-0.55 that year under the influence of 5 February and the
SVXY/UVXY leverage change.

### Consequence for the rest of the project, stated plainly

The reconstructed index carries measurement noise against the traded products of
roughly 120 bp a day before October 2020 and roughly 30 bp a day after. **This
bounds the precision of every result computed on the pre-2020 sample**, and any
estimate whose economic significance depends on differences smaller than that is not
supported by this data. It is a limitation of the reconstruction, disclosed here and
carried into the results section, not a reason to relax H1 after the fact.

---

## V7. Index reconstruction outputs

On the repaired panel, `sp_dji` convention, settlement prices:

| Quantity | Value |
|---|---|
| Sessions | 4,711 |
| Span | 2008-01-02 to 2026-09-18 |
| Sessions with a missing contract price | 0 |
| Sessions with a NaN return | 0 |
| Annualised return | −47.7% |
| Annualised volatility | 73.4% |
| Worst day | −25.96% (2018-02-06) |
| Best day | +96.10% (2018-02-05) |

The 5 February 2018 figure is the one to sanity-check against the outside world: the
index the short products track roughly doubled in a day, which is what destroyed
XIV. It is not an artefact of the reconstruction; it is the event.

---

## V8. Test suite

`python scripts/run_tests.py` — **185 passed, 2 skipped**, 187 collected. The two
skips are optional-dependency paths.

Four test expectations were themselves found to be wrong during this work, with the
code correct in each case: the number of 2018 trading days (251), a drawdown trough
(0.8316), the GPD shape parameter on Gaussian tails at the 98th percentile (ξ ≈
−0.15, slow Gumbel convergence), and the condition under which the Lo (2002) Sharpe
correction exceeds the naive standard error. Corrected in the tests, not in the
code, with the reasoning in each docstring.

---

## Open items

1. The 2016 and 2019 steps in V6 are not explained.
2. The seven SEC filings are not yet verifiable in this environment (V2).
3. Post-October-2020 slopes are 0.985 (VIXY), 0.991 (SVXY), 0.971 (UVXY) — close to
   but not equal to one. Whether the residual 1-3% is product tracking difficulty,
   fee drag mis-attributed to the slope, or remaining index noise is not resolved.
