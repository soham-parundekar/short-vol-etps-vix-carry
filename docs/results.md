# Results

What the numbers say, at the confidence the evidence supports.

Every figure in this document is traceable to a committed table; the table is named
beside it, and `python scripts/check_results_numbers.py` re-reads the tables and
asserts the figures quoted here (it exits non-zero on any disagreement, so a pipeline
change that moves a number cannot leave this document quietly wrong). Where a number is a derivation rather than a table entry, the derivation is
in `docs/validation.md` at the section named. The hypotheses and their rejection
criteria were fixed in `docs/research_design.md` before any data was retrieved (commit
2bdeb31, 07:40:36 UTC on 20 September 2026; first data retrieval 08:30:04 UTC), and
nothing below reinterprets a criterion: §9 of that document records where the evidence
leaves each claim.

---

## 1. Hypothesis verdicts

Written from the pre-registered criteria, before any narrative.

| | Predicted | Found | Criterion | Verdict |
|---|---|---|---|---|
| **H1** | The reconstructed index tracks VIXY and VXX within 10 bp/day net of fees | **133.2 bp/day** (2011-2015) falling to **31.7 bp/day** after 26 Oct 2020; leverage-adjusted slope 0.873 rising to 0.985 (`index_tracking_eras.csv`) | rejected if > 25 bp/day or residuals correlate with the roll weight | **Rejected** |
| **H2** | Mechanical rebalancing demand exceeded 10% of front-month open interest on the largest up-moves of 2016-18 | 25.0% of front-month open interest on 5 Feb 2018 at the lower asset bound (`rebalancing_flows.csv`) | rejected if it fails at *either* bound on those days | **Not rejected** - supported at the lower bound on 4 of 10 days, indeterminate on 6 |
| **H3** | Under a model fitted to data ending 2017-12-31, P(index +80% in a day) >= 10x P(+160%), with a threshold-stable survival gap | ratio **8.7x**; ordering holds at every EVT threshold; five-year survival gap 12.6 points unbounded, 8.7 capped (`termination_probabilities.csv`, `survival_curves.csv`, `survival_by_threshold.csv`) | rejected if the ordering reverses, the gap is threshold-dependent, or the event is not foreseeable | **Not rejected, stated magnitude unmet** |
| **H4** | Kelly-optimal short exposure strictly below 1.0, bootstrap interval excluding 1.0 | 0.62 [0.05, 1.34] full sample; **1.11 [0.22, 2.07]** pre-2018 (`kelly.csv`) | rejected if the interval contains 1.0 | **Rejected** |
| **H5** | Positive out-of-sample Sharpe net of costs, **and** alpha over PUT/SPX/VXX indistinguishable from zero | Sharpe **0.27** (Lo se 0.31); alpha **-1.4% a year**, t = -0.52 (`performance_oos.csv`, `alpha_regression.csv`) | rejected if either half fails | **Not rejected** |

Two of the five were rejected by their own criteria, one passed with its stated
magnitude unmet, and the two that were not rejected are weaker than their sentences
sound. That is the result.

---

## 2. Findings

### 2.1 The index and the products disagree because they are measured at different times

**What happened.** Tracking error between the reconstruction and VIXY is 133.2 bp a day
in 2011-2015 and **31.7 bp a day** from 26 October 2020, with the leverage-adjusted
slope rising from 0.873 to 0.985 (`index_tracking_eras.csv`; the regression-residual
definition of the same thing, which lets a fitted slope absorb the attenuation, gives
120.7 and 31.0). Over 2011-2017 that slope is 0.877 for VIXY (+1x), 0.872 for SVXY
(-1x) and 0.867 for UVXY (+2x) (`index_tracking.csv`).

**Mechanism.** VX futures settled at 3:15 p.m. CT until 23 October 2020 and at
3:00 p.m. CT after (`references/references.bib`, the two Cboe notices; V6). The
products' closing prices are struck at 4:00 p.m. ET. Before the change, the index and
the product were measured fifteen minutes apart; after it, at the same instant. A
common slope below one across three leverages and three issuers is attenuation from
noise in the regressor - the reconstruction - not product-specific tracking difficulty.

**Alternative explanation.** Fee drag, product tracking error, or an error in the
reconstruction itself. Against those: fees and tracking difficulty are product-specific
and would not produce one common factor; a reconstruction error would not disappear on
the date the settlement time changed. Residual slopes of 0.985, 0.991 and 0.971 after
October 2020 leave 1-3% unexplained (V6 open item).

**What the data cannot distinguish.** How much of the residual 1-3% is fee drag
mis-attributed to the slope rather than remaining index noise. Daily data cannot say.

**Economic significance.** On 5 February 2018 the difference is not a detail: the
settlement-based return is +96.1% and the three products' 4:00 p.m. closes imply
+32.0% to +34.2% (V9). In log terms **57.5% of that day's move happened after
4:00 p.m. ET**. Any statement about "the index's worst day" is therefore a statement
about a measurement convention as much as about the market.

### 2.2 The leverage-decay identity holds, and one block is why it appears not to

**What happened.** Over non-overlapping 21-day blocks the decay slope matches theory
for every product and regime except two, and both exceptions are the February 2018
block (`leverage_decay.csv`): SVXY at -1x gives -2.846 against a theoretical -1.000
over the full window and **-1.087 excluding that block**; UVXY at +2x gives -0.732
against -1.000, and -0.946 excluding it.

**Mechanism.** The identity `-(L^2-L)/2` is a second-order approximation. Over a block
containing a +96% day it is not accurate, and the block is also a 40x leverage point in
the regression (leave-one-block-out influence, `decay_influence.csv`).

**Alternative explanation.** That the products genuinely decayed faster than the
identity implies - which the excluding-that-block fits reject, and which the
approximation-error calculation (`decay_approximation_error.csv`) explains directly.

**Economic significance.** The identity costs a -1x product `(L^2-L)/2 = 1` times
realised variance. At a 60% annualised index volatility that is 0.36 in log terms a
year - about **30% of capital**, before fees - and the index's own volatility over the
sample is higher. It is the mechanical part of why these products lose money over time.

### 2.3 Mechanical rebalancing demand was large relative to the open interest that had to absorb it

**What happened.** On 5 February 2018, SVXY and UVXY together needed to buy an
estimated **55,690 front-month contracts** at the lower asset bound - **25.0% of that
contract's open interest** (`rebalancing_flows.csv`). The front VX contract closed at
33.20 - its high of the day - on 567,407 lots (`docs/validation.md` V9, quoting the
contract file).

**Mechanism.** A product at leverage `L` must trade `L(L-1) A r` at the close to
maintain its multiple; for -1x and +2x, `L(L-1) = 2`, so a +96% day requires buying
roughly twice the fund's assets.

**Alternative explanation.** Ordinary hedging demand, short covering, or discretionary
buying into the settlement window. The data cannot separate these from the mechanical
demand: it establishes the size of the requirement, not who filled it.

**What the data cannot distinguish.** Whether the flow *caused* the move. It is stated
as consistent with the account, not as a demonstration of it. An earlier draft of V9
said "forced buying"; that was stronger than the evidence and was corrected.

**Economic significance.** The de-levering counterfactual is the cleanest statement of
what the design change was worth: holding the same assets and the same shock and
changing only the coefficient from 2.0 to 0.75, the required trade falls from 55,690 to
**20,884 contracts, 25.0% to 9.4%** of front-month open interest
(`delevering_counterfactual.csv`). That is arithmetic, not an estimate - but it puts the
post-2018 product suite below the threshold H2 was written around.

### 2.4 The wipeout was foreseeable in order of magnitude; the timing was not

**What happened.** A GJR-GARCH model with a spliced GPD tail, fitted on data ending
31 December 2017 and never refitted, implies a one-day wipeout of a -1x product
(index +80%) about **once in 79 years** unconditionally, 1 in 2,835 in the calmest
quintile of volatility states, and **1 in 12.8 years for 5 February 2018 given data
through 2 February** (`termination_probabilities.csv`, `exante_warning_path.csv`).
The warning rose from 1 in 3,877 years on 12 January to 1 in 12.8 - three-hundredfold
- and still stood at about 1 in 3,200 trading days on the morning of the event.

**Mechanism.** The volatility state is the driver: the same parameters, updated only
with each day's return, move the implied return period by orders of magnitude.

**Alternative explanation.** That the model is simply mis-specified in the tail. Tested
three ways: the ordering and the survival gap hold at every threshold in the grid
(`survival_by_threshold.csv`); removing the largest pre-2018 day moves the ex-ante
number by 25% (`tail_jackknife.csv`, inside the 50% tolerance); exceedance rates by
volatility quintile show no under-reaction in calm regimes (p = 0.56,
`evt_calibration_by_sigma.csv`).

**What the data cannot distinguish.** How far the model's own volatility dynamics may
be extrapolated. Simulated unbounded, it generates daily volatility up to 6.9 against an
observed maximum of 0.16, and 81% of simulated wipeouts occur inside those spirals
(`simulation_diagnostics.csv`). Five-year survival is therefore reported as a pair:
**81.1% unbounded, 89.9% capped** for -1x, and 93.7% / 98.6% for -0.5x
(`survival_curves.csv`). The gap between the designs - 12.6 points unbounded, 8.7
capped - is the stable part.

**Economic significance.** 1 in 79 years is a 1.3% chance per year of losing
essentially everything. A product marketed for a multi-year holding period with that
hazard is not mispriced by a small margin; and the stated H3 magnitude (10x) was not
met at 8.7x, so the -0.5x design is safer by less than the hypothesis claimed.

### 2.5 Kelly could not rule out a full -1x short - and before the crash it favoured one

**What happened.** The empirical growth-optimal short is 0.62 with a bootstrap interval
of [0.05, 1.34] on the full sample and **1.11 [0.22, 2.07] on pre-2018 data**
(`kelly.csv`). H4 is rejected: the interval contains 1.0.

**Mechanism.** Expected log growth is flat near its optimum, and the bootstrap interval
on a distribution with this skew is wide.

**Alternative explanation.** That the optimum is genuinely below 1.0 and the sample is
too small to show it. This is exactly what the data cannot settle, which is why H4's
criterion was written as an interval test rather than a point comparison.

**What the data cannot distinguish.** Whether the upside is bounded. Under the fitted
tail (xi > 0, unbounded support) every short has positive ruin probability, so the
model-implied optimum is exactly zero; the simulated "Kelly" figures (0.014, 0.059) are
one over the largest simulated draw and are not estimates (`kelly.csv`, note column).

**Economic significance.** At the full-sample optimum, expected log growth is 13.1% a
year; at a full -1x short it is about +1.6%. The cost of over-sizing is therefore about
11.5 points of annual compound growth - large, but not the catastrophe a naive reading
of "Kelly says 0.62" suggests, which is why the criterion was an interval.

### 2.6 The variance forecast has modest real skill, and the premium filter is pro-cyclical

**What happened.** Real-time HAR forecasts of 21-day realised variance achieve an
out-of-sample R^2 of **0.285** with a Mincer-Zarnowitz slope of 0.91, against 0.060 and
0.53 for trailing realised variance (`har_oos_diagnostics.csv`). The variance risk
premium is positive on 87.4% of days and the contango filter is on 83.1%
(`signal_statistics.csv`).

**Mechanism.** The HAR's gain over trailing variance is calibration, not correlation:
the two correlate with the outcome almost identically (0.54 against 0.53), but trailing
variance is over-dispersed (slope 0.53).

**Alternative explanation.** That the R^2 is an artefact of the two crisis periods. The
sub-period table says partly: in 2013-2019 the R^2 against a hindsight constant is
0.005 (0.574 against the real-time expanding mean) and the slope is 0.51.

**Economic significance.** The premium filter is the one that does not work when it
matters. On 5 February 2018 it was **on**, with a VRP of 0.115 - implied variance
jumps before realised variance does, so the filter reads a volatility explosion as a
better selling opportunity (`signals_daily.csv`, V29). The term-structure filter, not
the premium filter, is what kept the strategy out.

### 2.7 Crash budgeting changes the loss distribution; it does not create return

**What happened.** Out of sample the strategy earns a Sharpe of **0.27** (Lo standard
error 0.31), 5.0% a year with a -26.3% drawdown, a worst day of -11.7% and a worst week
of -13.5% (`performance_oos.csv`). Volatility targeting without the crash budget earns
0.06 with a -43.2% drawdown (`backtest_variants.csv`). A constant short at the same
average exposure earns **0.40** with a worst day of -16.6%.

**Mechanism.** The budget caps size by a stated crash loss rather than by recent
volatility, so it does not expand the position in calm periods - which is where
volatility targeting would be largest and where the spikes begin. It binds on 45.7% of
out-of-sample days (`backtest_daily.csv`).

**Alternative explanation.** That the difference between 0.27 and 0.06 is one period's
luck rather than the rule. Against it: the drawdown difference (-26% against -43%) and
the worst-day difference are distributional, not a single episode. For it: the whole
result is specification-dependent (2.8), and the two numbers come from the same single
history.

**What the data cannot distinguish.** Whether the sizing rule or the entry filters
deserve the credit for February 2018. The decomposition says the filters: with the
signals removed and the budget left in place, the worst day is -24.2%
(`backtest_variants.csv`).

**Economic significance.** 5.0% a year against 3.2% of transaction costs and a 2.3%
collateral yield, with a Sharpe indistinguishable from zero and below the PutWrite
index (0.53) and the S&P 500 (0.75) over the same window (`performance_oos.csv`). As an
investment case that is not one. As a demonstration that the sizing rule changes the
shape of the loss distribution, it is evidence.

### 2.8 The strategy result is specification-dependent, and the chosen cell was a good one

**What happened.** Across 144 specifications the out-of-sample Sharpe runs from -0.35 to
0.53 with a **median of 0.06**; the pre-registered configuration's 0.27 is the 78th
percentile, and 64.6% of cells are positive (`specification_distribution.csv`).

**Mechanism.** Two choices dominate: the contango threshold decides whether the
position is held into February 2018, and the rebalance interval decides whether the
exit signal can be acted on. At a threshold of 1.025 the February return is -24.3%; at a
5-day rebalance it is -31.7% with a worst day of -38.0% (`robustness_parameters.csv`).

**Alternative explanation.** That the pre-registration makes the 0.27 the right number
to quote. The parameters were fixed before any data was retrieved and the commit
history proves it (V24), so 0.27 is not a mined result - but a pre-registered draw from
a distribution whose median is 0.06 is still a draw, and both numbers belong in any
honest summary.

**Economic significance.** The breakeven transaction cost is **2.05 ticks per side**
(`robustness_costs.csv`). One tick is the quoted spread in calm markets; two is not
unusual in a crisis, which is when this strategy trades most.

---

## 3. Conclusions, with their qualifications attached

1. **The February 2018 wipeout was foreseeable in order of magnitude from a model
   fitted before it, but not in timing** - 1 in 79 years unconditionally, 1 in 12.8 for
   the day itself given data through the previous close, and still about 1 in 3,200
   trading days on the morning. *Qualification*: the five-year survival probability
   depends on how far the volatility dynamics are extrapolated (81% unbounded, 90%
   capped), and the stated 10x ordering between designs came in at 8.7x.
2. **Mechanical rebalancing demand on that day was at least a quarter of front-month
   open interest, and the 2018 de-levering would have cut it to 9.4%** - arithmetic
   from disclosed assets and the leverage identity. *Qualification*: SVXY and UVXY
   only, so it understates the complex; it is a statement about the size of the
   requirement, not about who filled it or about causation.
3. **Sizing by a stated crash loss rather than by recent volatility changes the loss
   distribution** - Sharpe 0.27 against 0.06, drawdown -26% against -43%.
   *Qualification*: the median specification earns 0.06, a constant-weight short earns
   0.40 with a worse tail, and the strategy earns nothing at 2.05 ticks of cost.
4. **The reconstruction's disagreement with the traded products is a measurement-time
   artefact, not an error** - tracking error falls from 133.2 to 31.7 bp a day on the
   date the settlement time changed. *Qualification*: 1-3% of the post-2020 slope
   remains unexplained.
5. **Nothing here establishes skill.** The alpha over PUT, SPX and a VXX-like factor is
   -1.4% a year (t = -0.52) and insignificant in all five specifications tried.
   *Qualification*: with PUT and SPX correlated at 0.897 the individual loadings are not
   identified; only the alpha is.

---

## 4. What this does not show

Specific to this project, not generic:

- **That rebalancing flow caused the 5 February 2018 move.** Daily data gives the size
  of the mechanical requirement and the closing print; it cannot attribute the fifteen
  minutes of buying.
- **That the strategy would have been implementable at the quoted costs.** The cost
  model charges one tick per side on both legs of every roll, which is conservative in
  calm markets, but on 5 February 2018 the realistic cost of trading VX at the close is
  not something this data can establish.
- **That the -0.5x design is ten times safer than -1x.** It is 8.7 times safer on the
  headline threshold and between 5.3 and 9.4 across the grid.
- **That XIV's investors could have acted on the ex-ante warning.** The model's return
  period moved from 1 in 1,941 years on 29 January to 1 in 294 on 2 February and 1 in
  12.8 for 5 February (`exante_warning_path.csv`); acting on it required both the model
  and the willingness to exit on a morning that still read as 1 in 3,200 trading days.
- **That any of this generalises beyond VIX futures in 2008-2026.** One asset class,
  one history, one crash of this size in it.
- **That the strategy's 0.27 Sharpe is its expected return.** The standard error is
  0.31 and the specification median is 0.06.
- **That the reconstructed index is the licensed S&P index.** It is an independent
  reconstruction that tracks the products to 32 bp a day in the era where they are
  measured together (L6).

---

## 5. The three findings that are genuinely informative

1. **The settlement-time change (2.1).** It converts an apparent reconstruction failure
   into a dated, documented measurement artefact, and it explains why the index's worst
   day is three times the move the products themselves recorded. It is the only finding
   here that would change how someone reads *other* people's VIX-futures research.
2. **The de-levering counterfactual (2.3).** 25.0% to 9.4% of front-month open interest,
   from arithmetic on disclosed assets. It puts a number on what the 2018 product
   redesign did to the mechanical demand the market has to absorb in a spike - the
   question the whole episode raised.
3. **The gap between 0.27 and 0.06 (2.8).** A pre-registered configuration that lands in
   the upper quartile of its own specification grid is the most useful warning this
   project produces about backtests in general, including this one.

What is *not* in that list: the strategy's positive Sharpe. It is the headline the
project was built to test, and the evidence leaves it indistinguishable from zero and
below a constant-weight short.

---

## 6. Causal-language audit

Every sentence in this document containing "because", "caused", "drove" or "led to" was
re-read against its evidence. Two survive as causal claims, both about measurement
rather than markets: the tracking error falls *because* the settlement time changed (a
dated administrative fact, with the regime break at that date), and a -1x product must
trade twice its assets *because* of the leverage identity (arithmetic). Every statement
about the February 2018 price path is phrased as consistency, not causation.
