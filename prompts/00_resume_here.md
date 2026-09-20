# Resume here — handoff to the next session

A new Cowork task starts cold. Paste the block at the bottom of this file into it,
and it will pick the project up exactly where it stopped.

## Why a new task is needed

Two blockers ended the previous session, and both are resolved at task creation
rather than mid-conversation:

1. **Network egress.** Cowork applies network settings *when a session is created*.
   A change made during a running conversation does not affect it. So even after the
   organisation setting is changed, the data pull requires a fresh task.
2. **GitHub write access.** The git proxy injects a credential only for repositories
   in the session's authorised set, which is fixed when the task is created. Pushing
   to `soham-parundekar/short-vol-etps-vix-carry` requires it to be attached as a
   source of the new task.

## State at handoff

- 8 commits, 164 tests (162 pass, 2 skip — the `statsmodels` and `arch` cross-checks)
- Phases 0–4 complete; Phase 5 (acquisition) written but never run
- **No empirical result exists.** Nothing in the repository is reported from data
- Full history in `short-vol-etps-vix-carry.bundle` in the project folder
- Working tree mirrored at `D:\MFE\Projects\Project1_ShortVol_ETPsVIX_Carry`
  (every file except `Makefile`, which the device bridge refuses to write — it is in
  git and in the bundle)

## First actions for the new session

1. Verify egress: `curl -sS -o /dev/null -w "%{http_code}" https://cdn.cboe.com/`
   should return something other than `000`.
2. Verify the remote: `git ls-remote origin` should succeed, then push.
3. `python scripts/fetch_data.py` — roughly 230 VX contract files plus indices,
   prices, rates and filings. Expect a few minutes.
4. `python scripts/run_tests.py` — must be green before anything is built on the data.
5. Then `prompts/phases/06_data_cleaning_validation.md`, followed by
   `prompts/phases/07_index_reconstruction.md`. Phase 07 is the gate: if the
   reconstruction does not track VIXY and VXX within the stated tolerance, stop and
   diagnose rather than proceeding, because every downstream result inherits that
   error.

---

## Paste this into the new task

> Continue Project 1 of my MFE application portfolio: **"When Carry Kills — short
> volatility ETPs, rebalancing feedback and a crash-aware VIX carry strategy."**
>
> The project already exists. Clone or open it and read these first, in order:
> `README.md`, `docs/project_log.md`, `docs/research_design.md`, `prompts/README.md`.
> They contain the full state, the environment history, the five pre-registered
> hypotheses with their rejection criteria, and the phase prompts that drive
> execution.
>
> Repository: `https://github.com/soham-parundekar/short-vol-etps-vix-carry`
> Local folder: `D:\MFE\Projects\Project1_ShortVol_ETPsVIX_Carry`
> Full history also in `short-vol-etps-vix-carry.bundle` in that folder.
>
> Where it stopped: 8 commits, 164 tests (162 pass, 2 skip), phases 0–4 complete, no
> data downloaded and therefore **no empirical results at all**. The previous session
> was blocked on network egress and on GitHub write access; both should now be
> resolved in this task.
>
> Operate under the same terms as before — you are the execution owner, not an
> assistant waiting for instructions. Research first, code second. Validate every
> stage independently rather than assuming a successful run means a correct result.
> Never fabricate data, sources, results or a push. Commit at meaningful milestones
> and push. Keep `docs/project_log.md` current.
>
> Start by verifying egress and the git remote, then run `scripts/fetch_data.py`,
> then execute `prompts/phases/06_data_cleaning_validation.md` and
> `prompts/phases/07_index_reconstruction.md`. Report using the structured format in
> the master prompt: current phase, completed, validation, evidence, issues,
> resolution, current state, next action.
