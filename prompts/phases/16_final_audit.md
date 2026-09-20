# Phase 16 — Final quality audit

## 1. Objective

Review the finished project from five independent perspectives, attempt a clean-room
reproduction, and record the findings honestly — including the ones that are not
fixed.

## 2. Context

The audit is adversarial by design. Its purpose is to find what a sceptical reader
would find, first, so that the repository either fixes it or discloses it. A final
audit that concludes everything is fine has not been an audit.

## 3. Inputs

The entire repository, at the commit intended to be final.

## 4. Tasks

### A. Finance

- Are returns, fees, accruals and leverage handled correctly and consistently?
- Are units and signs right everywhere? Check by hand: one index return, one product
  NAV step, one strategy day, one flow figure.
- Is the accounting internally consistent — is the collateral credited exactly once?
- Are the product terms as filed?
- Is the treatment of the February 2018 de-levering right, and at the right date?

### B. Quantitative research

- Is each estimator appropriate for the data it is applied to?
- Is inference correct given overlapping horizons, serial correlation and fat tails?
- Is the in/out-of-sample discipline real, and demonstrable from the commit history?
- Is multiple testing accounted for?
- Are the conclusions supported at the confidence stated?

### C. Software

- Does the test suite pass from a clean checkout?
- Is every non-trivial function tested, and do the tests test behaviour rather than
  restate the implementation?
- Are parameters in configuration rather than hard-coded?
- Is randomness seeded?
- Is there dead code, duplicated logic, or a module that no longer matches its
  docstring?

### D. Data

- Is every source documented, cited and reachable?
- Is the manifest complete and verified?
- Are cleaning decisions documented with counts?
- Are survivorship and look-ahead addressed with evidence rather than assertion?
- Is anything redistributed that should not be?

### E. Academic presentation

- Does the repository read as serious quantitative research?
- Is the contribution stated relative to prior work?
- Are limitations honest and specific?
- Would this stand up to a question from someone who knows the area?

### F. Clean-room reproduction

- Clone into a fresh directory, follow the README exactly, run the pipeline end to
  end, and diff the regenerated outputs against the committed ones. Record every
  discrepancy, including ones attributable to data vintage.

## 5. Tools and methods

The test suite, `verify_manifest()`, a fresh clone, and a careful reading.

## 6. Execution instructions

Write the findings before fixing anything, so the audit records what the project
looked like when it was declared finished.

Classify each finding: **critical** (invalidates a conclusion), **material** (changes a
number), **minor** (cosmetic or stylistic), **disclosed** (a real weakness that is
documented rather than fixed).

Fix critical and material findings and re-run the affected analysis. Disclose the rest.
Do not quietly fix something and leave the audit saying it was fine.

If a conclusion does not survive the audit, change the conclusion.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Test suite from clean checkout | all pass | a documented skip | any failure |
| Manifest | verifies with no problems | — | any mismatch |
| Clean-room reproduction | outputs match, or differences explained by data vintage | one unexplained minor difference | material unexplained difference |
| Critical findings | none open | — | any open |
| Material findings | fixed and re-run, or disclosed with impact quantified | — | present and undisclosed |
| Secrets | none | — | any |
| Consistency | code, documentation and prompts agree | minor drift noted | substantive disagreement |

## 8. Self-review

- Was the audit adversarial, or a checklist ticked?
- Which finding was the most uncomfortable, and was it fully pursued?
- Is there anything known to be weak that has not been written down?
- If a reviewer spent an hour on this repository looking for the flaw, what would they
  find — and is it in `docs/limitations.md`?

## 9. Deliverables

- `docs/final_audit.md` — findings under all six headings, each classified, with the
  action taken
- Any fixes, in their own commits
- Updated `docs/limitations.md`

## 10. Git requirements

Fixes go in separate commits referencing the audit finding. The audit document is
committed last. Push, and verify the push.

## 11. Completion gate

- [ ] All six perspectives audited
- [ ] Findings written before fixes
- [ ] Every finding classified
- [ ] Critical and material findings resolved or disclosed with quantified impact
- [ ] Clean-room reproduction attempted and recorded
- [ ] Test suite passes from a clean checkout
- [ ] Manifest verified
- [ ] Conclusions revised where the audit required it
- [ ] `docs/final_audit.md` committed and pushed

## 12. Handoff

The project is complete when this gate is fully ticked — not when the code runs, not
when the repository exists, and not when the figures look good.
