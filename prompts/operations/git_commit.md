# Operation — Create a commit

## When to run

At a meaningful project state: a phase completed, a component working and tested, a
bug fixed, a methodology revised. Not on a schedule, and never to raise a commit
count.

## Inputs

The working tree, and the change it represents.

## Procedure

**Before staging**

- [ ] `git status` — understand everything that changed, including files you did not
      expect
- [ ] `git diff` — read it
- [ ] Run the full test suite; it must pass
- [ ] Run `operations/code_review.md` if analysis code changed

**Staging**

- [ ] Stage deliberately. Not `git add -A` without looking at what that includes
- [ ] Confirm nothing under `data/raw/` or `data/interim/` is staged unless the
      licensing decision permits it
- [ ] Confirm no `.env`, key, token or credential — grep for the usual patterns
- [ ] Confirm no large binary that should be regenerated instead
- [ ] `git diff --staged` once more

**The message**

Subject line: what changed, imperative or declarative, under about 70 characters.

Body: what changed and **why**; what was validated and how; anything a future reader
would need to know to understand the state. Numbers where they exist — test counts,
tracking error, a Sharpe ratio — so the history carries the evidence.

Do not describe the diff. The diff is in the commit.

**After**

- [ ] `git log --stat -1` — confirm the commit contains what was intended
- [ ] Push if the state is coherent, following
      `operations/github_push_verification.md`

## What counts as done

A commit representing a state the project could be left in. If it needs a follow-up
commit to be coherent, it was committed too early.

## Escalation

- Tests failing: do not commit. Fix, or commit to a branch and say so in the message
- Something unexpected in `git status`: understand it before staging it
- A secret already committed in an earlier commit: stop, rotate the credential, and
  rewrite history before pushing. Removing it in a later commit does not remove it
