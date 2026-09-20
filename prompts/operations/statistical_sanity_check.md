# Operation — Statistical sanity check

## When to run

After any estimation: a regression, a GARCH fit, a GPD fit, a forecast, a bootstrap.

## Inputs

The fitted object, the sample it was fitted on, and the assumptions the estimator
makes.

## Procedure

**Sample**

- [ ] How many observations were actually used? Compare with how many were passed in —
      the difference is silently dropped rows
- [ ] Is the sample the period intended?
- [ ] For a tail estimate: how many exceedances? Below about 50, say so wherever the
      number is quoted

**Assumptions**

- [ ] Independence: is there serial correlation the standard errors do not account
      for? With overlapping horizons there always is
- [ ] Stationarity: does the relationship look the same in the first and second half?
- [ ] Distribution: is normality assumed anywhere it should not be?
- [ ] Is the estimator being used outside the range where it is valid — extrapolating
      a GPD far beyond the largest observation, or a Gaussian Kelly formula on a
      fat-tailed sample?

**Estimates**

- [ ] Are the coefficients economically sensible in sign and magnitude?
- [ ] Is any parameter at a bound? That usually means the model is misspecified or the
      bound is wrong
- [ ] Are the standard errors plausible — neither implausibly tight nor so wide the
      estimate says nothing?
- [ ] Is R² suspiciously high for the kind of data? A daily-return regression with an
      R² above 0.3 deserves a look for a leak

**Robustness**

- [ ] Does the estimate survive an alternative specification?
- [ ] Does it survive dropping the largest observation?
- [ ] Does it survive on each half of the sample?
- [ ] Is the result driven by one period? Plot the rolling estimate

**Inference**

- [ ] Are standard errors HAC where the data is serially correlated?
- [ ] Is the bandwidth at least `h − 1` for an `h`-horizon overlapping regression?
- [ ] Are multiple comparisons accounted for, or at least counted?
- [ ] Is statistical significance being reported without economic significance?

## What counts as done

Diagnostics recorded alongside the estimate, in the committed table rather than only
in a console. An estimate reported without its diagnostics is not reportable.

## Escalation

- Assumption violated: either use an estimator that does not need it, or report the
  estimate with the violation disclosed. Never silently
- Estimate not robust: report the range, not the point
- Suspiciously good fit: run `tasks/lookahead_audit.md` before reporting anything
