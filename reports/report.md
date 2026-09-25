# When Carry Kills

**Short-volatility ETPs, rebalancing feedback, and a crash-budgeted VIX carry strategy**

Soham Parundekar · September 2026

Code and data pipeline: <https://github.com/soham-parundekar/short-vol-etps-vix-carry>

---

## Key findings

**The reconstructed index and the products that tracked it were measured fifteen minutes
apart until October 2020, and that timing — not fee drag or tracking difficulty —
accounts for most of their apparent disagreement: tracking error against VIXY falls from
133.2 bp a day in 2011–2015 to 31.7 bp a day after the settlement time changed, and on
5 February 2018 57.5% of the index's +96.1% move, in log terms, occurred after the
products' 4:00 p.m. close.** On that day the mechanical rebalancing demand of SVXY and
UVXY alone was an estimated 55,690 front-month VX contracts, 25.0% of that contract's
open interest at the lower asset bound, which the 2018 de-levering to −0.5× and +1.5×
would have reduced to 20,884 contracts and 9.4% — arithmetic from disclosed assets and
the leverage identity, not an estimate. **Bounding position size by an explicitly
estimated crash loss rather than by recent volatility does change the loss distribution —
an out-of-sample Sharpe of 0.20 and a −26.8% drawdown against −0.03 and −43.5% for
volatility targeting alone — but it does not create return: a constant 0.173 short earns
0.40 over the same window, the strategy's alpha over PUT, SPX and a VXX-like factor is
−2.2% a year (t = −0.77), and the median of the 144-specification grid from which the
pre-registered configuration was drawn is 0.06.**

---

## Contents

1. [Introduction](#1-introduction)
2. [Institutional background and what the filings say](#2-institutional-background-and-what-the-filings-say)
3. [Data](#3-data)
4. [Methodology](#4-methodology)
5. [Results](#5-results)
6. [Robustness and red-team](#6-robustness-and-red-team)
7. [Discussion](#7-discussion)
8. [Limitations](#8-limitations)
9. [Conclusion](#9-conclusion)
10. [References](#10-references)

Every numeric claim below names the committed table it comes from.
`python scripts/check_results_numbers.py` re-reads those tables and asserts the figures
quoted in this report and in `docs/results.md`; it exits non-zero on any disagreement.

---

## 1. Introduction

On Monday 5 February 2018 the VIX rose from 17.31 to 37.32 and the front VX futures
contract settled at its high of the day. Two exchange-traded products offering the same
−1× daily exposure to the same index met different ends. Credit Suisse announced the
acceleration of XIV the following morning, citing the clause in its pricing supplement
that is triggered when the intraday indicative value falls to 20% or less of the prior
closing indicative value (`filing_terms.csv`; the 8-K exhibit states the prior close of
$108.3681 and names 5 February as the acceleration event date). ProShares' SVXY, a fund
rather than a note and therefore carrying no such clause, lost about 90% of its value and
survived; three weeks later ProShares changed its objective to −0.5× and UVXY's from +2×
to +1.5×, effective at the close of 27 February 2018 (`filing_terms.csv`, ProShares Trust
II 10-K for FY2017, Note 9).

The episode raises three questions that are separable and individually testable.

**Was the short-volatility trade a risk premium or compensation for a crash?** The
variance risk premium — implied variance systematically above subsequently realised
variance — is well documented (Carr & Wu, 2009; Bollerslev, Tauchen & Zhou, 2009), and
the VIX futures term structure is in contango most of the time, so a short position in a
rolling front-month basket earns carry. Whether that carry is a premium an investor can
keep depends on what the left tail costs.

**Did the products' own design contribute to the move?** A fund at daily leverage `L`
must trade `L(L−1)·A·r` at the close to maintain its multiple. For `L = −1` and `L = +2`
the coefficient `L(L−1)` is 2 in both cases, so an inverse fund and a double-long fund
*both buy* after the index rises. Cheng & Madhavan (2009) derive this; Augustin, Cheng &
Van den Bergen (2021) document its role in February 2018. The size of that requirement
relative to the open interest that had to absorb it is measurable from disclosed assets.

**Can the premium be harvested if position size is bounded by what a crash would cost?**
Volatility targeting — the standard answer — sizes largest when realised volatility is
lowest, which in this asset is precisely the state from which spikes begin. The
alternative tested here sizes by an explicitly estimated crash loss:
`w = min(σ*/σ̂, ℓ_max/StressLoss, w_max)`.

Five hypotheses, each with a stated rejection criterion, were committed to the repository
at 07:40:36 UTC on 20 September 2026, fifty minutes before the first data retrieval at
08:30:04 UTC (`docs/research_design.md`; commit 2bdeb31; the timing is verified in
`docs/validation.md` V24). Nothing in this report reinterprets a criterion. Two of the
five hypotheses were rejected, one passed with its stated magnitude unmet, and the two
that were not rejected are weaker than their sentences sound. That is reported as the
result rather than reframed.

### What is and is not new

The components are individually standard, and `docs/literature_review.md` says so: the
term-structure signal is Simon & Campasano (2014); the rebalancing identity is Cheng &
Madhavan (2009); the decay identity is Avellaneda & Zhang (2010); the HAR forecaster is
Corsi (2009); the conditional-EVT tail model is McNeil & Frey (2000). Three things here
are not standard practice:

1. **An ex-ante survival comparison across product designs.** The tail model is estimated
   on data ending 31 December 2017 and never refitted, so the probability it assigns to
   Volmageddon is genuinely out of sample; the same model prices the −0.5× design, which
   turns "de-levering helped" into a survival curve with a number attached.
2. **Offered leverage against growth-optimal leverage.** The Kelly fraction on the same
   index, with a bootstrap interval, compared directly with the −1× the products sold.
3. **Sizing by a stated crash loss rather than by recent volatility**, evaluated against
   the specification distribution it was drawn from rather than reported alone.

---

## 2. Institutional background and what the filings say

Every product term this project asserts is taken from a filing retrieved from SEC EDGAR,
quoted, and checked against the configuration by a regular expression; the record is
`reports/tables/filing_terms.csv`, which stores the document, the form type, the claim,
the pattern, and the matched quotation. Twenty-eight terms were verified this way. The
ones the analysis depends on:

| Product | Structure | Objective | Fee | Source |
|---|---|---|---|---|
| XIV | ETN (Credit Suisse) | −1× daily, S&P 500 VIX Short-Term Futures Index | 1.35%/yr investor fee factor | 424B2, 30 June 2017 |
| VXX | ETN (Barclays) | +1×, the **total-return** index | 0.89%/yr | Series B 424B2, Jan 2018 |
| SVXY | ETF (ProShares Trust II) | −1× daily → **−0.5×** from 27 Feb 2018 | 0.95%/yr management fee | 424B3 Feb 2018; 10-K FY2017 |
| UVXY | ETF (ProShares Trust II) | +2× daily → **+1.5×** from 27 Feb 2018 | 0.95%/yr | same |
| VIXY | ETF (ProShares Trust II) | +1× | 0.85%/yr | same |
| SVIX | ETF (VS Trust) | −1× daily, **its own index** priced 3:45–4:00 p.m. ET | 1.35%/yr | 424B3, Jan 2022 |

Four features of this table do analytical work later.

**The acceleration clause is a structural difference, not a difference in exposure.**
XIV's pricing supplement grants the issuer an optional acceleration right and an event
acceleration at 20% of the prior close; SVXY, as a series of a Delaware statutory trust,
has no analogue. Two products with identical daily objectives therefore had different
survival functions on the same path. This is why H3 is framed as a comparison of
*designs* (−1× against −0.5×) rather than of issuers.

**The de-levering has a dated, disclosed effective time.** The 10-K states "effective as
of close of business on February 27, 2018". The configuration stores 2018-02-28 because
that is the first daily *return* computed under the new objective, and the data confirms
it: implied leverage on 27 February is −1.21 for SVXY and +2.48 for UVXY, and on
28 February −0.24 and +1.13 (`filing_terms.csv`, note column). The leverage-decay
regression uses that break date; getting it wrong by one day would mix regimes across the
largest observation in the sample.

**The products' NAV calculation time is 4:15 p.m. ET, and their market close is
4:00 p.m. ET, while the index is struck at the futures settlement.** Until 23 October
2020 the VX settlement was 3:15 p.m. CT (4:15 p.m. ET); from that date, 3:00 p.m. CT
(4:00 p.m. ET). This is the single most consequential institutional fact in the project
and is developed in §5.1.

**VXX tracks the total-return index; the ETFs track the excess-return index.** The
reconstruction is built as an excess-return index with a total-return variant that adds
the T-bill accrual on the S&P DJI convention — the same convention the ETN pricing
supplement's "Daily Accrual" describes, with the three-month Treasury rate of the prior
index business day.

**Scope note.** The flow analysis covers SVXY and UVXY only, because they are the only
geared products in the sample with disclosed asset anchors in the archived filings. XIV
and the other ETNs are excluded, so every flow estimate **understates** the complex's
total mechanical requirement.

---

## 3. Data

Sample: 2 January 2008 to 18 September 2026, daily, 4,711 index sessions. All sources are
free and public and none requires registration, an API key, or the circumvention of any
access control. Raw data is not redistributed: `scripts/fetch_data.py` retrieves it and
`data/raw/_manifest.json` records, for each of 338 files, its URL, retrieval timestamp
and SHA-256.

| Dataset | Source | Role |
|---|---|---|
| VX futures settlement, OHLC, volume, open interest, per expiry | Cboe (modern per-expiry archive + legacy archive for Jan 2008 – Aug 2014 expiries) | Index rebuild, term structure, flow denominator |
| VIX, VIX3M, VIX9D, VIX6M, VVIX, PUT, BXM | Cboe index history | Implied leg of the VRP, slope robustness variant, PutWrite benchmark |
| VXX, VIXY, SVXY, UVXY, SVIX, SPY, ^GSPC | Yahoo Finance (Stooq fallback) | Tracking validation, decay test, realised-variance proxy |
| DTB3, DGS3MO | FRED | Collateral accrual |
| Product filings (424B2, 424B3, 8-K, 10-K) | SEC EDGAR | Every product term asserted |

Full provenance, including retrieval policy and rate limits: `docs/data_sources.md`.

### Three data hazards handled explicitly

**Reverse splits.** VXX and UVXY have reverse-split repeatedly. The split adjustment is
reconstructed independently from the ratio of adjusted to unadjusted closes and checked
against the provider's own adjustment; the ProShares 424B3 documents the 2017 SVXY 2-for-1
and the VIXY/UVXY 1-for-4 reverse splits, which the reconstruction matches.

**The VIX3M history begins on 18 September 2009**, inside the design window. The primary
term-structure signal is therefore the interpolated `cm30/cm90` slope from the futures
curve itself, which is available from the start of the sample; `VIX/VIX3M` is carried as a
robustness variant. The choice was fixed at commit 3db0269, before any data was
retrieved, and was not selected on performance.

**Assets outstanding are not observed daily.** Because the flow estimate is linear in
assets, assets are **bounded, never point-estimated**. Anchors are net assets and share
counts for SVXY, UVXY and VIXY at the ends of 2014–2017 and on 26 February 2018, all
quoted from the ProShares Trust II 10-K for FY2017. Between consecutive anchors the
adjusted share count is taken to lie between the two anchor values (lower bound the
smaller, upper the larger); outside the first and last anchor nothing is claimed and the
dates are flagged and excluded. Construction and the checks that raise are in
`docs/methodology.md` M4. The band is narrow where the share count was stable and very
wide where it was not — SVXY's adjusted share count rose 9.6-fold between 29 December 2017
and 26 February 2018 — which is why the H2 claim is stated at the **lower** bound.

### The realised-variance proxy

Daily variance is the squared overnight log return plus the Rogers–Satchell intraday range
estimator, on **SPY** OHLC. Three decisions, each with evidence in
`variance_proxy_comparison.csv` (methodology M7):

- *SPY, not the S&P 500 index.* The index's opening print equals the previous close on 14%
  of days (SPY: 0.9%) because it is computed from constituents that have not yet traded,
  so its overnight return is mostly missing.
- *A range estimator, not squared returns.* Daily log-variance has a standard deviation of
  2.49 for squared close-to-close returns against 1.25 for the chosen proxy, and
  first-order autocorrelation 0.28 against 0.57.
- *Not Yang–Zhang*, which is a window estimator with no single-day value; its components
  are used directly. A 21-day Yang–Zhang correlates 0.999 with the 21-day average of the
  proxy.

The proxy averages 19.1% annualised, 4.6% above close-to-close variance. That direction
*understates* the measured premium, which is noted in `docs/limitations.md` L16 rather
than adjusted away.

---

## 4. Methodology

Full detail, including every convention and parameter, is in `docs/methodology.md`. This
section states what is done and why.

### 4.1 Index reconstruction

Two nearest monthly VX contracts with roll weight `w1 = dr/dt` linear in business days
across a roll period running from one settlement date to the next (the S&P Dow Jones
convention). The critical detail: **the daily return prices the contracts held at `t−1` on
both days.** Differencing a "front month" series instead books the calendar spread as a
price move on every roll date. A synthetic panel in which the term structure is steeply
sloped but every contract's own price is constant must produce exactly zero index return;
the reconstruction returns zero, while a naive front-month `pct_change()` books a fake loss
above 2% on every roll date (`docs/validation.md` V4). Both plausible roll conventions were
built and the choice made on evidence: the S&P DJI convention gives lower residual
dispersion against every product and no significant residual loading on the roll weight
(`roll_convention.csv`; for VIXY, `t = −0.61`, `p = 0.54`).

The settlement calendar is derived from the contract specification — the Wednesday thirty
days before the third Friday of the following month, adjusted for holidays — and
unit-tested against known expiries.

### 4.2 Product mechanics

**Rebalancing.** `ΔE_t = L(L−1)·A_{t−1}·r_t` per fund, summed over SVXY and UVXY at each
asset bound, converted to contracts at `$1,000 × F1` and expressed against the open
interest of the front contract and of the front two.

**Decay.** `V_T/V_0 = (I_T/I_0)^L · exp(−½(L²−L)σ²T)`, tested by regressing
`ln(V_T/V_0) − L·ln(I_T/I_0)` on realised variance over non-overlapping 21-day blocks,
separately before and after the documented February 2018 leverage change, with 63-day
blocks and overlapping windows with Newey–West errors as cross-checks.

### 4.3 The tail model

A GJR-GARCH(1,1) with Hansen (1994) skewed-*t* innovations on daily index log returns,
fitted on data ending 31 December 2017 (`garch_fit.csv`: persistence 0.938, ν = 5.75,
λ = 0.201, α = 0.279, γ = −0.245, β = 0.781; four starts from each of two seeds agreeing
to 6.3 × 10⁻⁷). A Generalised Pareto distribution is then fitted to standardised residuals
above a threshold chosen by a rule fixed in advance (McNeil & Frey, 2000), on pre-2018
residuals only: the 92.5% quantile, 189 exceedances, ξ = 0.181 (`evt_thresholds.csv`). The
innovation law is spliced — rescaled skewed-*t* below the threshold, GPD above it carrying
exactly the empirical exceedance mass.

A one-day index simple return of `w/|L|` removes a share `w` of a product at leverage `L`;
with `w = 0.8` that is +80% for −1× and +160% for −0.5×. Unconditional probabilities are
the one-day conditional probability **averaged over every day of the fitting sample**, not
evaluated at the average volatility, which would understate them because the probability is
convex in volatility. Survival is by Monte Carlo over five years, 20,000 paths, run twice:
with the model's own volatility dynamics and with conditional volatility capped at its
2008–2017 maximum.

Kelly is `argmax E[ln(1 − f·R)]` on daily simple returns with a 1,000-replication
stationary bootstrap (Politis & Romano, 1994), mean block 21 days. No model-based estimate
is offered: with an unbounded fitted tail (ξ > 0) the model-implied optimum is exactly zero.

### 4.4 Forecasting and signals

Corsi's HAR with daily, weekly and monthly components at horizon `h = 21` trading days,
estimated in logs. The **target is the log of the arithmetic average variance** over
`t+1 … t+h`, not the average of daily log variance — an early implementation targeted the
geometric mean, which is a materially different quantity and biased the premium; the
correction is documented in `docs/validation.md` V20a and is covered by three regression
tests that fail on the old code. Forecasts are retransformed by `exp(μ + σ²/2)` with σ² the
training residual variance, with Duan smearing as a reported variant. Real-time forecasts
use an expanding window from 1,000 feature rows, refit every 21 trading days, trained only
on rows whose targets were fully realised by the forecast date.

`VRP_t = (VIX_t/100)² − 252·forecast_t` in annualised variance. The unit conversion lives in
one function, is tested by hand, and is checked on a real date against the raw Cboe file.
The 252-vs-255.5 convention mismatch overstates the premium by about 0.0005 against a median
VRP of 0.0077; it is stated in L16 rather than adjusted, alongside the proxy's larger
opposite effect.

The term-structure signal is `cm30/cm90`. The interpolated curve leaves `cm30` missing on
234 sessions (5.0%) when no listed contract is shorter than 30 days; on those days `cm30`
is interpolated between spot VIX (the curve's observable zero-maturity point) and the front
contract, each fill flagged. Contango is on when `slope < 1.0`; VRP is on when `VRP > 0`;
the position requires both. A missing input gives no position, never a default.

### 4.5 The strategy and one amendment made before it was run

`w_t = min(σ*/σ̂_t, ℓ_max/StressLoss_t, w_max)` with `σ* = 0.15`, `ℓ_max = 0.20`,
`w_max = 1.0`, and `StressLoss_t = w·move_t` for a one-day index rise `move_t = max(q_t,
floor_t)`. Here `q_t` is the fitted conditional 99.9% one-day move for the next session
from a GJR-GARCH-plus-GPD model estimated on index log returns **to 31 December 2015 only**
— the design window — with parameters then frozen and only the volatility state filtered
forward. Every input is formed at the close of `t`; the engine applies the one-day lag.

**The amendment.** The pre-registered configuration originally set `floor_t` to the 5
February 2018 move (96.1%). Applied from 2008, that sizes every pre-2018 position using
a day that had not happened yet — a leak by this project's own look-ahead rule and
contrary to the research design's requirement of an *ex-ante* stress loss. It was
replaced with the **running maximum one-day index rise observed through `t`**, which is
the real-time form of the same idea and is exact from 5 February 2018 onwards. The
amendment was committed **before any backtest was run**. The event floor is still run
and reported beside the honest version as a calibration of what knowing the answer in
advance is worth; because it sizes *larger* before 2018 (floor 0.14–0.33 rather than
0.96), the honest version is the one that takes the bigger loss on 5 February 2018.

**Costs** are charged at 1 tick (0.05 VIX points) per side on the weighted futures price
actually held, on both sources of trading: the rebalance back to target after the position
drifts, and the index's own daily roll on two legs (about twelve round trips a year). The
engine charged neither before Phase 11 — the drift and the re-entry after a gap were free,
and the roll was not charged at all — which understated the friction of a rolling futures
basket. Fixed before the run.

**Collateral** earns the T-bill accrual on the S&P DJI convention, credited once on full
capital (the index returns are excess returns) and credited identically to every benchmark
that holds collateral, so the comparison isolates sizing rather than the cash leg.

**Windows.** Parameters fixed on the design window to 31 December 2015; evaluation from
1 January 2016, a window containing February 2018, March 2020 and August 2024. The two are
reported separately and never pooled into a headline.

---

## 5. Results

### 5.1 The index and the products disagree because they are measured at different times

Tracking error between the reconstruction and VIXY is **133.2 bp a day in 2011–2015 and
31.7 bp a day from 26 October 2020**, with the leverage-adjusted slope rising from 0.873 to
**0.985** (`index_tracking_eras.csv`; the regression-residual definition, which lets a
fitted slope absorb the attenuation, gives 120.7 and 31.0). Over 2011–2017 the slope is
0.877 for VIXY (+1×), 0.872 for SVXY (−1×) and 0.867 for UVXY (+2×)
(`index_tracking.csv`). H1's criterion — 25 bp/day — is therefore **rejected**.

The mechanism is administrative. VX futures settled at 3:15 p.m. CT until 23 October 2020
and at 3:00 p.m. CT after; the products' closing prices are struck at 4:00 p.m. ET. Before
the change the index and the product were measured fifteen minutes apart; after it, at the
same instant. A common slope below one across three leverages, three products and two
issuers is attenuation from noise in the regressor — the reconstruction measured at the
wrong instant — not product-specific tracking difficulty. Fee drag and tracking difficulty
are product-specific and would not produce one common factor; a reconstruction error would
not disappear on the date the settlement time changed. Post-2020 slopes of 0.985 (VIXY),
0.991 (SVXY) and 0.971 (UVXY) leave 1–3% unexplained, which daily data cannot allocate
between residual fee drag and remaining index noise.

The economic significance is not a detail. On 5 February 2018 the settlement-based index
return is **+96.1%** while the three products' 4:00 p.m. closes imply **+32.0% to +34.2%**
(`docs/validation.md` V9). In log terms **57.5% of that day's move happened after
4:00 p.m. ET.** Any statement about "the index's worst day" is a statement about a
measurement convention as much as about the market — and XIV's acceleration was triggered
by an *intraday indicative value*, which is a third clock again.

*Figure: `reports/figures/index_vs_products.png`.*

### 5.2 The leverage-decay identity holds, and one block is why it appears not to

Over non-overlapping 21-day blocks the decay slope matches theory for every product and
regime except two, and both exceptions are the February 2018 block
(`leverage_decay.csv`): SVXY at −1× gives **−2.846** against a theoretical −1.000 over the
full window and **−1.087 excluding that block**; UVXY at +2× gives **−0.732** against
−1.000, and **−0.946 excluding it**.

The identity `−(L²−L)/2` is a second-order approximation; over a block containing a +96%
day it is not accurate, and the block is a 40× leverage point in the regression
(`decay_influence.csv`, `decay_approximation_error.csv`). The reading that the products
genuinely decayed faster than the identity implies is rejected by the excluding-that-block
fits and explained directly by the approximation-error calculation.

The identity costs a −1× product `(L²−L)/2 = 1` times realised variance. At a 60%
annualised index volatility that is 0.36 in log terms per year — about **30% of capital**
before fees — and the index's own volatility over the sample is higher. This is the
mechanical part of why these products lose money over time, and it is why the "buy and
hold the inverse" reading of the carry trade fails independently of any crash.

*Figures: `decay_regression.png`, `decay_blocks.png`.*

### 5.3 Mechanical rebalancing demand was large relative to the open interest that had to absorb it

On 5 February 2018, SVXY and UVXY together needed to buy an estimated **55,690 front-month
contracts at the lower asset bound — 25.0% of that contract's open interest**
(`rebalancing_flows.csv`). The front VX contract closed at 33.20, its high of the day, on
567,407 lots. H2's criterion required the 10% threshold to hold at *either* bound on the
largest up-moves of 2016–18; it holds at the lower bound on 3 of 10 such days and is
indeterminate on 7, so H2 is **not rejected**. Two of those three clear the threshold by
less than a quarter of a percentage point (10.18% and 10.23%), so H2's support outside
5 February 2018 is thin.

The mechanism is arithmetic: a product at leverage `L` must trade `L(L−1)·A·r` at the
close, and for both −1× and +2× that coefficient is 2, so a +96% day requires buying
roughly twice the fund's assets. What the data cannot do is attribute causation. Ordinary
hedging demand, short covering and discretionary buying into the settlement window are not
separable from mechanical demand in daily data. The finding establishes the **size of the
requirement**, not who filled it. An earlier draft of the validation note said "forced
buying"; that was stronger than the evidence and was corrected.

The cleanest statement of what the design change was worth is the de-levering
counterfactual: holding the same assets and the same shock and changing only the leverage
coefficient from 2.0 to 0.75, the required trade falls from 55,690 to **20,884 contracts,
25.0% to 9.4%** of front-month open interest (`delevering_counterfactual.csv`). That is
arithmetic, not an estimate, and it puts the post-2018 product suite below the threshold
H2 was written around.

*Figures: `flow_vs_open_interest.png`, `product_assets_with_anchors.png`,
`feb2018_detail.png`.*

### 5.4 The wipeout was foreseeable in order of magnitude; the timing was not

The GJR-GARCH-plus-GPD model fitted on data ending 31 December 2017 and never refitted
implies a one-day wipeout of a −1× product (index +80%) about **once in 79 years**
unconditionally, **1 in 2,835 in the calmest quintile** of volatility states, and **1 in
12.8 years for 5 February 2018 given data through 2 February**
(`termination_probabilities.csv`, `exante_warning_path.csv`). The warning path rose from
1 in 3,877 years on 12 January to 1 in 1,941 on 29 January, 1 in 294 on 2 February, and
1 in 12.8 for the day itself — a three-hundredfold move — and still stood at about **1 in
3,200 trading days on the morning of the event**.

The driver is the volatility state, not the parameters: the same frozen parameters,
updated only with each day's return, move the implied return period by orders of
magnitude. Mis-specification was tested three ways. The ordering and the survival gap hold
at every threshold in the grid (`survival_by_threshold.csv`); removing the largest
pre-2018 day and refitting every step moves the ex-ante number by 25%
(`tail_jackknife.csv`, inside the 50% tolerance fixed in advance); and exceedance rates by
volatility quintile show no under-reaction in calm regimes (p = 0.56,
`evt_calibration_by_sigma.csv`).

What the data cannot settle is how far the model's own volatility dynamics may be
extrapolated. Simulated unbounded, the model generates daily volatility up to 6.9 against
an observed maximum of 0.16, and 81% of simulated wipeouts occur inside those spirals
(`simulation_diagnostics.csv`). Five-year survival is therefore reported as a pair:
**81.1% unbounded and 89.9% capped for −1×, against 93.7% and 98.6% for −0.5×**
(`survival_curves.csv`). The **gap between the designs — 12.6 points unbounded, 8.7 capped
— is the stable part**, and it is the honest form of "de-levering helped".

H3 required a probability ratio of at least 10× between the −1× and −0.5× wipeout
thresholds, with a threshold-stable survival gap and a foreseeable event. The ordering
holds at every threshold, the gap is stable, and the event is foreseeable in order of
magnitude — but the ratio is **8.7×**, not 10×. H3 is **not rejected on its stated
criterion, with its stated magnitude unmet**, and that distinction is preserved rather
than rounded.

One in 79 years is a 1.3% chance per year of losing essentially everything. A product
marketed for a multi-year holding period with that hazard is not mispriced by a small
margin.

*Figures: `exante_warning.png`, `survival_curves.png`, `qq_gpd.png`, `mean_excess.png`,
`shape_across_thresholds.png`.*

### 5.5 Kelly could not rule out a full −1× short — and before the crash it favoured one

The empirical growth-optimal short is **0.62 with a bootstrap interval of [0.05, 1.34]** on
the full sample and **1.11 [0.22, 2.07] on pre-2018 data** (`kelly.csv`). H4 required the
interval to exclude 1.0; it contains it, so H4 is **rejected**.

Expected log growth is flat near its optimum and the bootstrap interval on a distribution
with this skew is wide. Whether the optimum is genuinely below 1.0 with too small a sample
to show it is exactly what the data cannot settle — which is why the criterion was written
as an interval test rather than a point comparison. Under the fitted tail every short has
positive ruin probability, so the model-implied optimum is exactly zero; the simulated
"Kelly" figures in the table (0.014, 0.059) are one over the largest simulated draw and are
labelled as not being estimates.

At the full-sample optimum expected log growth is 13.1% a year; at a full −1× short it is
about +1.6%. The cost of over-sizing is roughly 11.5 points of annual compound growth —
large, but not the catastrophe a naive reading of "Kelly says 0.62" suggests. The more
uncomfortable number is the pre-2018 point estimate of 1.11: on the evidence available
before the crash, growth-optimal sizing *favoured* the full inverse exposure the products
sold.

*Figure: `kelly_growth_curve.png`.*

### 5.6 The variance forecast has modest real skill, and the premium filter is pro-cyclical

Real-time HAR forecasts of 21-day realised variance achieve an out-of-sample R² of
**0.285** with a Mincer–Zarnowitz slope of **0.91**, against 0.060 and 0.53 for trailing
realised variance (`har_oos_diagnostics.csv`). The gain is calibration, not correlation:
the two correlate with the outcome almost identically (0.54 against 0.53), but trailing
variance is over-dispersed. Whether the R² is an artefact of the two crisis periods is
partly conceded by the sub-period table: in 2013–2019 the R² against a hindsight constant
is 0.005, though it is 0.574 against the real-time expanding mean, and the slope is 0.51.

The variance risk premium is positive on **87.4%** of days and the contango filter is on
**83.1%** (`signal_statistics.csv`).

The finding that matters is that **the premium filter is the one that does not work when
it matters.** On 5 February 2018 it was **on**, with a VRP of 0.115: implied variance
jumps before realised variance does, so the filter reads a volatility explosion as a
better selling opportunity (`signals_daily.csv`, V29). The term-structure filter, not the
premium filter, is what kept the strategy out of that day. A design in which the VRP filter
is the primary entry condition would have been long the carry into Volmageddon.

*Figures: `har_forecast_vs_realised.png`, `vrp_timeseries.png`, `term_structure.png`,
`signal_state.png`.*

### 5.7 Crash budgeting changes the loss distribution; it does not create return

Out of sample (1 January 2016 – 18 September 2026, 2,695 sessions) the strategy earns a
Sharpe of **0.20 with a Lo (2002) standard error of 0.31**, a CAGR of **4.1%**, a maximum
drawdown of **−26.8%**, a worst day of **−11.7%** and a worst week of **−13.5%**
(`performance_oos.csv`). Volatility targeting without the crash budget earns **−0.03 with a
−43.5% drawdown** (`backtest_variants.csv`). The budget binds on 45.6% of out-of-sample
days.

H5 required *both* a positive out-of-sample Sharpe net of costs *and* an alpha over
PUT/SPX/VXX indistinguishable from zero. The alpha is **−2.2% a year, t = −0.77**
(`alpha_regression.csv`), insignificant in all five specifications tried. Both halves hold,
so H5 is **not rejected** — but the hypothesis was written to be uncomfortable in both
directions, and what it establishes is weak. A Sharpe of 0.20 with a standard error of 0.31
is not distinguishable from zero. It sits below the Cboe PutWrite index (**0.53**) and the
S&P 500 (**0.75**) over the same window.

The comparison that does the most damage is the simplest one. **A constant 0.173 short —
the strategy's own average exposure, held every day with no signals and no sizing rule —
earns a Sharpe of 0.40** (`performance_oos.csv`). What the dynamic rule buys is the tail:
its worst day is −11.7% against the constant short's **−16.6%**. It buys a better tail at
the cost of return.

Nor can the sizing rule claim credit for February 2018. With the signals removed and the
budget left in place, the worst day is **−24.2%** (`backtest_variants.csv`). The entry
filters, not the crash budget, are what avoided the event — and §5.6 showed that only one
of the two filters was responsible.

*Figures: `equity_curve.png`, `drawdowns.png`, `rolling_sharpe.png`,
`weight_and_binding_constraint.png`.*

---

## 6. Robustness and red-team

Nine adversarial questions were put to the project and answered with numbers rather than
prose (`redteam_answers.csv`). The ones that changed how the results are reported:

**Specification dependence.** Across **144 specifications** the out-of-sample Sharpe runs
from **−0.37 to 0.50 with a median of 0.06**; the pre-registered configuration's 0.20 is
the **74th percentile**, and 67.4% of cells are positive
(`specification_distribution.csv`). Two choices dominate: the contango threshold decides
whether the position is held into February 2018, and the rebalance interval decides whether
the exit signal can be acted on. At a threshold of 1.025 the February 2018 return is
**−24.3%**; at a 5-day rebalance it is **−31.7%** with a worst day of **−38.0%**
(`robustness_parameters.csv`). The parameters were fixed before any data was retrieved and
the commit history proves it, so 0.20 is not a mined result — but a pre-registered draw
from a distribution whose median is 0.06 is still a draw, and both numbers belong in any
honest summary.

**The weakest assumption.** The contango filter's threshold. It cleared 1.0 by **0.72%** at
the close of 2 February 2018. The escape from Volmageddon rests on that margin and on
same-day execution at the close.

**Costs.** The out-of-sample Sharpe reaches zero at **1.77 ticks per side** (0.088 VIX
points). One tick is the quoted spread in calm markets; two is not unusual in a crisis,
which is when this strategy trades most (`robustness_costs.csv`).

**Look-ahead.** A deliberately leaked signal (same-day information) earns a Sharpe of
**1.54** against the honest 0.20. The whole-chain perturbation test — perturb every input
after a cut-off date and require every earlier weight and return to be bit-identical —
passes, and is itself mutation-checked so that a test that would pass on broken code is
caught. A one-day leak multiplies the Sharpe; it does not create the honest one.

**Concentration.** The largest single out-of-sample day (+11.7% on 10 August 2017)
accounts for 21.8% of the total return of 53.6%. The three stress windows each cost the
strategy money: Volmageddon 2018 −8.9%, COVID 2020 −4.8%, the yen-carry unwind of August
2024 +0.1%. No single period creates the result, but the best year (2017, +25.5%) is a
large share of it.

**Survivorship.** XIV is in the product sample for its entire life including its
termination; no product was dropped.

**Subsample stability.** Leave-one-year-out and the sub-period tables are in
`robustness_subsamples.csv` and `subsample_stability.png`; the result is not driven by one
year, but its dispersion across years is wide relative to its mean.

*Figures: `specification_distribution.png`, `parameter_heatmap.png`,
`cost_sensitivity.png`, `subsample_stability.png`.*

---

## 7. Discussion

**The measurement finding travels further than the strategy finding.** The settlement-time
result (§5.1) converts an apparent reconstruction failure into a dated, documented
measurement artefact, and it explains why the index's worst day is roughly three times the
move the products themselves recorded at their closes. It is the only finding here that
would change how someone reads *other* people's VIX-futures research: any study comparing a
settlement-struck index to 4:00 p.m. product prices before 26 October 2020 is comparing two
different instants, and any regression of one on the other is attenuated by a knowable
amount.

**The de-levering counterfactual answers the question the episode actually raised.** The
policy question after February 2018 was not whether inverse VIX products are risky —
everyone agreed they were — but whether the mechanical demand they generate is large
enough to matter to the market that has to absorb it, and whether the redesign fixed that.
25.0% to 9.4% of front-month open interest, from arithmetic on disclosed assets, is a
number. It is a lower-bound number in two senses: it covers only SVXY and UVXY, excluding
XIV and the other ETNs, and it is stated at the lower asset bound.

**On whether the carry is a premium or compensation for a crash, the evidence points to
compensation, and the strategy does not overturn it.** The ex-ante model says the crash was
foreseeable in order of magnitude from data available before it (§5.4); Kelly on pre-2018
data favoured a full −1× short (§5.5), which is what a premium looks like right up until it
isn't; the decay identity costs a −1× product roughly 30% of capital a year at the index's
volatility (§5.2); and a crash-budgeted implementation earns a Sharpe indistinguishable
from zero with a negative point-estimate alpha (§5.7). The premium exists — 87.4% of days
have a positive VRP — but by the time it is sized for the tail that its own left side
implies, it is not worth harvesting at these costs.

**The most useful methodological result is the gap between 0.20 and 0.06.** A
pre-registered configuration that lands at the 74th percentile of its own specification
grid is the most instructive warning this project produces about backtests in general,
including this one. Pre-registration protects against searching the grid; it does not
protect against having drawn a good cell. Reporting the grid alongside the chosen cell is
the only remedy, and it is one that almost no published backtest offers.

**What is conspicuously absent from the list of useful findings is the strategy's positive
Sharpe.** It is the headline the project was built to test, and the evidence leaves it
indistinguishable from zero, below a passive PutWrite index, and below a constant-weight
short of the same average size.

---

## 8. Limitations

Stated in full in `docs/limitations.md` (L1–L24). The ones that bound what this report may
claim:

- **Daily data only.** The intraday sequence on 5 February 2018 — including the
  after-hours move that triggered XIV's acceleration — cannot be resolved. The flow
  analysis shows mechanical demand was *large relative to* open interest; it does not
  establish that it caused the size of the move.
- **Assets outstanding are inferred, not observed**, for most of the sample. Results are
  reported as a range between bounds anchored on disclosed figures, and the claim is
  required to hold at the lower bound.
- **One day dominates the tail.** 5 February 2018 is the largest observation in the sample,
  so every tail headline is reported across the EVT threshold grid and with that day
  jackknifed out.
- **The reconstruction is not the licensed index.** It is an independent rebuild that
  tracks the products to 32 bp a day in the era where they are measured together.
- **1–3% of the post-2020 tracking slope is unexplained** and daily data cannot allocate it
  between residual fee drag and index noise.
- **Futures only.** No free historical option data, so option-based implementations of the
  same premium are out of scope.
- **The −0.5× design is 8.7 times safer on the headline threshold**, between 5.3 and 9.4
  across the grid — not the ten times H3 stated.
- **Two convention effects push the measured premium in opposite directions** and are
  stated rather than adjusted: the VIX 365/252 mismatch overstates it by about 0.0005 in
  annualised variance, and the realised-variance proxy's 4.6% excess over close-to-close
  variance understates it by more.
- **A backtest is not an expected return.** The strategy trades an index with stylised
  costs and reaches zero Sharpe at 1.77 ticks per side.
- **Nothing here generalises beyond VIX futures in 2008–2026** — one asset class, one
  history, one crash of this size in it.

### Causal language

Every sentence in this report containing "because", "caused", "drove" or "led to" was
re-read against its evidence. Two survive as causal claims, both about measurement rather
than markets: the tracking error falls *because* the settlement time changed (a dated
administrative fact with the regime break at that date), and a −1× product must trade twice
its assets *because* of the leverage identity (arithmetic). Every statement about the
February 2018 price path is phrased as consistency with an account, not as a demonstration
of it.

---

## 9. Conclusion

Five pre-registered hypotheses, two rejected:

| | Verdict | Why |
|---|---|---|
| **H1** index tracks products within 10 bp/day | **Rejected** | 133.2 bp/day in 2011–2015; the cause is a fifteen-minute measurement gap, not tracking failure |
| **H2** rebalancing demand > 10% of front-month OI | **Not rejected** | 25.0% at the lower bound on 5 Feb 2018; supported on 3 of 10 days (two marginally), indeterminate on 7 |
| **H3** P(+80%) ≥ 10× P(+160%), threshold-stable | **Not rejected, magnitude unmet** | ratio 8.7×; ordering and survival gap stable at every threshold |
| **H4** Kelly short strictly below 1.0 | **Rejected** | 0.62 [0.05, 1.34] full sample; 1.11 [0.22, 2.07] pre-2018 |
| **H5** positive OOS Sharpe, alpha indistinguishable from zero | **Not rejected** | Sharpe 0.20 ± 0.31; alpha −2.2%/yr, t = −0.77 |

The short-volatility trade of the 2010s was a real premium attached to a real tail, and the
products that sold it were fragile in a way that was visible in advance from their own
filings and from a model fitted before the event. A model estimated on data ending
31 December 2017 put a wipeout-sized day at 1 in 79 years unconditionally and 1 in 12.8 for
5 February 2018 given the previous close — foreseeable in order of magnitude, not in
timing. The mechanical demand those products generated on that day was at least a quarter
of the front contract's open interest, and the 2018 redesign cut that requirement to under
a tenth.

Bounding position size by an estimated crash loss rather than by recent volatility does
what it is designed to do: it changes the shape of the loss distribution, halving the
drawdown against volatility targeting and cutting the worst day against a constant short.
It does not turn the premium into something worth holding. The resulting Sharpe of 0.20 is
indistinguishable from zero, below a passive PutWrite index, below a constant short of the
same average size, at the 74th percentile of a specification grid whose median is 0.06, and
zero at two ticks of transaction cost.

That is a negative result on the question the project set out to answer, and it is reported
as one.

---

## 10. References

Full bibliography with verification status:
[`references/references.bib`](../references/references.bib). Archived filings:
[`references/filings/`](../references/filings/).

Augustin, P., Cheng, I.-H. & Van den Bergen, L. (2021). Volmageddon and the failure of
short volatility products. *Financial Analysts Journal* 77(3), 35–51.

Avellaneda, M. & Zhang, S. (2010). Path-dependence of leveraged ETF returns. *SIAM Journal
on Financial Mathematics* 1(1), 586–603.

Bollerslev, T., Tauchen, G. & Zhou, H. (2009). Expected stock returns and variance risk
premia. *Review of Financial Studies* 22(11), 4463–4492.

Carr, P. & Wu, L. (2009). Variance risk premiums. *Review of Financial Studies* 22(3),
1311–1341.

Cheng, I.-H. (2019). The VIX premium. *Review of Financial Studies* 32(1), 180–227.

Cheng, M. & Madhavan, A. (2009). The dynamics of leveraged and inverse exchange-traded
funds. *Journal of Investment Management* 7(4), 43–62.

Corsi, F. (2009). A simple approximate long-memory model of realized volatility. *Journal
of Financial Econometrics* 7(2), 174–196.

Diebold, F. X. & Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business
& Economic Statistics* 13(3), 253–263.

Eraker, B. & Wu, Y. (2017). Explaining the negative returns to volatility claims: An
equilibrium approach. *Journal of Financial Economics* 125(1), 72–98.

Glosten, L. R., Jagannathan, R. & Runkle, D. E. (1993). On the relation between the
expected value and the volatility of the nominal excess return on stocks. *Journal of
Finance* 48(5), 1779–1801.

Hansen, B. E. (1994). Autoregressive conditional density estimation. *International
Economic Review* 35(3), 705–730.

Lo, A. W. (2002). The statistics of Sharpe ratios. *Financial Analysts Journal* 58(4),
36–52.

McNeil, A. J. & Frey, R. (2000). Estimation of tail-related risk measures for
heteroscedastic financial time series: An extreme value approach. *Journal of Empirical
Finance* 7(3–4), 271–300.

Newey, W. K. & West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and
autocorrelation consistent covariance matrix. *Econometrica* 55(3), 703–708.

Patton, A. J. (2011). Volatility forecast comparison using imperfect volatility proxies.
*Journal of Econometrics* 160(1), 246–256.

Politis, D. N. & Romano, J. P. (1994). The stationary bootstrap. *Journal of the American
Statistical Association* 89(428), 1303–1313.

Rogers, L. C. G. & Satchell, S. E. (1991). Estimating variance from high, low and closing
prices. *Annals of Applied Probability* 1(4), 504–512.

Simon, D. P. & Campasano, J. (2014). The VIX futures basis: Evidence and trading
strategies. *Journal of Derivatives* 21(3), 54–69.

Yang, D. & Zhang, Q. (2000). Drift-independent volatility estimation based on high, low,
open, and close prices. *Journal of Business* 73(3), 477–491.

**Primary sources.** Credit Suisse VelocityShares 424B2 (30 June 2017) and 8-K exhibit 99.1
(6 February 2018); ProShares Trust II 424B3 (15 February 2018) and 10-K for FY2017;
Barclays iPath Series B 424B2 (January 2018) and the March 2022 issuance suspension;
VS Trust 424B3 (28 January 2022); Cboe circulars on the VX settlement time change
(October 2020). All retrieved from SEC EDGAR and Cboe, archived in `references/`, and
quoted in `reports/tables/filing_terms.csv`.
