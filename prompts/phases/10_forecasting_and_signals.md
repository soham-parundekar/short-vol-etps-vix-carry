# Phase 10 — Realised variance, HAR forecasting and signal construction

## 1. Objective

Produce the two entry signals the strategy uses — a term-structure filter and a
variance-risk-premium filter — with forecasts that are genuinely real time, and
demonstrate that the forecasting step has out-of-sample skill worth having.

## 2. Context

The variance risk premium is the difference between an option-implied variance that is
observable and a realised variance that is not yet known. It therefore requires a
*forecast*, and the forecast is where look-ahead bias enters this kind of project.
Two mistakes are common and both are easy to make:

1. Using the realised variance that actually occurred instead of a forecast of it.
2. Estimating the forecasting model on the whole sample, so that the coefficients used
   on a date in 2010 were fitted partly on data from 2020.

There is a subtler third. On date `t`, a training observation dated `s` has a
dependent variable spanning `s+1 … s+h`, which is only observable once `s + h ≤ t`.
The most recent usable training row is dated `t − h`, not `t`. An expanding-window
loop that trains on everything up to `t` is leaking `h` days of information on every
refit.

## 3. Inputs

- `data/processed/index_daily.csv`, `curve_constant_maturity.csv`
- `data/interim/etp_prices.csv` (SPX OHLC for the variance proxy)
- Cboe VIX and VIX3M
- `config/config.yaml` → `forecast.*`, `strategy.contango_threshold`, `strategy.vrp_min`

## 4. Tasks

1. Build the daily variance proxy from OHLC. Compare the available estimators
   (close-to-close, Parkinson, Garman–Klass, Rogers–Satchell, and overnight plus
   intraday) and record which is used and why. Note that Yang–Zhang is a
   *window* estimator and has no single-day value; if a daily series is described as
   Yang–Zhang anywhere, the deviation must be stated explicitly.
2. Fit the HAR regression in sample and report coefficients with HAC standard errors
   at a bandwidth of at least `h − 1`, since the dependent variable overlaps.
3. Produce strictly real-time expanding-window forecasts with periodic refitting.
4. Evaluate them: out-of-sample R², RMSE, and a Mincer–Zarnowitz regression testing
   whether the slope is one.
5. Compare against two naive benchmarks: the trailing realised variance itself, and a
   random walk. A HAR that does not beat trailing RV is not earning its complexity.
6. Construct `VRP = (VIX/100)² − forecast`, in consistent annualised variance units.
7. Construct the term-structure signal. Use the interpolated `cm30/cm90` ratio as the
   primary measure (available for the whole sample) and `VIX/VIX3M` as the robustness
   variant; demonstrate the two agree on their overlap.
8. Combine the signals and record the fraction of days on which each is on, each is
   the binding constraint, and both agree.
9. Run `tasks/lookahead_audit.md` on everything produced here.

## 5. Tools and methods

`svcarry.econometrics.realized`, `.har`, `.hac`; `svcarry.strategy.signals`.

## 6. Execution instructions

Use the repository's `har_oos_forecast`, which enforces the `t − h` training cutoff,
rather than writing a fresh loop. If a fresh loop is written, it must pass the
look-ahead test in `tests/test_har.py`: perturb the variance series after a cutoff and
require every earlier forecast to be bit-identical.

Signal thresholds come from `config/config.yaml` and are fixed in the design window.
Do not adjust them after seeing out-of-sample results; if an adjustment is genuinely
warranted, it is a change to the design, logged as such and disclosed.

Keep units straight. VIX is an annualised volatility in percentage points; the HAR
output is a daily variance; the VRP is an annualised variance. Convert once, in one
place, and test it.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Look-ahead test | forecasts before the cutoff bit-identical | — | any difference |
| OOS R² | > 0.25 | 0.10–0.25 | < 0.10 |
| Beats trailing RV | lower RMSE out of sample | comparable | worse |
| Mincer–Zarnowitz | slope within 0.2 of 1.0 | 0.2–0.4 | beyond, i.e. biased |
| VRP sign | positive on a clear majority of days | ~50% | mostly negative — check units |
| Signal overlap | `cm30/cm90` and `VIX/VIX3M` agree on ≥ 90% of overlapping days | 80–90% | < 80% |
| Coverage | signals defined on ≥ 95% of sample days after burn-in | 90–95% | < 90% |

## 8. Self-review

- Recompute one VRP value by hand from the raw VIX level and the forecast.
- Is the HAR estimated in logs? If so, is the retransformation bias corrected?
- Does the forecast series have a suspiciously high correlation with the realised
  value at the same date? That is the signature of a leak.
- What fraction of days does the strategy end up invested? If it is above 90%, the
  filters are doing nothing; if below 30%, the sample of active days may be too small
  to say anything.
- Were the thresholds chosen in the design window, and can that be demonstrated from
  the commit history?

## 9. Deliverables

- `data/processed/signals_daily.csv` — variance proxy, HAR forecast, VRP, slope
  measures, individual and combined signals
- `reports/tables/har_fit.csv`, `har_oos_diagnostics.csv`
- `reports/figures/vrp_timeseries.png`, `har_forecast_vs_realised.png`,
  `signal_state.png`
- Methodology note on the variance-proxy choice

## 10. Git requirements

Commit code, signal panel, tables and figures. Commit message reports the out-of-sample
R², the Mincer–Zarnowitz slope and the fraction of days each signal is on.

## 11. Completion gate

- [ ] Variance proxy chosen and the choice justified
- [ ] HAR fitted with correct overlapping-horizon inference
- [ ] Real-time forecasts produced and the look-ahead test passed
- [ ] Forecast beats the naive benchmarks out of sample
- [ ] VRP units verified by hand
- [ ] Both slope measures built and shown to agree
- [ ] Signal statistics recorded
- [ ] Thresholds demonstrably fixed in the design window

## 12. Handoff

Phase 11 consumes `signals_daily.csv` and must be told the burn-in date before which
signals are undefined, and the fraction of days invested, so that the strategy's
statistics are interpreted on the right sample.
