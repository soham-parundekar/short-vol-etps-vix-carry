# Task — Resolve the index roll convention

## Parent phase

`prompts/phases/07_index_reconstruction.md`

## Objective

Choose between the candidate roll conventions on evidence, and record the choice with
the evidence that settled it.

## Why this is a separate task

The two conventions differ by one business day in when the roll weight is applied.
The difference is small on any given day — typically `1/dt ≈ 4.8%` of the position —
and completely invisible in a plot of the index level. It is nonetheless a systematic
error that enters every downstream return, and it is exactly the kind of choice that
gets made by assumption and never revisited.

Isolating it as a task forces the decision to be made once, on a stated criterion,
before any result depends on it.

## Inputs

- The reconstructed index under each convention
- VIXY, VXX and SVXY returns, split-adjusted
- The fee for each product

## Procedure

1. For each convention, form the daily difference
   `d_t = r_index,t − (r_product,t + fee_accrual_t)`
   for VIXY and for VXX.
2. Report, per convention and per product: mean of `d`, standard deviation of `d`,
   correlation of `r_index` with `r_product`, and the slope from regressing the
   product return on the index return.
3. Regress `d_t` on the roll weight `w1_{t−1}` with HAC standard errors. A
   significant slope means the roll is mis-timed under that convention.
4. Repeat the comparison on two subsamples (pre-2016, post-2016) to confirm the
   ranking is not a feature of one period.

## Decision rule

Choose the convention with the lower standard deviation of `d` **and** an insignificant
relationship between `d` and the roll weight. If those two criteria disagree, prefer
the one with no roll-weight relationship: an unbiased-on-average reconstruction that
is wrong in a way correlated with the roll is worse than one with slightly larger
noise, because the error will be correlated with the signal.

If neither convention passes the roll-weight test, the problem is the calendar rather
than the convention. Return to `svcarry.index.calendar` and check the settlement dates
against the contract specification before proceeding.

## Validation

| Check | Pass | Failure |
|---|---|---|
| Separation | the two conventions differ measurably in tracking sd | indistinguishable — say so and note the choice does not matter |
| Roll-weight test | HAC t-statistic below 2 for the chosen convention | above 3 |
| Subsample stability | same convention wins in both subsamples | ranking flips, unexplained |

## Output

`reports/tables/roll_convention.csv`; the chosen value written to
`config/config.yaml` under `index.roll_convention`.

## Record

`docs/validation.md`, with the comparison table inline — both conventions, not only
the winner.
