# Task — Choose and defend the peaks-over-threshold level

## Parent phase

`prompts/phases/09_tail_model_and_survival.md`

## Objective

Select the threshold above which the Generalised Pareto Distribution is fitted, using
a procedure decided in advance, and report the sensitivity of every headline number to
that choice.

## Why this is a separate task

Threshold choice is the bias–variance trade-off of extreme value theory and the place
where a tail estimate can be quietly tuned. Too low, and observations from the body of
the distribution contaminate the fit, biasing the shape parameter. Too high, and there
are too few exceedances for the estimate to mean anything. Between those extremes sits
a range within which an analyst who has already seen the answer can pick the number
that gives the answer they prefer.

The defence is to fix the procedure first and report the whole grid afterwards.

## Inputs

- Standardised residuals from the GJR-GARCH fit (both the full-sample and the
  pre-2018 fit)
- `config/config.yaml` → `tail.threshold_quantile`, `tail.threshold_grid`

## Procedure

1. Produce the mean-excess plot with pointwise standard errors. For a GPD tail the
   mean excess is linear in the threshold with slope `ξ/(1−ξ)`; identify the level
   above which it is plausibly linear.
2. Fit the GPD across the full threshold grid. Tabulate, per threshold: the number of
   exceedances, `ξ` and its standard error, `β`, and the Kolmogorov–Smirnov p-value on
   the probability-integral transform of the excesses.
3. Identify the region over which `ξ` is stable — flat within about one standard error.
4. Apply the decision rule below.
5. Recompute **every** headline number at every threshold in the grid, and report that
   table alongside the headline.
6. Produce the QQ plot at the chosen threshold.

## Decision rule

Choose the lowest threshold that satisfies all of:

- at least 50 exceedances,
- `ξ` within one standard error of its value at the next two higher thresholds,
- KS p-value above 0.10,
- inside the region the mean-excess plot identifies as linear.

Prefer the lowest such threshold because it maximises the number of exceedances, which
is what the standard errors are made of.

If no threshold satisfies all four, say so and report a range rather than a point
estimate for every downstream probability. That is a legitimate outcome and it is far
better than picking a threshold and hoping.

**The threshold for the pre-2018 fit is chosen using pre-2018 data only.** Choosing it
on the full sample and applying it to the pre-2018 fit would smuggle the event into an
ex-ante claim through the back door.

## Validation

| Check | Pass | Failure |
|---|---|---|
| Exceedances | ≥ 50 at the chosen threshold | < 30 |
| Stability | `ξ` varies by less than 0.10 across the stable region | varies by more than 0.20 and a point estimate is reported anyway |
| Goodness of fit | KS p > 0.10 | < 0.05 |
| Shape sign | `ξ > 0` | `ξ < 0` reported without investigation |
| Sensitivity | headline numbers reported across the whole grid | only the chosen threshold reported |
| Ex-ante hygiene | pre-2018 threshold chosen on pre-2018 data | chosen on the full sample |

## Output

`reports/tables/evt_thresholds.csv` — the grid;
`reports/tables/termination_probabilities.csv` — headline numbers at every threshold;
`reports/figures/mean_excess.png`, `qq_gpd.png`, `xi_vs_threshold.png`.

## Record

`docs/validation.md` — the chosen threshold, the four criteria, and the sensitivity
table. If the answer moves by more than a factor of three across the grid, that fact
goes in the abstract, not the appendix.
