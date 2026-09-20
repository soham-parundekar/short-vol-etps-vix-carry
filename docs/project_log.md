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
