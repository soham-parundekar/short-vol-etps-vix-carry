# Task — <title>

> Template for a sub-task within a phase. Shorter than a phase prompt, but the
> validation section is not optional here either.

## Parent phase

`prompts/phases/NN_<slug>.md`

## Objective

One or two sentences.

## Why this is a separate task

What makes it worth isolating: it is error-prone, it is reused across phases, or the
decision it produces needs to be recorded independently of the phase that consumes it.

## Inputs

Files, config keys, upstream decisions.

## Procedure

1. ...
2. ...

## Decision rule

If this task produces a *choice* rather than a number, state in advance how the choice
is made and what evidence settles it. This is what prevents the decision from being
made after seeing which option gives the nicer result.

## Validation

| Check | Pass | Failure |
|---|---|---|

## Output

Where the result is written, and in what form.

## Record

Where the decision and its justification are recorded (`docs/validation.md`,
`docs/project_log.md`, or a table in `reports/tables/`).
