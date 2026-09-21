# Phase 09 — Tail model, termination probability, survival and Kelly

## 1. Objective

Answer the project's central quantitative question: under a model fitted only to data
available beforehand, how probable was an index move large enough to terminate a −1×
product, how much does de-levering to −0.5× change that, and how does the growth-optimal
exposure compare with the leverage the products offered? Tests H3 and H4.

## 2. Context

This is an extrapolation exercise. The event of interest is larger than almost
everything in the sample, so the empirical distribution answers "zero" or "once",
depending on the window. Extreme value theory supplies a principled interpolation, and
a GARCH filter supplies the time-varying scale, so the two-stage McNeil–Frey
construction is the appropriate tool.

The integrity of the answer rests on two things: that the model is estimated on
pre-event data when the claim is an ex-ante one, and that the result is reported
across a grid of thresholds rather than at one convenient choice.

## 3. Inputs

- `data/processed/index_daily.csv`
- `config/config.yaml` → `tail.*`
- Wipeout thresholds from `svcarry.etp.mechanics.wipeout_threshold`:
  80% index move for −1×, 160% for −0.5×

## 4. Tasks

1. Fit a GJR-GARCH(1,1) with skewed-*t* innovations to daily index log returns. Fit
   twice: on the full sample, and on data ending 2017-12-31.
2. Check the fit: convergence from multiple starts, persistence below one, Ljung–Box
   on squared standardised residuals, and the sign of the asymmetry term. For an
   inverse-volatility exposure the damaging shock is a large **positive** index move,
   so a negative asymmetry coefficient is the expected sign; an unexpected sign is
   something to investigate, not to report silently.
3. Fit the GPD to standardised residuals above the threshold. Run
   `tasks/choose_evt_threshold.md`. Produce the mean-excess plot, the threshold
   stability grid and the QQ plot.
4. Compute `P(R ≥ 0.80)` and `P(R ≥ 1.60)` for the one-day simple return,
   unconditionally and conditional on the lowest quintile of conditional volatility.
   Report both under the full-sample and the pre-2018 fit. Express as annualised
   probabilities and as return periods in years.
5. Simulate survival: paths over the configured horizon from the fitted model, for
   `L ∈ {−1, −0.5}`, recording first passage to an 80% single-day loss. Report
   survival curves with simulation standard errors.
6. Compute the Kelly-optimal short exposure under the empirical distribution, under
   simulated returns from the fitted model, and with a stationary-bootstrap confidence
   interval. Compare with −1× and −0.5×.
7. Jackknife the single largest observation and recompute every headline number.
8. Write the tail tables and figures.

## 5. Tools and methods

`svcarry.econometrics.garch`, `.evt`, `.kelly`, `.bootstrap`. Use the log return for
the GARCH filter and convert to simple returns for the termination thresholds — the
80% figure is defined on the simple return, and conflating the two understates the
probability.

## 6. Execution instructions

Report the pre-2018 estimate as the ex-ante number and the full-sample estimate as a
descriptive one, and never present the latter as the former.

Report the threshold grid in full. If the answer moves by more than a factor of three
across the grid, the honest headline is a range, not a point.

If the fitted shape parameter is negative — implying a bounded tail — investigate
before reporting. For a volatility index that would be a surprising result and more
likely indicates a threshold set too low or a sample too short.

Simulation seeds come from configuration so that every number in the report is
reproducible.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| GARCH convergence | same optimum from ≥ 2 starts | starts disagree slightly | no convergence |
| Persistence | `α + β + γ/2` in (0.90, 0.999) | (0.85, 0.90) | ≥ 1 |
| Ljung–Box on z² | p > 0.05 at 10 and 20 lags | 0.01–0.05 | < 0.01, i.e. ARCH remains |
| GPD shape | ξ > 0, se well below ξ | ξ ≈ 0 | ξ < 0 unexplained |
| KS on the PIT | p > 0.10 | 0.05–0.10 | < 0.05 |
| Threshold stability | ξ varies < 0.10 across the grid | 0.10–0.20 | > 0.20 |
| Ordering | `P(R≥0.80)` ≥ 10 × `P(R≥1.60)` | 3–10 × | ordering reversed |
| Jackknife | headline probability moves < 50% when the largest day is removed | 50–200% | > 200%, i.e. one day is the result |
| Kelly CI | excludes 1.0 | contains 1.0 at the edge | contains 1.0 comfortably (H4 rejected) |
| Simulation error | survival curve standard errors < 1pp | 1–2pp | larger |

## 8. Self-review

- Is the pre-2018 model genuinely pre-2018 — including the threshold choice and any
  parameter tuned by looking at the full sample?
- Are log and simple returns kept straight everywhere? Check one number by hand.
- Does the conditional-on-calm probability fall BELOW the unconditional one? Under a
  GARCH scale it must, because the one-day tail probability rises with sigma; if it
  does not, the conditioning is wrong. *(Corrected in Session 6: this line originally
  asserted the reverse, which no GARCH model can produce. The question it was reaching
  for - does the model under-state risk in calm regimes? - is a calibration test on
  exceedance rates by volatility quintile; see docs/validation.md V14.)*
- How many exceedances are above the threshold? Below about 50, the GPD standard
  errors are wide and the report must say so.
- Is the Kelly calculation on simple returns with the solvency constraint enforced?

## 9. Deliverables

- `reports/tables/garch_fit.csv`, `reports/tables/evt_thresholds.csv`
- `reports/tables/termination_probabilities.csv` (both fits, both leverages,
  conditional and unconditional)
- `reports/tables/kelly.csv`
- `reports/figures/mean_excess.png`, `qq_gpd.png`, `survival_curves.png`,
  `kelly_growth_curve.png`
- A validation section covering the threshold decision and the jackknife

## 10. Git requirements

Commit code, tables and figures; seeds are in configuration so nothing random needs
committing. Commit message reports the ex-ante probability for each design and the
Kelly fraction with its interval.

## 11. Completion gate

- [ ] Both GARCH fits converged and diagnosed
- [ ] EVT threshold chosen by a recorded procedure; full grid reported
- [ ] Termination probabilities computed for both leverages, both fits, conditional
      and unconditional
- [ ] Survival simulated with standard errors
- [ ] Kelly computed with a bootstrap interval
- [ ] Jackknife of the largest observation performed
- [ ] H3 and H4 evaluated against their rejection criteria

## 12. Handoff

Phase 11 consumes the fitted conditional 99.9% quantile as the model leg of the stress
scenario. Phase 12 consumes the threshold grid and the jackknife. Phase 13 consumes
the probabilities, the survival comparison and the Kelly result.
