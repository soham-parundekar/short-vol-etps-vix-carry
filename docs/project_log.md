# Project log

Append-only. Entries record what actually happened, including what failed. A decision
that was later changed appears twice, with both entries kept.

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
