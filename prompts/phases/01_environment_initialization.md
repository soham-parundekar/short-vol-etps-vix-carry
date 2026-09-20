# Phase 01 — Environment and repository initialisation

## 1. Objective

Establish a working execution environment and a clean repository, and — crucially —
**determine what the environment can and cannot do before any analysis depends on
it**. The phase ends when the topology is known: where code runs, where data can be
fetched from, where the repository lives, and which of these require someone's
intervention.

## 2. Context

This project reconstructs a VIX futures index from Cboe data, analyses the mechanics
of leveraged and inverse volatility ETPs, and backtests a crash-budgeted short
volatility strategy. It needs: Python with the scientific stack, outbound HTTPS to
Cboe / Yahoo / FRED / SEC, git, and a GitHub remote.

None of those can be assumed. Execution environments differ in which hosts they can
reach and which packages they can install, and discovering a restriction three hours
into a data pipeline is expensive. Probe first.

## 3. Inputs

- The project folder (may be empty; inspect before writing anything)
- The GitHub account whose style the repository should match
- Nothing else

## 4. Tasks

1. Inspect the project folder recursively. Record what is already there. Do not
   delete, overwrite or restructure anything whose contents are not understood.
2. Probe the Python environment: version, and which of numpy, pandas, scipy,
   matplotlib, statsmodels, arch, yfinance, pytest are importable.
3. Probe package installation: attempt one install and record the outcome. A refusal
   from an organisation egress policy is a fact about the environment, not a problem
   to route around.
4. Probe outbound network **per host**, not in general. At minimum:
   `cdn.cboe.com`, `query1.finance.yahoo.com`, `fred.stlouisfed.org`, `www.sec.gov`,
   `github.com`. Record the status code for each.
5. Probe every additional execution surface available (a shell on the user's own
   machine, a browser, a file bridge) and record what each can do.
6. Inspect the GitHub account's existing repositories and infer the naming
   convention. Choose a repository name consistent with it.
7. Create the repository skeleton, `.gitignore`, licence, `pyproject.toml`,
   `requirements.txt`.
8. Decide the execution topology in writing: where code runs, where data lands, where
   the repository of record lives, and what must be mirrored where.
9. Initialise git, configure identity, make the first commit.

## 5. Tools and methods

Shell probes (`curl -o /dev/null -w "%{http_code}"` per host), Python imports, `git`,
the GitHub REST API for account inspection. Nothing project-specific yet.

## 6. Execution instructions

Do all of the above without asking. Ask only where the environment genuinely blocks
progress and the unblocking action belongs to someone else — network policy, repository
creation permission, credentials. When asking, state exactly what is blocked, what the
options are, and which one is recommended, then continue with everything that is not
blocked rather than waiting.

If packages cannot be installed, do not treat the missing library as a wall. Estimators
that a library would have provided can be implemented directly; say so explicitly in
the repository so a reader knows the choice was deliberate.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Folder inspected | recursive listing recorded | — | anything written before inspecting |
| Package probe | every needed import classified present/absent | one absent with a workaround | absent with no workaround and no note |
| Host probe | status code recorded per host | some hosts blocked, workaround identified | "the network works" recorded without per-host evidence |
| Repo name | matches the account's existing convention | minor deviation, justified | invented style |
| `.gitignore` | excludes raw data, secrets, build artefacts, notebooks' checkpoints | — | any of those committable |
| First commit | exists, message describes the state | — | no commit |

## 8. Self-review

- Did anything get written into the project folder before it was inspected?
- Is any credential, token or key present in a tracked file? Grep for likely patterns.
- Is the topology decision recorded somewhere durable, or only in a chat message?
- Would a reader of the repository be able to tell which environment constraints
  shaped the design?

## 9. Deliverables

- Repository skeleton with `src/`, `tests/`, `docs/`, `data/{raw,interim,processed}/`,
  `config/`, `scripts/`, `prompts/`, `reports/`, `references/`
- `.gitignore`, `LICENSE`, `pyproject.toml`, `requirements.txt`
- `docs/project_log.md` opened with the environment findings
- First git commit

## 10. Git requirements

Commit the skeleton and configuration. Do **not** commit: any data, any token,
`.env`, virtual environments, `__pycache__`. Message states what the repository is
and what the environment probe found.

## 11. Completion gate

- [ ] Existing folder contents inspected and recorded
- [ ] Python and package availability recorded
- [ ] Per-host network reachability recorded
- [ ] GitHub account inspected; repository name chosen and justified
- [ ] Skeleton created; `.gitignore` covers data and secrets
- [ ] Execution topology written down
- [ ] First commit made
- [ ] Any blocker stated precisely, with the action needed and from whom

## 12. Handoff

Phase 02 needs: the environment constraints (which hosts are reachable, which
packages are available), because they determine whether filings can be fetched
directly or must be read through another channel; and the repository path.
