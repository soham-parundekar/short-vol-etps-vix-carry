# Task — Bound the products' assets outstanding

## Parent phase

`prompts/phases/08_etp_mechanics_and_flows.md`

## Objective

Produce an upper and a lower bound on each product's net assets through time, with the
method documented, so that the rebalancing-flow result can be stated as a range that
holds at both bounds.

## Why this is a separate task

Assets outstanding is the weakest input in the project. The flow estimate is *linear*
in it, so an asset series that is wrong by a factor of two makes the headline claim
wrong by a factor of two. Free sources do not give a clean daily history for every
product over the whole sample.

Treating this as a task with an explicit bounding method — rather than as a data
lookup — is what keeps the eventual claim honest.

## Inputs

- `references/filings/ProSharesTrustII_10K_*.htm` — net assets by fund at period ends
- Daily product prices
- Shares outstanding where a free source provides them
- Any disclosed creation/redemption information

## Procedure

1. Collect every directly disclosed net-asset figure, with its date, into a table.
   These are the anchors.
2. Between anchors, construct two series:
   - **Lower bound.** Hold the share count constant at the preceding anchor's implied
     level and let assets move only with price. This understates assets in periods of
     net creation.
   - **Upper bound.** Interpolate the share count between anchors and let assets move
     with both shares and price, taking the higher of the two where they cross.
3. Where a daily shares-outstanding series is available, use it as the central
   estimate and keep the bounds as a sanity check on it.
4. Validate both series against every anchor: at an anchor date, both bounds must
   bracket the disclosed figure.
5. Plot the two series with the anchors marked. A bound that does not visibly contain
   the anchors is wrong.
6. Propagate both bounds through the flow calculation, and report the flow as a band.

## Decision rule

No point estimate is reported for any date at which assets were not disclosed. Where a
single number is unavoidable for exposition, it is the midpoint of the band and is
labelled as such in the same sentence.

If the project's conclusion holds at the lower bound, state it unconditionally. If it
holds only at the upper bound, state it conditionally and say so in the abstract, not
in a footnote.

## Validation

| Check | Pass | Failure |
|---|---|---|
| Bracketing | every disclosed anchor lies between the bounds | an anchor outside the band |
| Width | the band is narrow enough that the conclusion is the same at both edges | the conclusion flips inside the band and this is not disclosed |
| Plausibility | assets never exceed the product's known peak, never go negative | either |
| Consistency | implied shares × price reconciles to assets | a dimensional inconsistency |

## Output

`data/processed/product_assets_bounds.csv`;
`reports/figures/product_assets_with_anchors.png`.

## Record

`docs/methodology.md` — the bounding method. `docs/limitations.md` — the fact that the
flow result is only as good as this bound, and what would improve it (a subscription
data source with daily shares outstanding).
