# Literature and market-structure review

Scope: what is already established about the volatility risk premium, VIX futures term
structure, leveraged-ETP mechanics, and the February 2018 episode — and where this
project sits relative to it. Citations are in `references/references.bib`; every entry
there records whether its metadata was verified against the publisher or is
deliberately incomplete.

Throughout, four things are kept distinct and labelled:
**[fact]** institutional or contractual reality,
**[finding]** an empirical result from a specific paper's data,
**[interpretation]** that paper's reading of its result,
**[choice]** a methodological decision of this project.

---

## 1. The volatility risk premium

**Carr & Wu (2009)** establish that variance swap rates exceed subsequently realised
variance across equity indices and large stocks, and that the gap is large, persistent,
and not explained by conventional risk factors. **[finding]** They interpret it as
compensation for a separately priced volatility risk. **[interpretation]**

**Bollerslev, Tauchen & Zhou (2009)** decompose the premium and show that its
variation predicts aggregate stock returns at quarterly horizons. **[finding]** The
result matters here for a narrower reason: it means the premium is *time-varying*, so
a strategy that harvests it should condition on its size rather than being always-on.
That is the justification for the variance-risk-premium filter used in this project's
strategy, and it is a justification taken from the literature rather than from
backtesting. **[choice]**

**Cheng (2019)** studies the VIX premium — the gap between VIX futures prices and
subsequently realised VIX — and documents that it is not simply a compensation that
accrues steadily. **[finding]** He shows the premium is *negatively* related to
expected variance: it shrinks, and can invert, exactly when volatility is expected to
rise. **[finding]** This is a first-order point for any short-volatility strategy,
because it says the carry does not merely stop paying in a crisis but stops paying
*before* one. It is the strongest available argument that a term-structure filter is
capturing something real rather than fitting the sample. **[interpretation]**

**Eraker & Wu (2017)** build an equilibrium model that generates the negative average
returns of long volatility claims from an agent with recursive preferences facing
time-varying volatility. **[finding]** Their contribution here is that the negative
drift of long-volatility products — equivalently, the positive drift of short ones —
is an equilibrium feature rather than an anomaly, which sets the bar for what "alpha"
would have to mean in this project.

**Simon & Campasano (2014)** study the VIX futures basis directly and document that
strategies that short VIX futures when the basis is in contango, and avoid or reverse
the position in backwardation, produce large historical returns before costs.
**[finding]** This is the closest antecedent to this project's strategy and must be
treated as such: the term-structure signal used here is not novel, and the project does
not claim it is. **[choice]** What is added is the sizing rule and the honest
accounting for the crash.

**Whaley (2013)** documents the cost of holding long volatility products over time and
the resulting transfer from long to short holders. **[finding]** Useful here mainly as
a reminder that the short side's profit is structural and was well understood before
2018 — which makes the failure of the products a question about leverage and design,
not about whether the premium existed.

---

## 2. VIX futures and the index construction

**[fact]** VIX futures are cash-settled on a Special Opening Quotation of the VIX index,
with a $1,000 multiplier and a final settlement date that is the Wednesday 30 days
before the third Friday of the following month, pulled back a business day for
holidays (`cboe_vixspecs`). This project derives its expiry calendar from that rule
rather than scraping it, and unit-tests the derivation.

**[fact]** The S&P 500 VIX Short-Term Futures Index holds the two nearest monthly
contracts and rolls continuously between them across a roll period that runs from one
settlement date to the next, with weights linear in business days remaining
(`spdji_vixmethodology`). The excess-return version reflects the futures position; the
total-return version adds a 91-day Treasury-bill accrual.

**[fact]** All six products studied here reference that index family. XIV, ZIV, VIIX
and TVIX were ETNs of Credit Suisse; SVXY, UVXY and VIXY are ProShares commodity-pool
ETFs; VXX is a Barclays ETN; SVIX is a VS Trust ETF launched in 2022.

**Bollen, O'Neill & Whaley (2017)** examine intraday price discovery between VIX
futures and the VIX index. **[finding]** Their result is relevant as a limitation
rather than an input: it establishes that the interesting dynamics on a day like
5 February 2018 are intraday, and this project works at daily frequency and therefore
cannot resolve them. That constraint is stated in `docs/limitations.md` rather than
glossed.

---

## 3. Leveraged and inverse product mechanics

**Cheng & Madhavan (2009)** derive the end-of-day rebalancing requirement of a
constant-leverage fund and show that the required trade is proportional to
`L(L−1)` times assets times the index return, so that both leveraged-long and inverse
funds trade *with* the market at the close. **[finding]** They note the potential for
this flow to amplify late-day moves. **[interpretation]**

**Avellaneda & Zhang (2010)** derive the path-dependence of leveraged ETF returns in
continuous time,
`V_T/V_0 = (I_T/I_0)^L exp(−½(L²−L)σ²T)`,
and verify it empirically across a range of funds. **[finding]** The drag term is zero
only for `L ∈ {0,1}`; for `L = −1` it equals `σ²T`, which on a benchmark whose
annualised volatility routinely exceeds 60% is an enormous structural cost.

These two results are the analytical backbone of this project's mechanics section.
Neither is re-derived as though new; both are implemented, tested against simulation,
and then tested on the actual product data — including across the February 2018
leverage change, which provides a natural experiment on the identity itself. **[choice]**

---

## 4. The February 2018 episode

**Augustin, Cheng & Van den Bergen (2021)** is the careful study of Volmageddon. They
document the size of the inverse-product complex going into the event, the mechanical
rebalancing demand implied by the day's move, and the interaction between that demand
and the thin late-afternoon VIX futures market. **[finding]** They argue the episode
is best understood as a predictable consequence of product design interacting with
market capacity rather than as an exogenous shock. **[interpretation]**

**[fact]** The contractual detail that distinguishes the products: Credit Suisse's
pricing supplement permitted acceleration when the intraday indicative value fell to
20% or less of the prior day's close. On 5 February 2018 the prior close was $108.3681
and the trigger was met (`cs2018acceleration`). SVXY, as an ETF, had no such clause and
survived; ProShares subsequently reduced SVXY's target exposure from −1× to −0.5× and
UVXY's from +2× to +1.5× (`proshares2017tenk`, `proshares2018prospectus`).

**This project takes the mechanism as established** and asks the questions the episode
raises but does not answer: what probability a model estimated *before* the event would
have assigned to the triggering move; how much of the fragility the de-levering
actually removed, measured as a survival probability rather than asserted; how the
offered leverage compares with the growth-optimal exposure; and whether the premium
survives when position size is bounded by an explicit crash budget. **[choice]**

---

## 5. Econometric method

**Glosten, Jagannathan & Runkle (1993)** for the asymmetric GARCH specification.
**Hansen (1994)** for the skewed Student-*t* innovation density, standardised to mean
zero and unit variance, with closed-form CDF and quantile function — both needed here
for simulation and for the EVT threshold step.

**Pickands (1975)** and **Balkema & de Haan (1974)** for the limit theorem that
justifies fitting a Generalised Pareto Distribution to excesses over a high threshold.
**McNeil & Frey (2000)** for the two-stage conditional approach: filter with GARCH,
apply EVT to the standardised residuals, and scale the resulting residual quantile by
the conditional volatility. This is the method the project uses for the termination
probabilities, and the reason it is appropriate is that the raw index returns are far
from i.i.d. while the standardised residuals are much closer to it.

**Corsi (2009)** for the HAR specification of realised variance. **Parkinson (1980)**,
**Garman & Klass (1980)**, **Rogers & Satchell (1991)** and **Yang & Zhang (2000)** for
range-based variance estimation, which is necessary here because only free daily OHLC
data is available. Note that Yang–Zhang is a *window* estimator and has no single-day
value; where a daily series is needed the project uses the overnight squared return
plus the Rogers–Satchell intraday term, which are the components Yang–Zhang is built
from, and says so. **[choice]**

**Newey & West (1987, 1994)** for heteroskedasticity- and autocorrelation-consistent
inference, which is not optional here: the HAR regression has overlapping dependent
variables by construction, and ignoring that inflates *t*-statistics by roughly the
square root of the horizon.

**Lo (2002)** for the standard error of the Sharpe ratio under non-normality. This
matters more than usual for a short-volatility strategy: with strongly negative skew
and high kurtosis, the naive `√T` error understates the uncertainty substantially.

**Kelly (1956)**, applied to simple returns so that the solvency constraint
`1 − fR > 0` is the ruin constraint, which is what makes the criterion meaningful for
a position that can be wiped out in a day. **Politis & Romano (1994)** for the
stationary bootstrap, used for confidence intervals on statistics whose sampling
distribution depends on volatility clustering that an i.i.d. bootstrap would destroy.

---

## 6. What this project adds

Stated narrowly, because the components are individually standard:

1. **An ex-ante survival comparison across product designs.** The tail model is
   estimated on data ending 31 December 2017 and used to price the termination event
   for a −1× and a −0.5× design. The question "was this foreseeable, and how much did
   de-levering help" is answered with a probability and a survival curve rather than
   with hindsight.
2. **Offered leverage against growth-optimal leverage.** The Kelly fraction on the
   same index, with a bootstrap interval, compared directly with −1× and −0.5×. This
   turns a qualitative complaint about product design into a testable statement.
3. **Crash-budgeted sizing, evaluated out of sample.** A sizing rule whose binding
   constraint is an explicitly estimated crash loss rather than recent volatility,
   with parameters fixed on 2008–2015 and evaluated from 2016 onwards, and with the
   resulting return decomposed against the PutWrite index to ask whether what remains
   is alpha or crash compensation.

None of the three requires a new estimator. The contribution is the combination and
the discipline of the evaluation, which is the appropriate ambition for a project of
this scope.
