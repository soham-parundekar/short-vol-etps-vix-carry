# Phase 07 — Index reconstruction and tracking validation

## 1. Objective

Rebuild the S&P 500 VIX Short-Term Futures Index from the cleaned futures panel and
demonstrate, quantitatively, that the rebuild is the same object the traded products
track. Everything downstream — the tail model, the survival analysis, the strategy —
is computed on this series, so this phase is the load-bearing one.

## 2. Context

The index holds the two nearest monthly VX contracts and shifts weight from the near
to the far contract linearly in business days across a roll period running from one
VIX futures settlement date to the next:

```
w1 = dr / dt,   w2 = 1 - w1
r_t = (w1_{t-1} F1_t + w2_{t-1} F2_t) / (w1_{t-1} F1_{t-1} + w2_{t-1} F2_{t-1}) - 1
```

`F1` and `F2` are the settlement prices of **the contracts held at t−1**, priced on
both days. This is the single most important sentence in the phase. Differencing a
"front month price" series instead books the calendar spread as a price move on every
roll date, and the resulting series looks plausible — it is smooth, it has the right
volatility, and it is wrong.

Vendors differ on whether the roll trade is booked at the close of the settlement date
or of the following business day. The project builds both and chooses on evidence.

## 3. Inputs

- `data/interim/vx_panel.*`
- `data/interim/rates.csv` (for the total-return accrual)
- `data/interim/etp_prices.csv` (VIXY, VXX, SVXY for validation)
- `config/config.yaml` → `index.*`, `products.*`

## 4. Tasks

1. Build the roll calendar from the contract specification; verify the settlement
   dates against known expiries.
2. Build both roll conventions.
3. Reconstruct the excess-return index under each; produce levels and daily returns.
4. Add the Treasury-bill accrual on the convention the index methodology specifies to
   produce the total-return version.
5. Interpolate the constant-maturity curve at the configured horizons, without
   extrapolating beyond the longest listed contract.
6. Compute the carry and term-structure measures.
7. **Validate against the traded products.** For VIXY and VXX, compare the daily
   reconstructed excess return with the product's daily return plus its accrued fee.
   Report mean difference, standard deviation of the difference, correlation, and the
   regression of product return on index return (slope should be 1 for the 1× products
   and −1 for SVXY before February 2018).
8. Choose the roll convention by tracking error. Record the comparison, not only the
   winner. Run `tasks/resolve_roll_convention.md`.
9. Check the residual against the roll weight: a systematic relationship means the
   roll is mis-timed even if the average error is small.
10. Reconstruct the 5 February 2018 index move independently and reconcile it with
    the XIV indicative value path implied by the filings.
11. Write the index to `data/processed/` and the tracking table to `reports/tables/`.

## 5. Tools and methods

`svcarry.index.calendar`, `svcarry.index.reconstruct`, `svcarry.econometrics.hac` for
the validation regressions.

## 6. Execution instructions

Test the reconstruction on synthetic panels with analytically known answers before
running it on real data. At minimum: a flat curve must give exactly zero return; a
steeply sloped curve with each contract's own price constant must also give exactly
zero; a parallel move of both contracts must pass through exactly.

Do not tune the reconstruction to reduce tracking error against the products beyond
the choice of roll convention. The products have fees, cash drag and their own
tracking error; a reconstruction that matches them perfectly is suspicious.

If the tracking error fails the criterion below, stop and diagnose rather than
proceeding — every downstream result inherits this error.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Synthetic tests | all three exact to machine precision | — | any deviation |
| Tracking sd vs VIXY | ≤ 10 bp/day | 10–25 bp | > 25 bp |
| Tracking mean vs VIXY | within ±1 bp/day of the fee accrual | ±1–3 bp | > 3 bp |
| Regression slope vs VXX | 1.00 ± 0.02 | ± 0.05 | outside |
| Residual vs roll weight | no significant relationship (HAC t < 2) | 2–3 | > 3, i.e. the roll is mis-timed |
| SVXY slope pre-2018 | −1.00 ± 0.03 | ± 0.06 | outside |
| Coverage | index defined on ≥ 99% of sample trading days | 97–99% | < 97% |
| 5 Feb 2018 | reconstructed move reconciles with the filed indicative values | small unexplained residual | material disagreement |

## 8. Self-review

- Is the return on each settlement date computed on the contracts held the day before?
- Does the level series jump on any roll date?
- Is the tracking error larger in high-volatility periods? That is expected, but check
  it is not larger in a way that tracks the roll weight.
- Does the total-return version exceed the excess-return version by approximately the
  accumulated bill return, and no more?
- Has the reconstruction been tuned to the products in any way beyond the convention
  choice?

## 9. Deliverables

- `data/processed/index_daily.csv` — levels, returns, held contracts, weights, carry
- `data/processed/curve_constant_maturity.csv`
- `reports/tables/index_tracking.csv`
- `reports/figures/index_vs_products.png`, `reports/figures/tracking_residuals.png`
- A validation section in `docs/validation.md` recording the convention decision

## 10. Git requirements

Commit the processed index if it is small and derived from data the project is
entitled to redistribute; it is a derived series, not vendor data, but record the
reasoning. Commit the tracking table and figures. Commit message reports the tracking
error and the convention chosen.

## 11. Completion gate

- [ ] Synthetic tests pass exactly
- [ ] Both conventions built and compared
- [ ] Tracking error within criterion against at least two products
- [ ] Residual shows no relationship with the roll weight
- [ ] Convention decision recorded with the evidence
- [ ] 5 February 2018 reconciled against the filings
- [ ] Index written to `data/processed/`

## 12. Handoff

Phases 08–11 consume `index_daily.csv`. They must be told: the roll convention chosen
and why, the measured tracking error (which is a floor on the precision of any
downstream claim), the days on which the index is undefined, and the reconstructed
5 February 2018 move, which becomes the historical floor for the stress scenario in
Phase 11.
