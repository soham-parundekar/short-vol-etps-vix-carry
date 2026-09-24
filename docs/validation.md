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

**Result.** 338 recorded files, **338 verify byte-for-byte**. No file differs from
its recorded hash and none is missing. (For most of this work the seven SEC filings
were absent from the analysis environment; the check reported them as missing rather
than passing them, which is the behaviour being relied on here.)

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

**H1 is rejected.** Daily tracking error against VIXY, split on the settlement-time
change (`index_tracking_eras.csv`, added in Phase 13 so these numbers live in a
committed table rather than in this paragraph):

| Era | Settlement | TE, raw difference (bp/day) | TE, regression residual | Leverage-adjusted slope |
|---|---|---|---|---|
| 2011-01 to 2015-12 | 15:15 CT | 133.2 | 120.7 | 0.873 |
| 2016-01 to 2017-12 | 15:15 CT | 117.0 | 108.5 | 0.886 |
| 2018 (leverage change year) | 15:15 CT | 447.1 | 290.3 | 0.543 |
| 2019-01 to 2020-10-23 | 15:15 CT | 139.1 | 137.4 | 0.958 |
| 2020-10-26 onward | **15:00 CT** | **31.7** | 31.0 | 0.985 |

H1's criterion is written on the raw difference, which is the first of the two columns;
the second lets a fitted slope and intercept absorb the attenuation and is the smaller
number. Either way the criterion (25 bp/day) is exceeded everywhere except after
October 2020, where it is exceeded by less. *Correction, Phase 13: this table
previously showed only the regression-residual column, labelled simply "tracking
error", and the two definitions were not distinguished.*

The slopes are the signature that matters. A slope below one, common across products
of *different leverage and different issuer*, is not product-specific tracking
difficulty — it is attenuation from noise in the regressor, i.e. in the
reconstructed index. Over 2011-2017 the leverage-adjusted slope is 0.877 for VIXY
(+1x), 0.872 for SVXY (−1x) and 0.867 for UVXY (+2x) (`index_tracking.csv`): one
common factor across three issuers and three leverages. *Correction, Phase 13: these
were quoted as 0.887 / 0.889 / 0.877 from an exploratory run, and the committed
table's `slope_over_lev` column divided an already-leverage-adjusted slope by the
leverage again — flipping its sign for inverse products. The column is gone and the
`slope` column is the leverage-adjusted one.*

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

## V9. 5 February 2018, reconciled against the filings

The single most consequential return in the sample. If the reconstruction is wrong
anywhere, it is worth being wrong here, so this date is checked against a primary
document rather than against another model.

**The reconstruction says** the index rose **+96.10%** on 2018-02-05.

**The independent anchor.** Credit Suisse's acceleration release states two numbers
and one rule:

> "Because the intraday indicative value of XIV on February 5, 2018 was **equal to or
> less than twenty percent of the prior day's closing indicative value**, an
> acceleration event has occurred."
> "On February 2, 2018, the closing indicative value was **$108.3681**."

XIV was an inverse (-1x) note on this index with a daily investor fee factor of
0.0135 (both quoted in V10). Applying the reconstructed return:

| | |
|---|---|
| Prior closing indicative value (from the filing) | $108.3681 |
| Reconstructed index return, 2018-02-05 | +96.10% |
| Implied closing indicative value at -1x, net of fee and T-bill accrual | **$4.22** |
| Acceleration threshold, 20% of the prior close | $21.67 |
| Threshold breached? | yes, by a factor of five |

The reconstruction therefore predicts the acceleration event that the filing records,
from futures settlement prices alone, with no product data used as an input. Note
what this does and does not show: the trigger is defined on the *intraday* indicative
value, and the figure above is an end-of-day one, so this confirms the event and the
magnitude rather than the precise instant of the breach.

### The same date, measured at 4:00 p.m., says something entirely different

| Product | Leverage | Its own 4:00 p.m. close | Index move this implies |
|---|---|---|---|
| VIXY | +1x | +34.24% | **+34.24%** |
| SVXY | -1x | -31.99% | **+31.99%** |
| UVXY | +2x | +66.21% | **+33.11%** |
| reconstruction | - | - (4:15 p.m. settlement) | **+96.10%** |

Three products, three issuers, three different leverages, one long and two geared -
and they agree with each other to within **2.25 percentage points** on what the index
did. They agree with each other and disagree with the 4:15 p.m. settlement by a factor
of three. In log terms, **57.5% of the day's move happened after 4:00 p.m. ET**.

This is V6's asynchronicity in its most extreme instance. The raw contract data is
consistent with it: the February-2018 VX contract opened at 16.15, ranged from 15.20
to 33.35, and **closed at 33.20 - its high of the day**, on 567,407 lots. A close at
the high on heavy volume is consistent with concentrated buying into the settlement
window, and V13 shows the geared funds' mechanical demand that day was at least a
quarter of front-month open interest. Daily data cannot say who did the buying, so
this is stated as consistent with the rebalancing account, not as a demonstration of
it. (An earlier draft called it "forced buying"; that was stronger than the evidence.)

**And the filings say so directly.** ProShares' own prospectus:

> "A 'single day' is measured from the time a Fund calculates its net asset value
> ('NAV') to the time of the Fund's next NAV calculation. **The NAV calculation time
> for the Funds is typically 4:15 p.m. (Eastern Time)**."

So the funds strike NAV at 4:15 p.m., aligned with the pre-October-2020 futures
settlement, while the closing *price* this project regresses on is the 4:00 p.m.
consolidated close. The gap is between the index and the traded price, not between
the index and the fund's NAV. On 5 February 2018 that distinction was the difference
between a fund down 32% and a fund down 96%.

### The leverage change, dated two ways

ProShares Trust II's 10-K, Note 9:

> "Effective as of **close of business on February 27, 2018**, the investment
> objective of ProShares Ultra VIX Short-Term Futures ETF and ProShares Short VIX
> Short-Term Futures ETF changed ... to seek results ... that correspond to **one and
> one-half times (1.5x)** the performance of the ... Index for a single day."

`config/config.yaml` stores `leverage_change_date: 2018-02-28`. That is not a
disagreement: the filing dates the *change*, the configuration dates the first daily
*return* computed under the new objective, and a change at the close of the 27th
first affects the return from the 27th close to the 28th close. Confirmed in the
data rather than argued:

| Date | SVXY implied leverage | UVXY implied leverage |
|---|---|---|
| 2018-02-27 | -1.21 | +2.48 |
| **2018-02-28** | **-0.24** | **+1.13** |

and over the following 60 sessions the fitted slopes are -0.565 and +1.687, against
targets of -0.5 and +1.5 - attenuated by about 13%, which is the same era attenuation
V6 documents, from the same cause.

---

## V10. Every product term, quoted from its filing

**Proposition.** No product term asserted anywhere in this repository comes from
recall or from a secondary description. Each is located in the archived primary
document by a stored search pattern, and the surrounding passage is kept.

**Test.** `python scripts/extract_filing_terms.py`. Twenty-seven terms across seven
filings. The script writes every quotation to `reports/tables/filing_terms.csv`
alongside the pattern that found it, compares each against `config/config.yaml`, and
**exits non-zero** if any term cannot be located or any configuration value
disagrees.

**Result.** 27/27 located, 0 disagreements outstanding.

| Filing | Terms |
|---|---|
| CS VelocityShares 424B2 (2017-06-30) | 5/5 |
| CS XIV acceleration release (2018-02-06) | 4/4 |
| ProShares 424B3 (2018-02-15) | 7/7 |
| ProShares Trust II 10-K FY2017 | 4/4 |
| iPath Series B pricing supplement (2018-01-03) | 3/3 |
| iPath Series B Amendment No. 1 (2022-03-14) | 1/1 |
| VS Trust 424B3 (2022-01-28) | 3/3 |

**Does the check fail when it should?** Mutation-tested three ways: a deliberately
wrong fee in the configuration exits 1 and names the disagreement; a removed archived
file exits 1 and names each claim it can no longer support; the unmodified repository
exits 0.

### What reading the filings actually changed

Four things, none of which would have surfaced without opening the documents.

**1. A fee that was wrong.** `config/config.yaml` gave SVIX a fee of 1.29%. The
archived launch prospectus says:

> "SVIX pays the Sponsor a management fee ... in an amount equal to **1.35% per
> annum** of its average daily net assets."

1.29% appears nowhere in the document. Corrected to 1.35%, per the decision rule that
the filing wins. Materiality: 0.06% a year is about 0.24 bp a day against a 51 bp
daily tracking error - it moves the mean residual and no conclusion.

**2. A claim attached to the wrong document.** The VXX investor fee of 0.89% was
recorded against `Barclays_iPath_VXX_SeriesB_424B2.htm`. That file turns out to be
Amendment No. 1 of 14 March 2022 - a one-page notice with no fee schedule at all. The
fee is stated in the January-2018 pricing supplement, which was also archived:

> "the net effect of the fee accumulates over time and is subtracted at the rate of
> **0.89% per year**, which we refer to as the 'investor fee rate'."

The claim has been moved to the document that supports it. This is exactly the error
the task exists to catch: the number was right, the citation was not.

**3. A structural difference between the products that the project had not recorded.**
VXX is linked to the **total-return** version of the index; XIV was linked to the
**excess-return** version. The project reconstructs ER. Recorded in
`docs/limitations.md` as a known bias in VXX's mean residual.

**4. Why VXX tracks worse than VIXY after 2022.** The amendment that turned out not to
contain the fee contains something better:

> "Effective as of the open of trading on March 14, 2022, we will **suspend, until
> further notice, any further sales from inventory and any further issuances** of the
> ETNs ... this may cause the ETNs to trade at a premium or discount in relation to
> their indicative value."

With creations suspended, the arbitrage that holds an ETN to its indicative value is
switched off. VXX's 2022-2026 daily tracking error is 101 bp against VIXY's 28 bp over
the identical window, and the issuer's own filing says why.

---

## V11. The price series against disclosed per-share NAV

**Proposition.** The split-adjusted product returns used throughout are right,
including across the SVXY 2-for-1 split and the VIXY/UVXY 1-for-4 reverse splits of
July 2017.

**Test.** The ProShares 10-K states each fund's per-share NAV at four year-ends. A
ratio of per-share NAVs is invariant to splits, so it is directly comparable to the
cumulative split-adjusted return over the same year - a comparison the split handling
cannot pass by accident, because a mishandled split is an error of a factor of 2 or 4.

**Result.** Nine comparisons (three funds, three years). Eight agree to within 0.8
percentage points over a full year; the ninth, SVXY in 2017, to 2.8 points on a +179%
year. The residual is what the 4:15 p.m. NAV strike against the 4:00 p.m. closing
price predicts (V6).

### V11a. A trap in the anchors themselves

Converting the 10-K's share counts into the price series' share basis by applying the
recorded split history gave share counts wrong by exactly the product of the
intervening split ratios - a factor of 2 for SVXY and about 1,900 for UVXY. The
filing had already restated every row onto its own share basis; applying the splits
again counted them twice. It was caught because each anchor states the share count
twice (as a count, and implicitly as net assets over price) and the two disagreed.
`svcarry.etp.assets` now takes net assets over price wherever a value is disclosed,
which needs no split arithmetic at all, and requires every valued anchor to imply the
same basis.

---

## V12. The leverage-decay identity (H2, mechanical part)

`ln(V_T/V_0) - L ln(I_T/I_0)` regressed on realised variance over non-overlapping
21-day blocks; theory says the slope is `-(L^2-L)/2`. Overlapping blocks with HAC
errors and a 63-day horizon are run as cross-checks. Full table:
`reports/tables/leverage_decay.csv`.

| Product | L | Slope | Theory | Verdict |
|---|---|---|---|---|
| VIXY | +1 | -0.030 | 0 | pass |
| VXX | +1 | +0.004 | 0 | pass |
| SVXY | -1, full window | **-2.846** | -1.000 | **fail** |
| SVXY | -1, excl. Feb-2018 block | -1.087 | -1.000 | pass |
| SVXY | -0.5 | -0.403 | -0.375 | pass |
| UVXY | +2, full window | -0.732 | -1.000 | warn |
| UVXY | +2, excl. Feb-2018 block | -0.946 | -1.000 | pass |
| UVXY | +1.5 | -0.384 | -0.375 | pass |
| SVIX | -1 | -1.171 | -1.000 | warn, benchmark mismatch (L9) |

### V12a. One block, and why it is not deleted

The 21-day and 63-day estimates for pre-2018 SVXY disagree (-2.85 against -1.08),
which the phase prompt names as the sign that block length is doing work it should
not. Leave-one-block-out locates it: **dropping the single block containing 5-6
February 2018 moves the SVXY slope by +1.76**; the next most influential block moves
it by 0.11. Two documented causes, neither a data error:

1. **The identity is an approximation.** Over that block, exact discrete rebalancing
   `prod(1 + L r)` and the continuous-time identity differ by **27.8 percentage
   points** at L = -1, against 2.3 points in a typical block. A +96% day is not a
   small return.
2. **The measurement gap takes three sessions to close.** VIXY - a +1x fund with no
   rebalancing to do - trails the index by 61.9 points after one session, 15.3 after
   two, 3.7 after three, and about 1 thereafter.

So the block is reported both ways, with these diagnostics beside it
(`decay_influence.csv`, `decay_approximation_error.csv`, `figures/decay_blocks.png`).
With it excluded, the 21-day and 63-day estimates agree: -1.087 and -1.075.

### V12b. The documented de-levering, visible in prices

Pooled regression with a post-break interaction at 2018-02-28:

| | step at the break | theory | t vs 0 | t vs theory | post-break slope |
|---|---|---|---|---|---|
| SVXY -1 to -0.5 | +0.685 | +0.625 | **13.4** | 1.17 | -0.403 (theory -0.375) |
| UVXY +2 to +1.5 | +0.562 | +0.625 | **7.0** | -0.78 | -0.384 (theory -0.375) |

(pre-window excluding the February 2018 block; with it included the break is still
significant, t = 6.0 and 4.9, but the step is contaminated by V12a.) The break is at
the date the filings give and of the size theory predicts.

### V12c. Intercepts - partially met

The phase criterion asks the intercept to recover the fee within 100 bp a year. With
the slope held at theory (so the intercept cannot absorb slope error), six of seven
products sit 0.2-2.7 points from minus the fee; adding the collateral T-bill yield
improves some and worsens others. The intercept is not separately identified from
collateral yield, trading costs and the ER/TR distinction in this regression, and is
reported as **warn** (`decay_intercepts.csv`). SVIX's -8.75%/yr is not evidence about
the identity at all: SVIX tracks a different index (L9).

---

## V13. Rebalancing flows (H2)

**Dimensional check, 5 February 2018, lower bound**

| Step | Value |
|---|---|
| SVXY assets | $431.4m, L(L-1) = 2.00, flow $829.2m |
| UVXY assets | $531.2m, L(L-1) = 2.00, flow $1,021.1m |
| index return | +96.10% |
| aggregate | $1,850.3m |
| / ($1,000 x F1 = 33.225) | **55,690 contracts** |
| front-month open interest | 222,804 contracts -> **25.0%** |
| front-two open interest | 510,632 contracts -> 10.9% |

Open interest is that of the specific contracts the index held that day - the front
month, and separately the front two.

**Plausibility.** The lower bound never exceeds 100% of front-month open interest; its
maximum over the whole anchored window is the 25.0% of 5 February 2018. The upper bound
exceeds the entire contract on 7 sessions, which marks it as uninformative wherever a
fund's share count moved sharply between annual anchors - it is plotted separately
and never used for the claim.

**H2, against its pre-registered rule.** Rejected only if the flow is below 10% of
front-month open interest under both bounds on the largest up-moves of 2016-2018. Of
the ten largest in the anchored window, none is below at both bounds, so **H2 is not
rejected**. Stated at its actual strength: it is supported at the lower bound on **3 of
the 10**, and indeterminate - above 10% only at the upper bound - on the other 7. The
lower bound covers SVXY and UVXY only; XIV, the largest -1x product on that day, is
excluded, so it understates the complex.

The three, and how much room they have:

| Date | Index return | Lower bound | Upper bound |
|---|---|---|---|
| 2016-01-07 | +12.02% | 10.18% | 142.5% |
| 2016-06-13 | +15.85% | 10.23% | 126.0% |
| **2018-02-05** | **+96.10%** | **25.00%** | 131.6% |

Two of the three clear 10% by less than a quarter of a percentage point. H2's support
outside 5 February 2018 is therefore thin, and the honest reading is that the hypothesis
rests on the one day.

*Corrected by the final audit (F-A2).* Every version of this document through Phase 15
said "4 of the 10 ... on the other 6". The fourth day was 2017-08-10, whose lower-bound
share is **9.97%** - which prints as "10.0%" at one decimal place and was counted as
clearing a threshold it does not clear. The number existed only in prose and was never in
a table or in `check_results_numbers.py`, which is why it survived four phases. It is now
asserted by that script.

**What this does not show.** That the flow caused the move. Daily data establishes that
the mechanical demand was large relative to the open interest that had to absorb it,
and V9 shows the price rising into the settlement window; it cannot separate that
demand from the other buyers in the same fifteen minutes.

**The de-levering, as a counterfactual.** Holding 5 February's assets and shock fixed
and changing only the coefficient from 2.0 to 0.75 cuts the lower-bound trade from
55,690 to 20,884 contracts - from 25.0% to 9.4% of front-month open interest. The 62.5%
reduction is arithmetic, not an estimate; what the counterfactual adds is that the
same shock would have landed just below the 10% threshold H2 uses.

---

## V14. The GJR-GARCH filter

Skewed-*t* GJR-GARCH(1,1) on daily index **log** returns, fitted twice: on data ending
2017-12-31 (2,518 days, the ex-ante model) and on the full sample (4,710 days,
descriptive only). `reports/tables/garch_fit.csv`.

| Check | pre-2018 | full | Criterion |
|---|---|---|---|
| Same optimum from two seeds x four starts | params agree to 6e-7 | 5e-7 | pass |
| Persistence a + b + g/2 | 0.938 | 0.926 | pass, in (0.90, 0.999) |
| Ljung-Box on z^2, 10 / 20 lags | p = 0.81 / 0.34 | 0.74 / 0.55 | pass |
| KS on the probability-integral transform | p = 0.43 | 0.81 | pass |
| Asymmetry gamma | -0.245 (t = -6.4) | -0.306 | expected sign |

The asymmetry is the reverse of the equity leverage effect, as it should be for long
VIX futures: an **up**-shock raises next-day variance by alpha = 0.28 times its square,
a down-shock by only alpha + gamma = 0.03. The skewness parameter is positive (0.20).

**Is the scale calibrated across regimes?** Under a correct scale, 5% of standardised
residuals exceed their 95th percentile in every volatility quintile. Pre-2018: 5.2%,
5.8%, 5.4%, 5.2%, 3.6% from calm to turbulent, chi-square p = 0.56 - no evidence of
miscalibration, and in particular none that the model under-reacts in calm regimes.
Full sample: p = 0.006, driven by too *few* exceedances in the turbulent quintile
(3.1%), i.e. the model over-reacts after shocks.

---

## V15. The EVT threshold

Chosen on **pre-2018 residuals only** by the rule in
`prompts/tasks/choose_evt_threshold.md`: the lowest quantile with at least 50
exceedances, xi within one standard error of the next two thresholds, KS on the
excesses p > 0.10, and inside the linear region of the mean excess (taken as the lower
and upper halves of [q, 0.99] implying xi within one standard error of each other).

| q | exceedances | xi (se) | KS p | linear | passes |
|---|---|---|---|---|---|
| 0.900 | 252 | 0.169 (0.072) | 0.74 | no - halves imply 0.08 vs 0.19 | no |
| **0.925** | **189** | **0.181 (0.085)** | 0.66 | yes | **chosen** |
| 0.950 | 126 | 0.233 (0.117) | 0.93 | yes | yes |
| 0.970 | 76 | 0.204 (0.150) | 0.83 | yes | yes |
| 0.990 | 26 | 0.303 (0.374) | 0.73 | - | no, too few |

xi is positive at every threshold (a heavy tail, as expected) and moves by 0.07 across
the region with at least 50 exceedances. An informal reading of the mean-excess plot
had suggested 0.95; the coded rule, with its sharper linearity test, stops at 0.925,
and the rule governs. The full-sample rule chooses 0.90.

---

## V16. Termination probabilities and H3

The one-day index **simple** return that removes 80% of a product is 80% at -1x and
160% at -0.5x; on the log scale the model is fitted in, 0.588 and 0.956. Checked by
hand for 5 February 2018: sigma = 0.0801, standardised threshold 7.38, GPD tail
0.075 x (1 + 0.181 x 5.92 / 0.630)^(-1/0.181) = 3.09e-4 a day, i.e. 1 in 12.8 years -
the pipeline's number.

**Ex-ante, pre-2018 model, headline threshold** (`termination_probabilities.csv`):

| State | -1x wipeout | -0.5x wipeout |
|---|---|---|
| unconditional (average over 2008-2017 days) | **1 in 79 years** | 1 in 685 years |
| across the whole threshold grid | 1 in 53 - 85 years | 1 in 279 - 797 years |
| calm quintile of volatility | 1 in 2,835 years (grid 484 - 3,991) | 1 in 34,333 years (grid 2,443 - 61,700) |
| 12 January 2018 | 1 in 3,877 years (grid 592 - 5,629) | 1 in 47,450 years (grid 2,984 - 88,484) |
| **5 February 2018, data through 2 February** | **1 in 12.8 years** (grid 10.0 - 13.7) | 1 in 115 years (grid 53 - 135) |

The unconditional numbers move by 1.6x (-1x) and 2.9x (-0.5x) across the grid, inside
the factor of three beyond which the phase prompt requires a range as the headline.
The calm-state numbers move by 8x to 30x across the grid and are therefore reported as
ranges, never as points: far into the tail, small differences in xi compound.

**The warning, day by day** (`exante_warning_path.csv`, `figures/exante_warning.png`).
Parameters frozen at 31 December 2017, volatility state updated as each day arrives:
1 in 2,163 to 3,877 years through mid-January, 1 in 105 after the +8% day on
29 January, 1 in 12.8 after the +14% day on 2 February. A three-hundred-fold rise in a
week - and still a one-day probability of about 1 in 3,200 trading days on the morning
of the event.

**A correction to the phase prompt.** Its self-review asserted that the
calm-quintile probability "should" exceed the unconditional one. Under any GARCH
scale the one-day tail probability rises with sigma, so the reverse must hold, and it
does. The real question behind the assertion - whether the model under-states risk
in calm regimes - is tested in V14 and the answer is no. Prompt corrected; the
property is now a test.

**H3, against its pre-registered rule.** Rejected if the ordering reverses, if the
survival gap is unstable across the grid, or if the -1x probability is below 1 in
10,000 years. None holds: ordering preserved at every threshold, the gap is stable
(V17), and the ex-ante -1x probability is 1 in 79 years. **H3 is not rejected.** But
its stated magnitude is not met: the -1x probability is **8.7 times** the -0.5x
probability at the headline threshold and 5.3 to 9.4 times across the grid - not the
order of magnitude the hypothesis claimed. Reported as a warning, not reworded.

---

## V17. Survival, and where the simulated risk comes from

20,000 five-year paths from the pre-2018 model, seed from configuration. Standard
errors at five years are 0.28 points or less.

| Five-year survival | -1x | -0.5x | gap |
|---|---|---|---|
| model dynamics unbounded | 81.1% | 93.7% | 12.6 pp |
| volatility capped at the 2008-2017 maximum | 89.9% | 98.6% | 8.7 pp |
| gap across the threshold grid, unbounded | | | 12.1 - 14.0 pp |
| gap across the threshold grid, capped | | | 7.8 - 9.4 pp |

**Why two versions.** Averaging the in-sample one-day probabilities gives 1 in 79
years; the unbounded simulation implies a hazard nearer 1 in 24. The difference is
not simulation error. The fitted recursion - alpha of 0.28 on up-shocks, GPD
innovations - generates volatility spirals far outside anything observed
(`simulation_diagnostics.csv`, 4,000 paths):

| | 2008-2017 | simulated |
|---|---|---|
| daily volatility, 99.9th percentile | 0.137 | 0.412 |
| daily volatility, maximum | 0.158 | **6.92** |

The 1.1% of simulated days with volatility above the observed maximum carry **81%** of
simulated wipeouts, and 41% of paths that suffer one suffer another within 20 days. That is extrapolation of the variance dynamics, not of
the innovation tail. Capping volatility at its observed maximum removes it; the pair
brackets the answer and neither is offered alone. Notably, 5 February 2018 itself did
not come out of such a spiral: it was an 8.5-sigma innovation at a volatility of 127%
annualised, well inside the observed range.

---

## V18. Kelly and H4

Growth-optimal short exposure `f* = argmax E[ln(1 - f R)]` on daily **simple** index
returns, with the solvency bound `f < 1 / max R`, and a 1,000-replication stationary
bootstrap (mean block 21 days). `reports/tables/kelly.csv`.

| Returns | f* | 95% interval |
|---|---|---|
| full sample | 0.62 | [0.05, 1.34] |
| pre-2018 | **1.11** | [0.22, 2.07] |
| full sample without 5 Feb 2018 | 0.86 | [0.22, 1.45] |

**H4 is rejected**: the interval contains 1.0 in every case. Before the crash the
empirical point estimate was *above* one - the historical record said a full -1x
short was roughly growth-optimal. At the full-sample optimum, expected log growth is
13.1% a year; at -1x it is about +1.6%.

**Why there is no model-based Kelly number.** The fitted tail has xi > 0 and unbounded
support, so for any short exposure f > 0 there is positive probability that R exceeds
1/f, which makes E[ln(1 - f R)] minus infinity. The model-implied growth-optimal short
is exactly zero. Kelly computed on simulated returns returns 0.014 and 0.059
(unbounded, capped), each just below one over its own largest draw (0.015, 0.059): it
measures how many draws were taken, not an optimum. So whether -1x was "too much"
by the Kelly criterion is not something the sample can settle - it turns on whether
the upside is bounded, which is an assumption, not an estimate.

---

## V19. The jackknife

The largest day of each sample removed and everything refitted
(`tail_jackknife.csv`).

| Sample | Day removed | -1x probability | -0.5x | xi | Kelly f* |
|---|---|---|---|---|---|
| pre-2018 | 24 Jun 2016, +32.7% | -25% (79 -> 105 yrs) | -33% | 0.181 -> 0.173 | 1.11 -> 1.22 |
| full | 5 Feb 2018, +96.1% | -42% (26 -> 44 yrs) | -60% | 0.169 -> 0.151 | 0.62 -> 0.86 |

The ex-ante headline moves by 25%, inside the 50% tolerance: no single pre-2018 day
is the result. In the full sample, 5 February 2018 moves the -1x number by 42% (pass)
and the -0.5x number by 60% (warning): the event itself carries more of the tail than
any earlier day did.

---

## V20. The variance proxy

`variance_proxy_comparison.csv`. SPY `rs_overnight`: 5,713 days from 5 January 2004,
no non-positive values, 19.1% annualised (close-to-close 18.7%), daily log-variance sd
1.25 and AR(1) 0.57 against 2.49 and 0.28 for squared returns. The S&P 500 index's open
equals the previous close on 14% of days, and its overnight leg carries 10.5% of
close-to-close variance against SPY's 36%: the index's open is stale and is not used.
Yang-Zhang (21-day window) against the 21-day average proxy: correlation 0.999, level
ratio 0.992. **Pass.**

### V20a. The log target - a defect found and fixed before any result used it

The committed log-HAR averaged the daily **logs** over `t+1 .. t+h` and exponentiated
the forecast, which targets the *geometric* mean of daily variance. A variance risk
premium needs the arithmetic mean. On a proxy this noisy the two are far apart: over the
evaluation sample the 21-day arithmetic mean is on average **1.50 times** the geometric.
The model's own evaluation could not see it, because it compared the forecast with the
geometric mean too.

What it was worth, re-running the committed code on the same data: forecasts 31% lower,
**61%** of realised average variance on average; VRP positive on **99.0%** of days
(fixed: 87.4%), median VRP 0.0152 (fixed: 0.0077), combined signal on 82.5% of days
(fixed: 73.8%). The VRP filter would have been almost inert while appearing to work.

Fixed in `har_features`: the target is `log(mean(rv))`; predictors unchanged. Tests
(each fails on the old code, checked): the target equals the log of the arithmetic
window mean; retransformed forecasts are unbiased for the level of average variance on
a noisy simulated proxy (ratio within 10%, where the geometric target falls 20% short);
forecasts extend to the last sample date.

## V21. HAR forecasts out of sample

4,671 forecasts, 25 January 2008 to 19 August 2026 (the last 21 forecasts have no
outcome yet). `har_oos_diagnostics.csv`, full sample:

| Model | RMSE (ann. var.) | QLIKE | OOS R^2 (eval mean / expanding) | MZ slope (se) |
|---|---|---|---|---|
| **HAR log (primary)** | **0.0754** | 0.365 | **0.285 / 0.303** | **0.91 (0.15)** |
| HAR level | 0.0868 | 0.351 | 0.053 / 0.077 | 0.53 (0.09) |
| HAR log, smearing (not adopted) | 0.0757 | 0.358 | 0.278 / 0.296 | 0.86 (0.14) |
| Trailing 21-day RV | 0.0865 | 0.463 | 0.060 / 0.083 | 0.53 (0.12) |
| Today's RV (random walk) | 0.1223 | 1.325 | -0.880 / -0.833 | 0.32 (0.05) |
| Expanding mean | 0.0903 | 0.788 | -0.026 / 0 | - |

| Check | Result | Verdict |
|---|---|---|
| Look-ahead (perturbation, three tests) | bit-identical before the cut-off | **Pass** |
| OOS R^2 > 0.25 | 0.285 | **Pass**, narrowly |
| Beats trailing RV | RMSE 13% lower, QLIKE 21% lower | **Pass** - but Diebold-Mariano is significant on QLIKE (t = -4.08) and **not** on MSE (t = -1.14) |
| MZ slope within 0.2 of 1 | 0.91, t(slope = 1) = -0.62 | **Pass** |
| Leak signature | corr(forecast, outcome) 0.54 vs 0.53 for trailing RV; in logs 0.72 | Pass: nothing a leak would produce |

**Where the headline is weaker.** By sub-period the pass does not hold uniformly:

| Period | OOS R^2 (eval mean) | MZ slope | RMSE vs trailing RV |
|---|---|---|---|
| 2008-2012 | 0.32 | 0.86 | 0.101 vs 0.100 - no better |
| 2013-2019 | 0.005 | **0.51** | 0.020 vs 0.023 |
| 2020-2026 | 0.15 | 0.92 | 0.089 vs 0.114 |

In the calm 2013-2019 period the forecast barely beats a hindsight constant (against the
real-time expanding mean it reaches 0.57) and is over-dispersed: MZ slope 0.51. In
2008-2012 it does no better than trailing RV on MSE. The full-sample pass is carried by
QLIKE in every period and by MSE in the two later ones. Recorded rather than resolved:
the thresholds were fixed in advance and are not re-tuned.

**Level bias.** The forecast's mean is 12% below the mean outcome, while its median is
26% above the typical outcome: the right skew of variance. The log residuals are
right-skewed (skewness 1.2 full sample; already 1.10 in the first training window), so
the normal-theory retransformation understates the conditional mean; Duan's smearing
factor is 9% larger on the full sample. Smearing was not the pre-specified method and
the primary passes its criteria, so it is not adopted; it is carried to Phase 12 as a
robustness variant (VRP positive 81.7% of days, invested 69.1%). L15.

## V22. VRP units, by hand

`vrp_hand_check` in the pipeline record, 12 January 2018: raw Cboe line
`01/12/2018,9.740000,10.310000,9.540000,10.160000`, so VIX = 10.16 and implied variance
0.010323. The forecast rebuilt by hand from the proxy and the coefficients refitted on
27 December 2017 (const -1.471, 0.0823, 0.3192, 0.4161; residual variance 0.3653):
daily variance 2.5525e-5, 8.02% annualised, 0.006432 in annualised variance.
VRP = 0.010323 - 0.006432 = **0.003890**, equal to the panel value to machine precision.
The pipeline raises if the two ever differ. A unit test does the same at VIX = 20.

VRP is positive on **87.4%** of days (pass: a clear majority), median 0.0077 - in
volatility terms, VIX about 2 points above a 17% forecast.

## V23. The two slope measures

On the 4,276 days where both exist, `cm30/cm90` and `VIX/VIX3M` give the same contango
state on **91.7%** (pass, >= 90%); on the 211 overlap days where `cm30` is spot-anchored,
91.5%. The ratios themselves correlate 0.81: they agree about the sign more than about
the level; `VIX/VIX3M` runs on average 0.036 below `cm30/cm90`.

## V24. Signal statistics and coverage

After the burn-in (first signal 25 January 2008), `signal_statistics.csv`:

| | Share of days |
|---|---|
| Combined signal defined (coverage) | **99.94%** (pass) - undefined on 3 days when the equity market was shut and futures traded: 3 Apr 2015, 5 Dec 2018, 9 Jan 2025 |
| Contango on | 83.1% |
| VRP on | 87.4% |
| **Invested (both on)** | **73.8%** - inside the 30-90% band |
| The two filters agree | 77.2% |
| Out, contango alone binding | 13.6% |
| Out, VRP alone binding | 9.2% |
| Out, both | 3.3% |

The filters are not redundant: each is the only binding constraint on a material share
of days. By year the invested share ranges from 40% (2008) and 53% (2020) to 97%
(2017) (`signal_statistics_by_year.csv`).

**Parameter provenance** (look-ahead audit, step 5): threshold 1.0, VRP minimum 0.0,
`rs_overnight`, log HAR, horizon, lags, burn-in and refit interval all appear in
`config/config.yaml` at commit 2bdeb31 (07:40:36 UTC); the primary slope measure in the
Phase 10 prompt at commit 3db0269 (08:01:09 UTC); the first data retrieval in the
manifest is 08:30:04 UTC. Nothing was changed after. The config comment naming
VIX/VIX3M contradicted the prompt; the comment was corrected, not the value.
**Timing table** (step 2): `timing_audit.csv`, no row where use precedes availability.
The shift test (step 3) needs the backtest and belongs to Phase 11.

---

## V25. The sizing chain: timing

| Check | Result | Verdict |
|---|---|---|
| Perturbation over the whole chain | inputs after a cut-off changed by a record +150% day; every applied weight and every strategy return before it bit-identical | **Pass** |
| Mutation check on that test | a one-day peek in the floor, and one in the volatility state, both caught | Pass |
| Timing table | `timing_audit.csv`, nineteen inputs, each input's strike time compared against the settlement its position is booked at, **per date**; no row where use precedes availability | **Pass** - but see A-02/A-05: this row was a hard-coded `False` until the recursive audit, and it was concealing 1,482 days of fifteen-minute overlap |
| Shift test (Sharpe, out of sample) | lag 0: **1.54**, lag 1: **0.20**, lag 2: **-0.13** | **Pass**, strictly decreasing |
| Parameter provenance | every strategy parameter in `config/config.yaml` at commit 2bdeb31, before the first data retrieval; the two Phase 11 changes committed at 69b748d before any backtest was run | **Pass** |

The leak calibration is the second row of the shift test: a one-day leak would have
turned a Sharpe of 0.20 into 1.54 and cut the worst day from -11.7% to -4.2%. Whatever
the honest result is, it is not a contaminated version of a good one.

## V26. The crash floor, and what the amendment cost

The floor is the largest one-day index rise observed to date: 0.14 in 2008, 0.21 from
2011, 0.25 from 2015, **0.327** from 24 June 2016, 0.961 from 5 February 2018. The
model's conditional 99.9% move (design-window GJR-GARCH, persistence 0.934, EVT
threshold at the 0.90 quantile by the Phase 09 rule, xi = 0.054) has a median of 0.178,
so the floor is the binding half of the scenario on **75.9%** of days.

Run with the configured hindsight floor instead (0.961 throughout), the strategy's
out-of-sample Sharpe is **0.25** rather than 0.20, its worst day -6.6% rather than
-11.7% and its maximum drawdown -20.4% rather than -26.8%. Knowing the answer in
advance is worth about 0.05 of Sharpe and half the worst day - the honest version is
the weaker one, which is the direction that makes the amendment credible.

## V27. Costs and turnover

Annual turnover of 11.4 (out of sample): 7.2 rebalancing the drift back to target and
4.2 from the index's own roll, which is 39.2% of the out-of-sample cost bill. Costs are
3.2% of capital a year against a collateral accrual of 2.3%. (The figure quoted here was
38.7% until the recursive audit: that is the *full-sample* share, quoted inside an
out-of-sample breakdown - A-08.)

| Cost (ticks per side) | 0 | **1 (default)** | 2 | 4 |
|---|---|---|---|---|
| Out-of-sample Sharpe | 0.46 | **0.20** | -0.06 | -0.58 |

**Pass** (monotone), with the caveat that matters more than the pass: at two ticks the
strategy loses money, and the Sharpe reaches zero at 1.77 ticks. An accounting that
charged only changes in the target weight - as the engine did before Phase 11 - would
have reported 0.22, and one that ignored the roll as well, 0.30.

## V28. Performance, by window, never pooled

Out of sample (2016-01-04 to 2026-09-18, 2,695 days), on excess returns:

| | Sharpe (Lo se) | CAGR | Vol | Max DD | Worst day | Worst week |
|---|---|---|---|---|---|---|
| **Strategy** | **0.20 (0.31)** | 4.1% | 12.5% | -26.8% | -11.7% | -13.5% |
| Constant weight 0.173 short | 0.40 (0.32) | 7.0% | 13.4% | -29.4% | -16.6% | -18.3% |
| Buy-and-hold -1x (XIV fee) | 0.50 (0.33) | **-7.8%** | 77.6% | -99.2% | -96.1% | -96.6% |
| Buy-and-hold -0.5x (SVXY fee) | 0.49 (0.33) | 13.9% | 38.8% | -71.0% | -48.0% | -51.1% |
| Cboe PutWrite | 0.53 (0.32) | 8.5% | 12.5% | -28.9% | -11.5% | -18.3% |
| S&P 500 (SPY, total return) | 0.75 (0.31) | 15.0% | 17.7% | -33.7% | -10.9% | -18.0% |

In the design window the strategy's Sharpe is 0.45 against the constant weight's 0.46.

Three things this table says and the headline does not:

1. **The dynamic rule does not beat a fixed small short.** A constant 0.173 short has a
   higher Sharpe out of sample (0.40 against 0.20) and a higher CAGR. What the signals
   and the budget buy is the tail: the worst day is -11.7% against -16.6%, the worst
   week -13.5% against -18.3%, and the skew -3.0 against -4.1. On this evidence the
   dynamic parts earn their keep as a risk control, not as a source of return.
2. **A Sharpe ratio is not a verdict here.** Buy-and-hold -1x has the second-highest
   Sharpe in the table and lost 7.8% a year: the ratio is computed on daily returns
   whose -96% day it can barely see, while compounding cannot ignore it.
3. **The strategy's own Sharpe is not distinguishable from zero.** 0.20 with a Lo (2002)
   standard error of 0.31.

Variants, out-of-sample Sharpe: no crash budget (volatility targeting alone) **-0.03**
with a -43.5% drawdown; no signals (always on) **0.26** with a -24.2% worst day. After the
A-02 timing correction these two no longer point the same way. The crash budget carries
the return: removing it costs 0.23 of Sharpe and widens the drawdown by 17 points. The
signals cost 0.07 of Sharpe and buy the tail: removing them *raises* the ratio to 0.26
while doubling the worst day to -24.2%. The honest statement is that the budget earns the
return and the filters pay for the tail, not that both add return.

## V29. February 2018: what the escape rests on

The strategy lost 0.07% on 5 February 2018, against -95.1% for buy-and-hold -1x, and
-8.9% over the whole volmageddon window. It was flat that day because the contango
filter turned off at the close of Friday 2 February - and it turned off by
**0.72%**: `cm30/cm90` printed **1.0072** against a threshold of 1.0.

The variance-risk-premium filter did *not* turn off. It was on through the event and
rose with it (VRP 0.115 on 5 February), because implied variance jumps before realised
variance does: in a spike that filter says "sell volatility" precisely when volatility
is exploding.

Had the position been held, the weight computed at the close of 1 February (0.395)
against a +96.1% index day is a **-38.0%** loss - which is exactly what the two-day-lag
variant records as its worst day. So the single most favourable fact about this
strategy rests on one filter clearing its threshold by seven parts in a thousand, on
the last day it could have. Reported as fragility, not as evidence that the rule works.
L18; Phase 12's threshold grid (0.95 to 1.025) will price it.

## V30. H5

`alpha_regression.csv`, `alpha_regression_specs.csv`. Out of sample, on excess returns,
Newey-West at 8 lags:

    r_strategy = alpha + b_PUT r_PUT + b_SPX r_SPX + b_VXX r_VXXlike + e

**alpha = -2.2% a year, t = -0.77, p = 0.44**, R^2 = 0.44, n = 2,691. The alpha is
insignificant in all five specifications run (three-factor, PUT+SPX, VXX only, PUT
only, SPX only): between -2.2% and +0.4% a year, every |t| below 0.78.

The individual betas should not be read as economic loadings: PUT and SPX correlate
0.897, so the three-factor PUT coefficient (-0.35) is a partial coefficient in a
badly conditioned regression. Univariate betas are +0.33 on PUT and +0.31 on SPX.
The up/down split of the equity beta is the informative one: **0.18 in up markets,
0.43 in down markets** (difference p = 0.009). The average beta understates what this
position does when the market falls.

| H5 | Criterion | Result |
|---|---|---|
| First half | positive out-of-sample Sharpe net of 1 tick per side | 0.20 - **holds**, but with a standard error of 0.31 |
| Second half | alpha not distinguishable from zero at 5% | t = -0.77 - **holds** |

**H5 is not rejected.** The uncomfortable reading, which the write-up keeps: the
premium survives crash budgeting in the sense that what is left is positive and
indistinguishable from both zero and a fixed small short position, and every one of
its factor-adjusted returns is consistent with being paid for crash exposure rather
than for skill.

---

## V31. The specification grid

144 cells: contango threshold (0.95, 0.975, 1.0, 1.025) x volatility target (0.10,
0.15, 0.20) x crash budget (0.10, 0.20, 0.30, 1.00) x rebalance interval (1, 5, 21),
each run end to end and each written to `specification_distribution.csv`.

| | Out-of-sample Sharpe |
|---|---|
| Minimum | -0.37 |
| First quartile | -0.04 |
| **Median** | **0.06** |
| Third quartile | 0.20 |
| Maximum | 0.50 |
| **Chosen configuration** | **0.20 - the 74th percentile** |
| Share of cells above zero | 67.4% |

**Warning, by the phase's own criterion.** The chosen configuration is not the maximum,
but it sits in the upper quartile rather than near the median. The parameters were
fixed in `config/config.yaml` before any data was retrieved (V24), so this is not
selection after the fact - but it does mean the pre-registered cell was a lucky one,
and the median specification's Sharpe of **0.06** is the number a reader should carry
as "what this strategy earns if you did not happen to pick well".

Specifications run in this phase: 204 (144 grid + 50 one-at-a-time + 10 cost cells).
Phase 11 ran 13 backtest variants and Phase 10 five forecast specifications, so the
project has run about 220 in total, all reported.

## V32. One-at-a-time sweeps

`robustness_parameters.csv`, out-of-sample Sharpe, baseline 0.20:

| Parameter | Cells | Range | Where the baseline sits |
|---|---|---|---|
| Contango threshold | 0.95 / 0.975 / **1.0** / 1.025 | -0.17 to 0.20 | **the best of the four** |
| Crash budget `l_max` | 0.10 / **0.20** / 0.30 / 1.00 | -0.03 to 0.37 | second of four; tighter is better |
| Rebalance interval | **1** / 5 / 21 days | 0.03 to 0.38 | middle; 5 days is the worst |
| Volatility target | 0.10 / **0.15** / 0.20 | 0.11 to 0.29 | middle |
| Volatility lookback | 10 / **21** / 63 | 0.18 to 0.30 | middle; 63 days is the best |
| Slope measure | **cm30/cm90** / VIX/VIX3M | 0.20 / 0.16 | the primary does better - **reversed by A-02**, because VIX3M is a cash index and is now execution-aligned too |
| Variance proxy | **rs** / parkinson / gk / close-to-close | 0.06 to 0.27 | third of four; close-to-close is much worse |
| HAR horizon | 10 / **21** / 42 | 0.16 to 0.26 | middle |
| HAR lags | **(1,5,22)** / (1,5,10) / (1,10,44) | 0.15 to 0.20 | the best of three |
| HAR log transform | **log** / level | 0.20 / 0.24 | the level specification does better - **reversed by A-02** |
| Retransformation | **normal** / smearing | 0.20 / 0.23 | smearing does better - **reversed by A-02** |
| Crash floor | **running max** / event (hindsight) | 0.20 / 0.25 | the honest one is lower |
| EVT threshold | eight quantiles | 0.20 flat | the floor binds, so the tail model barely matters |
| Index construction | **rolled** / shifted / constant-maturity / calendar spread | 0.04 to 0.20 | see V33 |
| Signal lag | 0 / **1** / 2 | -0.13 to 1.54 | the leak calibration |

**Four orderings reverse after the A-02 timing correction**, and they are listed above
rather than smoothed over: the VIX3M slope, the level HAR, smearing retransformation and
the Parkinson variance proxy all now beat the pre-registered choice. Three of the four are
alternative *forecast* specifications, which is consistent with the correction having
removed information from the VRP filter rather than with any of them being better models.
The configuration is not changed after the fact; but the honest reading of this table is
now that the pre-registered cell is a middling choice on several axes, not a good one.

Two cells change the interpretation rather than the number:

* **Rebalancing weekly turns the February 2018 result inside out.** At a 5-day
  interval the exit signalled on Friday 2 February is not executed until the next
  rebalance, so the position is held through the event: worst day **-38.0%**, February
  return **-31.7%**, Sharpe 0.03. At 21 days the grid happens to rebalance clear of it
  and the Sharpe is 0.38. The protection is therefore not a property of the sizing
  rule; it is a property of acting on the signal the same day.
* **A threshold of 1.025 holds the position into the event**: February return
  **-24.3%**, worst day -24.2%, Sharpe 0.01.

## V33. Alternative constructions

| Construction | Out-of-sample Sharpe |
|---|---|
| Rolled index (the reconstruction used throughout) | 0.20 |
| One-day-shifted roll convention | 0.20 |
| Constant-maturity 30-day basket | 0.20 |
| Calendar spread, front against fourth month | 0.04 |

The reconstruction choice does not carry the result: the two alternative ways of
holding the curve give the same answer to two decimal places. The calendar-spread
version - which isolates the slope from the level - earns much less, so what the
strategy is paid for is being short the level, not the shape.

## V34. Subsamples

`robustness_subsamples.csv`. Configured periods: 2008-2012 **0.92**, 2013-2017 0.28,
2018-2021 **-0.27**, 2022-onwards 0.10. Single years inside the evaluation window run
from **-1.12** (2020), -1.04 (2018) and -0.97 (2022) to **+1.20** (2017) and +0.93 (2023).

Leave-one-year-out on the evaluation window: 0.03 (excluding 2017) to 0.32 (excluding
2018). So no single year manufactures the result, but 2017 carries a large share of
it: drop that one year and the Sharpe falls from 0.20 to 0.03 - a thinner margin than
before the A-02 correction, and the sharpest single statement of how little this strategy
earns outside one year. Leave-one-stress-window-out moves it to at most 0.27, and no
stress window accounts for more than half the total return (-8.9% and -4.8% for
Volmageddon and Covid; the August 2024 window is **+0.1%**, a small gain rather than a
loss, because the correctly lagged VRP filter kept the position flat - against a total of
+53.6%).

## V35. The red team, answered with numbers

`redteam_answers.csv`, in the prompt's order:

1. **Weakest assumption**: the contango threshold. February 2018 by threshold: -0.1%
   at 0.95, 0.975 and 1.0; **-24.3% at 1.025**.
2. **Could look-ahead explain it?** A one-day leak gives a Sharpe of 1.54 against
   0.20, and a *fifteen-minute* leak was in fact present until the recursive audit (A-02),
   worth 0.069 of Sharpe; the whole-chain perturbation test passes and is mutation-checked.
3. **Survivorship**: XIV is in the product sample for its whole life, including its
   acceleration on 2018-02-21, and no product was dropped.
4. **Cost breakeven**: **1.77 ticks per side** (0.088 VIX points) takes the
   out-of-sample Sharpe to zero.
5. **Period dominance**: 2017 contributes +25.5% of a +53.6% total; excluding it the
   Sharpe is 0.03. No stress window exceeds half the total.
6. **Single-day dominance**: the largest day is -11.7% (10 August 2017), 17% of the
   total return in absolute terms - 21.8%, up from 17.0% before the A-02 correction
   shrank the denominator; the tail jackknife is V19.
7. **Parameter selection**: grid median 0.06, chosen 0.20 at the 74th percentile.
8. **Asset bounds**: H2 is already stated at the lower bound (Phase 08); the upper
   bound only strengthens it.
9. **Is the story fitted?** The alpha is -2.2% a year (t = -0.77) and the equity beta
   is asymmetric (0.18 up, 0.43 down) - which is what the design predicted before the
   data was seen. But a constant-weight short earns more per unit of risk than the
   dynamic rule, so the part of the story that says the *rule* adds value is not
   supported.

---

## V36. Clean-clone reproduction (Phase 15)

The repository was cloned to a fresh directory and exercised as a reader would. What
happened, in full, including the two defects it found.

**What reproduces from the clone alone.**

| Step | Result |
|---|---|
| `python scripts/run_tests.py` | **245 passed, 2 skipped** — identical to the source tree |
| `python scripts/check_results_numbers.py` | **passes** — every number in the four write-ups matches its committed table |
| `python scripts/make_figures.py` | **20 of 24 figures rebuild**; 4 fail with a clear message |
| `python scripts/run_pipeline.py --only clean` | stops with exit code **2** and names the command to run |

**What does not, and why that is correct.** `data/raw/` is gitignored, so a clone holds
the manifest but not the 338 raw files. The pipeline does not download implicitly: the
clean stage stops with

> Missing raw VIX futures files: data/raw/cboe/vx → run: `python scripts/fetch_data.py --only futures`

and explains that every input must come through `fetch_data.py` so that its URL,
retrieval time and SHA-256 are recorded. Four figures (`index_vs_products`,
`decay_regression`, `decay_blocks`, `feb2018_detail`) read cached product price files
rather than a processed CSV, so they fail the same way and `make_figures.py` exits 1.
That is the intended behaviour, not a reproduction failure: the alternative is a figure
built from data whose provenance was never recorded.

**Defect 1: three committed figures were stale.** Rebuilding all 24 figures produced
byte-identical output for 21 and *different* output for `feb2018_detail`,
`rolling_sharpe` and `weight_and_binding_constraint`. The cause is a Phase 14 gap, not
non-determinism: those three were last written in Phase 11 (commit 9ed5840), while
`viz/figures.py` changed in Phase 14 (7ca64e4), so the figures in the repository were
not the output of the code that builds them. Rebuilt and committed in Phase 15. Three
consecutive rebuilds now give byte-identical output, and the rebuilt versions were each
read and checked against the claims they support.

**Defect 2: `shade_windows` measured the axis before there was one.** The stress-window
labels all sit on one row, so `volmageddon 2018` and `covid 2020` — about two years
apart on an eighteen-year axis — printed on top of each other. A first fix compared the
gap between windows against `ax.get_xlim()`, which looked right and did nothing, because
`shade_windows` is called *before* the data is plotted: the limits are still matplotlib's
default `(0, 1)`, so every gap measured as enormous. (The same latent assumption sits in
the open-window branch, which resolves `hi=None` to `get_xlim()[1]`; it is not exercised
by any current figure and is left as a known limitation rather than changed untested.)
The working fix defers the decision to draw time and compares the labels' *rendered*
extents, which is the only point at which both the limits and the text width exist. A
test asserts the labels do not overlap and fails on the pre-fix behaviour.

**What this test does not establish.** That the tables themselves reproduce from raw
data — that needs the 338 raw files, which this environment cannot fetch (see the note
in `README.md`). The clone test establishes that the code, the tests, the number checks
and 20 of the 24 figures reproduce from what the repository actually contains. **V37
closes this gap.**

## V37. Full reproduction from raw data (recursive audit, Pass 1)

The gap V36 left open — whether the *tables* reproduce from the raw files — was closed in
the recursive audit. A fresh `git clone` into an empty Linux container, the 338 raw files
restored and verified against the manifest, and `scripts/run_pipeline.py` run end to end
with no other change.

| Step | Result |
|---|---|
| Interpreter and libraries | Python 3.11.15, **numpy 2.4.4, pandas 3.0.2, scipy 1.17.1, matplotlib 3.10.9** — every one materially newer than the lower bounds in `requirements.txt` |
| `scripts/run_tests.py` (no pytest present, bundled shim) | **245 passed, 0 failed, 2 skipped** |
| `verify_manifest()` over 338 entries | **clean** |
| `scripts/run_pipeline.py` (full, from raw) | completes; all eight stages |
| **42 of 42 tables** against the committed versions | **byte-identical** |
| **24 of 24 figures** against the committed versions | **byte-identical** |
| 8 of 8 processed datasets | byte-identical |

This is a stronger result than the project had previously established, and it is what
made the rest of Pass 1 possible: with the unchanged pipeline reproducing every committed
artefact bit for bit, every difference produced by the A-02 correction is attributable to
that correction alone and to nothing about the environment.

**Independent recalculation alongside it.** The headline statistics were also recomputed
from the committed `backtest_daily.csv` by a separate implementation that imports none of
`svcarry`. CAGR, annualised volatility, maximum drawdown, hit rate, worst and best day,
time invested, average and maximum weight and annualised turnover all agree in all three
windows to within 4.2e-15. The engine's internal identities hold: `ret = gross - costs`
to 1.0e-16, `costs = cost_rebalance + cost_roll` to 1.0e-16, `turnover = rebalance + roll`
to 2.2e-16, `equity = cumprod(1 + ret)` to 5.6e-14. The Sharpe convention was confirmed to
be excess of the T-bill accrual by backing the implied rate out of the ratio: 1.43% a year
full sample, 0.24% design, 2.32% out of sample, each consistent with realised bill yields
in that window.

**Test count, dated so it cannot drift silently.** **245 passed, 2 skipped** at the start
of the recursive audit; **264 passed, 2 skipped** at the close of Pass 4, the audit having
added nineteen tests - thirteen in `tests/test_timing_and_costs.py` (A-02/A-05), four in
`tests/test_figure_single_writer.py` (A-12) and two in `tests/test_evaluation.py` (A-13).
The live number is whatever `make test` prints; `README.md`'s Status table is the one place
it is quoted, because quoting it in four places is what made it drift (A-16).

---

## Open items

1. The 2016 and 2019 steps in V6 are not explained.
2. The seven SEC filings are not yet verifiable in this environment (V2).
3. Post-October-2020 slopes are 0.985 (VIXY), 0.991 (SVXY), 0.971 (UVXY) — close to
   but not equal to one. Whether the residual 1-3% is product tracking difficulty,
   fee drag mis-attributed to the slope, or remaining index noise is not resolved.
4. The HAR forecast is weak in 2013-2019 (OOS R^2 0.005, MZ slope 0.51) and no better
   than trailing RV on MSE in 2008-2012 (V21).
5. The retransformation understates the conditional mean by about 9% (V21, L15);
   smearing is carried to Phase 12.
6. Why the strategy's partial PUT beta is negative while its univariate beta is
   positive is collinearity, not a finding; the separate loadings are not identified
   (V30).
7. Why a 21-day rebalance does better than a daily one (0.38 against 0.20) is not
   established: lower costs and a lucky alignment around February 2018 both
   contribute, and this sample cannot separate them.
8. `shade_windows` resolves an open window's right edge with `ax.get_xlim()[1]`, which
   is matplotlib's default `(0, 1)` when the function is called before the data is
   plotted (V36, defect 2). No current figure passes an open window, so the path is
   unexercised; it is recorded rather than changed without a case to test it against.
