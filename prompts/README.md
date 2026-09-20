# Prompt pack

This directory is the instructional architecture used to build the project. It exists
for the same reason the code and the data manifest exist: so that the process is
inspectable and repeatable, not just the output.

The intended operating model is

```
master prompt  ->  phase prompt  ->  task prompt(s)  ->  execution
                                            |
                        validation -> self-review -> revision
                                            |
                              git commit -> push -> completion gate
                                            |
                                       next phase
```

Operational prompts sit outside that chain: they are reusable procedures invoked
whenever the situation calls for them (a code review, a debugging session, a commit).

## Conventions

Every phase prompt follows the same twelve-section structure, defined in
`templates/phase_prompt_template.md`: Objective, Context, Inputs, Tasks, Tools and
methods, Execution instructions, Validation criteria, Self-review, Deliverables, Git
requirements, Completion gate, Handoff.

**Validation criteria are mandatory and concrete.** Each phase defines what counts as
pass, warning and failure, with numbers where numbers are possible. A phase is not
complete because its code ran.

**Prompts and implementation must not diverge.** When the methodology changes, the
affected prompt is updated in the same commit as the code, and the change is recorded
in `docs/project_log.md`. If a task turned out to be ambiguous or error-prone in
practice, the prompt that governed it is revised so the same ambiguity does not recur.

## Index

### Phases

| # | Prompt | Purpose | Consumes | Produces | Run |
|---|--------|---------|----------|----------|-----|
| 01 | [`phases/01_environment_initialization.md`](phases/01_environment_initialization.md) | Inspect environment, establish repo, decide execution topology | the project folder, GitHub account | repo skeleton, `.gitignore`, first commit | once |
| 02 | [`phases/02_literature_review.md`](phases/02_literature_review.md) | Understand the mechanism and the prior work; verify the filings | the topic | `docs/literature_review.md`, `references/references.bib`, archived filings | once, revisit on methodology change |
| 03 | [`phases/03_research_design.md`](phases/03_research_design.md) | Turn the topic into falsifiable hypotheses and a test plan | 02 | `docs/research_question.md`, `docs/research_design.md` | once |
| 04 | [`phases/04_data_source_discovery.md`](phases/04_data_source_discovery.md) | Locate and verify every dataset before writing a downloader | 03 | `docs/data_sources.md` | once |
| 05 | [`phases/05_data_acquisition.md`](phases/05_data_acquisition.md) | Build and run the reproducible download pipeline | 04 | `data/raw/**`, `_manifest.json`, fetch summary | once, re-runnable |
| 06 | [`phases/06_data_cleaning_validation.md`](phases/06_data_cleaning_validation.md) | Build the futures panel and prove it is clean | 05 | `data/interim/vx_panel.parquet`, data-quality report | once |
| 07 | [`phases/07_index_reconstruction.md`](phases/07_index_reconstruction.md) | Rebuild the index and validate it against the traded products | 06 | `data/processed/index.csv`, tracking table | once |
| 08 | [`phases/08_etp_mechanics_and_flows.md`](phases/08_etp_mechanics_and_flows.md) | Test the leverage identity; estimate rebalancing flows | 07 | decay table, flow series and figure | once |
| 09 | [`phases/09_tail_model_and_survival.md`](phases/09_tail_model_and_survival.md) | Fit GARCH-EVT; termination probabilities; survival; Kelly | 07 | tail tables, survival curves, Kelly result | once |
| 10 | [`phases/10_forecasting_and_signals.md`](phases/10_forecasting_and_signals.md) | HAR forecasts, VRP and term-structure signals | 06, 07 | signal panel, forecast diagnostics | once |
| 11 | [`phases/11_backtest.md`](phases/11_backtest.md) | Run the crash-aware carry strategy with honest timing and costs | 09, 10 | backtest results, performance tables | once |
| 12 | [`phases/12_robustness_and_redteam.md`](phases/12_robustness_and_redteam.md) | Try to break every conclusion | 08–11 | `docs/validation.md`, `docs/limitations.md`, sensitivity tables | once |
| 13 | [`phases/13_results_and_interpretation.md`](phases/13_results_and_interpretation.md) | Say what the numbers mean, and what they do not | 08–12 | results narrative | once |
| 14 | [`phases/14_visualisation.md`](phases/14_visualisation.md) | Produce the figures that answer questions | 08–12 | `reports/figures/**` | once |
| 15 | [`phases/15_documentation_and_report.md`](phases/15_documentation_and_report.md) | README, methodology, the report itself | all | `README.md`, `docs/methodology.md`, report | once |
| 16 | [`phases/16_final_audit.md`](phases/16_final_audit.md) | Five-perspective audit and clean-room reproduction | all | `docs/final_audit.md` | once |

### Tasks

| Prompt | Belongs to | Purpose |
|--------|-----------|---------|
| [`tasks/verify_filing_terms.md`](tasks/verify_filing_terms.md) | 02, 04 | Re-extract each product term from the archived filing rather than from prose |
| [`tasks/resolve_roll_convention.md`](tasks/resolve_roll_convention.md) | 07 | Choose between roll conventions on evidence and record the decision |
| [`tasks/estimate_product_assets.md`](tasks/estimate_product_assets.md) | 08 | Bound assets outstanding, the weakest input in the project |
| [`tasks/choose_evt_threshold.md`](tasks/choose_evt_threshold.md) | 09 | Pick and defend the peaks-over-threshold level |
| [`tasks/lookahead_audit.md`](tasks/lookahead_audit.md) | 11, 12 | Systematically hunt for information leakage |

### Operations (reusable)

| Prompt | When to run |
|--------|-------------|
| [`operations/code_review.md`](operations/code_review.md) | Before any commit that changes analysis code |
| [`operations/debugging.md`](operations/debugging.md) | When something fails or a result looks wrong |
| [`operations/data_quality_review.md`](operations/data_quality_review.md) | After any change to the data pipeline |
| [`operations/financial_logic_validation.md`](operations/financial_logic_validation.md) | After any change to returns, fees, leverage or costs |
| [`operations/statistical_sanity_check.md`](operations/statistical_sanity_check.md) | After any estimation step |
| [`operations/research_redteam.md`](operations/research_redteam.md) | Before declaring any finding |
| [`operations/git_commit.md`](operations/git_commit.md) | At every milestone |
| [`operations/github_push_verification.md`](operations/github_push_verification.md) | After every push |
| [`operations/session_log.md`](operations/session_log.md) | At the end of every working session |

### Templates

- [`templates/phase_prompt_template.md`](templates/phase_prompt_template.md)
- [`templates/task_prompt_template.md`](templates/task_prompt_template.md)
- [`templates/operation_prompt_template.md`](templates/operation_prompt_template.md)

## Status

Phases 01–05 are written from what was actually executed. Phases 06 onward were
written before execution and are revised in place when execution reveals that the
instruction was not precise enough; each such revision is noted in
`docs/project_log.md` so the difference between plan and practice stays visible.
