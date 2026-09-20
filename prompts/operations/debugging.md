# Operation — Debugging

## When to run

When something raises, when a number looks wrong, or when a result looks *right in a
way it should not*. The last case is the important one: an implausibly good result is
a bug report.

## Inputs

The failing command or the suspicious number, and the smallest input that reproduces
it.

## Procedure

1. **Reproduce deterministically.** Fix the seed, fix the date range, and reduce the
   input until the problem still occurs on the smallest possible case. Most bugs
   become obvious at this step.
2. **Read the actual error.** The bottom of the traceback is where the symptom is; the
   cause is usually several frames above it.
3. **State a hypothesis before changing anything.** "The roll weight is applied a day
   late" is a hypothesis. "Something is wrong with the index" is not.
4. **Test the hypothesis cheaply.** Print the three or four values that would
   distinguish it from the alternatives. Do not fix and re-run hoping.
5. **Check the boundary first.** A large share of bugs in time-series code live at the
   first observation, the last observation, or a regime change date.
6. **Check units and signs second.** The next largest share.
7. **Once found, write the failing test first,** then fix, then confirm the test passes
   and the whole suite still does.
8. **Ask what else the same mistake would have affected.** A sign error in one place is
   usually a sign error in three.

## For a suspicious *result* rather than an error

- Recompute one value by hand, from the raw inputs, on paper
- Compare against an independent implementation, even a crude one
- Check the sample: is it the period you think it is, with the number of rows you
  expect?
- Check for a leak with `tasks/lookahead_audit.md`
- Check whether one observation drives it: drop the largest and recompute

## What counts as done

The cause is understood — not merely that the symptom has gone. A change that makes an
error disappear without an explanation of why it occurred is not a fix, and the bug
will come back in another form.

A regression test exists.

## Escalation

- Bug in code that produced a committed result: log it in `docs/project_log.md` with
  what was wrong, why it mattered, the fix, and how the fix was validated
- Bug that changes a conclusion: additionally revise the conclusion and note the
  revision in the report
- Cannot reproduce after reasonable effort: record the conditions under which it
  appeared rather than pretending it did not happen
