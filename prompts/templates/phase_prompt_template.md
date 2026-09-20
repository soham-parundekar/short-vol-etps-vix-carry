# Phase NN — <title>

> Template. Copy to `prompts/phases/NN_<slug>.md` and fill every section. A section
> that does not apply is marked "not applicable, because ..." rather than deleted, so
> that a reader can tell the difference between "considered and irrelevant" and
> "forgotten".

## 1. Objective

One paragraph. What must be true at the end of this phase that is not true now?
State the outcome, not the activity.

## 2. Context

Everything an agent starting cold needs to know to execute this phase correctly:
the project's subject, where this phase sits in the chain, the decisions already
taken that constrain it, and the conventions in force (sample window, in/out-of-sample
split, timing rules, units).

## 3. Inputs

- Files that must already exist, with their paths
- Upstream decisions and where they are recorded
- Configuration keys consumed from `config/config.yaml`
- Assumptions inherited from earlier phases, stated explicitly

## 4. Tasks

Numbered, sequential, small enough that each is unambiguously done or not done.
Include the steps that are easy to skip: creating the directory, recording the
decision, updating the log.

## 5. Tools and methods

Libraries, modules in this repository, statistical methods, data sources. Name the
specific function where one already exists, so the phase extends the codebase rather
than duplicating it.

## 6. Execution instructions

What the agent does independently: research, write, run, debug, revise, document,
commit. State explicitly where a decision may be taken without asking, and the narrow
cases where it may not.

## 7. Validation criteria

**Mandatory.** For every meaningful output, define:

| Check | Pass | Warning | Failure |
|---|---|---|---|
| ... | ... | ... | ... |

Numbers where numbers are possible. "Looks reasonable" is not a criterion.

## 8. Self-review

Before declaring the phase complete, actively look for:

- errors in the financial logic (units, sign, timing, fees)
- data problems (gaps, duplicates, stale values, survivorship)
- look-ahead in anything used to make a decision at time *t*
- overfitting, and parameters chosen after seeing the result
- results that are suspiciously good
- documentation that no longer matches the code

For each, state what was checked and what was found — including "checked, nothing
found", which is information.

## 9. Deliverables

Exact paths of every file, table, figure and documentation update expected.

## 10. Git requirements

- What to commit; what must **not** be committed (raw data, secrets, large binaries)
- The commit point and a message that states what changed and why
- Whether to push, and how the push is verified

## 11. Completion gate

A checklist. Every box must be tickable with evidence, not opinion.

- [ ] ...

## 12. Handoff

What the next phase consumes: files produced, decisions taken, assumptions made,
and anything left unresolved that the next phase must not assume away.
