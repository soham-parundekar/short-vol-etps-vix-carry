# Operation — Financial logic validation

## When to run

After any change to code that computes a return, a fee, a leverage effect, an accrual,
a cost or a position size.

## Inputs

The changed code and one worked example small enough to check by hand.

## Procedure

**Units and conventions**

- [ ] Simple or log returns — and is the same convention used on both sides of every
      comparison?
- [ ] Variance or volatility? Daily or annualised? Percent or decimal?
- [ ] Is VIX in points (20) or decimals (0.20) at each point in the calculation?
- [ ] Calendar days or business days for fee accrual? (Fees accrue on calendar days;
      volatility annualises on trading days. Both appear in this project.)

**Signs**

- [ ] A short position: does a positive index return produce a loss?
- [ ] The asymmetry term in the GARCH fit: is its sign what the exposure implies?
- [ ] Carry in contango: does the short position earn it?
- [ ] Drawdowns negative, costs subtracted, accruals added

**Identities to check by hand, on one observation each**

- [ ] Index return equals the weighted price change on the contracts held at `t−1`
- [ ] Product NAV step equals `V(1 + a + Lr) − V·fee·days/365`
- [ ] Strategy return equals `accrual − weight × index return − cost`
- [ ] Rebalancing trade equals `L(L−1)Ar`, and restores exposure to `L × assets`
- [ ] Contract equivalents: dollars ÷ (1000 × futures price)

**Double-counting**

- [ ] Is the collateral accrual credited once, or twice (once inside a total-return
      index and again in the strategy)?
- [ ] Is a fee charged in both the index and the product?
- [ ] Are costs charged on entry and exit, and not twice on either?

**Direction-of-effect checks**

- [ ] Raising the cost assumption lowers the Sharpe
- [ ] Raising the volatility target raises both return and drawdown
- [ ] Tightening the stress budget lowers the maximum weight
- [ ] Lengthening the fee accrual lowers the NAV

**Known-event checks**

- [ ] 5 February 2018: the index rose sharply; a −1× product lost about 80%
- [ ] March 2020: sustained backwardation; the contango filter should be off
- [ ] August 2024: a sharp spike followed by a fast normalisation

## What counts as done

Every identity checked on a real observation, with the arithmetic written down
somewhere reproducible — a test, or a cell in a notebook that is committed.

## Escalation

- A failed identity: stop. This is a correctness bug and everything downstream is
  suspect until it is fixed
- A failed direction-of-effect check: almost always a sign error; find it before
  proceeding
- A failed known-event check: either the data is wrong or the construction is; both
  are blocking
