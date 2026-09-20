# Phase 03 — Research design

## 1. Objective

Turn the topic into a small number of falsifiable hypotheses, each with a stated
rejection criterion, and fix the sample, the in/out-of-sample split and the test plan
**before** any result is computed. The point of doing this now is that it is the only
moment at which these choices can be made without knowing which choice flatters the
answer.

## 2. Context

Phase 02 established what is known. The topic — short-volatility ETPs, VIX and
volatility carry — admits many projects, most of them descriptive. This phase selects
among them.

The selection criteria, in order: does the question have an answer that could come out
either way; can it be answered with free data; does answering it require real
quantitative work rather than plotting; and is the result interesting whichever way it
falls.

## 3. Inputs

- `docs/literature_review.md`
- `config/filings.yaml` (product terms)
- Data feasibility as understood so far (refined in Phase 04; revisit if it changes)

## 4. Tasks

1. Enumerate at least four candidate research questions and evaluate each against the
   criteria above. Record the rejected ones and why — a design document that shows
   only the chosen path hides the reasoning.
2. Select and refine the primary question.
3. Decompose it into sub-questions, each mapped to a specific empirical test.
4. State each hypothesis with (a) what it predicts and (b) **what observation would
   reject it**. A hypothesis with no rejection criterion is not a hypothesis.
5. Fix: sample start and end and the reason; the design window in which parameters may
   be chosen; the held-out window in which they may not; and any second estimation
   window needed to make an *ex ante* claim genuinely ex ante.
6. Specify methodology per sub-question: estimator, identification, benchmark, metric.
7. Specify the robustness plan: which parameters are swept, which alternative
   specifications are run, which subsamples, which stress windows.
8. Enumerate the design's own principal risks and the mitigation each one gets.
9. Write `docs/research_question.md` and `docs/research_design.md`.

## 5. Tools and methods

None computational. This phase is written, not run. The output is a commitment.

## 6. Execution instructions

Choose the design without asking. The only decision that warrants asking is one that
depends on the researcher's own purpose and cannot be inferred — and a question about
scope or emphasis is usually inferable from the project's stated objective.

Write the hypotheses so that at least one of them is uncomfortable. A design in which
every hypothesis predicts the flattering outcome is a design that will find it.

State explicitly what the project will **not** claim — causality, implementability,
prediction — so that the interpretation phase has a standard to be held to.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Hypotheses | each has an explicit rejection criterion with a number where possible | one criterion qualitative | any hypothesis unfalsifiable |
| Sample | start, end and split fixed with stated reasons | — | split chosen to include or exclude a known event |
| Out-of-sample | held-out window contains events not used in design | — | parameters chosen after seeing the held-out period |
| Ex-ante claims | a separate estimation window ending before the event | — | an "ex ante" probability estimated on data including the event |
| Alternatives | rejected candidate questions recorded | — | only the chosen path shown |
| Risks | each risk has a mitigation that is actually implementable | a risk with a weak mitigation, acknowledged | a known risk omitted |

## 8. Self-review

- Could every hypothesis come out the other way? If not, which one is rigged?
- Is any parameter in the design chosen because of something already observed in the
  data?
- Does the out-of-sample window really contain events the design window does not?
- Is the contribution stated relative to Phase 02's findings, or in isolation?
- Are the "will not claim" statements ones the project could actually be held to?

## 9. Deliverables

- `docs/research_question.md`
- `docs/research_design.md` — hypotheses, data plan, methodology, validation plan,
  expected outputs, risks, reproducibility plan

## 10. Git requirements

Commit both documents in one commit whose message states the primary question and the
split. This commit is the timestamp on the pre-registration; everything after it is
constrained by it.

## 11. Completion gate

- [ ] At least four candidate questions considered; rejections recorded
- [ ] Primary question stated in one sentence
- [ ] Every hypothesis has a rejection criterion
- [ ] Sample, design window and held-out window fixed with reasons
- [ ] A separate pre-event estimation window defined for any ex-ante claim
- [ ] Robustness plan enumerated before any result exists
- [ ] Risks and mitigations written
- [ ] Explicit list of what the project will not claim

## 12. Handoff

Phase 04 needs the dataset list implied by the methodology, the sample window, and the
frequency required. Later phases need the hypotheses and their rejection criteria,
which they are not free to revise after seeing results — a revision, if genuinely
warranted, is logged in `docs/project_log.md` with its reason and is disclosed in the
report.
