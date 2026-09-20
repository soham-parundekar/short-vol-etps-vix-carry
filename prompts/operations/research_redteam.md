# Operation — Red-team a finding

## When to run

Before any finding is written into the report, the README or a summary. Once per
finding, not once per project.

## Inputs

The finding as it would be stated, and every number behind it.

## Procedure

Argue against the finding as though being paid to. For each question, produce a
number, not an opinion.

**1. What is the weakest assumption this rests on?**
Name it. What happens to the finding if it fails? Compute that.

**2. Could look-ahead produce this?**
Run `tasks/lookahead_audit.md`. Compare against the deliberately leaky variant: if the
honest result is close to the leaky one, something is wrong.

**3. Could survivorship produce this?**
What was excluded from the sample, and why? Was anything dropped for being
short-lived, terminated, or hard to obtain?

**4. Could transaction costs eliminate it?**
At what cost level does the result reach zero? Is that level plausible for this
instrument in a crisis, when the position would actually need to trade?

**5. Does one period produce it?**
Recompute with each stress window excluded in turn. Recompute leaving out each year.
Report the distribution, not the mean.

**6. Does one observation produce it?**
Drop the largest. Then the largest three.

**7. Is it a selection artefact?**
How many specifications were run in total, including during development? Where does
the reported one sit in the distribution of all of them? If it is the best cell, say
so.

**8. Is there a mundane explanation?**
Data error, look-ahead, a unit mistake, a benchmark that is unfairly weak, a period
that happens to suit. Rule each out explicitly before reaching for the interesting
explanation.

**9. Is the economic story supported, or fitted?**
Would the same story have been told if the sign had come out the other way? If yes,
it is not evidence.

**10. What would change your mind?**
State the observation that would overturn the finding. If none exists, the finding is
not empirical.

## What counts as done

All ten answered with numbers, written into `docs/validation.md`. A question answered
"not applicable" carries a reason.

## Escalation

- The finding does not survive: change the finding. This is the normal outcome of a
  working red-team and is not a failure of the project
- It survives but only conditionally: state the condition in the claim itself, in the
  same sentence, not in a later caveat
- It survives cleanly: say what would overturn it anyway
