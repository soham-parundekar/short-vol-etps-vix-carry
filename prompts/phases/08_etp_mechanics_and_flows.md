# Phase 08 — Leveraged-product mechanics and rebalancing flows

## 1. Objective

Establish, on real product data, that the leverage-decay identity holds and that the
mechanical end-of-day rebalancing demand was economically large relative to the
market that had to absorb it. This phase tests hypothesis H2 and the mechanical part
of the product-design argument.

## 2. Context

Two identities drive the analysis.

**Rebalancing demand.** `ΔE_t = L(L−1) A_{t−1} r_t`. The coefficient `L(L−1)` is
positive for every `L` outside `[0,1]`, so both a +2× and a −1× fund must buy after
the index rises. De-levering from −1× to −0.5× cuts the coefficient from 2.0 to 0.75.

**Leverage decay.** `V_T/V_0 = (I_T/I_0)^L exp(−½(L²−L)σ²T)` under continuous
rebalancing, so regressing `ln(V_T/V_0) − L ln(I_T/I_0)` on realised variance should
give slope `−½(L²−L)` and an intercept recovering the fee.

The weak input is assets outstanding. Where they are not disclosed they must be
bounded, and the conclusion must hold at both bounds. This is the difference between
a result and an assertion.

## 3. Inputs

- `data/processed/index_daily.csv`
- `data/interim/etp_prices.csv` (with shares outstanding where available)
- `references/filings/**` (net assets from the 10-K)
- `config/config.yaml` → `products.*`

## 4. Tasks

1. For each product, run the decay regression over non-overlapping 21-day blocks and
   compare the slope with `−½(L²−L)` and the intercept with the fee.
2. Run the regression separately before and after 2018-02-28 for SVXY and UVXY. The
   estimated coefficient should move from the −1× and +2× values to the −0.5× and
   +1.5× values. This is a test that the documented leverage change is visible in
   prices at the date the filings say it happened.
3. Estimate assets outstanding for each product through time. Run
   `tasks/estimate_product_assets.md`. Produce an upper and a lower bound, not a
   point estimate, wherever the figure is inferred rather than disclosed.
4. Compute `ΔE_t` per product and in aggregate.
5. Convert to contract equivalents at the $1,000 multiplier using the front-month
   settlement price, and express as a share of front-month open interest.
6. Tabulate the largest index up-moves and the implied flow on each, under both asset
   bounds.
7. Quantify the effect of the February 2018 de-levering: the same shock, before and
   after, in contracts and as a share of open interest.
8. Produce the flow figure and table.

## 5. Tools and methods

`svcarry.etp.mechanics` (`decay_regression`, `rebalancing_trade`,
`aggregate_rebalancing_flow`, `contracts_equivalent`);
`svcarry.econometrics.hac` for inference.

## 6. Execution instructions

The decay regression uses non-overlapping blocks so the observations are independent.
Run an overlapping version with HAC errors as a cross-check and report both; if they
disagree materially, the block length is doing work it should not.

State the flow result as a range implied by the asset bounds, always. A single number
implies a precision that the inputs do not support.

**Do not claim causality.** The flow analysis establishes that the mechanical demand
was large relative to open interest. Daily data cannot establish that it caused the
size of any particular move, and the write-up must say so in the same breath as the
result.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Decay slope, 1× products | within 0.05 of 0 | 0.05–0.15 | beyond |
| Decay slope, −1× | within 0.15 of −1.0 | 0.15–0.35 | beyond |
| Decay slope, +2× | within 0.15 of −1.0 | 0.15–0.35 | beyond |
| Intercept | recovers the fee within 100 bp p.a. | 100–250 bp | beyond, unexplained |
| SVXY structural break | post-2018 coefficient nearer −0.375 than −1.0, and the difference significant | direction right, not significant | no break visible |
| Flow bounds | upper and lower bound computed; conclusion holds at both | holds only at the upper bound, stated | only a point estimate reported |
| Units | contract equivalents reconcile to dollars at $1,000 × price | — | a dimensional error |

## 8. Self-review

- Check the dimensions explicitly: dollars → contracts → share of open interest.
  A factor of 1,000 error here is invisible in a plot and fatal in a claim.
- Is open interest the front-month contract's, or the whole complex's? Say which.
- Are the product returns split-adjusted? An unadjusted VXX destroys the decay
  regression.
- Does the estimated flow ever exceed 100% of open interest? If so, either the asset
  estimate or the denominator is wrong.
- Is the causal language anywhere stronger than "large relative to"?

## 9. Deliverables

- `reports/tables/leverage_decay.csv`
- `reports/tables/rebalancing_flows.csv` (with bounds)
- `reports/figures/decay_regression.png`
- `reports/figures/flow_vs_open_interest.png`
- A methodology section describing the asset-bound construction

## 10. Git requirements

Commit code, tables and figures. Commit message reports the decay slopes against
theory and the headline flow figure as a range.

## 11. Completion gate

- [ ] Decay regression run for every product, both block schemes
- [ ] SVXY/UVXY structural break tested at the documented date
- [ ] Assets bounded, method documented
- [ ] Flows computed under both bounds
- [ ] Dimensional check performed and recorded
- [ ] Causal language audited
- [ ] H2 evaluated against its stated rejection criterion

## 12. Handoff

Phase 09 needs nothing from this phase directly. Phase 13 needs the decay results, the
flow range and the de-levering comparison. Phase 12 needs the asset-bound construction
so it can stress it.
