# Phase 11 — Crash-aware carry backtest

## 1. Objective

Run the strategy, out of sample, with honest timing and realistic costs, against
benchmarks that make the comparison meaningful. Tests H5.

## 2. Context

The strategy is a collateralised short position in the reconstructed index, entered
only when the curve is in contango and the variance risk premium is positive, sized by

```
w_t = min( σ* / σ̂_t ,  ℓ_max / StressLoss_t ,  w_max )
```

where `StressLoss_t` is the loss a unit position would take under the larger of the
fitted conditional 99.9% move and the reconstructed 5 February 2018 move.

The second constraint is the point of the exercise. Volatility targeting sizes largest
when recent volatility is lowest, which for an inverse-volatility position is exactly
the state from which the largest spikes begin. The crash budget does not adapt to calm.

Parameters were fixed in the design window (through 2015) and the evaluation window
begins in 2016. Nothing in this phase may change a parameter.

## 3. Inputs

- `data/processed/index_daily.csv`, `signals_daily.csv`
- `data/interim/rates.csv` (collateral accrual)
- Phase 09's conditional 99.9% quantile series
- `config/config.yaml` → `strategy.*`, `sample.design_end`, `sample.oos_start`

## 4. Tasks

1. Assemble the sizing inputs; produce the weight series and record which constraint
   binds each day.
2. Run the backtest with `signal_lag = 1`: a weight computed from the close of `t−1`
   earns the return from `t−1` to `t`.
3. Charge costs on turnover at the configured tick cost, expressed relative to the
   weighted futures price actually held.
4. Credit the collateral accrual on the full capital.
5. Build the benchmarks: buy-and-hold −1× with the XIV fee; buy-and-hold −0.5× with
   the SVXY fee; the Cboe PutWrite index; a constant-weight short position sized to
   the strategy's average exposure; and the S&P 500.
6. Report performance in the design window and the evaluation window **separately**,
   and never pool them into a headline number.
7. Report the six named stress windows for the strategy and every benchmark.
8. Run the alpha regression on PUT, SPX and VXX with HAC errors, and the up/down beta
   split.
9. Run `tasks/lookahead_audit.md` over the whole chain.
10. Run the deliberately leaky variant (`signal_lag = 0`) and report the difference.
    This is not a result; it is a calibration of how much a leak would have been
    worth, so a reader can judge whether the honest result is plausibly contaminated.

## 5. Tools and methods

`svcarry.strategy.sizing`, `.backtest`; `svcarry.evaluation.metrics`, `.regressions`.

## 6. Execution instructions

Do not tune anything. If the result is poor, that is the finding. If the result is
excellent, treat it as a warning and hunt for the leak before writing it up: an
out-of-sample Sharpe above roughly 1.5 on a strategy of this kind is more likely to be
a bug than a discovery.

Report the constant-weight benchmark honestly. If a fixed small short position does as
well as the dynamic rule, the signals are not earning their keep, and the write-up
must say so.

Report the strategy's worst day and worst week alongside its Sharpe, always, in the
same table.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Timing | weight applied to day `t` computed from data ≤ `t−1`, asserted in code | — | any same-day input |
| Leak calibration | leaky variant's Sharpe far above the honest one | similar | honest ≥ leaky, i.e. the lag is not working |
| Turnover | consistent with the rebalancing rule; annual turnover reported | — | turnover implying trading not described by the rule |
| Cost sensitivity | Sharpe declines monotonically in the cost assumption | — | non-monotone, i.e. a cost bug |
| Sample split | design and evaluation reported separately | — | a pooled headline |
| Feb 2018 | strategy loss materially smaller than buy-and-hold −1× | comparable | larger — check the sizing |
| Plausibility | OOS Sharpe ≤ 1.5 | 1.5–2.0, investigated | > 2.0 without an explanation |
| Benchmark set | includes constant-weight and buy-and-hold | — | only favourable benchmarks |

## 8. Self-review

- Is the collateral credited once, not twice (once in the index total return and again
  in the strategy)?
- Are costs charged on entry *and* exit?
- Does the equity curve have any single day that accounts for a large share of the
  total return? If so, name it in the write-up.
- What happens on days when the index is undefined? They must not be silently skipped.
- Is the Sharpe computed on excess returns?
- If the strategy is flat through February 2018, is that because the signal genuinely
  turned off beforehand, or because of a timing error?

## 9. Deliverables

- `data/processed/backtest_daily.csv`
- `reports/tables/performance_full.csv`, `performance_design.csv`,
  `performance_oos.csv`, `stress_windows.csv`, `alpha_regression.csv`
- `reports/figures/equity_curve.png`, `drawdowns.png`, `rolling_sharpe.png`,
  `weight_and_binding_constraint.png`, `feb2018_detail.png`

## 10. Git requirements

Commit code, results and figures. Commit message reports the out-of-sample Sharpe net
of the default cost, the maximum drawdown, the February 2018 return, and the alpha
with its t-statistic — including when the alpha is insignificant.

## 11. Completion gate

- [ ] No parameter changed in this phase
- [ ] Timing asserted in code and audited
- [ ] Leaky variant run and reported as a calibration
- [ ] Design and evaluation windows reported separately
- [ ] Full benchmark set, including constant-weight
- [ ] Stress-window table complete
- [ ] Alpha regression run with HAC errors
- [ ] H5 evaluated against its rejection criterion

## 12. Handoff

Phase 12 consumes the baseline configuration to sweep around. Phase 13 consumes the
performance tables and the alpha regression. Phase 14 consumes the daily series.
