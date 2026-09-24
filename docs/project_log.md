# Project log

Append-only. Entries record what actually happened, including what failed. A decision
that was later changed appears twice, with both entries kept.

> **Reading the performance numbers in this log.** Entries up to Session 13 quote an
> out-of-sample Sharpe of **0.27**. That number was superseded on 2026-09-24 by the
> recursive audit, which found a fifteen-minute look-ahead in the VRP filter after October
> 2020 (Session 14, register A-02). The current figure is **0.20**. Earlier entries are not
> rewritten — that is the point of an append-only log — so take any performance figure here
> as what was believed at the date of its entry, and `docs/results.md` as what is true now.

---

## 2026-09-20 — Session 1: environment, econometrics core, design, prompt pack

**Objective.** Take the project from an empty folder to a research design, a tested
analysis library and a repository, and establish what the execution environment can
actually do.

### Environment findings

Probed before writing anything.

| Surface | Result |
|---|---|
| Project folder `D:\MFE\Projects\Project1_ShortVol_ETPsVIX_Carry` | Empty. Nothing to preserve |
| Cloud Python | 3.11.15 with numpy 2.4, pandas 3.0, scipy 1.17, matplotlib 3.10, scikit-learn 1.8 |
| `statsmodels`, `arch`, `yfinance`, `pytest`, `pyarrow` | **Absent** |
| PyPI, npm | **403 at the egress proxy** — installation refused by policy, not by error |
| `cdn.cboe.com`, `query1/2.finance.yahoo.com`, `fred.stlouisfed.org`, `www.sec.gov` | **403 on CONNECT** — all market-data hosts blocked |
| `github.com`, `api.github.com` | Reachable; `git ls-remote` works |
| Local Linux workspace on the user's PC (`device_bash`) | **Failed to start** — no shell available on that machine |
| Device file bridge (list / stage / commit) | Working |
| Web search and fetch tools | Working — these reach hosts the container's own egress cannot |

**Consequences for the design, recorded because they are visible in the repository:**

1. Every econometric estimator is implemented against numpy/scipy and unit-tested
   against simulated data with known parameters, rather than imported. The test suite
   cross-checks against `statsmodels` and `arch` where importable and skips otherwise.
   This is a constraint turned into a property: the estimators are inspectable.
2. `pytest` is unavailable, so `scripts/run_tests.py` provides a zero-dependency
   runner with a minimal in-process pytest shim. The tests themselves are ordinary
   pytest tests and run under real pytest unchanged.
3. The bulk data pull cannot run here. Individual endpoints were verified through the
   web-fetch tool — notably the Cboe per-contract URL pattern, which returned the
   expected header and rows — but no dataset has been downloaded, and no result in
   this repository is reported from data.

### Work completed

| Commit | Contents |
|---|---|
| `cb065c5` | Repository skeleton; calendar; HAC/OLS; standardised normal, Student-*t* and Hansen skewed-*t*; GJR-GARCH; GPD/EVT; realised-variance estimators; HAR. 83 tests |
| `2bdeb31` | Configuration; filings register; cached and hashed HTTP layer; Cboe, prices, FRED and EDGAR downloaders; `scripts/fetch_data.py`; index reconstruction; ETP mechanics. 109 tests |
| `ef232d4` | `docs/research_question.md`, `docs/research_design.md` |
| `c3ea965` | Signals; crash-budgeted sizing; backtest engine; performance metrics; attribution regressions; Kelly; stationary bootstrap. 145 tests |
| `3db0269` | Prompt pack: index, three templates, sixteen phase prompts |
| `943b826` | Prompt pack: five task prompts, nine operational prompts |

**Test suite: 143 passing, 2 skipped** (the two skips are the `statsmodels` and `arch`
cross-checks, which skip when those packages are absent).

### Problems encountered and what was done

**1. `pytest` unavailable.** Wrote `scripts/run_tests.py` with an in-process shim
supplying `mark.parametrize`, `approx`, `raises`, `skip` and `fixture`. First version
failed with `NameError` on `parametrize` inside a class body — class bodies do not
close over enclosing function scope in Python. Fixed by binding the function to a
local alias first.

**2. `ndarray == pytest.approx(...)` returned an array.** NumPy's `__eq__` took
precedence over the shim's. Fixed by setting `__array_ufunc__ = None` and
`__array_priority__` on the approx class so NumPy defers to the reflected operation.

**3. Kelly optimiser bracket bug — a real defect, found by a test.**
`kelly_fraction` bounded the search symmetrically at `±1/max(R)`. The growth objective
is `−inf` wherever `1 − fR ≤ 0`, which for a sample containing a large *down*-move
happens at the negative end of that bracket. A bounded Brent search does not survive
`−inf` inside its interval, and the optimiser returned a value that was visibly wrong
(1.79 against a Gaussian benchmark of 2.0 on a Gaussian sample).
Fixed by deriving the two-sided solvency bounds separately: `f < 1/max(R)` and
`f > 1/min(R)`. After the fix `f*` agrees with `−mean/variance` on a Gaussian sample to
within 0.1%. The same fix was applied inside the bootstrap loop. *Worth recording
because the symptom was a plausible-looking number, not an error.*

**4. Four test expectations were wrong, not the code.** Each was corrected with its
reasoning written into the test:
- 2018 had 251 US trading days, not 250 (10 full-day closures including the
  5 December mourning day).
- A drawdown arithmetic slip (0.9240 written where the trough was 0.8316).
- A GPD fitted to Gaussian tails gives `ξ ≈ −0.15` at the 98th percentile, not
  `ξ ≈ 0`: convergence to the Gumbel limit is famously slow. The test now asserts the
  economically relevant property — the estimator does not manufacture a heavy tail —
  rather than pretending the finite-sample bias is absent.
- The Lo (2002) Sharpe standard-error correction only exceeds the naive one when the
  Sharpe is *positive* and the skew negative. The original test used a series with a
  near-zero Sharpe, where the correction correctly goes the other way. Rewritten with
  the short-volatility shape it is meant to describe.

**5. Two test expectations were poorly calibrated rather than wrong.** The
look-ahead-leak test asserted a leaked Sharpe above 15; the correct figure for
"short only on down days" is about 11 (≈ 0.4/0.583 per day annualised). Threshold
lowered to 8 and the arithmetic written into the comment.

### Validation performed

- Calendar: settlement dates checked against eight independently known expiries,
  including the 2018-02-14 contract; weekday and monthly-uniqueness invariants over
  2006–2030.
- Distributions: density integrates to one, mean 0 and variance 1, CDF equals the
  integrated PDF, and the quantile function inverts the CDF, for six parameter sets.
  Skewed-*t* with zero skew reduces exactly to the standardised *t*.
- GARCH: parameter recovery from 12,000 simulated observations; recursion checked
  against a hand-written loop; no residual ARCH by Ljung–Box; forecast converges to the
  unconditional variance.
- EVT: parameters recovered from simulated GPD samples; out-of-sample exceedance rate
  at the estimated 99.9% quantile within the expected band; mean-excess slope matches
  `ξ/(1−ξ)`; Hill estimator recovers a known Pareto index.
- HAR: a look-ahead test that perturbs the variance series after a cut-off and requires
  every earlier forecast to be bit-identical.
- Index reconstruction: synthetic panels with analytically known answers. The load-
  bearing one builds a steep term structure in which every contract's own price is
  constant — the correct construction returns exactly zero, while a naive front-month
  `pct_change()` books a fake loss above 2% on every roll date.
- ETP mechanics: the rebalancing trade checked from first principles against "restore
  exposure to `L` × assets"; the decay identity recovered from a simulated,
  exactly-rebalanced product; the fee recovered from the regression intercept.
- Backtest: the engine's one-day lag destroys a deliberately leaked signal's Sharpe
  (from ~11 to ~0); perturbing the index after a cut-off leaves every earlier strategy
  return bit-identical.

### Decisions made

| Decision | Alternatives | Why |
|---|---|---|
| Repository name `short-vol-etps-vix-carry` | `Project1-ShortVol`, `vix-carry-research` | Matches the account's kebab-case convention |
| Implement estimators rather than import | Wait for package access; drop the methods | Access is refused by policy; and the resulting code is inspectable and tested, which is better for the project's purpose |
| Primary slope signal `cm30/cm90`, not `VIX/VIX3M` | Truncate the design window to 2009+ | The Cboe VIX3M file starts 2009-09-18, inside the design window; the futures-implied slope covers the whole sample and is closer to what the strategy trades. `VIX/VIX3M` retained as a robustness variant with an overlap test |
| Daily variance proxy = overnight + Rogers–Satchell, not literal Yang–Zhang | Use a 21-day rolling Yang–Zhang | Yang–Zhang is a window estimator with no single-day value. The components used are the ones it is built from. Documented rather than glossed |
| Build both roll conventions and choose on tracking error | Assert the S&P convention | A one-day roll error is invisible in a plot and systematic in every return |
| Bound assets outstanding rather than estimate them | Interpolate a point estimate | The flow result is linear in assets; a point estimate would imply precision the inputs do not support |
| Sample starts 2008 | 2006, or 2004 | Second-month liquidity is unreliable before late 2005; 2008 keeps the crisis in sample |

### Research implications

Nothing empirical yet — no data has been downloaded, so no hypothesis has been tested.
The design is fixed and committed (`ef232d4`), which is the point: the sample split,
the thresholds and the rejection criteria are now on the record before any result
exists.

### Blocked on

1. **Egress policy.** All market-data hosts refused. The user has chosen to enable full
   network access; it had not taken effect by the end of this session. Nothing
   downstream of Phase 05 can run until it does.
2. **GitHub push.** The repository `soham-parundekar/short-vol-etps-vix-carry` was
   created by the user, but this session's git proxy refuses to inject a credential
   for it: *"not in this session's authorized repository set"*. Six commits are
   unpushed. A full `git bundle` was written to the project folder as a fallback so
   the history can be published from the user's own machine. **The work is not on
   GitHub and has not been described as if it were.**

### Next action

Run `scripts/fetch_data.py` the moment egress allows, then Phase 06 (cleaning and
panel construction) followed by Phase 07 (index reconstruction and tracking
validation). Until then: visualisation module, pipeline runner and README skeleton,
none of which need data.

---

## 2026-09-20 — Session 2: first run on real data; three bugs, one open question

**Objective.** Both blockers cleared by the user (network via a local fetch, GitHub
via a bundle push). Stage the downloaded data in, build the futures panel, and run
the index reconstruction with its tracking validation.

### Data landed

233 monthly VX contracts (2008-01-16 → 2027-05-18), 7 Cboe index series, 8 price
series, 3 FRED series, 7 SEC filings. 251 of 251 staged files re-hash to the SHA-256
recorded in the manifest, so nothing was corrupted crossing the device bridge.

**Calendar validated against reality.** The 233 settlement dates the calendar derives
from the contract specification match, exactly, the 233 contract files Cboe served
across 2008-2027 — no discrepancy in either direction. The calendar was never fitted
to the data; this is an out-of-sample check on it.

### Bug 1 — NYSE New Year's Eve rule (calendar)

Five dates carried settlement prices and real volume while the calendar called them
holidays. Two of them, 2010-12-31 and 2021-12-31, were the code's fault: a holiday
falling on a Saturday is observed on the preceding Friday **unless that Friday is the
last trading day of the calendar year**, and 1 January fell on a Saturday in 2011 and
2022. The carve-out was missing, so both sessions were dropped and every business-day
count in the surrounding roll periods shifted. Fixed, with the rule written out.

The other three — 2015-04-03, 2018-12-05, 2025-01-09 — are real: CFE held a session
while the equity market was shut. That is not a bug but a missing distinction, so the
calendar now carries separate NYSE and CFE markets, and the roll calendar takes its
business days from the futures panel itself rather than from any derived calendar.
After the fix, zero panel dates fall outside the calendar.

### Bug 2 — inverted split factor (prices)

The provider reports a 1-for-5 reverse split as 0.2. Historical prices must be
multiplied by 1/0.2 = 5 to splice onto the current share count; the code multiplied by
0.2, which prints a +2,400% return on the split date and mis-scales everything behind
it. Found by comparing the manual reconstruction against the provider's adjusted
close: max absolute difference 4.05 in return units.

### Bug 3 — the cross-check was itself invalid (prices)

After fixing Bug 2 the two series still disagreed. Yahoo's chart endpoint returns
OHLC that is **already split-adjusted**: `close.pct_change()` and
`adjclose.pct_change()` are identical to the bit for these products. So "rebuild the
adjustment from raw close and the split factors" is not an independent check, it is a
second adjustment. The manual path now detects a pre-adjusted provider and raises
rather than returning a plausible wrong answer. Seven tests added covering both bugs.

### Index reconstruction — built, and it looks right

4,704 daily observations, 2008-01-02 → 2026-09-18. Annualised return −47.1%,
annualised volatility 73.3%: the expected signature of a rolling short-term VIX
futures position. **5 February 2018 reconstructs as +96.1%** — the index almost
doubled in a day, against a −1× product's 80% wipeout threshold. Worst day −26.0%,
the following session's reversal.

### H1 — REJECTED as stated, with a diagnosis

The hypothesis was a tracking error of 10 bp/day against VIXY and VXX net of fees,
failing above 25 bp. Actual, by era:

| product | era | n | sd (bp/day) | corr | slope |
|---|---|---|---|---|---|
| VIXY | 2011-2017 | 1,637 | 124.5 | 0.9573 | 0.8871 |
| VIXY | 2018-2021 | 1,008 | 242.8 | 0.9098 | 0.7943 |
| VIXY | **2022-2026** | 1,182 | **28.2** | **0.9980** | **0.9858** |
| VXX | 2022-2026 | 1,182 | 101.2 | 0.9731 | 0.9201 |

Two hypotheses raised and **rejected** by test rather than by argument:

1. *Settlement-time mismatch between the 4:15pm futures settlement and the 4:00pm
   equity close.* Rebuilding the index on the futures `close` column instead of
   `settle` made the best era worse (28 → 104 bp) and did not help the others.
2. *The settle-versus-close gap in the futures data explains the era pattern.* The
   gap is **larger** in 2022-2026 (median 0.29%) than in 2011-2017 (0.13%), i.e.
   largest exactly where tracking is best.

The decisive diagnostic: the regression slope divided by each product's own leverage
is 0.8871 (VIXY, +1x), 0.8886 (SVXY, -1x) and 0.8767 (UVXY, +2x) over 2011-2017 —
three issuers, three leverages, **one common attenuation factor of 0.884**. An
attenuation common to all three cannot be a property of the products; it is
errors-in-variables in the regressor, which is the reconstructed index. The implied
idiosyncratic noise is about 0.36 × index volatility in the early era and near zero
from 2022.

So the reconstruction is essentially exact in 2022-2026 and carries real noise before
it. That noise is the open question, and it bounds the precision of every downstream
claim until it is resolved.

### Open: the 2012 endpoint-boundary gap

The modern Cboe archive begins 2013-01-02 and truncates every contract already listed
then: the January-2013 contract's modern file holds 10 rows where its legacy file
holds 275. Consequently the seven sessions of 20-31 December 2012 have no contract
priced at all. The downloader now fetches the legacy file as a companion
(`VXL_<expiry>.csv`) for boundary contracts and the loader takes the union; this
needs one re-run of the fetch on a machine with network access to take effect.

### Next

1. Re-run the futures fetch to close the December 2012 gap.
2. Resolve the pre-2022 index noise. Next candidates, in order: settlement-price
   granularity and staleness in the second-month contract; whether the roll period
   boundary matches the S&P methodology exactly (the tracking residual should be
   regressed on the roll weight, which is the test the phase prompt already
   specifies); and whether the products' own tracking error against their benchmark
   accounts for part of it.
3. H1 stands rejected as written until then. It is not to be relaxed to fit.

---

## Session 3 — 20 September 2026

The December 2012 gap is closed, and the pre-2022 index noise is resolved: it is a
market-structure fact with a date attached, not a defect in the reconstruction.
Getting there turned up three more data defects, all of the same dangerous kind —
the pipeline completed, the output looked normal, and prices were missing.

### The re-run, and what it exposed

The fetch re-run retrieved 80 legacy companion files (January-2008 through
August-2014 expiries; the legacy archive ends there). All 331 locally-present files
verify byte-for-byte against the manifest.

Closing the December 2012 gap immediately exposed a worse one. Checking coverage
session by session rather than only at the boundary showed **95 consecutive
sessions, 2013-01-02 to 2013-05-17, with no contract priced at all**. Cboe's modern
archive publishes `Settle = 0` for 852 cells across 98 sessions in the first half of
2013 while populating every other column normally. The zeros were correctly
converted to NaN — but *after* de-duplication, and the de-duplication rule was
"modern archive wins", so the empty modern row beat the legacy row holding the real
price.

This had been in the index the whole of the previous session and did not announce
itself: the reconstruction returns NaN on an unpriced day and the level forward-fills
across it.

Two further defects found alongside it:

* Fourteen legacy files carry a legal disclaimer above the CSV header. The parser
  read that line as the header, failed, and `load_vx_panel` swallowed the exception.
* That swallowing was itself the deeper defect. A file that cannot be parsed now
  raises by default.

All three fixes were **mutation-tested**: each was reverted in turn and the new test
file re-run, failing 1, 3 and 2 of its 10 tests respectively. A test that would not
have caught the bug is not a test.

The panel is now 41,872 rows over 4,711 sessions with zero unpriced days, and the
index covers 2008-01-02 to 2026-09-18 with zero NaN returns.

### Cross-validating the two archives

13,127 (date, expiry) cells carry a settlement price in both archives. **One**
disagrees: 2013-05-28, February-2014 expiry, modern 20.10 against legacy 10.25. The
rest of the curve that session runs 15.20 up to 19.60 in monotone contango, so 10.25
would sit 9.35 points below the front month at nine months out. The legacy print is
bad; the merge rule already resolves it correctly, and it is now a test.

### The roll convention, settled

`sp_dji` wins all 16 tracking comparisons against `shifted`, by 1.3 to 7.1 bp a day.
And the residual-on-roll-weight regression the phase prompt specified comes back
clean: every |t| < 1.21, every p ≥ 0.227. The roll is not the source of the tracking
error. Recorded with its numbers in `reports/tables/roll_convention.csv`.

### The open question, answered

Two hypotheses rejected by measurement: second-month staleness (the index-return ×
roll-weight interaction is insignificant in every era, |t| ≤ 1.10, and the second
month's share of front-two volume is flat at 0.38-0.44 across all nineteen years),
and closing prices in place of settlement prices (worse in every era).

What the evidence supports is non-synchronous measurement. Regressing the de-levered
product return on the index at t−1 as well as t, over 2011-2017, the lagged index
loads at t = 4.97, 4.62 and 4.49 for VIXY, SVXY and UVXY — the signature of an index
struck *after* the product's closing price.

And there is a dated cause. Cboe moved the VX daily settlement calculation from
3:15 p.m. CT to **3:00 p.m. CT effective 26 October 2020** — that is 4:00 p.m. ET,
exactly when the products' consolidated close is struck. Before it the two series
are measured fifteen minutes apart.

The break was located in the data rather than assumed: the ratio of median tracking
difference before to after is maximised at 2020-10-26 (3.51) and falls away on either
side (2.71 at 1 October, 2.42 at 15 November, 1.08 at 15 December). Daily tracking
error against VIXY goes from 137 bp in 2019-2020 to 31 bp after.

Honestly stated: this explains the largest and final step, not all of it. The lagged
loading dies after 2015 and the contemporaneous slope improves around 2019, both
before the settlement change. Those are recorded as unexplained in
`docs/validation.md` rather than attributed to a mechanism not demonstrated.

**H1 remains rejected as written.** The consequence is carried forward explicitly:
the reconstruction carries roughly 120 bp/day of measurement noise against the
products before October 2020 and roughly 30 bp/day after, and that bounds the
precision of every pre-2020 result.

### Also this session

* `docs/validation.md` written — the file several docstrings already pointed at.
* The `index` pipeline stage implemented properly (it was a stub); it now builds both
  conventions, both comparison tables, the constant-maturity curve and the carry
  measures, and records its QC block in `reports/_pipeline_state.json`.
* The test-runner shim gained fixtures (`tmp_path`, `monkeypatch`, user fixtures
  including generators), `pytest.warns`, and honoured `match=` on `raises`.
* `data/raw/_manifest.json` is now tracked. It holds no vendor data, only URLs,
  timestamps, sizes and hashes — excluding it made the raw layer unverifiable by a
  reader, which defeats its purpose.

### Next

1. Phase 07 close-out: reconcile 5 February 2018 against the product filings.
2. Stage the seven SEC filings and run `prompts/tasks/verify_filing_terms.md`.
3. Phase 08 onward: ETP mechanics and rebalancing flows.

---

## Session 4 — 21 September 2026

Phase 07 closed. The reconstruction is now anchored to a primary document at the one
date where being wrong would matter most, and every product term in the repository
has been quoted from the filing that states it.

### 5 February 2018 reconciles to the filing

Credit Suisse's acceleration release gives two numbers and a rule: XIV's closing
indicative value on 2 February 2018 was $108.3681, and an acceleration event occurs
when the intraday indicative value falls to twenty percent or less of the prior
close. Applying the reconstructed index return for 5 February (+96.10%) at -1x, net
of the 0.0135 daily fee factor and the T-bill accrual, gives **$4.22** against a
threshold of **$21.67**.

So the reconstruction predicts, from futures settlement prices alone and with no
product data as an input, the event that destroyed XIV. That is the strongest
single check available on the whole series.

### The same date measured at 4:00 p.m. says the index rose 33%, not 96%

| | leverage | own close | implied index |
|---|---|---|---|
| VIXY | +1x | +34.24% | +34.24% |
| SVXY | -1x | -31.99% | +31.99% |
| UVXY | +2x | +66.21% | +33.11% |
| reconstruction | | | **+96.10%** |

Three issuers, three leverages, one long and two geared, agreeing with each other to
2.25 percentage points and disagreeing with the 4:15 p.m. settlement by a factor of
three. **57.5% of the day's move, in log terms, happened after 4:00 p.m. ET.**

The raw contract data shows the mechanism: the February-2018 VX contract opened at
16.15, ranged 15.20 to 33.35, and closed at 33.20 — its high — on 567,407 lots. That
is forced buying into the settlement window, which is Phase 08's subject appearing
early.

And ProShares' own prospectus confirms the measurement gap directly: "The NAV
calculation time for the Funds is typically 4:15 p.m. (Eastern Time)". The funds
strike NAV at 4:15 with the futures settlement; the *traded price* is the 4:00
consolidated close. On 5 February that distinction was a fund down 32% versus a fund
down 96%.

### The leverage change: a discrepancy that was not one

The 10-K says "effective as of close of business on February 27, 2018"; the
configuration stores 2018-02-28. Not a conflict — the filing dates the change, the
configuration dates the first return computed under it. Confirmed in the data:
implied leverage on 27 Feb is −1.21 (SVXY) and +2.48 (UVXY), on 28 Feb −0.24 and
+1.13.

### What reading the filings changed

`scripts/extract_filing_terms.py` locates 27 terms across 7 filings by stored search
patterns, writes each quotation with the pattern that found it, compares against the
configuration, and exits non-zero on any failure. Mutation-tested: a wrong config
value exits 1 and names it; a removed filing exits 1 and names every claim it
supported; the clean repository exits 0.

Four things surfaced that would not have otherwise:

1. **SVIX's fee was wrong.** Config said 1.29%; the launch prospectus says "1.35% per
   annum" and 1.29% appears nowhere in the document. Corrected. Immaterial to any
   conclusion (0.24 bp/day against a 51 bp tracking error) but wrong is wrong.
2. **The VXX fee was cited to the wrong document.** It was recorded against a file
   that turns out to be Amendment No. 1 of March 2022 — a one-page notice with no fee
   schedule. The fee is in the January-2018 pricing supplement, also archived. The
   number was right; the citation was not. This is precisely what the task exists to
   catch.
3. **VXX tracks the total-return index; XIV tracked excess-return.** The project
   reconstructs ER. Recorded as a known bias in VXX's mean residual.
4. **Why VXX tracks worse than VIXY after 2022.** The same amendment: issuance
   suspended 14 March 2022, so the creation arbitrage that holds an ETN to its
   indicative value is switched off. VXX 101 bp/day against VIXY 28 bp over the
   identical window, explained by the issuer's own filing.

### Also this session

* All seven SEC filings staged; **338/338 manifest entries now verify byte-for-byte**.
* `docs/limitations.md` written — eight items, each naming the results it bears on.
* `docs/validation.md` gains V9 (the February 2018 reconciliation) and V10 (filing
  terms), and V2 updated to full coverage.
* The project folder on the author's machine was never a git repository; the working
  push had been coming from a clone elsewhere. It is now the repository, with origin
  set, and `git ls-remote` works from the analysis environment, so the remote can be
  verified after each push instead of assumed.

### Next

Phase 08 — ETP mechanics. The rebalancing identity ΔE = L(L−1)·A·r, the decay
identity, and the flow estimates. 5 February 2018 is already the worked example.

---

## Session 5 — 21 September 2026

Phase 08 (leveraged-product mechanics and rebalancing flows) complete. H2 is not
rejected, and is supported unconditionally on the day that matters most.

### The decay identity holds — except in one block, for two documented reasons

Slopes land on theory for every product and regime once one 21-day block is handled:
SVXY −0.5× −0.403 (theory −0.375), UVXY +1.5× −0.384 (−0.375), SVXY −1× −1.087 (−1.000),
UVXY +2× −0.946 (−1.000), VIXY and VXX within 0.03 of zero.

The pre-2018 21-day and 63-day estimates first disagreed (−2.85 vs −1.08 for SVXY).
Leave-one-block-out found the cause: the block holding 5–6 February 2018 moves the
slope by +1.76, against 0.11 for the next most influential. Two separable reasons,
neither a data error: the identity is a continuous-time approximation that errs by
27.8 points at a +96% day (2.3 in a normal block), and the 4:00/4:15 measurement gap
takes three sessions to close — shown with VIXY, a +1× fund with nothing to rebalance,
which still trailed the index by 61.9 points after one session. The block is reported
both ways, not deleted.

The documented de-levering is visible in prices at the documented date: step +0.685
for SVXY (theory +0.625, t = 13.4) and +0.562 for UVXY (theory +0.625, t = 7.0), both
statistically indistinguishable from theory.

### Assets: bounded, and a trap found by cross-checking

The ProShares 10-K gives net assets and share counts at four year-ends, and share
counts on 26 February 2018. First, the price series was validated against the
disclosed per-share NAVs: nine split-invariant comparisons, eight within 0.8 points
over a full year. Then two bugs in the bounding, both caught by checks rather than by
eye:

* Re-applying the split history to the 10-K's share counts double-counted splits the
  filing had already restated — off by a factor of ~1,900 for UVXY. Caught because
  each anchor states the share count two ways and they disagreed.
* Two of the four year-ends fall on weekends, and the bracketing check skipped any
  anchor not in the trading calendar — half the anchors unverified while the check
  passed. Caught by looking at the figure. Anchors now sit on the NAV session.

### Flows and H2

5 February 2018, lower asset bound: $1.85bn → 55,690 contracts → **25.0% of
front-month open interest** (10.9% of the front two). It is the largest day in the
whole anchored window, and the lower bound excludes XIV. The upper bound exceeds the
entire contract on 7 sessions and is plotted separately, never used for the claim.

Against the pre-registered rule, H2 is not rejected. At its real strength: supported at
the lower bound on 4 of the 10 largest up-moves of 2016–2018, indeterminate (upper
bound only) on 6. Same shock with the post-2018 coefficients: 25.0% → 9.4% — a
62.5% cut that is arithmetic, not an estimate.

### Two findings from the filings

* **SVIX tracks a different index.** Its benchmark is priced from a 3:45–4:00 p.m.
  average, not the settlement. Its −8.75%/yr intercept is a benchmark mismatch, not
  evidence about the identity. Now a verified filing term (28/28) and L9.
* Intercepts are not separately identified from collateral yield, fees and trading
  costs (L11); reported as a warning, not as cost estimates.

### A correction

In Session 4 and in the Phase 07 commit messages I described the February-2018
contract closing at its high as "forced buying into the settlement window". The data
shows a close at the high on heavy volume; it cannot show who bought or that they were
forced to. `docs/validation.md` V9 now says "consistent with", and this entry records
the correction rather than editing the earlier one. Found by the causal-language audit
the phase prompt requires.

### Also

`docs/methodology.md` written (M1–M5), `docs/limitations.md` gains L9–L11, validation
gains V11–V13. The shared date-axis helper printed every year twice when it chose
half-year ticks; fixed for every figure. Tests: 200 passed, 2 skipped.

### Next

Phase 09 — the tail model and survival (H3): GJR-GARCH with skewed-t innovations and
conditional EVT on data ending 31 December 2017.

---

## Session 6 — 21 September 2026

Phase 09 (tail model, termination probability, survival, Kelly) complete.
**H3 not rejected, but its stated magnitude is not met. H4 rejected.**

### The ex-ante model

Skewed-t GJR-GARCH(1,1) on log returns ending 2017-12-31: same optimum from two seeds
(to 6e-7), persistence 0.938, no ARCH left in the residuals (Ljung-Box p = 0.81/0.34),
PIT uniform (KS p = 0.43). The asymmetry has the right sign for long VIX futures: an
up-shock moves next-day variance by 0.28 times its square, a down-shock by 0.03.

EVT threshold by the recorded rule on pre-2018 residuals: 0.925 quantile, 189
exceedances, xi = 0.181. I had read 0.95 off the mean-excess plot; the coded linearity
test is sharper and stops at 0.925. The rule governs; the full grid is reported.

### What the model said, before the event

Unconditionally, a -1x wipeout day at **1 in 79 years** (53-85 across the grid), and
-0.5x at 1 in 685. Then day by day, parameters frozen, state updated: 1 in 2,163-3,877
years through mid-January 2018; 1 in 105 after 29 January; **1 in 12.8 for 5 February,
given data through 2 February**. Foreseeable over a product's life, a three-hundred-fold
warning in the final week - and still about 1 in 3,200 trading days on the morning.

### H3 and H4

H3: none of the rejection conditions holds - the ordering is preserved at every
threshold, the five-year survival gap is stable (12.1-14.0 points unbounded, 7.8-9.4
capped), and 1 in 79 years is far from the 1-in-10,000 floor. But the hypothesis claimed
the -1x probability was at least ten times the -0.5x one; it is **8.7 times** (5.3-9.4
across the grid). Reported as not rejected with the magnitude unmet, not reworded.

H4: rejected. Empirical Kelly 0.62 [0.05, 1.34] on the full sample; **1.11** [0.22,
2.07] on pre-2018 data. Before the crash the historical record said a full -1x short
was about growth-optimal.

### Three things that were not what they first looked like

* **Simulated survival vs in-sample averaging** (hazard ~1 in 24 vs 1 in 79 years) is
  not noise. The model generates volatility spirals it never observed - simulated daily
  volatility up to 6.9 against an observed maximum of 0.16 - and 81% of simulated
  wipeouts happen inside them. Survival is now run unbounded and capped, and the pair
  is reported.
* **The model-based Kelly** (0.001, then 0.258, then 0.014 and 0.059 under the
  pipeline's seed) is not an estimate at all: with an unbounded fitted tail, every short
  has positive ruin probability and the model optimum is exactly zero; the simulated
  number is just one over the largest draw.
* **My own phase prompt was wrong.** It asserted calm-state tail risk "should" exceed
  the unconditional risk; under any GARCH scale it cannot. Tested the question it was
  reaching for instead - exceedance rates by volatility quintile - and found no
  under-reaction in calm regimes (p = 0.56). Prompt corrected, property now a test.

### Errors caught before they shipped

* The Kelly figure's y-axis showed a peak of 33 "per year": the series was annualised
  twice. Correct figure 13.1%.
* A calm-quintile range written from a partial reading of the grid (931-3,991 years);
  the table says 484-3,991. Every V16 figure was then re-checked against the pipeline.
* The spiral diagnosis first came from an exploratory run; it now comes from the
  pipeline (`simulation_diagnostics.csv`), so every reported number is reproducible.

### Also

`svcarry.econometrics.tailrisk` (spliced law, conditional exceedance, forward
filtering, survival, simulated returns); ten tests including a look-ahead-by-
perturbation test on the volatility filter, both load-bearing tests mutation-checked.
Methodology M6, limitations L12-L14, validation V14-V19.

### Next

Phase 10 — forecasting and signals: realised variance, HAR forecasts, the variance risk
premium and the term-structure signal.

---

## Session 7 — 21 September 2026

**Phase 10 — realised variance, HAR forecasts and the entry signals.** Complete.

### The result

Real-time log-HAR forecasts of 21-day realised variance, 4,671 of them from January 2008:
out-of-sample R^2 **0.285** (0.303 against the real-time expanding mean), Mincer-
Zarnowitz slope **0.91** (se 0.15), RMSE 13% and QLIKE 21% below trailing RV. The QLIKE
gain is significant (Diebold-Mariano t = -4.08); the MSE gain is not (t = -1.14). VRP
positive on **87.4%** of days. `cm30/cm90` and `VIX/VIX3M` agree on **91.7%** of their
overlap. Contango on 83.1%, VRP on 87.4%, **invested 73.8%**, coverage 99.94%.

### The defect that mattered: the log model forecast the wrong mean

Before building the VRP I checked what the committed log-HAR was forecasting. Its target
averaged the daily **logs** of variance over the next 21 days; exponentiated, that is a
geometric mean. The VRP needs the arithmetic mean, and on a one-day range proxy (daily
log sd 1.25) the arithmetic mean is 1.5 times the geometric. The model's own
evaluation compared its forecast with the same geometric mean, so every diagnostic
looked fine.

Re-running the committed code on the same data: forecasts at 61% of realised average
variance, VRP positive on **99.0%** of days rather than 87.4%, median VRP doubled. The
VRP filter would have been off on one day in a hundred - inert, while its statistics
looked healthy. Fixed in the target only; three tests added, each confirmed to fail on
the old code.

### Two further decisions, and one I did not make

* **SPY, not the index, for OHLC.** The index's open equals the prior close on 14% of
  days; its overnight leg carries a tenth of close-to-close variance. The prompt said
  "SPX OHLC"; the deviation is in M7.
* **Spot-anchoring `cm30`.** The interpolated `cm30` is missing on 234 sessions (5.0%)
  where no contract is inside 30 days - after expiries followed by five-week cycles.
  Spot VIX is the curve's zero-maturity point, so those days are interpolated from it;
  flagged, and agreement with `VIX/VIX3M` is unchanged (91.5% vs 91.7%). Without it
  coverage would be 95.0% and the strategy forced flat on a calendar pattern.
* **Not adopted: smearing.** The log residuals are right-skewed (1.2; already 1.10 in
  the first training window), so the normal-theory retransformation leaves forecasts
  12% low in mean. Duan's smearing would be the better estimator of the conditional
  mean. But the method was fixed in advance, the primary passes its criteria, and the
  OOS results were already in front of me - adopting it now would be the kind of change
  the phase prompt forbids. It goes to Phase 12 as a variant (VRP positive 81.7%,
  invested 69.1%).

### Where the forecast is weak

2013-2019: OOS R^2 0.005, MZ slope 0.51. 2008-2012: no better than trailing RV on MSE.
The full-sample pass is real but narrow (0.285 against a 0.25 bar) and carried by the
crisis periods on MSE and by QLIKE everywhere.

### Errors caught before they shipped

* I first wrote that the proxy's 4.6% excess over close-to-close variance came from a
  negative overnight/intraday covariance. Checked: the covariance is positive. The
  excess is in the intraday range (+14% over squared open-to-close); cause open.
* I first wrote that the proxy and day-count effects both understate the VRP. The day
  count overstates it (0.0005); the proxy understates it (0.0017); net 0.001.
* Two numbers in V23 were written from memory (a "five point" slope gap; "2.5 vol
  points"); the tables say 0.036 and 2.0.

### Also

`svcarry.econometrics.forecast_eval` (QLIKE, metrics, Diebold-Mariano);
`build_signal_panel`, `spot_anchored_front`, `signal_statistics`; `stage_signals`; three
figures; `har_oos_forecast` gains `retransform` and runs to the sample end; the VRP is
rebuilt by hand, forecast included, from the raw Cboe line on every run. Tests: seven for
the panel (the look-ahead perturbation test mutation-checked against two injected
leaks), five for HAR, three for forecast evaluation, three for the figures. Suite:
228 passed, 2 skipped. Methodology M7, validation V20-V24,
limitations L15-L17. The config comment naming `VIX/VIX3M` as the signal contradicted
the pre-data prompt; the comment was corrected, the value untouched.

### Handoff to Phase 11

Signals are defined from **25 January 2008** (first tradeable close, with the one-day
lag, 28 January 2008). The combined signal is on **73.8%** of days after that, from 40%
(2008) to 97% (2017); undefined on three equity-market holidays, where it means no
position. `signals_daily.csv` holds no realised outcome; the evaluation series is in
`har_oos_forecasts.csv` and must not be joined into the backtest.

### Next

Phase 11 — the backtest and H5.

---

## Session 8 — 23 September 2026

**Phase 11 — the crash-budgeted backtest and H5.** Complete. **H5 not rejected.**

### Two decisions taken, and committed, before the backtest was run

Commit 69b748d, with no result in view:

* **The crash floor was reading the future.** The configuration set it to the
  5 February 2018 move and applied it from 2008. The research design asks for an
  *ex-ante* stress loss and the project's own audit rule calls that a leak, so the
  floor became the largest one-day rise observed to date (0.14 in 2008, 0.327 from
  June 2016, 0.961 from February 2018). It sizes **larger** before 2018, so the honest
  version is the one that would have taken the bigger loss. The event floor is kept as
  a labelled calibration: it is worth about 0.06 of out-of-sample Sharpe and half the
  worst day.
* **The engine was under-charging.** Turnover was the change in the *target* weight, so
  the drift back to target was free and re-entering after a gap was free, and the
  index's own roll - two legs, twelve round trips a year - was not charged at all. All
  three are now charged; the roll alone is 39% of the cost bill.

### The result

Out of sample (2016-2026, 2,695 days): **Sharpe 0.27** with a Lo standard error of
**0.31**, CAGR 5.0%, maximum drawdown -26.3%, worst day -11.7%, worst week -13.5%,
turnover 11.3 a year, costs 3.2% against a 2.3% collateral accrual. Design window
0.45. **Alpha over PUT, SPX and a VXX-like factor: -1.4% a year, t = -0.52** - and
insignificant in all five specifications. H5 asked for a positive Sharpe and an
insignificant alpha: both hold, so **H5 is not rejected**, with the Sharpe itself
indistinguishable from zero.

### The three findings that are not in the headline

1. **A constant 0.173 short does better.** Sharpe 0.40 against 0.27, CAGR 7.0% against
   5.0%. What the dynamic parts buy is the tail: worst day -11.7% against -16.6%, skew
   -3.0 against -4.1. The phase prompt said to report this honestly if it happened; it
   happened.
2. **February 2018 turns on 0.72%.** The strategy lost 0.07% on 5 February because the
   contango filter turned off at the previous close - with `cm30/cm90` at 1.0072
   against a threshold of 1.0. Held, the position loses 38%, which is exactly what the
   two-day-lag variant records. The VRP filter stayed *on* through the event.
3. **Buy-and-hold -1x has a higher Sharpe than the strategy and lost 7.8% a year.**
   The ratio cannot see a -96% day; compounding cannot ignore it. Worst day and worst
   week now sit in the same table as the Sharpe for every series.

### Checks

Perturbation over the whole chain (mutation-checked against two injected one-day
peeks); timing table extended to eighteen inputs, none used before it was available;
shift test strictly decreasing (lag 0: 1.12, lag 1: 0.27, lag 2: -0.13); cost
sensitivity monotone (0.52 / 0.27 / 0.01 / -0.50 at 0, 1, 2, 4 ticks); the day's
accounting reproduced by hand on 10 August 2017, including the drift and roll
turnover; the EVT threshold rule moved into a module and the Phase 09 tail stage
re-run bit-identical to confirm the refactor changed nothing.

### Also

The crash scenario's model is fitted on the design window alone (to 2015-12-31) and
filtered forward with frozen parameters, so no post-2015 observation sizes a post-2015
position. Auxiliary factor specifications were added because PUT and SPX correlate
0.897 and their separate loadings are not identified - the alpha is stable across
them, the betas are not. Validation V25-V30, limitations L18-L21, methodology M8.

### Next

Phase 12 — robustness and red-teaming. The first thing it should price is the
0.72% margin of 2 February 2018 (the contango grid runs to 1.025).

---

## Session 9 — 23 September 2026

**Phase 12 — robustness and red-team.** Complete. The strategy claim comes out of this
phase materially weaker than it went in, and the write-up now says so.

### The number that matters most

Across the 144-cell grid (threshold x volatility target x crash budget x rebalance
interval) the out-of-sample Sharpe runs from **-0.35 to 0.53, median 0.06**. The
pre-registered configuration earns 0.27 - the **78th percentile**. The parameters were
fixed before any data was retrieved and the commit history proves it, so this is not
selection after the fact; but it does mean the chosen cell was a fortunate one, and
0.06 is the honest central estimate for "this strategy, specified some other
reasonable way".

### Two cells that change the interpretation, not just the number

* **Rebalancing weekly holds the position through 5 February 2018** - the exit
  signalled on Friday is not executed until the next rebalance date: worst day -38.0%,
  February -31.7%, Sharpe 0.01. At 21 days the grid happens to rebalance clear of it
  (0.42).
* **A threshold of 1.025 does the same**: February -24.3%.

So the crash protection is a property of *acting on the signal the same day*, not of
the sizing rule. The rule's own contribution is real but narrower: Sharpe 0.27 against
0.06 for volatility targeting alone, drawdown -26% against -43%.

### What survived

The reconstruction: the shifted roll convention (0.27) and a constant-maturity basket
(0.27) give the same answer as the rolled index (0.27). The tail model barely matters
once the running-maximum floor binds - the EVT threshold sweep is flat. The alpha is
insignificant in every specification tried. Survivorship is clean: XIV is in the sample
for its whole life.

### What did not

The calendar-spread version - short front, long fourth, which isolates the slope -
earns 0.07, so what the strategy is paid for is being short the *level*. The
close-to-close variance proxy takes the Sharpe to 0.08. And the cost breakeven is
**2.05 ticks per side**: at anything above that the strategy earns nothing.

### Claims revised, not dropped

`docs/research_design.md` gains a section 9 written **below** the untouched
pre-registration, stating each hypothesis at the confidence the robustness leaves it,
plus three claims the design implied that the evidence does not support: that the entry
rules add return, that crash budgeting alone makes the trade survivable, and that the
strategy is an attractive standalone investment.

### Errors caught

* The parameter heatmap outlined the cell at *positions* (1, 0) when asked for the cell
  at *labels* (1.0, 0.2) - a figure that quietly mislabels the chosen configuration.
  Fixed, with a test that fails on the old behaviour (the first version of that test
  passed on it, because `int(1.0)` happened to equal the right position; the test was
  rewritten with a 3x3 grid where the two differ).
* The robustness sweeps cached the fitted tail model on `id(returns)`. A temporary
  Series can reuse an address once collected, so that cache could have handed one index
  construction's tail model to another. Re-keyed on the construction's name before any
  robustness number was produced.

### Also

`stage_robust` builds two index constructions the project had not used before (a
constant-maturity 30-day basket and a front-versus-fourth calendar spread) so the
"alternative constructions" row is a real re-run rather than an assertion. 204
specifications in this phase; about 220 across the project, all reported. Validation
V31-V35, limitations L22-L23.

### Next

Phase 13 — results: every conclusion stated at the confidence Phase 12 supports.

---

## Session 10 — 23 September 2026

**Phase 13 — results and interpretation.** Complete. `docs/results.md` states each
hypothesis against its pre-registered criterion, then interprets the findings at the
confidence Phase 12 leaves them.

### The verdicts, in one line each

H1 **rejected** (133.2 bp/day tracking error in 2011-2015 against a 25 bp criterion).
H2 **not rejected** (25.0% of front-month open interest at the lower bound).
H3 **not rejected, stated magnitude unmet** (8.7x, not the 10x claimed).
H4 **rejected** (Kelly interval contains 1.0; pre-2018 it was centred at 1.11).
H5 **not rejected** (Sharpe 0.27 with a standard error of 0.31; alpha -1.4% a year,
t = -0.52) - and weaker than that sentence sounds, which the document says in the same
paragraph rather than a later one.

### Traceability turned up two errors in my own numbers

The phase's rule is that a number in the prose must be pointable to a committed table.
Checking that, rather than asserting it:

* **V6's tracking errors were not in any table.** They came from an exploratory run
  and used the *regression residual* (120.6 bp), while H1's criterion is written on
  the raw difference (133.2 bp). Both are now computed by the pipeline into
  `index_tracking_eras.csv`, labelled, with the settlement-time split that makes the
  regime shift visible. The verdict is unchanged under either definition.
* **`index_tracking.csv` had a mislabelled column.** `slope_over_lev` divided a slope
  that was already leverage-adjusted (the regressor is `L x index`) by the leverage
  again - flipping its sign for SVXY and halving it for UVXY. The column is gone; the
  `slope` column is the leverage-adjusted one, and V6's "0.887 / 0.889 / 0.877" is
  corrected to the table's 0.877 / 0.872 / 0.867. The substance - one common factor
  near 0.87 across three issuers and three leverages - is unchanged.

Both corrections are recorded in V6 itself, and a third number (the -1x variance drag,
which I first wrote as 18% a year) was recomputed to 30% at 60% volatility before it
reached the document.

### `scripts/check_results_numbers.py`

Forty-odd figures from `results.md`, each re-read from its table and asserted, exiting
non-zero on any disagreement. It is the phase's traceability criterion made
executable: a future pipeline change that moves a number now fails a check instead of
leaving the write-up quietly wrong.

### What the document says that the project's own framing did not

The three findings it nominates as genuinely informative are the settlement-time
artefact, the de-levering counterfactual (25.0% to 9.4% of open interest), and the gap
between the chosen configuration's 0.27 Sharpe and the specification grid's median of
0.06. The strategy's positive Sharpe - the headline the project was built around - is
explicitly *not* on that list.

### Next

Phase 14 — visualisation: the figures that carry those three findings.

---

## Session 11 — 23 September 2026

**Phase 14 — visualisation.** Complete. Twenty-four figures, each with a question it
answers, all regenerating from one script.

### What changed

`scripts/make_figures.py` is now the single owner of the figure set: one builder per
figure, a registry that pairs each with **the question it answers** and the committed
files it reads, and `--list`, `--only` and `--index` for working on one at a time.
`docs/figure_index.md` is generated from that registry rather than maintained by hand,
so a figure without a question cannot quietly survive. `run_pipeline --only figures`
and `make figures` both go through it.

Five figures existed only as functions and had never been rendered (the index against
the products, the term structure, and three others); three are new:
`shape_across_thresholds` (does the tail estimate depend on where the tail starts?),
`specification_distribution` (the 144 cells as a histogram, with the median at 0.06 and
the chosen cell at 0.27 marked), and `decay_blocks` was brought into the registry
rather than being left as a stage side-effect. `stage_backtest` now writes
`benchmarks_daily.csv` so the strategy figures rebuild without re-running the backtest.

### Three honesty fixes in the figures themselves

* **The tracking-residual panel was a flat line with one spike.** 5 February 2018 is
  −6,187 bp against a typical day of ±100, so drawn to scale the panel showed nothing.
  The axis is now clipped at the 0.5th and 99.5th percentiles, the 14 days outside it
  are marked with triangles, and the source note says so and names the largest. The
  regime shift the panel exists to show — noisy before October 2020, quiet after — is
  now visible.
* **Two figures encoded meaning in colour alone.** `style.greyscale_check` flags seven
  hue pairs in the palette within 0.07 of each other in luminance, so the binding
  constraint now varies marker as well as colour, and the signal-state strip puts each
  state in its own horizontal band.
* **Six series with six direct labels collided** at the right edge of the February 2018
  figure. Direct labels now appear only while there are four or fewer series, which is
  the project's own stated rule.

### Also

The asset-bounds figure would not rebuild from the committed CSV, because the stage
drops the extrapolated rows before writing while the in-memory frame still carries the
flag; the figure now accepts either and still refuses to plot an extrapolated point as
bounded. Three new viz tests, including one that fails if the residual panel lets a
single outlier set its scale.

### One bug found by re-running

`timing_audit.csv` grew every time the backtest stage ran: the stage appended its rows
to whatever was there instead of replacing them, so the committed copy had 50 rows of
which 32 were duplicates. The stage now replaces its own rows, and running it twice
leaves 18 rows both times.

### Next

Phase 15 — documentation and the report.

---

## Session 12 — 24 September 2026

**Phase 15 — documentation and report.** The phase prompt's instruction was to write the
key findings first: "If that section cannot be written clearly, the project is not
finished." It could, in three sentences, and they are now the opening of the report, the
README and the one-page summary, saying the same thing in the same numbers.

### Written

* `reports/report.md` — the full write-up. Introduction, institutional background built
  from the 28 verified filing terms, data with its three hazards, methodology, results in
  seven findings, robustness and red-team, discussion, limitations, conclusion,
  references.
* `reports/summary_one_page.md` — question, method, three findings, one caveat.
* `README.md` — key findings with numbers matching `docs/results.md`; a main-outputs
  section; limitations rewritten to name the weaknesses actually found (grid median 0.06,
  the constant short's 0.40, the 0.72% margin, the 2.05-tick breakeven, H3's unmet
  magnitude) rather than the generic ones written before any results existed.

### The number check now covers everything

`scripts/check_results_numbers.py` was written in Phase 13 for `docs/results.md`. It now
asserts the report, the summary and the README as well — 28 further assertions covering
filing-term coverage, the sample span, the roll-convention evidence, the ex-ante GARCH
and EVT parameters, the warning path date by date, the probability ratio across the whole
threshold grid, and the red-team answers the report quotes.

It caught one error immediately: the report said 24 verified filing terms and the table
holds 28. The table was right.

### The clean-clone reproduction found two defects

Recorded in full as V36. In summary:

* **Three committed figures were not the output of the code that builds them.**
  `feb2018_detail`, `rolling_sharpe` and `weight_and_binding_constraint` were last
  written in Phase 11; `viz/figures.py` changed in Phase 14. Rebuilding produced
  byte-identical output for the other 21 and different output for these three. Rebuilt,
  inspected against the claims they support, and committed. This is the second time a
  "the script ran, therefore the artefact is current" assumption has been wrong in this
  project, after the stale bundle in Phase 09.
* **A fix that looked right and did nothing.** The stress-window labels collided
  (`volmageddon 2018` over `covid 2020`). The first fix compared the gap between windows
  against `ax.get_xlim()` — but `shade_windows` runs *before* the data is plotted, so the
  limits were still `(0, 1)` and every gap measured as enormous. The figure came back
  unchanged, which is the only reason it was caught. The working version defers to draw
  time and compares rendered text extents. Mutation-checked: the test fails on the
  pre-fix behaviour.

What a clone reproduces: 245 tests, the number check, and 20 of 24 figures. What it does
not: anything needing the 338 raw files, which are gitignored by design — the pipeline
stops with exit code 2 and names the command to run rather than downloading implicitly.

### Divergences from the prompt pack, this phase

* The prompt asks for an 8–10 page report; `reports/report.md` is about that length in
  print but is written as a repository document with tables and links rather than as a
  paginated PDF. No PDF is produced, because every number in it is asserted against a
  live table by a script and a PDF would freeze that link.
* The prompt asks to "update the prompt pack where execution diverged". The divergences
  from earlier phases were already recorded where they happened — the running-max stress
  floor replacing the event floor (M8), SPY rather than SPX for the variance proxy (M7),
  the log-HAR target correction (V20a). This session added no new methodological
  divergence, so the pack is unchanged beyond this note.

### Next

Phase 16 — final audit.

---

## Session 13 — 24 September 2026

**Phase 16 — final audit.** Six perspectives at commit `50a6c3b`, the commit at which the
project was declared finished. The findings were written and committed (`700c45a`) before
any fix, so the record shows what the project looked like when it was called complete.

**2 material, 3 minor, 4 disclosed, 0 critical.** Full document: `docs/final_audit.md`.

### The two material findings were both numbers that lived only in prose

* **F-A2.** "H2 is supported at the lower bound on 4 of 10 days" appeared in five
  documents across four phases. It is **3 of 10**. The fourth day, 2017-08-10, sits at
  **9.97%** — which prints as "10.0%" at one decimal place and was counted as clearing a
  threshold it does not clear. Worse for the claim: of the three that do clear it, two
  clear by under a quarter of a point (10.18%, 10.23%), so H2 rests on 5 February 2018.
  The verdict is unchanged — the pre-registered rule is failure at *both* bounds, and no
  day fails at both — but the strength claim was overstated. Corrected everywhere, the
  margins are now named, and the count is derived from the table by
  `check_results_numbers.py` rather than asserted in prose.
* **F-A1.** Methodology M5 documented `ΔE_t = L(L−1)·A_{t−1}·r_t` while the code uses
  `A_t`. On 5 February 2018 the two give 25.0% and 24.8% at the lower bound. Neither is
  exactly right — a fund rebalances against the `t−1` mark grown by the day's own move —
  so M5 now states what the code does and why the choice is ambiguous, and reports both.
  The code is unchanged: altering a published number for a reason the audit cannot
  establish as correct would be worse than documenting the ambiguity.

Both were found by re-deriving headline numbers **by hand from the raw contract panel**
rather than reading them off the tables. That is the only part of the audit that found
anything; the checklist sections found nothing because they were already instrumented.

### What the hand checks confirmed

One index return on an ordinary day and on a roll date, to 1e-12 — the naive front-month
version would have booked **+1067 bp** of fake return on that roll date. The backtest
identity `R = a − w·r − c` across the whole series to 1.8e-16. Collateral credited exactly
once, to 1.0e-16. The February 2018 de-levering date confirmed **independently from
implied leverage** in the price data (SVXY −1.21 → −0.24; UVXY +2.48 → +1.12). The
pre-registration provable from git: config at 07:40:36Z, first data retrieval at
08:30:04Z, both independently checkable.

### One false alarm, recorded rather than hidden

A first pass tested the backtest identity with an extra `shift(1)` and found 2,567
violating rows, worst on 5 February 2018. The engine applies `signal_lag` internally, so
the emitted `weight` is already the held weight. The audit check was wrong, not the
engine. An auditor who stopped there would have reported a false critical finding.

### Clean-room reproduction

Zero unexplained discrepancies. 245 tests, the number check, `make verify` over 338 files,
and **all 20 rebuildable figures byte-identical** — a change from Phase 15, where the same
test found three stale figures. Four figures cannot be built in a clone at all because they
read cached price files; that is the intended design and is disclosed.

> Corrected by the recursive audit (register A-06). This paragraph said "**all 24 figures
> byte-identical**" and then, two sentences later, that four of them cannot be built in a
> clone. Both cannot be true: the clean-room test rebuilt 20 and the other 4 exited with an
> error. The overstated version is the one that was copied into the project completion
> note. It is exactly the failure this section's own closing paragraph names — a number
> that lived only in prose — and it survived because the figure count was never in a
> table. All 24 figures *have* since been reproduced byte-identically, but from the full
> raw data rather than from a clone; that result is V37, not this one.

### The lesson

Every number that appears in prose should be in a table and in the number check. Both
material findings here were prose-only numbers: one contradicted the code it described,
the other the table it summarised. This is the same failure mode as the V6 tracking
numbers caught in Phase 13 — and `check_results_numbers.py`, which exists precisely to
prevent it, had never been given this one.

### Status

The project is complete. All sixteen phases run, the completion gate is ticked, and the
one conclusion the audit required to change has been changed.

---

## 2026-09-24 — Session 14: recursive audit, Pass 1

**Objective.** Re-audit the finished project as a system of dependencies rather than a
sequence of phases, assuming something is still wrong. Entered from a fresh clone in an
empty container with no project history, so nothing could be taken on trust from the
working tree.

### What the entry checks established before anything was changed

The unchanged pipeline was run end to end from the raw data, in a container with **numpy
2.4.4, pandas 3.0.2, Python 3.11.15** — all materially newer than the pinned lower bounds.
**All 42 tables and all 24 figures came back byte-identical**, as did all 8 processed
datasets (V37). The suite passed 245 / 2 skipped under the bundled shim with no pytest
installed. The manifest re-hashed clean over 338 entries. The local working tree was shown
to be content-identical to `origin/main` at `c4c5ec6` by LF-normalised blob hashing. The
headline statistics were reproduced to 4.2e-15 by an independent implementation importing
none of `svcarry`.

This mattered for what followed: with the baseline reproducing bit for bit, every later
difference was attributable to a correction and not to the environment.

### A-02: the project's own first finding, inside the project

The engine applies `w = w_raw.shift(1)` and `R_t = a_t − w_t r_t`, so a weight built from
information dated `t−1` is a position held **at the settlement of `t−1`**. `r` is a VX
settlement-to-settlement return. Cboe moved that settlement from 4:15 p.m. ET to **4:00
p.m. ET on 26 October 2020**. The VIX cash close stayed at 4:15 p.m. ET. So from that date
the VRP filter was set from a price struck fifteen minutes after the price the position was
booked at — for 1,482 trading days.

This is the same fifteen-minute gap as H1, which is the project's headline finding about
other people's index-versus-product comparisons.

Cost: out-of-sample Sharpe **0.27 → 0.20**, CAGR 5.0% → 4.1%, alpha −1.4% → −2.2% a year
(t −0.52 → −0.77). 161 decision days change, all after October 2020. **The design window is
unchanged at 0.4508**, so no parameter was chosen on contaminated information. 14 of 42
tables, 9 of 24 figures and 4 processed datasets were regenerated.

The correction makes the project's conclusion *stronger*: 0.20 sits further below the
constant-weight short's 0.40 and the PutWrite index's 0.53, and volatility targeting alone
now earns a **negative** Sharpe (−0.03, was +0.06), which sharpens the crash-budget case.
Two things got worse and are reported as such: one day now carries **21.8%** of total
return, up from 17.0%, and four one-at-a-time alternatives now beat the pre-registered cell
where they previously did not (V32).

### A-05: why sixteen phases and a six-perspective audit missed it

`timing_audit.csv` was cited in `docs/final_audit.md` as *mechanical* evidence of no
look-ahead — "0 of 18 inputs". The column was
`timing["use_precedes_availability"] = False`, assigned as a literal in two places. Nothing
was computed, so the table could not have reported a violation however bad the timing was.
The convention itself was stated in three places in three mutually inconsistent forms — the
config comment described a two-day lag, two rows of the timing table described a two-day
lag, and the engine implemented one day — and **no test pinned the relationship between a
signal date, a weight date and the return it earns.**

`svcarry.timing` now holds a registry of each input's strike time, compares it against the
execution settlement per date, and writes a computed verdict with a count of offending
dates; the pipeline exits non-zero if any row is `True`. Strip the extra lag and it reports
1,482 violating dates across four inputs, and a mutation test requires exactly that.

### Also corrected in this pass

| | |
|---|---|
| **A-01** | No `.gitattributes`. Committed blobs are LF, the authoring tree is CRLF, so any clone with `core.autocrlf=false` reported **all 168 tracked text files as modified** — 63,788 insertions against 63,788 deletions, not one real change. The project reads "local and remote agree" off `git status`, so that signal has to mean the same thing on every machine |
| **A-03** | The drift-turnover denominator is the gross return; the docstring's formula said the net return, which the code never computed. Exact is circular within a day, so the approximation stays — but it is now stated and **bounded by a test** against an exact sequential reference. Measured cost: 2.4e-05 of out-of-sample Sharpe |
| **A-04** | Tests built figures and never closed them, so matplotlib warned partway through `test_viz`. Fixed centrally in the runner and in a new `tests/conftest.py`, not in twenty tests |
| **A-06** | The Phase 16 entry above claimed "all 24 figures byte-identical" and, two sentences later, that four cannot be built in a clone. 20 were rebuilt; 4 errored. The overstated version had been copied into the project completion note |
| **A-08** | V27 quoted an out-of-sample turnover breakdown and then a **full-sample** roll share of the cost bill (38.7%) inside the same sentence. The out-of-sample figure is 39.2% |

### The lesson, restated

Phase 16 drew the lesson that every number in prose should be in a table and in the number
check. Pass 1 says the same thing about *verifications*: every claim that a check passed
should be the output of a check that could have failed. The look-ahead table, the test
count in the README (244 against 245 everywhere else), and the figure-reproduction claim
were all assertions in the shape of evidence. `check_results_numbers.py` now asserts the
timing audit's verdict and row count directly, so this specific failure cannot recur
silently either.

### Status

Pass 1 corrections are complete, regenerated and revalidated. The audit continues:
Pass 1 has not yet reached the econometrics implementations, the EVT and survival layer,
the index reconstruction, the literature review or the prompt system, and by the recursive
rule Pass 2 re-examines the whole project rather than only what changed here. The register
is [`final_audit_issue_register.md`](final_audit_issue_register.md).

---

## 2026-09-24 — Session 15: recursive audit, Passes 2 and 3

### Pass 2 — the instructions, and the estimators

Three findings. The important one was upstream of everything in Pass 1:
`prompts/tasks/lookahead_audit.md` specified a **date-granular** timing table and never
required the verdict to be computed, which is why A-05's hard-coded `False` satisfied it
and why a fifteen-minute overlap was out of scope. The same prompt already lists "*a
signal computed from a close and traded at the same close*" among the ways look-ahead
arrives. It named the failure mode and specified a check too coarse to catch it. The
prompt now requires strike times, a computed per-date verdict, the pipeline gated on it,
and a mutation test (A-11). Also: the literature that would have prevented A-02 was
already cited and read too narrowly (A-09), and three prompts named output tables the
project does not produce — one of them never produced under any name (A-10).

What Pass 2 could not break, all by independent recomputation rather than by reading the
project's own output: the GJR-GARCH log-likelihood (to 1.6e-04 from the published
definitions, and confirmed a genuine optimum — re-optimisation gains 0.000000), all
sixteen GPD fits via `scipy.stats.genpareto` (~4e-05), Kelly (2e-08), the variance proxy
(1.6e-16), the HAR level specification exactly and the log specification's convention
identified and found to match M7 word for word, Newey-West up to √(n/(n−k)), the entire
index rebuilt from the 313 raw contract files (**all 4,710 returns to 4.0e-16**, including
all 225 roll dates, where a naive front-month `pct_change` would have been wrong by 9.99%
on average), the settlement calendar (of 227 expiries the 7 deviations are all correct
holiday pull-backs), and all 28 filing quotations found verbatim in the source documents.

### Pass 3 — a docstring that was true about the wrong thing

One finding, the same shape as A-05. `stage_figures` said the figures "live in one script
rather than being scattered through the analysis stages" while the stages drew **twenty of
the twenty-four** themselves. Running each figure-writing stage against the `make_figures`
output showed **six of the twenty came out byte-different** — ordering, not data: a stage
passes series in insertion order, `make_figures` reads the CSV and `groupby`s it, which
sorts. A full run hid it because `stage_figures` runs last; `--only tail` left a committed
figure quietly modified, which is A-01's problem again. Twenty duplicate call sites
removed, `make_figures` now the sole writer as the docstring always claimed, and
`tests/test_figure_single_writer.py` asserts it (A-12).

Verified after the change: the full pipeline from raw data reproduces **42 of 42 tables,
24 of 24 figures and 8 of 8 processed datasets byte-identically**, and `--only mechanics`
now leaves all 24 figures untouched.

Also clean in Pass 3: the 20,000-path survival simulation and the bootstrap intervals are
genuinely seeded (all ten tail-stage outputs byte-identical on re-run); H3's return periods
reproduce to 7.3e-12 and its ratio to 8.677×, correctly declared short of its 10× bar; the
manifest's 338 entries have no missing field and its earliest retrieval at 08:30:04Z
confirms the pre-registration gap; and there is **no claim anywhere** of the leverage
critique that H4's rejection failed to support — the report states the opposite, that
pre-crash growth-optimal sizing favoured the full inverse exposure the products sold.

### The pattern across three passes

Every finding above the Minor line is the same defect in a different place: **a statement
about the project that was true in prose and false in the code.** The timing convention
(A-02/A-05), the prompt that specified it (A-11), the figure-reproduction claim (A-06),
the test count (A-07), the window a percentage came from (A-08), and the single-writer
claim (A-12). The project's Phase 16 lesson was that every number in prose should be in a
table. The audit's lesson is the same sentence about verifications: every claim that a
check passed should be the output of a check that could have failed.

### Status

Pass 3 found one issue, so it is not a clean pass and the audit continues.

---

## 2026-09-24 — Session 16: recursive audit, Pass 4

### A-13: the Sortino column was not the Sortino ratio

`performance_stats` took the standard deviation of the negative excess returns **about
their own mean**, over the count of losses. The Sortino denominator is the target downside
deviation, `sqrt((1/n) sum min(ex,0)^2)` over every observation. Selecting the subset by
the target and then measuring dispersion within it reports how varied the losses were, not
how large — and a series whose losses were all the same size would have had a denominator
of zero.

It ran conservative: out of sample 0.177 against a true 0.245, full 0.309 against 0.405,
design 0.492 against 0.598. No Sortino value appears in the prose of any write-up, so no
conclusion moved. The suite had **no Sortino test at all**, which is why a plausible
one-liner was never confronted with a case that distinguishes it from the correct formula.
Two tests now do: one requires the target-downside form on a series where the two cannot
coincide, the other requires that doubling every loss worsens the ratio and that identical
losses stay finite.

The full pipeline re-run changed **only the `sortino` column, in exactly the eight tables
that carry it**. All 24 figures and all 8 processed datasets byte-identical.

### A-14: the audit auditing its own work

M7a — written in Pass 1 to pin down strike times — presented the settlement clock as two
rows and missed a third change that `data_sources.md` already recorded: Cboe replaced the
settlement calculation with a tiered VWAP/TWAP procedure on 9 September 2024. It changes
how the 3:00 p.m. CT price is formed, not when, so no number moves; but a section written
to be definitive about timing should not be less complete than the data documentation it
draws on. M7a now records it, and notes that fifteen minutes is therefore a lower bound on
the overlap rather than an exact figure.

### What Pass 4 could not break

The Lo/Mertens Sharpe standard error to 8.3e-16, and every other statistic in the
evaluation layer — drawdown, VaR, CVaR at both levels, Calmar, skewness, kurtosis, hit
rate, the 1,998-day longest underwater run — to 1e-13 or better. The stationary bootstrap
on four independent properties: block length, equal-probability resampling,
autocorrelation preservation (0.675 against a sample 0.709, where iid gives 0.000), and
95% CI coverage of 92.3% on an AR(1) where iid manages 55.7%. `figure_index.md` against
the figures, with no gaps in either direction. `data_sources.md` against all 338 manifest
entries, including the Stooq fallback that is documented and honestly marked unused.

And the Phase 07 gate, which is worth recording: the prompt's own failure band is a
tracking error above 25 bp/day, the measurement was 133.2, and the project wrote down that
the gate had failed rather than passing it quietly. That failure is now the project's first
headline finding.

### Status

Pass 4 found two issues, so the audit continues.

---

## 2026-09-24 — Session 17: recursive audit, Pass 5

Two findings, and both are against the audit's own earlier work rather than the original
project.

**A-16 is the one worth recording.** A-07 was closed in Pass 1 after the README's Status
table was corrected from 244 tests. The README quoted the count in **two further places** -
its file tree and its command list - and both stayed stale, and Pass 1's own addition to
V37 became a fourth stale statement as later passes added tests. Checking that one
occurrence is right is not the same as checking that all of them are, and an audit that
closes a finding after fixing one occurrence has not closed it. The count is now stated in
exactly one place, which says so, and `validation.md` carries both counts with dates
attached so a record of a past run cannot read as a claim about the present.

**A-15** was an orphan label: `L8, Open questions carried forward` sat last in
`limitations.md` while holding a number in the middle of a scheme that six documents
cross-reference. The list is unnumbered now and the header states that the limitations run
L1-L7 and L9-L25.

### What Pass 5 could not break

All five single-day variance estimators reproduce **exactly** from their published formulas
on the real bars, and Yang-Zhang exactly including its `k`. The Newey-West bandwidth rule
matches every regression in the project, including the documented `max(h-1, rule)` that
gives 20 for the HAR. The leverage-decay constant is the right one from Itô, and the SVXY
regression reproduces **end to end** - 76 and 75 blocks, slope −2.845819 full and −1.087347
ex-Feb-2018, annualised intercept 0.755793, every one exact - which validates the Yahoo
parsing, the split adjustment, the block construction, the regression and the annualisation
in a single check. Its standard error is HC1 exactly, which is the right choice with one
extreme leverage point in the sample.

The forecast-evaluation layer reproduces to **ten decimals** on OOS R², RMSE, MAE, bias,
QLIKE and the whole Mincer-Zarnowitz regression including its HAC standard error — a second
independent confirmation of the HAC code, by a different route from Pass 2's.

One thing measured rather than assumed, because §46C asks about fees: the NAV recursion
charges the fee on the prior NAV, which is the ETF convention exactly and covers four of the
six products, and approximates the two ETNs' filed wording (`CIV x DailyPerformance x
fee/365`) by at most **1.5e-04 a year**. Against tracking errors of 133 and 32 bp/day that
is nothing.

And `prompts/operations/github_push_verification.md` turns out to specify the exact
escalation this audit needed: "produce a transferable artefact — a `git bundle` preserves
the full history — and give the exact commands to publish it from elsewhere. Never describe
unpushed work as pushed." That is what was done.

### Status

Pass 5 found two issues, so the audit continues.

---
