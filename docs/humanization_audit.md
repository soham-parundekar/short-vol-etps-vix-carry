# Final cleanup audit

A last pass over the finished project, after the recursive audit had returned a clean
one. Its brief was narrower and different: not "is the research right" — the register in
[`final_audit_issue_register.md`](final_audit_issue_register.md) answers that — but "is
this repository the research artefact, or is it still the workspace the research was done
in".

Ten substantive findings. Three of them turned out to be correctness issues rather than
presentation ones, which is the reason this file exists rather than a changelog line.

**Nothing here moved a number.** All 42 tables, 24 figures and 8 processed datasets
reproduce byte-identically from the raw data before and after, the suite is 264 passing
and 2 skipped either side, and `scripts/check_results_numbers.py` passes. The evidence is
in §11.

---

## H-01 · The prompt pack, and what the pre-registration claim rested on · **Major**

**What was wrong.** The repository shipped a `prompts/` directory: 35 files of phase
plans, task decision rules and standing review checklists, written as instructions for
executing the project. Ninety-one mentions across the documentation, the code comments,
`config/config.yaml` and the report pointed into it.

The problem was not tidiness. The project's strongest methodological asset is that its
hypotheses and parameters were fixed before any data existed, and that claim was cited
*through those files* — "fixed in the phase prompt (commit 3db0269)". A reader could
check it only by reading a pack of execution instructions, which is the wrong artefact to
put that weight on.

**What changed.** The pack is gone from the repository.
[`preregistration.md`](preregistration.md) replaces it with the evidence a pre-analysis
plan should rest on: the parameter set as `git show 2bdeb31:config/config.yaml` prints
it, the commit timestamps, the manifest's earliest `retrieved_utc`, and the four
substantive changes made afterwards with the reason and effect of each. Every reference
was rewritten to the thing it was really about — the design, the specification, the
validation procedure — rather than to the file that happened to carry it.

Two rules that lived only in the pack are now written out where they belong: the EVT
threshold selection rule in `preregistration.md` §3, and the look-ahead audit procedure
in [`validation.md`](validation.md) V25.

**Behaviour.** Unchanged. In `src/` and `scripts/` the edits touched only docstrings and
comments.

**Validation.** A repository-wide search for "prompt" returns one hit outside this file,
an ordinary use of the English verb. The last one to go was found only by the final sweep,
because the earlier passes searched markdown, Python and YAML and this one was a comment
inside a CSV: `data/reference/product_asset_anchors.csv` pointed at the removed
asset-bounding task note. It points at `methodology.md` M4 now, and re-running the
mechanics stage returned every table and dataset byte-identical, as a comment-only change
should. The link checker reports zero broken references across every markdown
file and every backticked repository path. Tests and outputs unchanged.

**Files.** `prompts/` (deleted, 35 files); `docs/preregistration.md` (new);
`README.md`, `docs/{research_design,methodology,validation,data_sources,project_log,final_audit,final_audit_issue_register}.md`,
`reports/report.md`, `config/config.yaml`, `scripts/run_pipeline.py`,
`src/svcarry/econometrics/evt.py`, `src/svcarry/etp/assets.py`,
`tests/test_tailrisk.py`.

---

## H-02 · Six cross-references a reader cannot resolve · **Moderate**

**What was wrong.** Six citations of the form `§46C`, `§54`, `§55` — "recorded because
§46C asks about fees", "in exactly the way §55 forbids". They point into a document that
is not in the repository and never was. Anyone reading `final_audit_issue_register.md`
hits an authority they cannot look up.

**What changed.** Each was replaced with the substance of the rule it was invoking. "The
point holds exactly: a numerically valid result computed from an incorrect financial
definition is still wrong" says the same thing and carries its own authority.

**Behaviour.** Unchanged; prose only.

**Files.** `docs/final_audit_issue_register.md`, `docs/project_log.md`.

---

## H-03 · The timing-overlap day count disagrees with itself · **Moderate**

**What was wrong.** The number of trading days on which the VRP filter was struck after
the settlement it traded at appears as **1,483** in three places and **1,482** in
fourteen others.

The computed value is 1,482: `svcarry.timing.extra_lag_required` over the 4,711-session
index returns 1,482 dates, 26 October 2020 through 18 September 2026 inclusive, and
`timing_audit.csv` carries that figure.

**Why it survived.** `check_results_numbers.py` asserts the table's 1,482 and passes.
The three wrong values sat in a module docstring, a pipeline comment and one paragraph of
the register — prose the number check does not reach. This is the same shape as A-08 and
the A-02 family: a statement true in a table and false in the text beside it. Eight audit
passes did not catch it because every pass that looked at this number looked at the
checked one.

**What changed.** Corrected to 1,482 in all three. A repository-wide search for "1,483"
now returns nothing.

**Behaviour.** Unchanged; comments and prose only.

**Files.** `src/svcarry/timing.py`, `scripts/run_pipeline.py`,
`docs/final_audit_issue_register.md`.

---

## H-04 · Documentation describing a project that had not run yet · **Major**

**What was wrong.** Three documents still described the state the project was in before
any data arrived.

`data_sources.md` was the worst of it. Its preamble explained a convention — sources are
marked "endpoint confirmed, bulk pull pending" until the pipeline runs — and four Status
rows carried that marking: the Cboe index histories, the FRED series, the SEC filings
and the per-contract futures. Its closing section said "**the bulk data pull is
pending** at the time of writing … this document is updated in the same commit". The
pull completed on 20 September. The document was never updated.

All four claims are false against the manifest: 338 files retrieved and hashed, including
all seven Cboe index series, all three FRED series and all seven filings.

`validation.md` carried an open item reading "The seven SEC filings are not yet verifiable
in this environment" while `filing_terms.csv` records 28 of 28 quoted terms re-found
verbatim in those same filings, and the register cites that result. The document
contradicted itself two thousand lines apart.

`research_design.md` opened with "Status: **design fixed, implementation in progress.**
Anything not yet estimated is marked `[pending data]`" on a project whose §9 reports what
the evidence left of all five hypotheses.

**Why it matters more than it looks.** A reader arriving at `data_sources.md` first — a
natural place to start — is told the project has no data. Every status line is now
generated from what the manifest actually holds, with the coverage window of each series.

**What changed.** The four Status rows rewritten from `data/raw/_manifest.json` and the
files themselves; the preamble now states what verification means here; the closing
section explains the two-machine fetch and why the manifest exists. The validation open
item is struck through and closed with its evidence rather than deleted, which is the
convention that file already uses. The `research_design.md` header now says what sections
1–8 are, when they were fixed, and points at `preregistration.md`.

**Behaviour.** Unchanged; documentation only.

**Validation.** Every new Status line checked against the manifest and, for the filings,
against `reports/tables/filing_terms.csv`. `check_results_numbers.py` now asserts the
manifest's entry count and its earliest retrieval timestamp, so the provenance claim these
rows rest on is checked rather than trusted (H-08).

**Files.** `docs/data_sources.md`, `docs/validation.md`, `docs/research_design.md`.

---

## H-05 · The project log read as an execution diary · **Moderate**

**What was wrong.** Three separate problems in one file.

1. **An environment probe.** Session 1 opened with a table of the build machine's tool
   surface — the project folder's absolute Windows path, "Cloud Python", a device file
   bridge, a local shell that failed to start, web fetch tools. None of it is about
   short-volatility ETPs. The *consequences* recorded underneath it are: they are why
   every estimator is hand-rolled and why the test runner is home-made.
2. **Nineteen headings in three formats.** `## 2026-09-20 — Session 1: …`,
   `## Session 3 — 20 September 2026`, `## 2026-09-24 — Session 14: …`, with eleven of
   them carrying no subject at all, so the log could not be scanned.
3. **Infrastructure vocabulary** throughout: "this session's git proxy refuses to inject
   a credential", "an empty container", "the user has chosen to enable full network
   access" — the author writing about themselves in the third person.

**What changed.** The probe became two sentences stating the constraint that mattered
(no PyPI, no market-data hosts, GitHub reachable) with the consequences kept intact. All
nineteen headings normalised to `## Session N — D Month YYYY: subject`, each subject taken
from that entry's own opening paragraph. Infrastructure wording replaced with plain
description. `### Divergences from the prompt pack` became `### Divergences from the
plan`.

Nothing was removed for being unflattering. Every bug, every correction, every
superseded number and the append-only warning at the top are untouched.

**Behaviour.** Unchanged; documentation only.

**Files.** `docs/project_log.md`.

---

## H-06 · Dead code and commented-out code · **Minor**

`scripts/run_pipeline.py` defined `_not_yet(name)`, a stage-guard factory that nothing
calls — the only unreferenced top-level definition in `src/` or `scripts/`. Removed.

`src/svcarry/evaluation/metrics.py` carried the superseded Sortino denominator as two
commented-out lines inside a twelve-line comment. The *explanation* is worth keeping —
A-13 is a good story about a named statistic computed wrongly — but a repository should
not carry code it does not run. The comment is six lines now, states the correction and
points at the register; the dead lines are gone.

**Behaviour.** Unchanged. `_not_yet` had no caller; the other edit is a comment.

**Files.** `scripts/run_pipeline.py`, `src/svcarry/evaluation/metrics.py`.

---

## H-07 · Markdown wrapping · **Minor**

Fifteen lines exceeded the ~88-column wrapping every file in the repository otherwise
follows, and the edits above left a further two dozen paragraphs ragged. Both are the
signature of prose edited by replacement rather than in an editor, and both are visible
in a diff.

Reflowed. Blocks containing URLs, tables, code fences, headings or multi-item lists were
left alone — the one attempt to reflow a list collapsed the report's table of contents
into a paragraph and was reverted.

**Validation.** A structural comparison against the previous commit confirms heading
counts, table-row counts, code fences and link targets are unchanged in every file. The
single table-row difference is the eleven-row environment probe removed under H-05.

---

## H-08 · Two quoted numbers nothing checked · **Minor**

The project's own standard is that a number in prose must be pointable to a table. Two
were not.

- **The grid's size.** "144 specifications" appears in the README, the one-page summary,
  the report and now the pre-registration. `specification_distribution.csv` has 144 rows
  and nothing compared the two.
- **The first data retrieval.** `2026-09-20T08:30:04Z`, and the "50 minutes" derived from
  it, appear in four documents and carry the pre-registration claim. The value is in the
  manifest; nothing read it back.

Both are asserted now in `check_results_numbers.py`, which also names
`preregistration.md` among the documents it covers.

**Behaviour.** The script gains two checks and a `json` import. It passes.

**Files.** `scripts/check_results_numbers.py`.

---

## H-09 · Stale README phrasing · **Minor**

"Full record: `docs/validation.md` (populated as each phase runs)" — a note written while
the file was being filled, on a finished project. Replaced with what the file actually
contains: thirty-seven checks, each with its proposition, its test and its result.

The environment paragraph was also rewritten. It said "the environment used to build this
repository could not reach the data hosts or PyPI through its egress proxy", which reads
as an apology for a constraint that produced two of the repository's better properties.
It now says so.

**Files.** `README.md`.

---

## H-10 · GitHub description · **Minor**

The repository had no description or topics, so its GitHub page gave a reader nothing
before they opened the README. Text supplied to the author to paste; not settable from
here.

---

## 11. Validation

Run before any change and again after all of them, from the same raw data.

| | Before | After |
|---|---|---|
| Test suite | 264 passed, 2 skipped | 264 passed, 2 skipped |
| Tables | 42 | 42, **byte-identical** |
| Figures | 24 | 24, **byte-identical** |
| Processed datasets | 8 | 8, **byte-identical** |
| `check_results_numbers.py` | passes | passes, with two more checks |
| `make verify` (re-hash 338 raw files) | manifest clean | manifest clean |
| Broken links and repository paths | — | 0 |
| Mentions of "prompt" outside `prompts/` | 91 | 1, an ordinary English verb (this file aside) |

And the check that matters most after deleting 35 files: a fresh `git clone` of the final
state, with the raw data restored and nothing else changed, runs the suite at 264/2 and
reproduces **all 42 tables, all 24 figures and all 8 processed datasets byte-identically**.
`git status` afterwards names one file, `reports/_pipeline_state.json`, which records when
the run happened. Nothing in the repository depended on anything removed from it.

Byte-identity was established by hashing every output before the first change and
comparing after the last. The headline figures are therefore unchanged and are not
restated here: `docs/results.md` holds them.

**What this pass did not do.** It did not re-derive the research. The recursive audit in
`final_audit_issue_register.md` is the record of that, and nothing here supersedes it.
H-03 and H-04 are corrections in its territory that it missed, and they are recorded as
such rather than folded into a tidying note.
