# Operation — Verify a push

## When to run

Immediately after every `git push`.

## Why

Because the only thing worse than a failed push is believing a push succeeded. Exit
codes are not always the whole story: a proxy can refuse, a remote can reject, a
branch can diverge, and a partial transfer can leave the remote behind the local
history. Never report a push as done without checking.

## Inputs

The local repository and the remote URL.

## Procedure

- [ ] Read the push output in full, not just the last line
- [ ] `git ls-remote origin` — confirm the remote head matches the local head
- [ ] `git log origin/main -1 --oneline` — confirm it is the commit just made
- [ ] `git status` — confirm the branch is not ahead of its upstream
- [ ] If the remote is public, open the repository page and confirm the commit and the
      file list appear
- [ ] Confirm the remote does not contain anything that should not have been pushed

## What counts as done

The remote head hash equals the local head hash, confirmed by a command whose output
was read.

## Escalation

- **Authentication or authorisation refused.** Report the exact error, name the
  repository and what access is missing, and say what is needed and from whom. Do not
  retry the same command hoping for a different result, and do not work around an
  access control
- **Non-fast-forward.** Fetch, inspect the divergence, and reconcile deliberately.
  Never force-push shared history
- **Large file rejected.** The file belongs in `.gitignore` and should be regenerated
  from the pipeline; add it, rewrite the commit, and push again
- **Push genuinely impossible in this environment.** Say so plainly, produce a
  transferable artefact — a `git bundle` preserves the full history — and give the
  exact commands to publish it from elsewhere. Never describe unpushed work as pushed
