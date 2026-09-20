# Operation — Code review

## When to run

Before any commit that changes analysis code: estimators, the reconstruction, the
mechanics, the backtest, or anything that produces a number that appears in a result.

## Inputs

The diff (`git diff --staged`), and the tests that cover the changed code.

## Procedure

**Correctness**

- [ ] Read the diff line by line, not the summary
- [ ] For every formula, check it against the source it implements — the filing, the
      methodology document, or the paper. Not against memory
- [ ] Check units and signs. Returns simple or log? Volatility daily or annualised?
      Variance or standard deviation? Percent or decimal? Short position positive or
      negative?
- [ ] Check timing: does anything use information from date `t` to make a decision
      dated `t`?
- [ ] Check boundaries: the first observation, the last, an empty input, a single row,
      an all-NaN column

**Data handling**

- [ ] Is any missing value silently filled or dropped? If so, is it counted?
- [ ] Does any operation depend on the index being sorted, and is that enforced?
- [ ] Does any join silently drop rows? Check shapes before and after
- [ ] Is any DataFrame mutated in place in a way a caller would not expect?

**Structure**

- [ ] Is a parameter hard-coded that belongs in `config/config.yaml`?
- [ ] Is logic duplicated that exists elsewhere in the package?
- [ ] Does every non-obvious financial choice carry a comment explaining *why*, not
      *what*?
- [ ] Does the docstring still describe what the function does?

**Tests**

- [ ] Is the new behaviour tested?
- [ ] Does the test check behaviour, or restate the implementation? A test that would
      pass against a copy of the code it tests is not a test
- [ ] Is there a test that would fail if the change were reverted?

## What counts as done

Every box ticked, the full test suite run and passing, and the diff reviewed in one
sitting. Findings are fixed before the commit, not after.

## Escalation

- A correctness bug affecting a committed result: fix it, re-run the affected
  analysis, and log it in `docs/project_log.md` with what it was worth
- A structural issue: fix it now if small, otherwise open a note in the log
- A disagreement between the code and a documented methodology: the methodology
  wins, or the methodology document is wrong and gets corrected — but never leave
  the two disagreeing
