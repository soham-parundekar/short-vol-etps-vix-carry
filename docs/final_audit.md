# Final audit

Phase 16. The repository reviewed from six perspectives at commit `50a6c3b`, the commit
at which the project was declared finished.

The findings below were **written before any fix was made**, so this document records
what the project looked like when it was called complete, not what it looks like after
the audit. Each finding is classified:

| | |
|---|---|
| **Critical** | invalidates a conclusion |
| **Material** | changes a number |
| **Minor** | cosmetic or stylistic |
| **Disclosed** | a real weakness, documented rather than fixed |

**Summary: 2 material findings, 3 minor, 4 disclosed, 0 critical.** Both material
findings are in the same place — H2's flow analysis — and neither changes H2's verdict.
One of them was found by re-deriving a headline number by hand from the raw contract
panel, which is the check that was worth doing.

---

## A. Finance

Everything in this section was re-derived by hand from the raw data and compared with
the committed output, rather than read.

### What was checked and passes

| Check | Result |
|---|---|
| One index return, rebuilt from the two contracts in the panel (2014-06-11) | matches to **1e-12** |
| The same on a **roll date** (2009-08-19), the case that breaks naive implementations | matches to 1e-12; a front-month `pct_change()` would have booked **+1067 bp** of fake return that day |
| `w1 = dr/dt` and `w1 + w2 = 1` on all 4,711 rows | exact |
| Level chaining `L_t = L_{t-1}(1 + r_t)` | exact |
| One strategy day, `R_t = a_t − w_held·r_t − c_t` (2024-01-18) | matches to 1e-12 |
| The same identity across the whole series | max residual **1.8e-16** |
| `costs = cost_rebalance + cost_roll` | max residual 1.4e-20 |
| Collateral credited exactly once (`ret = gross − costs`, `gross = a − w·r`) | max residual 1.0e-16 |
| One product NAV step, −1× with SVXY's fee | matches by hand |
| Product terms against the filings | 28 of 28 verified, none disagreeing with configuration |
| The February 2018 de-levering date | see below — **confirmed independently from prices** |

**The de-levering date, verified against the data rather than the filing.** The 10-K
dates the change to the close of 27 February 2018 and the configuration stores
2018-02-28, on the argument that this is the first daily *return* under the new
objective. Implied leverage computed from the price data confirms it exactly:

| | 27 Feb | 28 Feb |
|---|---|---|
| SVXY | −1.21 | **−0.24** |
| UVXY | +2.48 | **+1.12** |

A one-day error here would mix leverage regimes across the largest observation in the
sample. It is right.

**A note on one thing that looked wrong and was not.** A first pass tested the backtest
identity as `gross = a − w_{t−1}·r_t` and found 2,567 rows violating it, with the worst
on 5 February 2018. The engine applies `signal_lag` internally (`w = w_raw.shift(lag)`),
so the emitted `weight` column is already the *held* weight and must not be shifted
again. With the correct convention the identity holds to 1.8e-16. The audit check was
wrong, not the engine — recorded because an auditor who stopped at the first pass would
have reported a false critical finding.

### F-A1. The flow estimate uses assets at `t`, not `t−1` — **material**

`docs/methodology.md` M5 states the rebalancing identity as

> `ΔE_t = L(L−1)·A_{t−1}·r_t`

The code (`scripts/run_pipeline.py`, the flow loop) uses `A` indexed at **`t`**:

```python
A = bounds[s][f"assets_{k}"].reindex(dates)
per = L * (L - 1.0) * A * r_idx
```

The two are different quantities, and on the day the result rests on they differ
materially, because assets themselves moved that day: SVXY's lower-bound assets fell to
0.68× their previous level and UVXY's rose to 1.66×.

Impact on the headline, at the lower bound on 5 February 2018:

| | Contracts | Share of front-month OI |
|---|---|---|
| `A_t` (as coded, as published) | 55,690 | **25.0%** |
| `A_{t−1}` (as documented) | 55,187 | **24.8%** |

Which is correct is not obvious. The fund rebalances at the close of `t` against the
assets it holds *going into* that close, which is the `t−1` mark grown by the day's
move — so neither the plain `t−1` value nor the independently-interpolated `t` value is
the exact quantity. The interpolated bound at `t` is arguably closer, since it reflects
creations and redemptions during the day, but it also embeds the post-move share count,
which is precisely the contamination the lower bound exists to avoid.

**Verdict: material, does not change H2's verdict.** 25.0% and 24.8% are both far above
the 10% threshold. The defect is the disagreement between code and documentation, not
the number. **Action:** the methodology is corrected to state what the code does and why
the choice is ambiguous, and both figures are reported. The code is not changed, because
changing it would alter a published number for a reason the audit cannot establish as
correct.

### F-A2. "4 of 10 days" is wrong; it is 3 of 10 — **material**

`docs/results.md`, `docs/research_design.md` §9, `docs/validation.md` V13 and
`reports/report.md` (three places) all state that H2 is "supported at the lower bound on
4 of 10 days, indeterminate on 6". Recomputed from `rebalancing_flows.csv`, the ten
largest up-moves in the anchored 2016–2018 window give:

| Date | Index return | Lower bound | Upper bound |
|---|---|---|---|
| 2016-01-07 | +12.02% | **10.18%** | 142.5% |
| 2016-06-13 | +15.85% | **10.23%** | 126.0% |
| 2016-06-24 | +32.71% | 5.6% | 69.7% |
| 2016-09-09 | +15.48% | 2.7% | 23.2% |
| 2017-05-17 | +17.81% | 4.3% | 24.0% |
| 2017-08-10 | +19.06% | **9.97%** | 40.8% |
| 2017-08-17 | +13.93% | 2.8% | 12.1% |
| 2018-02-02 | +13.99% | 7.7% | 53.6% |
| 2018-02-05 | +96.10% | **25.00%** | 131.6% |
| 2018-02-08 | +11.44% | 5.4% | 12.5% |

**Three** days exceed 10% at the lower bound, not four. 2017-08-10 is at **9.97%**,
which displays as "10.0%" at one decimal place and was evidently counted as clearing the
threshold. It does not.

Worse for the claim's strength: of the three that do clear it, **two clear it by less
than a quarter of a percentage point** (10.18% and 10.23%). The honest statement is that
H2 rests on 5 February 2018 and on two days that are at the threshold rather than above
it.

**Verdict: material, does not change H2's verdict.** The pre-registered rejection rule
is failure at *both* bounds, and no day of the ten fails at both. H2 remains not
rejected. But the strength claim was overstated. **Action: fixed** — the count is
corrected to 3 of 10 with 7 indeterminate in all five places, and the two marginal days
are named so a reader can see how thin the margin is.

---

## B. Quantitative research

### What was checked and passes

**The in/out-of-sample discipline is real and provable from the commit history, not
asserted.** The configuration carrying `contango_threshold: 1.0`, `vol_target: 0.15`,
`max_stress_loss: 0.20` and `oos_start: "2016-01-01"` is in the tree at commit
`2bdeb31`, timestamped **2026-09-20T07:40:36Z**. The earliest `retrieved_utc` across all
338 manifest entries is **2026-09-20T08:30:04Z**. The parameters were fixed 50 minutes
before any data existed, and both timestamps are independently checkable.

**Inference is appropriate to the data.** HAR diagnostics use HAC with 20 lags
throughout, against a horizon of 21 (the `h−1` requirement). The alpha regression uses 8
HAC lags. The Sharpe carries a Lo (2002) standard error. The tail model is fitted with
four starts from each of two seeds, agreeing to 6.3e-7.

**Conclusions are stated at the confidence the evidence supports.** The out-of-sample
Sharpe is 0.27 with a standard error of 0.31 — a t-statistic of 0.85 — and the project
says so in every place it quotes the number, rather than reporting 0.27 alone.

**Multiple testing is disclosed rather than corrected, which is the right choice here.**
The 144-cell grid is published in full: median 0.06, range −0.35 to 0.53, the chosen cell
at the 78th percentile. A formal correction would be misleading, because the cell was
pre-registered rather than selected; publishing the distribution is more informative than
a p-value adjustment.

**Randomness is seeded and reproducible.** `kelly_fraction` with the same seed returns a
bit-identical result across every field; the survival simulation takes its seed from
configuration. The two `default_rng()` calls in `bootstrap.py` are fallbacks on an
optional `rng` parameter, and every caller in the pipeline passes a seed.

### B-1. The Kelly point estimate is seed-free but the interval is not labelled as seed-dependent — **minor**

`kelly.csv` reports `f_star` and a bootstrap interval. The point estimate does not depend
on the seed (confirmed: identical across seeds), but the interval does, and the table does
not say which seed produced it. The seed is in configuration and the run is reproducible,
so this is presentational. **Action: disclosed.**

---

## C. Software

### What was checked and passes

| Check | Result |
|---|---|
| Test suite from a clean checkout | **245 passed, 0 failed, 2 skipped** |
| The 2 skips | cross-checks against `arch`/`statsmodels`, which are not installable in this environment; documented |
| `make verify` (re-hash all 338 files against the manifest) | **manifest clean** |
| Secrets scan across `.py`, `.yaml`, `.md`, `.toml` | none |
| `.gitignore` covers `data/raw/**`, `.env`, `.env.*` | yes |
| Parameters in configuration rather than hard-coded | yes; the grids, thresholds, windows and seeds all live in `config/config.yaml` |
| Tests test behaviour, not implementation | the load-bearing ones do — see below |

**On whether the tests are real.** The ones that matter are behavioural and several are
mutation-checked, meaning they were deliberately run against broken code to confirm they
fail. The whole-chain look-ahead test perturbs every input after a cut-off and requires
every earlier weight and return to be bit-identical. The leak calibration shows a
same-day signal earns a Sharpe of 1.12 against the honest 0.27. The index reconstruction
is tested against a synthetic panel with a known answer of exactly zero.

### C-1. `return_period` in `evt.py` is dead code — **minor**

An AST scan for public functions in `src/` with no reference anywhere in the repository
returns eight candidates. Seven are false positives (`__all__` entries, or called from a
Makefile shell string — `verify_manifest` is one, and `make verify` was run and works).
`evt.return_period` is genuinely unreferenced: the pipeline computes return periods
inline as `1 / (252 · p)`. **Action: disclosed** rather than deleted, because deleting a
tested function in the final commit of a project is a worse trade than leaving it.

### C-2. Two figure-building helpers duplicate a date-parsing idiom — **minor**

`scripts/make_figures.py` has `_dated()` and `_read()` doing nearly the same thing.
Harmless, and not worth a change at this stage. **Action: disclosed.**

---

## D. Data

### What was checked and passes

| Check | Result |
|---|---|
| Manifest completeness | 338 entries, each with `url`, `retrieved_utc`, `sha256`, `bytes`, `content_type`, `status` |
| Manifest verification | clean — every file re-hashes to its recorded digest |
| Every source documented and reachable | `docs/data_sources.md`; all free and public, none requiring registration |
| Redistribution | none — raw data is gitignored, reproduced by `fetch_data.py` |
| Look-ahead | `timing_audit.csv`: **0 of 18** inputs have use preceding availability |
| Survivorship | XIV is in the sample for its whole life including its termination; no product dropped (`redteam_answers.csv` Q3) |
| Cleaning decisions documented with counts | yes — M1 lists six rules in application order; the 234 spot-anchored `cm30` sessions (5.0%) are counted and flagged per-row |

**The look-ahead evidence is mechanical, not asserted.** Beyond the timing audit table,
the perturbation test is run permanently as part of the suite, and the one place where a
look-ahead was found — the stress floor reading the 5 February 2018 move from 2008 — was
caught by this project's own rule and fixed before any backtest ran, with the offending
version kept and reported as a calibration of what knowing the answer is worth.

### D-1. The asset bounds rest on an assumption that daily data cannot test — **disclosed**

Between two anchors the adjusted share count is assumed to lie between the two anchor
values. It is exact at every anchor and it is the weakest assumption that yields a usable
band, but a fund whose share count travelled outside that range and back between two
year-ends would be mis-bounded. Already in M4 and L10. Re-affirmed here as the weakest
data assumption in the project, and it is the one F-A1 also touches.

### D-2. Four figures cannot be rebuilt from a clone — **disclosed**

`index_vs_products`, `decay_regression`, `decay_blocks` and `feb2018_detail` read cached
product price files rather than a processed CSV, so they fail in a clone with a clear
message and `make_figures.py` exits 1. This is the intended design — the pipeline never
downloads implicitly, so that a figure can never be produced from data whose provenance
was not recorded — but it does mean four of the committed figures are not independently
checkable without re-fetching. Recorded in V36.

---

## E. Academic presentation

**Does it read as serious quantitative research?** The structure supports it: a
pre-registered design with falsifiable criteria and a provable timestamp, estimators
implemented and unit-tested against simulated data with known parameters, a validation
document that records errors found and what they were worth, and a results document whose
every number is asserted against a committed table by an executable check.

**Is the contribution stated relative to prior work?** Yes, and honestly — the literature
review states that the components are individually standard and names the source for each
(Simon & Campasano, Cheng & Madhavan, Avellaneda & Zhang, Corsi, McNeil & Frey), with the
contribution claimed as the combination and the evaluation discipline rather than as a new
method.

**Are the limitations honest and specific?** Yes. The project reports that its strategy
does not beat a constant-weight short, that its headline sits at the 78th percentile of a
grid whose median is 0.06, that its escape from February 2018 rests on a 0.72% margin,
that two of its five hypotheses were rejected, and that one passed with its stated
magnitude unmet. These are in the README, not buried.

### E-1. The report has no abstract — **minor**

`reports/report.md` opens with a key-findings paragraph, which does the same work, but a
reader expecting a conventional structure will notice. **Action: disclosed**, on the view
that the key-findings block is more useful than an abstract would be.

### E-2. "Would this stand up to an hour from someone who knows the area?" — **disclosed**

The likeliest things such a reader would press on, and where each is addressed:

| What they would press on | Where it is |
|---|---|
| The index is a reconstruction, not the licensed index | L6, and §5.1's tracking evidence |
| One day dominates the tail | threshold grid, jackknife, V16/V17 |
| The strategy's Sharpe is not significant | stated everywhere the number appears |
| Assets are inferred, not observed | M4, L10, D-1 above |
| The 2.05-tick breakeven makes it unimplementable | §6, and the README limitations |
| The VRP filter was *on* into Volmageddon | §5.6, stated as a finding against the design |

The one thing such a reader would find that was **not** written down before this audit is
F-A2: the "4 of 10" count was wrong, and two of the correct three clear the threshold by
under a quarter of a point. That is now in the limitations.

---

## F. Clean-room reproduction

Cloned into a fresh directory and exercised as a reader would.

| Step | Result |
|---|---|
| `python scripts/run_tests.py` | **245 passed, 2 skipped** — identical to the source tree |
| `python scripts/check_results_numbers.py` | **passes** — every number in all four write-ups matches its table |
| `python scripts/make_figures.py` | **20 of 24 rebuild byte-identically; 0 differences**; 4 fail with a clear message (D-2) |
| `make verify` | manifest clean |
| `python scripts/run_pipeline.py --only clean` | stops with exit code 2 and names the fetch command |

**Zero unexplained discrepancies.** This is a change from Phase 15, where the same test
found three committed figures that were not the output of the code that builds them
(V36). Those were rebuilt, and the reproduction is now clean.

**What this does not establish.** That the tables reproduce from raw data — that needs the
338 raw files, which this environment cannot fetch. The reproduction establishes that the
code, the tests, the number checks and every figure that can be built from committed data
reproduce exactly.

---

## Findings summary

| # | Finding | Class | Action |
|---|---|---|---|
| F-A1 | Flow estimate uses `A_t`; methodology documents `A_{t−1}` | **Material** | Documentation corrected, both figures reported, code unchanged (the ambiguity is real) |
| F-A2 | "4 of 10 days" is actually 3 of 10; two of the three are marginal | **Material** | **Fixed** in all five places; marginality disclosed |
| B-1 | Kelly interval is seed-dependent and the seed is not on the table | Minor | Disclosed |
| C-1 | `evt.return_period` is dead code | Minor | Disclosed |
| C-2 | Duplicated date-parsing helper in `make_figures.py` | Minor | Disclosed |
| E-1 | No abstract in the report | Minor | Disclosed |
| D-1 | Asset-bound interpolation assumption | Disclosed | Already in M4/L10; re-affirmed |
| D-2 | Four figures not rebuildable from a clone | Disclosed | Intended design; in V36 |
| E-2 | What a hostile expert reader would find | Disclosed | Table above; F-A2 was the gap |

**Critical findings: none.** No conclusion in this project is invalidated by the audit.

**Conclusions revised by the audit:** one. H2's strength claim moves from "supported at
the lower bound on 4 of 10 days" to "on 3 of 10, two of them by less than a quarter of a
percentage point". H2's verdict — not rejected — is unchanged, because the pre-registered
rejection rule is failure at both bounds and no day fails at both.

---

## Self-review

**Was the audit adversarial, or a checklist ticked?** Adversarial in section A, where
every headline was re-derived by hand from the raw contract panel rather than read off the
table — which is how both material findings were found. Sections C and D are closer to a
checklist, because the things they check (manifest, secrets, seeds, skips) are binary and
were already instrumented.

**Which finding was the most uncomfortable, and was it fully pursued?** F-A2. "4 of 10"
had been repeated in five documents across four phases without anyone recomputing it, and
the true count is 3 — with two of those three at 10.18% and 10.23%, which is to say H2's
support outside 5 February 2018 is thinner than the project had been claiming. It was
pursued to the individual day and the margin is now named rather than rounded. The
uncomfortable part is not the arithmetic; it is that a number invented in prose survived
four phases of review because it was never in a table. That is the same failure mode as
the V6 tracking numbers caught in Phase 13, and it is the reason
`check_results_numbers.py` exists — but this number was never added to it.

**Is there anything known to be weak that has not been written down?** After this audit,
no. F-A1's ambiguity — that neither `A_t` nor `A_{t−1}` is exactly the quantity a fund
rebalances against — is now stated in M5 and is the most honest available account of a
limitation that daily data cannot resolve.

**The lesson worth carrying.** Every number that appears in prose should be in a table
and in the number check. Both material findings here are numbers that lived only in prose:
one contradicted the code it described, the other contradicted the table it summarised.
`check_results_numbers.py` was extended in this phase to cover the corrected H2 count, so
this specific failure cannot recur silently.
