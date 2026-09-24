# Limitations

Everything the project knows to be imperfect, in one place, with the results each
item bears on. The test for inclusion is whether a careful reader who found it
themselves would feel it had been concealed.

Items are stated at the strength the evidence supports. Where something is
unexplained it says so rather than offering a mechanism that has not been shown.

---

## L1. The reconstructed index carries measurement noise against the traded products

**Magnitude.** Roughly 120 bp a day before 26 October 2020, roughly 30 bp a day
after. Fitted slopes of product on index: 0.87 over 2011-2017, 0.96 over 2019 to
October 2020, 0.98 after.

**Cause, as far as it is established.** The dominant term is that the two series were
measured fifteen minutes apart. Cboe struck the VX daily settlement at 3:15 p.m. CT
until 26 October 2020 and at 3:00 p.m. CT after; 3:00 p.m. CT is 4:00 p.m. ET, which
is when the products' consolidated closing price is struck. `docs/validation.md` V6
dates the break in the data and V9 shows it at its most extreme, on 5 February 2018,
where 57.5% of the day's index move happened after 4:00 p.m.

**Not fully explained.** The lead-lag coefficient dies after 2015 and the
contemporaneous slope improves around 2019, both before the settlement-time change.
No mechanism for either has been demonstrated.

**What it bounds.** Every result computed on the pre-2020 sample. An effect whose
economic significance depends on differences smaller than ~120 bp a day in that
period is not supported by this data. This is a property of the reconstruction, not
of the strategy, and it does not bias a return series - it widens the interval around
any comparison against a traded product.

---

## L2. VXX is linked to the total-return index; the reconstruction is excess-return

The iPath Series B pricing supplement states that the ETNs are linked to the
"S&P 500 VIX Short-Term Futures Index **TR**". XIV was linked to the excess-return
version. This project reconstructs ER (the futures-only return), with a total-return
variant available when a T-bill accrual is supplied.

**Consequence.** VXX's mean tracking residual against the ER reconstruction carries a
known positive bias of approximately the T-bill rate less the 0.89% fee. At 2023-2025
rates that is on the order of 1-2 bp a day.

**What it bears on.** The *mean* residual in `reports/tables/index_tracking.csv` for
VXX only. It does not affect the slope, the tracking error, or any result that rests
on covariation rather than on level.

---

## L3. VXX has been closed to issuance since March 2022

Barclays suspended further sales and issuances effective 14 March 2022. With
creations switched off, the arbitrage that holds an ETN near its indicative value
does not operate, and the issuer's own amendment says the notes may trade at a
premium or discount.

**Consequence.** VXX's post-2022 price series is not a clean proxy for index
performance. Its daily tracking error over 2022-2026 is 101 bp against VIXY's 28 bp
over the identical window.

**What it bears on.** Any use of VXX as a validation benchmark after March 2022.
VIXY is the appropriate +1x comparator for that period and is used as such.

---

## L4. Two product terms rest on documents that may have been superseded

| Term | Value used | Source | Risk |
|---|---|---|---|
| VXX investor fee | 0.89%/yr | iPath Series B **preliminary** pricing supplement, 3 Jan 2018 | The document states on its face that the information "is not complete and may be changed". The final supplement has not been archived. |
| SVIX management fee | 1.35%/yr | VS Trust 424B3, 28 Jan 2022 (launch) | A later amendment reducing the fee has not been checked. The configuration previously carried 1.29%, which could not be located in any archived filing. |

**What they bear on.** The mean tracking residual for those two products. Both are
sub-basis-point-per-day effects against tracking errors of 51-101 bp. Neither enters
the strategy, the tail model, or the survival analysis.

---

## L5. The pre-2013 futures history comes from a different Cboe archive

Contracts expiring before roughly January 2013 are served only by a legacy archive
keyed by month code rather than by settlement date, and dated `MM/DD/YYYY` rather
than ISO. The two archives were cross-validated on 13,127 overlapping cells and
agree in 13,126 (`docs/validation.md` V4), so this is a documented splice rather than
an unexamined one - but it is a splice.

**What it bears on.** Anything computed on 2008-2012. The single disagreement found
was a bad legacy print, adjudicated by curve shape and resolved in favour of the
modern archive.

---

## L6. Reconstructed, not licensed

The index used throughout is a reconstruction from public futures settlement prices,
not the published S&P Dow Jones Indices series. The roll convention was selected on
evidence (`docs/validation.md` V5) rather than taken from the licensed methodology
document, of which only the roll-period definition has been obtained.

**What it bears on.** Everything. It is also what makes the project possible: the
reconstruction extends before the products existed, is free of product fees, and
exposes its own inputs. The tracking validation in V5, V6 and V9 is the evidence
offered in place of a licence.

---

## L7. Market prices, not NAV

The product series used are consolidated closing prices from a free provider,
split-adjusted. Net asset values are not used, because a long free history of them is
not available. L1 is the direct consequence. On stressed days the closing price can
also carry a premium or discount to fair value that is not measured here - 5 February
2018 being the clearest case, where three products agreed with each other to 2.25
percentage points, which argues against large *idiosyncratic* distortion but does not
rule out a common one.

---

## L9. SVIX does not track the index this project reconstructs

SVIX's benchmark is Volatility Shares' own Short VIX Futures Index, which the
prospectus describes as "calculated daily at 4:00 p.m. (Eastern time) from the average
price of the VIX futures contracts between 3.45 p.m. and 4:00 p.m." - a fifteen-minute
average, not the settlement price the S&P index and this reconstruction use. Every
SVIX comparison against the reconstructed index is therefore a benchmark mismatch.

**What it bears on.** SVIX's tracking error, its decay slope (-1.17 against -1.00) and
especially its decay intercept (-8.75%/yr with the slope held at theory). None of
those is evidence for or against the leverage-decay identity. SVIX is kept in the
tables, labelled, because the comparison is still informative about how closely a
differently-priced short-volatility product follows the S&P construction.

---

## L10. The flow result covers a window and two funds

Assets can be bounded only between disclosed anchors, which currently run from
31 December 2014 to 26 February 2018 (794 sessions), and only for SVXY and UVXY among
the geared products. Nothing is claimed outside that window. XIV - the largest -1x
product on 5 February 2018 - and the other ETNs are excluded.

**Consequence.** The lower-bound flow understates the complex by construction, which
makes it a conservative basis for H2. The upper bound is not informative wherever a
fund's share count moved sharply between annual anchors: it exceeds the whole
front-month contract on 7 sessions, and on **7 of the 10** largest up-moves of 2016-2018
the H2 threshold is met only at that bound.

**How thin the support outside 5 February 2018 is** (corrected by the final audit, F-A2;
every version through Phase 15 said 4 of 10 and 6 indeterminate). Three of the ten days
clear 10% at the lower bound, and two of the three clear it by less than a quarter of a
percentage point:

| Date | Lower bound |
|---|---|
| 2016-01-07 | 10.18% |
| 2016-06-13 | 10.23% |
| 2018-02-05 | 25.00% |

The fourth day previously counted, 2017-08-10, is at **9.97%** - it printed as "10.0%" at
one decimal place. H2 is not rejected, because its pre-registered rule is failure at
*both* bounds and no day fails at both; but the hypothesis rests on 5 February 2018, and
the other two supporting days are at the threshold rather than above it.

**Which asset date the flow uses.** The estimate uses assets at `t` rather than `t-1`
(M5). Neither is exactly the quantity a fund rebalances against, and on 5 February 2018
the two give 25.0% and 24.8% at the lower bound. Daily data cannot resolve the
difference.

**What would improve it.** Later ProShares 10-Ks (to extend the window past February
2018) and a daily shares-outstanding source (to replace the bounding assumption in
`docs/methodology.md` M4 with observations).

---

## L11. The decay intercept is not separately identified

The intercept of the decay regression absorbs the fee, the yield on collateral, the
ER/TR distinction, trading costs and any slope error together. Holding the slope at
theory removes the last; the others remain confounded. Intercepts are reported as a
warning-level check, not as estimates of any one cost.

---

## L12. The survival numbers depend on how far the variance dynamics are extrapolated

Under its own dynamics the pre-2018 model generates volatility spirals it never
observed - simulated daily volatility up to 6.9 against an observed maximum of 0.16 -
and 81% of its simulated wipeouts happen inside them. Capping volatility at the
observed maximum raises five-year survival from 81% to 90% (-1x) and from 94% to 99%
(-0.5x). Neither version is the answer; the pair is reported.

**What it bears on.** Every survival figure and the size of the survival gap between
the designs (13 points unbounded, 9 capped). It does not bear on the ordering, which
holds under both.

---

## L13. Tail probabilities in calm states are poorly determined

Far into the tail, small differences in the GPD shape compound. The one-day wipeout
probability in the calm quintile moves by a factor of 8 (-1x) to 25 (-0.5x) across the
threshold grid, and on 12 January 2018 by a factor of 10 to 30. These are reported only
as ranges. The unconditional figures move by less than a factor of three and are
reported as points with their ranges.

---

## L14. Kelly cannot settle whether -1x was too much

The empirical growth-optimal short exposure is estimated with an interval so wide
([0.05, 1.34] on the full sample) that it contains 1.0 - so H4 is rejected - and a
model with an unbounded upper tail implies an optimum of exactly zero. The answer turns
on whether the index's upside is bounded, which the data cannot establish. Stated as a
limit of the method, not of the sample.

---

## L15. The forecast is biased low in level, and weak in calm years

Out of sample the HAR forecast's mean is 12% below the mean outcome. The log residuals
are right-skewed, so the normal-theory retransformation understates the conditional
mean; a smearing correction would raise forecasts by about 9% and cut the share of
VRP-positive days from 87.4% to 81.7%. And the forecast's skill is uneven: in 2013-2019
it barely beats a hindsight constant and its Mincer-Zarnowitz slope is 0.51; in
2008-2012 it is no better than trailing RV on squared error.

**What it bears on.** The VRP filter's on/off state on marginal days, and so the
invested share. Not the sign of the premium on most days: the median gap is 2 volatility
points. Smearing is a Phase 12 robustness variant.

---

## L16. The realised-variance proxy is not the variance the VIX prices

VIX squared is a risk-neutral expectation over 30 calendar days of the S&P 500's
variance. The forecast is of a range-based proxy on SPY over 21 trading days: a
different instrument (SPY, because the index's opening print is stale), a different
estimator (4.6% above close-to-close variance on average, from the intraday range), and
a different day count (252 against an equivalent 255.5, 1.4%). The instrument makes
no measurable difference (close-to-close volatility 18.7% on SPY and on the index). The
estimator **understates** the premium by about 0.0017 in annualised variance at the
sample-average level; the day count **overstates** it by about 0.0005. Net, about 0.001
understated, against a median premium of 0.0077.

**What it bears on.** The level of the VRP, and a few marginal signal days. A
close-to-close proxy is a Phase 12 robustness variant.

---

## L17. The contango signal is filled on 5% of days

`cm30` does not exist on 234 sessions (5.0%) because no listed contract is shorter than
30 days; there it is interpolated from spot VIX. The fill is flagged and agrees with
`VIX/VIX3M` as often as unfilled days do (91.5% vs 91.7%), but it is a construction,
not an observation. Weekly VX contracts, listed since 2015, would observe the point
directly; they are not in the archive this project uses.

**What it bears on.** The contango state on those sessions. Phase 12 reports the
strategy with those sessions forced flat.

---

## L18. The February 2018 escape rests on one day and seven parts in a thousand

The strategy was flat on 5 February 2018 because `cm30/cm90` printed 1.0072 against a
threshold of 1.0 at the close of 2 February. A threshold of 1.01 - inside the grid
Phase 12 sweeps - leaves the position on, and the weight held that day (0.395) against
a +96.1% index move is a 38% loss. The variance-risk-premium filter stayed on
throughout: implied variance rises before realised variance does, so that filter is
pro-cyclical in exactly the state it would need to protect against.

**What it bears on.** Every February 2018 number for the strategy, and the volmageddon
row of the stress table. Not the rest of the record: 2008, 2011, 2015, 2020 and 2024
are losses of 3-8%, none of which turns on a single day's signal.

---

## L19. The dynamic rule does not beat a fixed small short

Out of sample a constant 0.173 short earns a Sharpe of 0.40 against the strategy's
0.27, and 7.0% a year against 5.0%. The signals and the crash budget buy a better
tail - worst day -11.7% against -16.6%, skew -3.0 against -4.1 - not a better ratio.
The strategy's Sharpe is also below the PutWrite index (0.53) and the S&P 500 (0.75).

**What it bears on.** Any claim that the entry rules add return. They do not, on this
sample. The claim the evidence supports is narrower: that sizing by a stated crash
loss rather than by recent volatility changes the shape of the loss distribution -
volatility targeting alone gives a Sharpe of 0.06 and a 43% drawdown.

---

## L20. The benchmarks are simulated, and one of them is sized with hindsight

The buy-and-hold products are daily-rebalanced NAVs on the reconstructed index with
the published fees, not the traded ETPs: the -1x line keeps compounding after
February 2018, where XIV was accelerated and paid out about 4% of its prior value, so
the simulated series is if anything the *kinder* comparison after that date. The
constant-weight benchmark is sized at the strategy's own realised average exposure in
each window, which is a number an investor could not have known in advance; it is a
like-for-like exposure comparison, not an implementable rule. The PutWrite index and
SPY are total returns, and the T-bill accrual is subtracted before every Sharpe.

---

## L21. Costs decide the result

At the configured tick the strategy earns 5.0% a year against 3.2% of costs, so the
answer is roughly "half the gross return goes to friction". At two ticks per side the
out-of-sample Sharpe is 0.01. The tick model charges a full tick on each leg of the
roll, where a calendar spread would usually trade inside that, so the default is
conservative - but the conclusion is not robust to the cost assumption in either
direction, and no result from this strategy should be quoted without it.

---

## L22. The result is specification-dependent, and the chosen cell is a good one

Across the 144-cell grid the out-of-sample Sharpe runs from -0.35 to 0.53 with a
**median of 0.06**. The pre-registered configuration earns 0.27, the 78th percentile.
The parameters were fixed before any data was retrieved and the provenance is in the
commit history, so this is not selection after the fact - but a reader should treat
0.27 as one draw from that distribution rather than as the property of the strategy,
and the median cell as the honest central estimate.

**What it bears on.** Every strategy claim. Phase 13 states them at this confidence,
not at the baseline's.

---

## L23. The crash protection is a property of trading daily, not of the sizing rule

The strategy avoided 5 February 2018 because it acted on a signal generated the
previous close. Rebalancing weekly - the same rule, executed less often - holds the
position through the event: worst day -38.0%, February -31.7%. A threshold 2.5% higher
does the same. The sizing rule caps the loss *given* a position; what kept the position
small enough to matter on that day was the entry filter, and the entry filter needs
same-day execution.

**What it bears on.** Any claim that crash budgeting alone makes the trade survivable.
The evidence supports a narrower claim: budgeting bounds the loss from a position you
are still holding (Sharpe 0.27 against 0.06 for volatility targeting alone, drawdown
-26% against -43%), and the filters decide whether you are holding one.

---

## L24. Two tracking errors, and which one the hypothesis used

H1 is written on the raw difference between the product's return and the leveraged
index return. A regression residual - letting a fitted slope and intercept absorb the
attenuation - is the smaller number (133.2 against 120.7 bp a day in 2011-2015; 31.7
against 31.0 after October 2020) and was what `docs/validation.md` V6 reported until
Phase 13. Both are now in `index_tracking_eras.csv`, labelled. The verdict is the same
under either.

**What it bears on.** The size of the tracking-error numbers quoted for H1, by about
10%, and nothing else. The regime shift - a factor of four across the settlement-time
change - is the finding, and it is the same in both columns.

---

## L8. Open questions carried forward

1. The 2016 and 2019 steps in the tracking-error series are unexplained (L1).
2. Post-October-2020 slopes are 0.985, 0.991 and 0.971 rather than 1.000. Whether the
   residual 1-3% is product tracking difficulty, fee drag mis-attributed to the
   slope, or remaining index noise is not resolved.
3. The decay intercepts (L11).
4. Whether the H2 threshold is met on the six large 2016-2018 up-moves where it is
   met only at the upper asset bound (L10).
5. Why the intraday range exceeds the squared open-to-close return by 14% on SPY
   (L16): intraday mean reversion and microstructure in highs and lows are both
   consistent with it.
6. Resolved in Phase 12: it does not survive a 2.5% change in the threshold or a
   weekly rebalance (L22, L23).
7. Why a 21-day rebalance beats a daily one is not separated into cost saving and
   luck around February 2018.
