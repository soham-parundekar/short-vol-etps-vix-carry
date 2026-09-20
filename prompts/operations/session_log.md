# Operation — End-of-session log entry

## When to run

At the end of every working session, and at every milestone within a long one.

## Inputs

What actually happened. Not what was planned.

## Procedure

Append to `docs/project_log.md`:

```markdown
## YYYY-MM-DD — <short title>

**Objective.** What this session set out to do.

**Completed.** What was actually finished, with evidence: file paths, test counts,
commit hashes.

**Files.** Created and modified.

**Commands.** The ones that matter for reproducing the state or for understanding a
result. Not every shell invocation.

**Results.** Numbers produced, with where they are stored.

**Problems.** What failed, what was surprising, what was blocked and by what.

**Debugging.** What was wrong, why it mattered, how it was fixed, how the fix was
validated.

**Validation.** What was checked, and what the check found — including checks that
found nothing.

**Decisions.** What was decided, the alternatives, and why. A decision recorded
without its alternatives is not auditable.

**Implications.** What this changes about the research: a hypothesis now less likely,
a method that does not work, a limitation discovered.

**Next.** The single next action.
```

## Rules

- Factual. Do not record intent as achievement
- If something did not work, it goes in. The log's value is that it contains the
  failures
- If a number changed, record the old value and the new one, and why
- If a prompt turned out to be imprecise, record it and revise the prompt
- Do not fabricate progress, and do not round a partial result up to a finished one

## What counts as done

The entry is written, committed, and would let someone reconstruct both the state of
the project and the reasoning that produced it.

## Escalation

- Blocked on something external: record what, who can unblock it, and what is being
  done in the meantime
- A decision that changed an earlier one: record both and the reason for the change,
  rather than editing the earlier entry. The log is append-only
