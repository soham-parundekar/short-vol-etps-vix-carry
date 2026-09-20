# Phase 12 — Robustness and red-team

## 1. Objective

Try to break every conclusion the project has reached, and report what survives and
what does not. The output is not reassurance; it is a map of where the evidence is
strong and where it is fragile.

## 2. Context

By this point the project has four kinds of claim: a reconstruction claim, a mechanics
claim, a tail/survival claim, and a strategy claim. Each rests on choices that could
have been made differently. A robustness section that sweeps parameters and reports
that everything holds is usually a section that swept the wrong parameters.

The useful question is not "does the result survive small perturbations" but "what is
the smallest change to the setup that reverses it, and is that change reasonable?"

## 3. Inputs

Everything produced by Phases 07–11, plus `config/config.yaml` → `robustness.*`.

## 4. Tasks

**Sweeps.** Transaction costs 0–4 ticks; contango threshold; volatility target; stress
loss budget (including the value at which the crash constraint never binds, which
recovers plain volatility targeting); rebalance frequency 1/5/21 days; EVT threshold
grid; HAR horizon and lag structure; roll convention; carry definition.

**Subsamples.** The four configured periods, plus a leave-one-year-out sweep of the
out-of-sample window. Report the full distribution of outcomes, not the mean.

**Alternative constructions.** The calendar-spread variant of the strategy; the
constant-maturity index as an alternative to the rolled one; the `VIX/VIX3M` slope
instead of `cm30/cm90`.

**Red-team questions**, each answered with a number:

1. What is the single weakest assumption, and what happens if it fails?
2. Could look-ahead explain the strategy result? (Compare against the leaky variant
   and re-audit the chain.)
3. Could survivorship explain anything? XIV is in the product sample for its whole
   life — confirm, and check nothing else was dropped.
4. At what transaction cost does the out-of-sample Sharpe reach zero?
5. Does one period dominate? Recompute every headline with each stress window
   excluded in turn.
6. Does one day dominate the tail result? (Jackknife from Phase 09.)
7. Is the result an artefact of parameter selection? Report the distribution of
   out-of-sample Sharpe across the entire parameter grid, and state where the chosen
   configuration sits in that distribution.
8. Would the conclusion survive the asset-outstanding bounds moving to their extremes?
9. Is the economic interpretation supported, or is it a story fitted to the numbers?

**Multiple testing.** Count the specifications actually run and report the best and
median out-of-sample Sharpe across them alongside the chosen one. The gap between the
best cell and the median is the honest measure of how much selection could explain.

## 5. Tools and methods

The existing pipeline, parameterised from configuration. No new estimators.

## 6. Execution instructions

Run the sweeps programmatically from configuration so that the grid is visible in the
repository rather than described in prose.

Report the full grid. A robustness table that shows only the cells that worked is
worse than no robustness table, because it creates false confidence.

Where a conclusion does not survive, say so plainly and revise the claim in
`docs/research_design.md` and the report. A hypothesis rejected by its own stated
criterion is a result.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Grid completeness | every configured sweep run and reported | one sweep omitted with a reason | selective reporting |
| Chosen vs grid | chosen configuration near the median, not the maximum | upper quartile | the maximum of the grid |
| Cost breakeven | reported explicitly in ticks | — | not computed |
| Period dominance | no single stress window accounts for more than half the total return | 50–75% | > 75% without disclosure |
| Tail jackknife | headline moves < 50% | 50–200% | > 200% |
| Claim revision | any failed hypothesis revised in the design document | — | a failed hypothesis quietly dropped |

## 8. Self-review

- Were any of these checks run earlier, found inconvenient, and not repeated here?
- Is there a specification that was tried during development and is not in the grid?
  It belongs in the count.
- Does the interpretation change at any point in the grid? If so, the headline should
  be conditional.
- Is the "smallest change that reverses the result" actually small?

## 9. Deliverables

- `reports/tables/robustness_costs.csv`, `robustness_parameters.csv`,
  `robustness_subsamples.csv`, `specification_distribution.csv`
- `reports/figures/cost_sensitivity.png`, `parameter_heatmap.png`,
  `subsample_stability.png`
- `docs/validation.md` — every validation performed, with results
- `docs/limitations.md` — what the project cannot establish and why

## 10. Git requirements

Commit sweeps, tables, figures and both documents. Commit message states which
conclusions survived and which did not — especially which did not.

## 11. Completion gate

- [ ] Every configured sweep run
- [ ] Leave-one-period-out completed
- [ ] All nine red-team questions answered with numbers
- [ ] Specification count and distribution reported
- [ ] Cost breakeven computed
- [ ] Failed conclusions revised, not dropped
- [ ] `docs/validation.md` and `docs/limitations.md` written

## 12. Handoff

Phase 13 consumes the robustness results and must state every conclusion at the
confidence the robustness supports — not at the confidence the baseline suggested.
