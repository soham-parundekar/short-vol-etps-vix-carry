# Phase 13 — Results and interpretation

## 1. Objective

Say what the numbers mean, in financial terms, at the confidence the evidence
supports — and say clearly what they do not establish.

## 2. Context

Interpretation is where a careful empirical project usually becomes an overclaiming
one. Three specific slippages to guard against:

- **correlation → causation.** The rebalancing-flow result says the mechanical demand
  was large relative to open interest. It does not say the demand caused the move.
- **backtest → expected return.** An out-of-sample Sharpe is an estimate from one
  history of one asset class, with a standard error that is large when the return
  distribution is this skewed.
- **statistical → economic significance.** A significant alpha of 40 bp a year on a
  strategy with a 20% drawdown is not an investment case, and an insignificant alpha
  is a finding rather than a failure.

## 3. Inputs

Every table and figure from Phases 07–12; the hypotheses and rejection criteria from
Phase 03.

## 4. Tasks

1. For each hypothesis, state: what was predicted, what was found, and whether the
   stated rejection criterion is met. Do this before writing any narrative, so the
   narrative cannot quietly reinterpret a rejection.
2. For each material finding, write: what happened, the mechanism consistent with it,
   at least one alternative explanation, and what the data cannot distinguish.
3. Quantify the economic significance of every statistical result.
4. State the headline conclusions with the qualifications the robustness section
   requires attached to them, not in a later paragraph.
5. Write the "what this does not show" section, and make it specific to this project
   rather than generic.
6. Identify the two or three findings that are genuinely informative, and say why.

## 5. Tools and methods

None computational. If a number is needed that does not exist yet, go back and compute
it rather than estimating it in prose.

## 6. Execution instructions

Write the hypothesis verdicts first, mechanically, from the criteria. Then write the
interpretation around them.

Where a result is surprising, say that it is surprising and give the most likely
mundane explanation before the interesting one.

Where the evidence supports a weaker claim than the project set out to make, make the
weaker claim. A correctly hedged null result is a better project than an overstated
positive one, and a reader who can see the hedging trusts the rest.

Attach a number to every claim. "The de-levering materially improved survival" is
weaker than "the five-year survival probability rose from X to Y under the pre-2018
model, a gap stable across the threshold grid".

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Hypothesis verdicts | all stated against the pre-registered criteria | one criterion reinterpreted, disclosed | a criterion silently changed |
| Causal language | no causal claim from an association | hedged causal phrasing | unhedged causal claim |
| Economic significance | reported for every statistical result | — | significance reported alone |
| Alternatives | at least one alternative explanation per major finding | — | none offered |
| Qualification placement | caveats attached to the claim | in a later paragraph | absent |
| Traceability | every number in the text traceable to a table | — | a number that appears only in the prose |

## 8. Self-review

- Read every sentence containing "because", "drove", "caused" or "led to". Is the
  causal claim supported?
- Read every headline number. Can it be pointed to in a committed table?
- Would the interpretation change if the reader saw the full specification grid? They
  will see it.
- Is any hypothesis being treated as confirmed when its criterion was not met?
- Is the null result, if there is one, stated as a finding rather than apologised for?

## 9. Deliverables

- `docs/results.md` — hypothesis verdicts and the interpretation
- Updated `docs/limitations.md`
- The results and discussion sections of the report

## 10. Git requirements

Commit the results document. Commit message states the verdict on each hypothesis in
one line each.

## 11. Completion gate

- [ ] Every hypothesis has a verdict against its pre-registered criterion
- [ ] Every finding has a mechanism and at least one alternative explanation
- [ ] Economic significance quantified throughout
- [ ] Causal language audited
- [ ] Every number traceable to a committed table
- [ ] "What this does not show" written and specific

## 12. Handoff

Phase 14 needs to know which findings carry the argument, so the figures serve them.
Phase 15 consumes the verdicts and the narrative.
