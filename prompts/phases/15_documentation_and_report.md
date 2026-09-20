# Phase 15 — Documentation and report

## 1. Objective

Make the project understandable and reproducible by someone who has never spoken to
its author, and write the report that states what was found.

## 2. Context

The repository is the deliverable as much as the report is. A reader arriving at it
should be able to establish, within a few minutes, what question was asked, what was
found, how confident they should be, and how to run it themselves.

## 3. Inputs

Everything. Particularly `docs/results.md`, the tables, the figures and the figure
index.

## 4. Tasks

1. Write `README.md`: title, research question, motivation, key findings **with
   numbers**, methodology summary, data sources, repository map, installation,
   how to obtain the data, how to run, how to reproduce, main outputs, limitations,
   references.
2. Write `docs/methodology.md`: every formula as implemented, every convention, every
   parameter and where it is set. This is the document that lets a reader check the
   code against the intent.
3. Complete `docs/validation.md` and `docs/limitations.md`.
4. Write the report: 8–10 pages covering introduction and motivation, institutional
   background and the filings, data, methodology, results, robustness, discussion,
   limitations, conclusion, references.
5. Write the one-page summary: question, method, three findings, one caveat.
6. Reconcile every number in the report and the README against the committed tables.
7. Update the prompt pack wherever execution diverged from the prompt, and log each
   divergence.
8. Complete `docs/project_log.md` through to the present.

## 5. Tools and methods

Markdown throughout unless a typeset PDF is required. Figures referenced from
`reports/figures/`. No number typed by hand that exists in a table.

## 6. Execution instructions

Write the key findings section first, in three sentences, before writing anything
else. If that section cannot be written clearly, the project is not finished.

State findings with their uncertainty in the same sentence. "Out-of-sample Sharpe of
0.62 (standard error 0.31)" rather than "Sharpe of 0.62".

The README's key findings must match `docs/results.md` exactly. Two documents drifting
apart is the most common inconsistency in a research repository and the easiest for a
reviewer to spot.

Describe what the project does not establish in the README, not only in the report.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Reproducibility | a clean clone + documented steps regenerates every result | one manual step, documented | undocumented manual step |
| Number consistency | every number in README and report matches a table | — | any mismatch |
| Findings consistency | README, report and `docs/results.md` agree | wording differs | substance differs |
| Completeness | every document in the design's deliverable list exists | — | a missing document |
| Secrets | no key, token or credential anywhere | — | any |
| Prompt alignment | prompts match what was done | minor drift, noted | substantive divergence undocumented |
| Report length | 8–10 pages | ±2 pages | padded or truncated |

## 8. Self-review

- Clone the repository into a clean directory and follow the README literally. Note
  every place it fails.
- Pick five numbers at random from the README and trace each to its table.
- Does the README's limitations section name the actual weaknesses, or generic ones?
- Would a reader who disagreed with the conclusion be able to find the evidence to
  argue with?

## 9. Deliverables

- `README.md`
- `docs/methodology.md`, `validation.md`, `limitations.md`, `results.md`,
  `project_log.md`
- `reports/report.md` (and a PDF if required)
- `reports/summary_one_page.md`
- Updated prompt pack

## 10. Git requirements

Commit all documentation. Commit message states that documentation is complete and
names the report. Push.

## 11. Completion gate

- [ ] README complete, with numeric key findings
- [ ] Methodology documents every formula and parameter
- [ ] Clean-clone reproduction attempted and its result recorded
- [ ] Every number traced to a table
- [ ] Report and one-pager written
- [ ] Prompt pack updated; divergences logged
- [ ] No secrets committed

## 12. Handoff

Phase 16 audits everything produced here.
