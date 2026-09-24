# Task — Look-ahead audit

## Parent phase

`prompts/phases/10_forecasting_and_signals.md` and `11_backtest.md`; repeated in
`12_robustness_and_redteam.md`.

## Objective

Establish, by test rather than by inspection, that nothing used to make a decision at
time *t* depends on information that was unavailable at time *t*.

## Why this is a separate task

Look-ahead bias is the single most common reason a quantitative backtest is wrong, and
it is rarely introduced deliberately. It arrives through a forward-filled series, a
model fitted on the whole sample, a rolling window that includes the current
observation, a signal computed from a close and traded at the same close, or a
training set whose dependent variable had not yet been realised.

Reading the code for it does not work reliably, because the code usually looks fine.
The audit is therefore mechanical.

## Inputs

Every series that feeds a decision: the variance proxy, the HAR forecast, the VRP, the
slope measures, the volatility estimate, the stress quantile, the weights, and the
backtest output.

## Procedure

**1. The perturbation test.** This is the core of the audit.

For each output series, pick a cutoff date `T`, perturb every input *after* `T` by a
large random amount, recompute, and assert that every output value dated on or before
`T` is **bit-identical**. Not approximately equal — identical. Any difference is a
leak, and its size is irrelevant to whether it is one.

Run this for: the realised-volatility estimate, the HAR forecast, the stress quantile,
the weight series, and the strategy returns.

**2. The timing table.** For every input, record in a table: the date it is indexed by,
**the clock time at which its value is final**, the date and clock time of the price the
decision it informs is executed at, and the date it is first used. Any row where "used"
precedes "available" is a leak. Commit the table.

Three requirements on this table, all of them added after the recursive audit found the
earlier version of it worthless (register A-02, A-05):

*The verdict must be computed, not written.* The first version of this table ended in

    timing["use_precedes_availability"] = False

and was then cited, in `docs/final_audit.md`, as *mechanical* evidence that nothing
leaked. It was a literal. A column that cannot take the value `True` is not a check, and
citing one as evidence overstates the project's rigour. Compare the two times per date,
count the dates on which the comparison fails, and let the pipeline **exit non-zero** if
any count is above zero.

*Dates are not enough; strike times decide it.* Two series dated the same day are not
necessarily observable at the same moment. The VX daily settlement moved from 4:15 p.m.
ET to 4:00 p.m. ET on 26 October 2020 while the VIX cash close stayed at 4:15 p.m. ET, so
from that date a VIX-derived signal used to size a position booked at the settlement is
fifteen minutes of hindsight — on every remaining day of the sample. A date-granular
table cannot see this, and the earlier one did not. Declare each input's strike time and
compare against the execution reference's strike time, which may itself change during the
sample.

*The check must be shown to catch something.* Write a mutation test that removes the
correction and requires the table to report the violation. An audit that has never failed
has not been tested.

Note the same limitation in the perturbation test of step 1: it perturbs inputs by whole
days and therefore cannot detect an intraday overlap either. The two steps are
complementary, and neither alone is sufficient.

**3. The shift test.** Re-run the backtest with `signal_lag` of 0, 1 and 2. The Sharpe
must fall as the lag rises. A lag-0 result that is not dramatically better than lag-1
suggests either that the signal has no short-horizon information at all, or that the
lag is not being applied.

**4. The correlation test.** Correlate each forecast with the contemporaneous realised
value it is forecasting. A forecast correlation approaching what a perfect forecast
would achieve is the signature of a leak.

**5. Parameter provenance.** For each strategy parameter, establish from the commit
history that its value was fixed before the out-of-sample period was examined. A
parameter changed after seeing out-of-sample results is a leak of a different kind and
must be disclosed as such.

## Decision rule

A leak found in the perturbation test is fixed, and the affected analysis is re-run
from that point. It is never noted and carried forward: a backtest with a known leak
has no informational content.

## Validation

| Check | Pass | Failure |
|---|---|---|
| Perturbation | every pre-cutoff output bit-identical | any difference |
| Timing table | no row where use precedes availability, **with the verdict computed per date from declared strike times** | any such row, or a verdict that is not computed |
| Timing table, mutated | removing the correction makes the table report the violation | the table still reports no violation |
| Shift test | Sharpe strictly decreasing in the lag | non-monotone or flat |
| Forecast correlation | well below a perfect forecast's | implausibly high |
| Parameter provenance | every parameter demonstrably fixed in the design window | any changed afterwards without disclosure |

## Output

`reports/tables/timing_audit.csv`; the perturbation tests live permanently in
`tests/` so that a future change cannot reintroduce a leak silently.

## Record

`docs/validation.md`. If a leak was found and fixed, `docs/project_log.md` records
what it was, what it was worth in performance terms, and how the fix was verified —
because the size of the leak is itself informative about how much of the original
result was real.
