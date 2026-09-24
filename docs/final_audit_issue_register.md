# Final audit — issue register

Recursive, project-wide audit of `short-vol-etps-vix-carry`, run against the state at
commit `c4c5ec6` (27 commits, local tree content-identical to `origin/main`).

This register is append-only. Every issue keeps its original description even after it
is fixed, so the record shows what was wrong rather than only what is now right.

**Severity.** *Critical* — potentially invalidates core results or reproducibility.
*Major* — materially affects methodology, results, interpretation or documentation.
*Moderate* — requires correction but does not invalidate the project. *Minor* —
quality, consistency, clarity or hygiene.

---

## Pass 1

Entry environment: fresh `git clone` into an empty Linux container with no project
history, numpy 2.4.4, pandas 3.0.2, Python 3.11.15 — all materially newer than the
lower bounds in `requirements.txt`. Raw data absent from the clone by design
(`data/raw/**` is gitignored); verified separately against the authoritative local
working copy, which holds it.

### A-01 · Reproducibility / Git hygiene · **Minor**

**What was wrong.** The repository contains no `.gitattributes`. The committed blobs
are LF; the working tree on the authoring machine is CRLF, normalised on commit by
that machine's global `core.autocrlf`. Any checkout or clone where `core.autocrlf` is
`false` — the default on Linux and macOS, and what a CI runner gets — reports **all
168 tracked text files as modified** immediately after cloning, with
`63,788 insertions(+), 63,788 deletions(-)` and not one byte of real change.

**Where found.** Repository root; reproduced on the authoritative local copy
(`git status --porcelain` → 168 ` M` entries; `git diff --ignore-cr-at-eol --stat` →
empty; `tr -d '\r' < LICENSE | git hash-object --stdin` → `9a15f5e`, exactly the
committed blob).

**Why it mattered.** The project leans on a clean working tree as a verification
signal — the manifest check, the clean-clone reproduction and the completion gate all
read "local and remote agree" from `git status`. That signal is platform-dependent as
shipped: on the authoring machine it is clean, on any other machine it is 168 files
of noise, which both hides real uncommitted changes and makes the documented
verification irreproducible for a reader.

**Root cause.** Line-ending policy left implicit, i.e. delegated to each user's
global git config, rather than declared in the repository.

**Blast radius.** No data, results, tables or figures. Affects `git status` output,
the clean-clone reproduction procedure in `docs/validation.md`, and any CI.

**What adding the policy then exposed.** With `.gitattributes` in place git immediately
flagged three tracked text files whose *committed blobs* contained CRLF while the other ~170
were LF: `data/raw/_manifest.json`, `references/filings/_index.json` and
`reports/tables/filing_terms.csv`. The repository's committed text content was itself
inconsistent, and which ending a file received depended on how it happened to be written
rather than on any decision. This is the harm the missing policy had already done, not a new
problem introduced by fixing it.

**Correction.** `.gitattributes` declaring `* text=auto eol=lf`, with `*.png`, `*.pdf`,
`*.htm`, `*.html` and `*.bundle` marked binary and the byte-compared text types
(`*.csv`, `*.json`, `*.py`, `*.md`, `*.yaml`, `*.toml`, `*.txt`, `Makefile`) pinned
explicitly. The three inconsistent files renormalised with `git add --renormalize`.

**Validation performed.** After renormalisation the manifest still verifies clean over 338
entries, both JSON files still parse, and `filing_terms.csv` still holds 28 rows with
`found=True` on every one. `git status` is clean on a Linux checkout for the first time.

**Status.** **Resolved.**

---

### A-02 · Bias (look-ahead) / Results / Documentation · **Major**

**What was wrong.** From 26 October 2020 onward the headline strategy sets each day's
position using an input struck **fifteen minutes after** the price at which that
position is booked. The variance-risk-premium filter is the leaking input.

The chain, each link verified empirically rather than read from a comment:

1. The engine applies the lag itself: `w = w_raw.shift(signal_lag)`, `signal_lag = 1`,
   and `gross_t = a_t − w_t · r_t` (`src/svcarry/strategy/backtest.py`).
   Verified: `max |backtest_daily.weight − strategy_weights.weight.shift(1)| = 0`, and
   `max |gross − (−weight_t · index_ret_t + accrual)| = 1.8e−16` at lag 0 on the
   stored weight. So the weight built from date *t* information earns the return of
   *t+1* — the position is in place at the **settlement of t**.
2. Nothing else lags. `svcarry.strategy.signals` states "Nothing in this module looks
   forward … the backtest can lag it by exactly one day"; `sizing.strategy_weights`
   states "Nothing is lagged here". Verified on the committed panel:
   `slope_cm(t) = cm30(t)/cm90(t)` to the digit (2008‑01‑02: 24.15647/24.33071 =
   0.9928385), so the signal on date *t* is built from date-*t* data. Effective total
   lag is therefore exactly one day, not two.
3. `r` is a VX **settlement**-to-settlement return (`reconstruct.build_curve(...,
   price_col="settle")`; `docs/methodology.md`: "The index is struck at the futures
   settlement").
4. Cboe moved the VX daily settlement from 3:15 p.m. CT to 3:00 p.m. CT — 4:15 p.m. ET
   to **4:00 p.m. ET** — effective **26 October 2020**. Confirmed against the primary
   source the project itself cites (Cboe notice, *Adjustment of Daily Settlement Time
   for Proprietary Index Products*): "from 3:15 p.m. to 3:00 p.m. CT", effective
   October 26, 2020.
5. `vrp` is built from the VIX cash close, which the project's own
   `reports/tables/timing_audit.csv` records as struck at **4:15 p.m. ET**.

So before 26 October 2020 the signal input and the execution price are struck at the
same instant (4:15 p.m. ET), which is the ordinary idealisation. From 26 October 2020
the input is struck at 4:15 p.m. ET and the execution price at 4:00 p.m. ET, and the
position is set with fifteen minutes of hindsight, on every one of the 1,483 trading
days in that period.

This is the *same fifteen-minute gap* the project identifies as its first headline
finding — the gap between the 4:15 p.m. index and the 4:00 p.m. product close. The
project found it in other people's index-versus-product comparisons and did not look
for it inside its own signal chain.

**Where found.** `config/config.yaml` `strategy.signal_lag`;
`src/svcarry/strategy/backtest.py`; `src/svcarry/strategy/signals.py`;
`reports/tables/timing_audit.csv` rows *VIX close*, *VRP, slopes, signals*, *weight w*.

**Why it mattered — quantified.** Re-running the project's own
`strategy_weights` and `run_backtest` with the committed inputs and **only** the VRP
filter's timing changed. Harness first validated against the committed artefacts:
every sizing column and the return series reproduce to ≤ 1.9e−16.

| variant | OOS Sharpe | OOS CAGR | ann. vol | max DD | Δ Sharpe |
|---|---|---|---|---|---|
| as committed | **0.2680** | 5.01% | 12.61% | −26.3% | — |
| **A** VRP lagged 1d from 2020‑10‑26 (minimal fix) | **0.1989** | 4.10% | 12.53% | −26.8% | **−0.069** |
| B VRP lagged 1d, whole sample | 0.1765 | 3.81% | 12.56% | −29.7% | −0.092 |
| C whole signal lagged 1d (upper bound) | −0.0417 | 0.56% | 14.70% | −45.2% | −0.310 |

161 decision days change under the minimal fix, all of them after October 2020. The
headline out-of-sample Sharpe of **0.27 is overstated by 0.069 — roughly a quarter of
its own magnitude.** The design window is untouched (0.4508 either way), so no
parameter choice is affected.

**Direction matters for how this is reported.** The correction makes the project's
conclusion *stronger*, not weaker: the strategy's corrected 0.199 sits further below
the constant-weight short's 0.40 and further below the PutWrite index's 0.53. Nothing
about the negative headline is at risk. What is at risk is the specific number 0.27,
which appears in the report, the one-page summary, the README, `docs/results.md`,
`docs/validation.md`, `docs/limitations.md`, `docs/project_log.md` and the project
completion note.

**Secondary defect, same root.** `reports/tables/timing_audit.csv` is an 18-row table
whose every row reads `use_precedes_availability = False` — a positive claim that no
input is used before it is available. Two rows do not describe the implemented engine:
*VIX close* and *VRP, slopes, signals* both give `first_used = "close of t+1"`, which
would require an effective two-day lag; the engine uses one. The row for *weight w*
(`available close of t`, `first used return of t+1`) is correct and contradicts the
other two. The table's own internal inconsistency is what allowed the overlap to pass
sixteen phases and a six-perspective final audit unnoticed.

**Third defect, same root.** `config/config.yaml` line 143 documents
`signal_lag: 1` as "signal from close of t-1 traded at close of t". Under the engine
the signal from the close of *t−1* is traded at the close of *t−1*. The comment
describes a two-day convention; one day is implemented.

**Root cause.** The timing convention is asserted in three places in three mutually
inconsistent forms and verified in none. No test pins the relationship between a
signal date, a weight date and the return it earns; `timing_audit.csv` is authored
prose, not a computed artefact.

**Blast radius.** Headline OOS performance → `performance_oos.csv`,
`backtest_variants.csv`, `robustness_*.csv`, `alpha_regression*.csv`,
`specification_distribution.csv`, `stress_windows.csv`, H5's verdict wording →
equity-curve, drawdown, rolling-Sharpe, parameter-heatmap and specification-
distribution figures → `reports/report.md`, `reports/summary_one_page.md`,
`docs/results.md`, `docs/validation.md`, `docs/limitations.md`, `README.md`,
`docs/project_log.md`, `docs/final_audit.md`, and the project completion note held
outside the repository.

**Correction.** Root cause fixed rather than disclosed, on the author's decision. New
module `src/svcarry/timing.py` holds a registry of every input's strike time and the
execution-settlement clock and derives the required lag per date.
`build_signal_panel(vix_extra_lag_from=...)` applies one extra day of lag to the
VIX-cash-derived signals from 2020-10-26; `config/config.yaml` gains a `timing:` block; the
robustness sweep was switched to the aligned columns so the grid sweeps the same
specification as the headline. The raw `vrp` and `slope_vix3m` columns are kept for
reporting, with `vrp_aligned` and `slope_vix3m_aligned` added, so the panel shows both what
was observed and what was tradeable. The config comment and `methodology.md` M7a now state
the convention once, correctly.

**Validation performed.** The counterfactual predicted an out-of-sample Sharpe of 0.1989;
the full pipeline re-run produced **0.198909**. Before any change the unchanged pipeline was
run from raw data and reproduced **all 42 tables and all 24 figures byte-identically**, so
every difference is attributable to this correction alone. 14 of 42 tables, 9 of 24 figures
and 4 of 8 processed datasets regenerated. `performance_design.csv` unchanged, confirming no
parameter was contaminated. Suite 258 passed / 2 skipped. `check_results_numbers.py` passes
against the new tables and now asserts the timing audit's verdict, its row count, and the
1,482 dates carrying a real extra-lag requirement.

**Final numbers.** OOS Sharpe 0.27 → **0.20** (se 0.31); CAGR 5.0% → **4.1%**; max drawdown
−26.3% → **−26.8%**; Sortino 0.237 → 0.177; alpha −1.4%/yr (t −0.52) → **−2.2%/yr
(t −0.77)**; grid percentile 78th → **74th**; grid range −0.35…0.53 → −0.37…0.50; cost
breakeven 2.05 → **1.77 ticks**; one-day-leak calibration 1.12 → **1.54**; volatility
targeting alone +0.06 → **−0.03**; concentration on 2017-08-10 17.0% → **21.8%**; August
2024 stress window −3.2% → **+0.1%**.

**Status.** **Resolved** — corrected at the root, regenerated, revalidated and propagated to
`README.md`, `reports/report.md`, `reports/summary_one_page.md`, `docs/results.md`,
`docs/validation.md` (V25–V28, V30–V35, new V37), `docs/limitations.md` (new L25),
`docs/methodology.md` (new M7a), `docs/research_design.md`, `docs/final_audit.md` (note),
`docs/project_log.md` (Session 14) and `scripts/check_results_numbers.py`.

---

### A-03 · Code · **Minor**

**What was wrong.** The backtest's drift-turnover term divides by the **gross**
return where its own documented formula divides by the net return. The docstring
defines `R_t = a_t − w_{t−1} r_t − c_t` and then gives
`turnover_t = |w_t − w_{t−1}(1 + r_{t−1})/(1 + R_{t−1})|`, but the code is
`drifted = w_pos.shift(1) * (1 + r.shift(1)) / (1 + gross.shift(1))`.

**Where found.** `src/svcarry/strategy/backtest.py`, drift-turnover block.

**Why it mattered.** Equity compounds at the net return, so the position's drifted
weight is very slightly misstated and turnover with it. The error is of the order of
the daily cost itself (a few basis points on a denominator near 1), so it does not
move any reported figure — but the code and its stated formula disagree, and the
formula is the one a reader would check.

**Blast radius.** `turnover`, `cost_rebalance`, `ann_turnover`, and the cost
attribution table, all at the fifth decimal or beyond.

**Correction.** The docstring now states what is computed and why — the net return is
circular within a day, since `R_{t-1}` needs `c_{t-1}` needs `turnover_{t-1}` — and
`tests/test_timing_and_costs.py::test_drift_denominator_approximation_is_bounded` builds the
exact sequential series and requires the difference to stay inside a stated tolerance. The
code is unchanged: putting a 4,711-iteration Python loop into a vectorised engine that runs
once per cell of a 144-cell grid, to move the fifth decimal place, is the worse trade. What
was wrong was an unmeasured approximation; it is measured now.

**Validation performed.** Exact sequential reference over the full sample: worst single
day's turnover differs by 1.8e-03, worst single day's return by 6.2e-06, out-of-sample
Sharpe by **2.4e-05**.

**Status.** **Resolved** (documented and bounded by test).

---

### A-04 · Code hygiene · **Minor**

**What was wrong.** Figures are created with `plt.subplots` and never closed, so a
run that builds many of them accumulates open figures. The test suite emits
matplotlib's `RuntimeWarning: More than 20 figures have been opened` from
`src/svcarry/viz/style.py:182` during `test_viz`.

**Where found.** `src/svcarry/viz/style.py:182`; surfaced by `tests/test_viz.py`.

**Why it mattered.** A warning in an otherwise clean 245-test run trains a reader to
ignore warnings, and the figure stage holds 24 figures' worth of state longer than it
needs to.

**Blast radius.** Test output and figure-stage memory. No figure content.

**Revised diagnosis.** `save_figure` already calls `plt.close(fig)`, so production code does
not leak. The leak is in the tests, which call the plot builders directly and never save. The
root cause is that neither harness reset process-wide state between tests.

**Correction.** Fixed centrally: `_reset_global_state()` in `scripts/run_tests.py` closes all
figures after every test, and a new `tests/conftest.py` does the same through an autouse
fixture under a real pytest. Twenty test functions are untouched.

**Validation performed.** The `RuntimeWarning: More than 20 figures have been opened` no
longer appears in a full run.

**Status.** **Resolved**.

---

### A-05 · Verification integrity · **Major**

**What was wrong.** `reports/tables/timing_audit.csv` — the artefact the project cites as
*mechanical* evidence that nothing leaks — had its verdict column assigned as a literal:

```python
timing["use_precedes_availability"] = False    # stage_signals
add["use_precedes_availability"] = False       # stage_backtest
```

Nothing was computed. The table could not have reported a violation however bad the timing
was, and it was concealing one (A-02) on 1,482 days.

**Where found.** `scripts/run_pipeline.py`, both halves of the table. Cited as evidence in
`docs/final_audit.md` §B and §D ("The look-ahead evidence is mechanical, not asserted…
`timing_audit.csv`: **0 of 18** inputs have use preceding availability") and in
`docs/validation.md` V25.

**Why it mattered.** This is the more important of the two findings. A-02 is a defect; A-05
is the reason a defect of that kind could survive sixteen phases and a six-perspective audit
that explicitly looked for look-ahead. A check that cannot fail is not a check, and citing
one as mechanical evidence overstates the project's rigour in exactly the way §55 forbids.

Compounding it, the convention was asserted in three mutually inconsistent forms —
`config.yaml` line 143 ("traded at close of t", a two-day description), the *VIX close* and
*VRP, slopes, signals* rows of the table (`first_used = close of t+1`, also two-day), and
the engine (one day) — and **no test pinned the relationship between a signal date, a weight
date and the return it earns.** `docs/final_audit.md` §A records an auditor shifting the
emitted weight a second time and finding 2,567 phantom violations, which is what happens
when a convention lives only in prose.

**Root cause.** A verification artefact authored as prose in the shape of a computation.

**Correction.** `src/svcarry/timing.py` holds a declarative registry of each input's strike
time; `timing_audit_table()` compares it against the execution settlement per date and emits
`strike_et`, `dates_needing_extra_lag`, `n_dates_use_precedes_availability` and a **computed**
`use_precedes_availability`. The pipeline raises `SystemExit` if any row is `True`. The table
is now written once, in one stage, which also removed the de-duplication hack that existed
because re-running a stage appended its rows again. `verify_weight_alignment()` checks the
signal-to-weight-to-return relationship against the artefacts, and the pipeline fails if it
does not hold.

**Validation performed.** `tests/test_timing_and_costs.py` pins the clock rule, the panel's
behaviour with and without the flag, the end-to-end convention on constructed data whose
answer is known, and — the mutation check — requires the table to report **1,482 violating
dates across four inputs** when the extra lag is removed. `check_results_numbers.py` now
asserts the table's verdict and row count, so the claim is in the number check rather than
only in prose.

**Blast radius.** No data or results of its own; it is the control that failed to catch
A-02. Documentation: `docs/final_audit.md`, `docs/validation.md` V25, `docs/methodology.md`
M7a.

**Status.** **Resolved.**

---

### A-06 · Reporting · **Moderate**

**What was wrong.** `docs/project_log.md` claimed, of the Phase 16 clean-room test, "245
tests, the number check, `make verify` over 338 files, and **all 24 figures
byte-identical**" — and then, two sentences later, "Four figures still cannot be built in a
clone because they read cached price files." Both cannot be true. The test rebuilt 20
figures and the other four exited with an error. `docs/final_audit.md` §F,
`docs/validation.md` V36 and `docs/project_log.md` at its Phase 15 entry all say 20 of 24
correctly; this one sentence does not, and it is the version that was copied verbatim into
the project completion note held outside the repository.

**Where found.** `docs/project_log.md`, Phase 16 "Clean-room reproduction".

**Why it mattered.** It overstates a reproducibility result in the document a reader is most
likely to quote, and §55 puts reproducibility claims among those that must not exceed the
evidence. It is also self-indicting: the same section's closing paragraph draws the lesson
that every number in prose should be in a table, and the figure count was never in one.

**Root cause.** A summary sentence written from the intent of the test rather than from its
output, in a document with no executable check over it.

**Correction.** Corrected in place to "all 20 rebuildable figures byte-identical", with the
original claim, why it was wrong, and why it survived recorded beside it. The completion note
is corrected separately. Pass 1 has since reproduced **all 24 figures byte-identically from
the full raw data** — a different and stronger test, recorded as V37, and not the one this
sentence was describing.

**Blast radius.** `docs/project_log.md`; the external completion note.

**Status.** **Resolved.**

---

### A-07 · Reporting · **Minor**

**What was wrong.** `README.md` reported "**244 tests passing**, 2 skipped". Every other
document, and the suite itself, said 245.

**Where found.** `README.md`, Status table.

**Why it mattered.** Small in itself, but it is a third instance of the same pattern as A-05
and A-06: a verification result quoted from memory rather than from output, in the file a
reader sees first. Three of them in one project is a pattern, not a typo.

**Correction.** Updated to 258 passing / 2 skipped, the count after this pass's additions.

**Status.** **Resolved.**

---

### A-08 · Reporting · **Minor**

**What was wrong.** `docs/validation.md` V27 reads "Annual turnover of 11.3 (out of sample):
7.1 rebalancing … and 4.2 from the index's own roll, which is 38.7% of the cost bill." The
turnover figures are out-of-sample; **38.7% is the full-sample share**. The out-of-sample
figure is 39.5% before the A-02 correction and 39.2% after. Three windows' worth of
arithmetic in one sentence, presented as one.

**Where found.** `docs/validation.md` V27.

**Why it mattered.** Not material to any conclusion, but it is a window mismatch inside a
single sentence in the document whose job is to make every number traceable — and it is
undetectable by `check_results_numbers.py`, which checks table-to-prose links and not which
window a prose figure came from.

**Correction.** Restated on the out-of-sample basis (39.2%), with the original figure and its
basis recorded.

**Status.** **Resolved.**

---

## Checked and found clean in Pass 1

Recorded so that a later pass does not re-litigate settled ground, and so the
register shows the audit's coverage rather than only its catches.

| Check | Method | Result |
|---|---|---|
| Test suite from a clean clone | bundled zero-dependency runner, no pytest available | **245 passed, 0 failed, 2 skipped** — matches the claim exactly, on numpy 2.4.4 / pandas 3.0.2 |
| Forward compatibility | suite run against dependencies far newer than the pins | no failures; the lower-bound-only pins hold up |
| Local tree vs `origin/main` | LF-normalised blob hashing | content-identical at `c4c5ec6`; **local and remote genuinely agree** |
| Retrieval manifest | `verify_manifest()` on the authoritative copy | **clean**, 338 entries (331 raw files + 7 filings) re-hashed |
| Project's own number checker | `scripts/check_results_numbers.py` | passes across `results.md`, `report.md`, `summary_one_page.md`, `README.md` |
| Headline performance statistics | independent reimplementation, no project imports | CAGR, ann. vol, max drawdown, hit rate, worst/best day reproduce to **≤ 4.2e−15** across all three windows |
| Weight and turnover statistics | independent reimplementation | `time_invested`, `avg_weight`, `max_weight`, `ann_turnover` reproduce exactly in all three windows |
| Backtest internal identities | independent | `ret = gross − costs` (1.0e−16), `costs = cost_rebalance + cost_roll` (1.0e−16), `turnover = t_rebalance + t_roll` (2.2e−16), `equity = cumprod(1+ret)` (5.6e−14) |
| Sharpe / Sortino convention | implied-rate back-out | excess of the T-bill accrual, as documented; implied annual rate 1.43% full, 0.24% design, 2.32% OOS — consistent with realised bill yields in each window |
| Constant-weight benchmark | independent reconstruction | the gap against a naive replication is transaction costs, correctly charged; its in-window sizing **is** disclosed (`docs/limitations.md`, `docs/methodology.md`, `docs/research_design.md`) — not a hidden look-ahead |
| Cited primary source, settlement time | fetched the Cboe notice | says "from 3:15 p.m. to 3:00 p.m. CT", effective October 26, 2020 — **citation accurate** |
| Overclaiming vocabulary | full-text sweep | zero occurrences of "fully reproducible", "fully automated", "production-ready", "statistically significant", "outperformed", "replicated" |
| Full pipeline re-run from raw data, unchanged code | 338 raw files restored and manifest-verified; pipeline run end to end | **42 of 42 tables and 24 of 24 figures byte-identical**, 8 of 8 processed datasets — a stronger reproduction than the project had established, and the control that makes the A-02 diff interpretable |
| Signal-to-weight-to-return alignment | empirical, on the committed artefacts | `backtest_daily.weight` equals `strategy_weights.weight.shift(1)` exactly; a signal that turns on at date *d* first earns the return of *d+1* |
| Design-window contamination | `performance_design.csv` before and after the correction | byte-identical; no parameter of the strategy was chosen on leaked information |
| H2 flow arithmetic | pipeline recomputation | 55,690 contracts and 24.995% of front-month open interest on 2018-02-05, reproducing the 25.0% claim; de-levering counterfactual 20,884 and 9.4% |
| F-A1's resolution | `docs/methodology.md` M5 | both `A_t` (25.0%) and `A_{t−1}` (24.8%) are reported, with the ambiguity stated — the Phase 16 action was actually carried out |
| Cited primary source, VX settlement time | fetched the Cboe notice the project cites | "from 3:15 p.m. to 3:00 p.m. CT", effective October 26, 2020 — **verbatim as claimed** |
| Inventory against claims | file counts | 42 tables, 24 figures, `report.md` 790 lines, `validation.md` 1,289, `project_log.md` 1,123 — all as claimed |

---

## Pass 2

A fresh project-wide pass, not a re-check of Pass 1's changes. Its targets were the
layers Pass 1 never reached: the econometric implementations, the index reconstruction
and settlement calendar, the raw data, the ETP mechanics and the archived filings, the
literature and its citations, the prompt system, and a re-reconciliation of every number
now that Pass 1 moved many of them.

Three findings. The most important is upstream of everything in Pass 1.

### A-11 · Prompt system · **Major**

**What was wrong.** `prompts/tasks/lookahead_audit.md` is the prompt that produced the
look-ahead audit, and it is the root cause of A-05 and therefore of A-02. Two defects:

1. **It specified a date-granular table.** "For every input, record in a table: the date
   it is indexed by, the date its information becomes available, and the date it is first
   used." Nothing asks for the clock time at which a value is struck. A-02 is a
   fifteen-minute overlap between two series dated the same day, so the audit as specified
   could not see it — and the artefact it produced did not.
2. **It did not require the verdict to be computed.** Nothing in the prompt says the
   comparison must be performed in code, or that the check must be capable of failing. The
   implementation duly wrote `use_precedes_availability = False` as a literal and the
   project cited it as mechanical evidence.

**The uncomfortable detail.** The same prompt already names A-02's exact mechanism. Its
list of how look-ahead arrives includes "*a signal computed from a close and traded at the
same close*". The prompt identified the failure mode and then specified a check too coarse
to detect it.

**Where found.** `prompts/tasks/lookahead_audit.md`, Procedure step 2 and the Validation
table.

**Why it mattered.** Fixing the code without fixing the prompt would leave the generative
cause in place: the next project built from this prompt pack would reproduce the same
defect. This is the backward-propagation rule applied to the instructions rather than to
the artefacts.

**Correction.** Step 2 now requires each input's **strike time**, the strike time of the
execution reference (which may change mid-sample, as the VX settlement did on 26 October
2020), a **computed** verdict with a per-date failure count, the pipeline gated on it, and
a **mutation test** proving the check catches the defect when the correction is removed.
The Validation table gains a mutated-table row. The prompt also now records that step 1's
perturbation test perturbs by whole days and therefore cannot detect an intraday overlap
either, so the two steps are complementary and neither alone is sufficient.

**Blast radius.** The prompt pack, and any future project built from it. No data or
results.

**Status.** **Resolved.**

---

### A-09 · Literature · **Minor**

**What was wrong.** `docs/literature_review.md` cites Bollen, O'Neill & Whaley (2017),
*Tail Wags Dog: Intraday Price Discovery in VIX Markets*, and files it under limitations:
"relevant as a limitation rather than an input… this project works at daily frequency and
therefore cannot resolve them." That reading is correct but incomplete. The same paper
carries a constraint the *design* had to satisfy: if the VIX index and the VX settlement
are struck at different moments, whether a VIX-derived signal is tradeable at the
settlement depends on which comes first — and that ordering changed on 26 October 2020.

**Why it mattered.** The literature needed to prevent A-02 was already cited. It was read
as a caveat about describing events rather than as a constraint on timing decisions, so it
did no work. No new source was required; the existing one needed a second reading.

**Correction.** A paragraph added to §2 separating the two readings explicitly and
pointing to M7a and L25, with the generalisable lesson: a paper filed under "limitations
we cannot address" may also carry a constraint the design must satisfy.

**Status.** **Resolved.**

---

### A-10 · Prompt system · **Minor**

**What was wrong.** Three prompt files named output artefacts the project does not
produce: `reports/tables/roll_convention_comparison.csv` (the table is
`roll_convention.csv`) and `reports/tables/data_quality.csv`, which was **never produced
under any name** — the cleaning counts went into `docs/validation.md` and the rules into
`docs/methodology.md` M1 instead.

**Where found.** `prompts/tasks/resolve_roll_convention.md`,
`prompts/phases/06_data_cleaning_validation.md`,
`prompts/operations/data_quality_review.md`.

**Why it mattered.** Small, but §60's point exactly: the prompt system must describe the
actual process. A reader following these prompts would look for two files that do not
exist, and one of them was a planned artefact silently dropped rather than deliberately
folded into a document.

**Correction.** Filenames corrected; the dropped table recorded as dropped, with where its
content actually went, rather than the reference quietly deleted.

**Status.** **Resolved.**

---

## Checked and found clean in Pass 2

Every row below is an independent recomputation or an external verification, not a reading
of the project's own output. The estimator checks matter particularly because the project's
own cross-checks against `arch` and `statsmodels` skip in every environment it has run in,
so nothing had previously compared these numbers with anything but themselves.

| Check | Method | Result |
|---|---|---|
| Hansen (1994) skewed-t density | numerical quadrature at both fitted parameter sets | integrates to 1.000000, mean ≈ 0, variance ≈ 1 — correctly standardised |
| GJR-GARCH log-likelihood | recursion and density written from Glosten-Jagannathan-Runkle and Hansen, no project code | reproduces the committed log-likelihood to **1.6e-04** (pre-2018) and **1.3e-04** (full) with the documented sample-variance initialisation; persistence and unconditional annual volatility to **10 decimal places** |
| Is the GARCH fit a maximum? | L-BFGS-B re-optimisation from the committed point | log-likelihood gain **0.000000**, parameters move ≤ 1.2e-10 — a genuine optimum, which nothing had checked |
| GPD / peaks-over-threshold | `scipy.stats.genpareto.fit` on exceedances of my own filtered residuals, all 8 thresholds × 2 samples | every ξ and β agrees to **~4e-05**; thresholds and exceedance counts identical. Validates the GARCH filter and the GPD MLE together |
| Kelly fraction | expected-log-growth maximisation, three samples | agrees to **2e-08**; ruin bounds `1/max(r)` exact |
| Daily variance proxy | Yahoo JSON parsed here; overnight + Rogers-Satchell from their definitions | reproduces `rv_proxy` to **1.6e-16** on all 4,708 shared dates |
| HAR, level specification | own OLS and own Newey-West | coefficients and OLS standard errors **exact**; HAC to 3e-05, the residual being precisely √(n/(n−k)) — a small-sample correction |
| HAR, log specification | four candidate conventions tested against the table | identified exactly: target = log of the **arithmetic** mean of future RV, predictors = means of log RV. Matches `har_fit.csv` to 1e-06 and matches `methodology.md` M7 word for word. The rejected geometric-mean target is the bug the project's own log records catching |
| Index reconstruction | 313 raw contract files parsed here, front-two basket rebuilt, **all 4,710 daily returns** recomputed | max absolute difference **4.0e-16**; zero rows differing by more than 1e-10 |
| Roll dates specifically | the 225 dates where the front contract changes | max difference **9.9e-17**. A naive front-month `pct_change` would have booked a mean absolute error of **9.99%** on those days, which is what the reconstruction exists to avoid |
| f1, f2 against raw settles | direct lookup with the documented open-interest filter | **exactly 0** difference on all 4,711 rows |
| Settlement calendar | rule derived independently: Wednesday 30 days before the third Friday of the following month | 227 expiries; the **7** that deviate are all Tuesdays, and all 7 are correct holiday pull-backs (Good Friday ×5, Juneteenth ×2) |
| Weight and term-structure identities | recomputed from the panel | `w1 + w2 = 1`, `w1 = dr/dt`, `days_to_exp`, `carry_log = ln(F2/F1)/(τ2−τ1)`, `basis_f1_vix = F1/VIX − 1`, `slope_cm`, `slope_vix3m`, `spread_f2_f1`, level chaining — all to ≤ 1.5e-09 |
| Raw data integrity | duplicates, ordering, gaps, missing contracts, extreme moves | no duplicate dates, strictly increasing, one 5-day calendar gap, zero rows with a missing held contract, `cm30` missing on 234 rows (4.97%, as documented). All 9 days with \|return\| > 25% are identifiable events (Aug 2015, Brexit, Feb 2018, Mar 2020, Jun 2020, Omicron, Aug 2024, Apr 2025) |
| Archived filings | all 28 quoted terms re-searched in the source documents | **28 of 28** quotations found verbatim and **28 of 28** search patterns re-match, after folding Unicode punctuation to ASCII. 11 carry a config cross-check, all agreeing |
| Rebalancing-flow arithmetic | recomputed from the committed assets and raw open interest | `contracts = flow/(1000·F1)` to 7e-12; `share = contracts/OI` exact; 2018-02-05 lower bound 55,689.99 contracts and 24.995% confirmed |
| De-levering counterfactual | coefficient ratio against flow ratio | `L(L−1)` goes 2.0 → 0.75 for **both** funds (SVXY −1→−0.5, UVXY 2→1.5); flow ratio = coefficient ratio = 0.375 exactly, reduction 0.625 exact. The documents say "coefficient", correctly, not "leverage" |
| Bibliography | 35 entries cross-referenced against prose citations | all 23 author-year citations in the literature review map to an entry; the uncited entries are the source documents cited in `data_sources.md`; no malformed DOIs; one entry honestly marked "partial; volume and pagination not confirmed" |
| Secrets and portability | pattern scan across code, config, docs and notebooks | no secrets; no absolute or machine-specific paths in any code or configuration file (they appear only in the project log's environment record and the resume prompt, where they belong) |
| Prompt-to-project file references | every path mentioned in the 35 prompt files resolved | two stale names found (A-10); everything else resolves |
| Full re-reconciliation | swept all documents for the 21 values Pass 1 moved | no stale value survives in any document describing the current state. The only remaining occurrences are in `docs/project_log.md` and `docs/final_audit.md`, both explicitly historical, both carrying forward-pointing notes |

---

## Pass 3

A third full pass. One finding, and it is the same shape as A-05: a statement about the
project that was true in a docstring and false in the code.

### A-12 · Code / Reproducibility · **Moderate**

**What was wrong.** `stage_figures` in `scripts/run_pipeline.py` carries this docstring:

> The figures live in one script rather than being scattered through the analysis stages,
> so that each regenerates from committed data on its own and the registry there --
> figure, question answered, inputs -- is the single list.

The analysis stages were drawing **twenty of the twenty-four figures themselves**, so each
of those twenty had two implementations: one in the stage that produced its inputs, one in
`scripts/make_figures.py`.

**And the two had drifted.** Measured by running each figure-writing stage against the
`make_figures` output, **six of the twenty come out byte-different**:

| Figure | Stage |
|---|---|
| `decay_regression` | mechanics |
| `flow_vs_open_interest` | mechanics |
| `rolling_sharpe` | backtest |
| `weight_and_binding_constraint` | backtest |
| `feb2018_detail` | backtest |
| `survival_curves` | tail |

The cause is series ordering, not data: a stage passes its series in the in-memory
insertion order, while `make_figures` reads the committed CSV and `groupby`s it, which
sorts. Legend order and draw order therefore differ, and so do the pixels.

**Where found.** `scripts/run_pipeline.py`: twenty `save_figure` call sites across
`stage_mechanics`, `stage_tail`, `stage_signals`, `stage_backtest` and `stage_robust`.

**Why it mattered.** A full run hid it completely, because `stage_figures` runs last and
overwrote every stage version -- which is why the committed figures were always the
`make_figures` output and why Pass 1's byte-identical reproduction of all 24 was genuine.
But `run_pipeline --only tail`, or `--only backtest`, left a committed figure quietly
modified. That is the same failure as A-01: an artefact changing under a partial operation
while `git status` is being relied on as a verification signal. And duplicated drawing
logic that has already drifted once in a way that does not matter can drift again in a way
that does.

**Root cause.** Figure drawing was never removed from the analysis stages when it was
centralised into `make_figures.py`, and the docstring was written as though it had been.
No check compared the two paths, and none could, because nothing knew there were two.

**Correction.** All twenty duplicate call sites removed, with the objects that existed
only to be plotted and the imports they needed. `make_figures.py` is the sole writer, as
the docstring always claimed -- verified by the fact that **no figure was written only by
a stage**, so nothing is lost. Two comments worth keeping were preserved at the deletion
sites: the note about a previous Kelly growth figure annualising an already-annualised
series (a peak of 33 "per year" instead of 0.13), and the heatmap caption's provenance.
The docstring now states what was untrue about it.

**Validation performed.** `tests/test_figure_single_writer.py` (4 tests) asserts that the
pipeline contains no unqualified `save_figure` call, constructs no `figdir / "*.png"`
destination, that the committed figures and the `make_figures` registry are the same set,
and that the registry has no duplicate key. Suite 262 passed, 2 skipped. The full pipeline
was then re-run end to end from raw data and all 42 tables, all 24 figures and all 8
processed datasets came back byte-identical to the pre-change state.

**Blast radius.** Six figures under partial runs; no table, no number, no conclusion.

**Status.** **Resolved.**

## Checked and found clean in Pass 3

| Check | Method | Result |
|---|---|---|
| Figure staleness | all 24 regenerated and byte-compared against the committed versions | **24 of 24 identical** -- no stale figure in the repository |
| Monte-Carlo seeding | `--only tail` re-run and all ten of its outputs compared | **10 of 10 byte-identical**, including the 20,000-path survival simulation and the bootstrap intervals -- the seeding claim holds |
| H3 return periods | recomputed as 1/(252·p) from the probabilities | agrees to **7.3e-12**; 78.9, 2835, 3877 and 12.8 years all reproduce |
| H3 magnitude | ratio recomputed | **8.677×**, reported as 8.7× and correctly declared short of its pre-registered 10× |
| Survival curves | final values against the write-ups | 0.811, 0.937, 0.899, 0.986 all reproduce; capped threshold-grid gap max 9.43 points |
| Retrieval manifest structure | every entry's fields, hosts, statuses and timestamps | 338 entries, **no missing field**, all HTTP 200, four hosts (Cboe 320, Yahoo 8, SEC 7, FRED 3), earliest retrieval **2026-09-20T08:30:04Z** -- confirming the pre-registration gap against the 07:40:36Z config commit |
| Research-question scope | conclusions read against the pre-registered question and sub-questions | conclusions stay inside it; the "what this project does not claim" section correctly disclaims causality for 5 February 2018 and explicitly names the daily-frequency limit |
| Q5's own bar | "a strategy that survives only at zero costs has not survived" | survives at 1 tick (0.20) and not at 2 (−0.06); the bar is met on its own terms |
| H4's consequence | searched for the leverage critique H4 failed to support | **no such claim anywhere.** The report states the result against its own thesis: "on the evidence available before the crash, growth-optimal sizing *favoured* the full inverse exposure the products sold" |
| Claim-to-evidence on H4 | how the rejection is reported | reported as **Rejected** with mechanism, an alternative explanation, and what the data cannot settle -- not softened |

---

## Pass 4

### A-13 · Financial theory / Statistics · **Moderate**

**What was wrong.** The `sortino` column in every performance table was not the Sortino
ratio. `svcarry.evaluation.metrics.performance_stats` computed

```python
downside = ex[ex < 0]
dsd = downside.std(ddof=1) * sqrt(periods)
sortino = ex.mean() * periods / dsd
```

The Sortino denominator is the **target downside deviation**,
`sqrt( (1/n) * sum_i min(ex_i - T, 0)^2 )` at target `T = 0`, with the mean taken over
**every** observation. The code instead selected the sub-target subset and then took the
standard deviation of that subset *about its own mean*, over the count of losses. That is
neither the Sortino denominator nor any standard statistic: it measures how varied the
losses were rather than how large them.

Two consequences follow from the wrong centre and the wrong count:

* A series whose losses were all the same size has zero dispersion about their own mean,
  so the denominator goes to zero and the ratio to infinity — however large those
  identical losses are.
* Scaling every loss up does not necessarily worsen the ratio, because only the spread
  between losses enters.

**Where found.** `src/svcarry/evaluation/metrics.py`, `performance_stats`.

**Why it mattered.** It is a named financial statistic reported in eight committed tables,
and §46C's point applies exactly: a numerically valid result computed from an incorrect
financial definition is still wrong. A reader comparing this column with any other
published Sortino was comparing two different quantities.

**Direction.** Conservative. The published figures were *below* the true ratio — out of
sample **0.177 against 0.245**, full sample 0.309 against 0.405, design 0.492 against
0.598 — so nothing was flattered, and no conclusion rested on the column: no Sortino value
appears in the prose of any write-up, only in the tables and as a metric named in
`research_design.md`.

**Root cause.** A plausible-looking one-liner, and nothing pinning the definition. The
project's own test suite had **no test for Sortino at all**, which is why the formula was
never confronted with a case that distinguishes it from the correct one.

**Correction.** The target downside deviation, over all observations, with the old formula
and why it is wrong recorded at the site. Documented in `docs/methodology.md` under a new
*Risk statistics* paragraph that also states the Sharpe and Lo-standard-error conventions,
and named in `docs/research_design.md`.

**Validation performed.** Two new tests in `tests/test_evaluation.py`: one constructs a
series with two distinct loss magnitudes and more gains than losses, so the two formulas
cannot coincide, and requires the target-downside form; the other requires that doubling
every loss worsens the ratio and that a series of identical losses stays finite and ranks
below a series of smaller ones — the two properties the old formula lacked. The full
pipeline was re-run: **only the `sortino` column changed, in exactly the eight tables that
carry it**; all 24 figures and all 8 processed datasets are byte-identical, and no other
column of any table moved. Suite 264 passed, 2 skipped. The value is now asserted in
`check_results_numbers.py`.

**Blast radius.** The `sortino` column of `performance_{oos,full,design}.csv`,
`backtest_variants.csv`, `robustness_{costs,parameters,subsamples}.csv` and
`specification_distribution.csv`. No figure, no prose number, no conclusion.

**Status.** **Resolved.**

---

### A-14 · Documentation · **Minor**

**What was wrong.** A finding against Pass 1's own work. `docs/methodology.md` M7a, added by
this audit to state the execution-timing convention, presented the settlement clock as a
two-row table: 4:15 p.m. ET to 23 October 2020, 4:00 p.m. ET after. `docs/data_sources.md`
records a **third** change the new section did not mention — Cboe replaced the settlement
*calculation* with a tiered VWAP/TWAP procedure effective 9 September 2024.

**Why it mattered.** It does not change the correction or any number: the procedure change
alters how the 3:00 p.m. CT price is formed, not when it is struck. But a section whose
whole purpose is to pin down strike times should not omit a documented change to how a
strike time is computed, and from September 2024 "strike time" is the end of a short
window rather than an instant. A reader checking M7a against `data_sources.md` would find
the latter more complete than the section written to be definitive.

**Where found.** `docs/methodology.md` M7a, against `docs/data_sources.md`.

**Correction.** M7a now records the 9 September 2024 procedure change, states why the
two-row table still governs, and notes that the consequence is that fifteen minutes is a
*lower bound* on the overlap rather than an exact figure — a window ending at 3:00 p.m. CT
is observable by then and one extending past it is struck later still, which only widens
the gap to the 4:15 p.m. VIX close. The correction is a full trading day either way, so
nothing in the implementation depends on resolving it.

**Status.** **Resolved.**

## Checked and found clean in Pass 4

| Check | Method | Result |
|---|---|---|
| Sharpe standard error | Lo/Mertens non-normal asymptotic variance implemented independently | reproduces to **8.3e-16** in all three windows — and the skewness and kurtosis terms matter here, with excess kurtosis at 31 out of sample |
| Drawdown, VaR, CVaR, Calmar, skew, kurtosis, hit rate | independent reimplementation, all three windows | every one reproduces to ≤ 1e-13; longest underwater run 1,998 days exact |
| Rolling Sharpe | independent | reproduces |
| Stationary bootstrap | four properties tested independently | realised mean block length 4.99 / 20.76 / 61.2 against 5 / 21 / 63; equal-probability resampling consistent with a multinomial (sd 23.2 against 24.5 theoretical); AR(1) autocorrelation preserved at 0.675 against a sample 0.709, where an iid bootstrap gives 0.000; **95% CI coverage 92.3%** on an AR(1) against 55.7% for iid |
| `figure_index.md` against the figures | set comparison and row parsing | 24 on disk, 24 indexed, registry identical, and every row carries both a question and an input — no gaps |
| `data_sources.md` against the manifest | host, URL-prefix and family comparison | all four hosts and every URL family documented; the Stooq entry is labelled a **fallback** and the status row says Yahoo was used, which the manifest confirms — documented but unused, and honestly so |
| The 2024 Cboe notice | followed up as a threat to A-02 | it changes the settlement *procedure*, not its time; A-02 unaffected (and A-14 records the omission) |
| Phase-07 tracking gate | prompt's own failure band (>25 bp/day) against the measured 133.2 and 31.7 | the gate **failed** and the project recorded it as failed — "H1 rejected … against a 25 bp criterion" — rather than quietly passing it. The failure became the project's headline finding |
| Phase-11 plausibility gates | prompt's bands against the corrected numbers | OOS Sharpe 0.20 within the "≤ 1.5" band; leak calibration 1.54 "far above the honest one"; cost sensitivity monotone; design and evaluation windows reported separately |
| Index coverage gate | prompt requires ≥ 99% of sample trading days | 4,710 of 4,711 returns defined (99.98%) |
