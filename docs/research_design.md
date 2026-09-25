# Research design

Sections 1 to 8 are the design as it was committed at `ef232d4` on 20 September 2026,
before any data was retrieved. No hypothesis, rejection criterion, method or validation
plan has been edited since, which is what makes §9 — written once the evidence was in —
readable against them. The one later change is in §6, where the list of expected outputs
no longer names the working procedure notes that left the repository in the final cleanup
(`docs/humanization_audit.md`, H-01). `docs/preregistration.md` records the parameter set
that was fixed alongside this document, and everything that changed afterwards.

---

## 1. Object of study

The **S&P 500 VIX Short-Term Futures Index** (excess-return version, "the index"
below) and the four exchange-traded products written on it:

| Product | Issuer | Wrapper | Daily leverage | Fee | Live | Acceleration clause |
|---|---|---|---|---|---|---|
| XIV | Credit Suisse AG | ETN (senior unsecured note) | −1× | 1.35% | Nov 2010 – Feb 2018 | Yes: intraday indicative value ≤ 20% of prior close |
| SVXY | ProShares Trust II | commodity-pool ETF | −1× → −0.5× (28 Feb 2018) | 0.95% | Oct 2011 – | No |
| UVXY | ProShares Trust II | commodity-pool ETF | +2× → +1.5× (28 Feb 2018) | 0.95% | Oct 2011 – | No |
| VXX | Barclays Bank PLC | ETN | +1× | 0.89% | Jan 2009 – (Series B from Jan 2018) | Optional, at issuer discretion |
| VIXY | ProShares Trust II | commodity-pool ETF | +1× | 0.85% | Jan 2011 – | No |
| SVIX | VS Trust (Volatility Shares) | commodity-pool ETF | −1× | 1.29% | Mar 2022 – | No |

Terms are taken from the filings catalogued in `config/filings.yaml`; every figure
above is re-extracted from the archived document by `scripts/extract_filing_terms.py`
and any discrepancy is recorded in `docs/validation.md`.

The comparison is close to controlled: same underlying exposure, different wrapper,
different leverage, different termination provisions.

---

## 2. Hypotheses

Each hypothesis states what would count as rejection. This is the commitment device
that stops the analysis from being written backwards from the results.

**H1 — Reconstruction fidelity.**
The index rebuilt from Cboe settlement data tracks VIXY and VXX to within a daily
tracking error of 10 bp (standard deviation of the difference between the rebuilt
excess return and the product's return plus its accrued fee).
*Rejected if* the tracking error exceeds 25 bp/day, or if residuals are
systematically related to the roll weight (which would indicate the wrong roll
convention).

**H2 — Rebalancing feedback is economically large.**
Aggregate mechanical end-of-day demand from leveraged and inverse VIX products,
`ΣE = Σ_p L_p(L_p − 1) A_{p,t−1} r_t`, exceeded 10% of front-month open interest on
the largest index up-moves of 2016–2018.
*Rejected if* the estimate is below that threshold under both the upper and lower
bounds on assets outstanding.

**H3 — De-levering changed survival, materially and predictably.**
Under a GJR-GARCH(1,1) with skewed-*t* innovations and conditional EVT tails
estimated on index data **ending 31 December 2017**, the probability of a one-day
index simple return ≥ 80% (which destroys 80% of a −1× product) is at least an order
of magnitude larger than the probability of a return ≥ 160% (the −0.5× equivalent),
and the five-year survival probability of the −0.5× design exceeds that of the −1×
design by a margin that is stable across EVT thresholds in the grid.
*Rejected if* the ordering reverses, or if the gap is not stable across the
threshold grid, or if the −1× probability implied by the pre-2018 model is so small
(< 1 in 10,000 years) that the event cannot be described as foreseeable.

**H4 — Offered leverage exceeded the growth-optimal exposure.**
The Kelly-optimal short exposure `f* = argmax E[ln(1 − f R)]`, where `R` is the daily
index simple return, is strictly smaller in magnitude than 1.0, with a bootstrap
confidence interval that excludes 1.0.
*Rejected if* the interval contains 1.0.

**H5 — The premium survives crash budgeting, but is largely crash compensation.**
A short-index strategy whose weight is capped by an ex-ante stress loss earns a
positive Sharpe ratio out of sample (2016 onwards) net of 1 tick per side, and in the
regression
`r_strategy = α + β₁ r_PUT + β₂ r_SPX + β₃ r_VXX + ε`
the estimated α is not statistically distinguishable from zero at the 5% level with
Newey–West standard errors.
*This hypothesis is written to be uncomfortable in both directions.* A positive and
significant α would be a stronger result than expected and would demand extra
scrutiny for look-ahead bias and overfitting rather than celebration; a negative
Sharpe would say the premium does not survive costs and crash budgeting, which is
also a publishable answer.

---

## 3. Data

Full detail, with URLs, licensing and known limitations, in `docs/data_sources.md`.

| Dataset | Source | Frequency | Window | Role |
|---|---|---|---|---|
| VX futures settlement, OHLC, volume, open interest, per contract | Cboe (`cdn.cboe.com`, per-expiry CSV) | Daily | 2006– | Index rebuild, curve, flow denominators |
| VIX, VIX3M, VIX9D, VIX6M, VVIX | Cboe index history CSV | Daily | 1990– (VIX3M from Sep 2009) | Implied-volatility level and slope |
| Cboe PutWrite (PUT), BuyWrite (BXM) | Cboe index history CSV | Daily | 1986– | Benchmark and alpha-regression factor |
| VXX, VIXY, SVXY, UVXY, SVIX | Yahoo Finance (Stooq fallback) | Daily OHLCV + splits | Product lives | Validation, decay test, factor |
| SPY / ^GSPC OHLC | Yahoo Finance | Daily | 2004– | Yang–Zhang realised variance, market factor |
| DTB3 / DGS3MO | FRED | Daily | 2004– | Total-return accrual, collateral return |
| Product filings | SEC EDGAR | — | — | Terms, fees, assets, acceleration clause |

**Sample.** 2 January 2008 to the most recent available trading day.
VIX futures began trading in March 2004, but the second-month contract is thinly
traded before late 2005 and the front-two-contract construction needs both legs to be
priced; starting in 2008 keeps the global financial crisis in sample while avoiding
the period where the curve is unreliable. The choice is tested: `docs/validation.md`
reports the reconstruction back to 2006 and shows where it degrades.

**In-sample / out-of-sample split.**
- **Design window: 2008-01-02 to 2015-12-31.** Every strategy parameter — signal
  thresholds, volatility target, stress cap, HAR specification — is fixed using this
  window and nothing else.
- **Evaluation window: 2016-01-01 onwards.** Contains February 2018, March 2020 and
  August 2024, i.e. three independent stress events that the parameters have never
  seen.
- The tail model is estimated twice: once on the full sample for description, and once
  on **data ending 31 December 2017** for the ex-ante survival question, so that the
  probability assigned to Volmageddon is genuinely out-of-sample.

---

## 4. Methodology

### 4.1 Index reconstruction

Roll weights follow the S&P Dow Jones Indices short-term methodology: the portfolio
holds the two nearest monthly VX contracts and shifts weight from the near to the far
contract linearly in business days across a roll period that runs from one VIX futures
settlement date to the next,

$$w_{1,t} = \frac{d_{r,t}}{d_{t,t}}, \qquad w_{2,t} = 1 - w_{1,t},$$

with `d_t` the business days in the roll period and `d_r` those remaining after `t`.
The daily excess return is

$$r_t = \frac{w_{1,t-1}F_{1,t} + w_{2,t-1}F_{2,t}}{w_{1,t-1}F_{1,t-1} + w_{2,t-1}F_{2,t-1}} - 1,$$

where `F_1` and `F_2` are the settlement prices of **the contracts held at `t−1`**,
priced on both days. Total return adds the S&P 91-day Treasury-bill accrual.

Two roll conventions (`sp_dji` and a one-business-day-shifted variant) are built and
the choice is made by tracking error against the traded products rather than by
assertion. The settlement calendar is derived from the contract specification, not
scraped, and is unit-tested against known expiries.

### 4.2 Term structure and carry

Constant-maturity futures are interpolated at 30–180 calendar days, without
extrapolation beyond the longest listed contract. Carry is measured three ways so that
no result depends on one definition:
`ln(F₂/F₁)/(τ₂−τ₁)`, `F₁/VIX − 1`, and `VIX/VIX3M`. A principal-component
decomposition of daily curve changes summarises level and slope dynamics and is used
to check that the signal is not simply a proxy for the level of volatility.

### 4.3 Leveraged-product mechanics

Derivation and empirical test of two identities:

- **Rebalancing demand.** `ΔE_t = L(L−1) A_{t−1} r_t`. The coefficient `L(L−1)` is
  positive for every `L` outside `[0,1]`, so 2× long and −1× inverse funds both buy
  after the index rises. De-levering to −0.5× cuts the coefficient from 2.0 to 0.75,
  a 62.5% reduction for the same shock.
- **Leverage decay.** Under continuous rebalancing and geometric Brownian motion,
  `V_T/V_0 = (I_T/I_0)^L exp(−½(L²−L)σ²T)`. Tested by regressing
  `ln(V_T/V_0) − L ln(I_T/I_0)` on realised variance over non-overlapping 21-day
  blocks; the slope should be `−½(L²−L)` and the intercept should recover the fee.
  Run separately for each product and separately before and after February 2018 for
  SVXY and UVXY, which doubles as a test that the leverage change is visible in the
  data at the date the filings say it happened.

Flows are converted to contract equivalents at the $1,000 VX multiplier and expressed
as a share of front-month open interest. Assets outstanding are the weak link:
where they are not directly disclosed they are bounded by scenario, and the
conclusions are required to hold at both bounds.

### 4.4 Tail model and survival

1. **Filter.** GJR-GARCH(1,1) with Hansen skewed-*t* innovations on daily index log
   returns. The asymmetry parameter is expected to be *negative* here (for an
   inverse-volatility exposure the damaging shock is a large positive index move),
   which is a sign check on the fit rather than a nuisance.
2. **Tail.** Conditional EVT (McNeil–Frey): a Generalised Pareto Distribution fitted
   to standardised residuals above the 95th percentile, with the full threshold grid
   0.90–0.99 reported.
3. **Termination probabilities.** `P(R ≥ 0.80)` and `P(R ≥ 1.60)` for the simple
   one-day index return, unconditionally and conditional on being in the lowest
   quintile of conditional volatility — the state in which these products attracted
   the most assets.
4. **Survival.** 20,000 Monte Carlo paths over five years from the fitted model, for
   `L ∈ {−1, −0.5}`, recording first passage to an 80% single-day loss and to the
   acceleration trigger. Reported as survival curves with simulation standard errors.
5. **Kelly.** `f* = argmax_f E[ln(1 − f R)]` under (a) the empirical distribution,
   (b) the fitted GARCH-EVT distribution, and (c) a stationary bootstrap, with
   confidence intervals. Compared with the −1× and −0.5× designs.

### 4.5 Crash-aware carry strategy

**Instrument.** Short exposure to the reconstructed index (equivalently, a short
position in the rolling front-two VX basket). A front-versus-fourth-month calendar
spread is implemented as a robustness variant, because it isolates the slope from the
level.

**Signals**, both observable at the close of `t−1` and traded at the close of `t`:
- *Contango filter*: hold only when `VIX/VIX3M < θ` (default θ = 1.0). Where VIX3M is
  unavailable (before September 2009) the interpolated `cm30/cm90` ratio is used, and
  the two are shown to agree on the overlap.
- *Variance risk premium*: `VRP_t = (VIX_t/100)² − E_t[RV_{t→t+21}]`, with realised
  variance forecast by a HAR model on a daily range-based variance proxy. Require
  `VRP_t > 0`.

**Sizing.** `w_t = min(σ*/σ̂_t, ℓ_max / StressLoss_t)` where `StressLoss_t` is the loss
the current position would take under the larger of (i) the fitted 99.9% conditional
tail move and (ii) the realised 5 February 2018 index move. The second term is the
whole point: it caps size by what a crash would cost rather than by recent
volatility, which is exactly the failure mode of volatility targeting in this asset.

**Execution and costs.** Daily rebalancing at the close; one-day lag between signal
and execution; 1 tick (0.05 VIX points) per side by default, swept 0–4 ticks;
collateral earns the T-bill accrual. Every trade uses only information available
before it.

**Benchmarks.** Buy-and-hold −1× (the XIV/SVXY experience), the Cboe PutWrite index,
a constant-weight short-index position sized to the same average exposure, and the
S&P 500.

**Evaluation.** Sharpe, Sortino (target downside deviation at a target of zero, over all
observations - see `docs/methodology.md`, and A-13 for the definition this replaced),
skewness, excess kurtosis, maximum drawdown, 99% CVaR, turnover, and returns in each of
six named stress windows. Plus the alpha regression in H5.

---

## 5. Validation plan

Detail in `docs/validation.md`. Summary of what is checked and against what:

| Component | Independent check |
|---|---|
| Settlement calendar | Known expiry dates from Cboe file names and contract spec |
| Roll weights | Sum to one, monotone within a roll period, sweep 0→1 |
| Index reconstruction | Synthetic panels with analytically known answers; then tracking error against VIXY / VXX / SVXY net of fees |
| Leverage identity | Regression slope against the closed-form `−½(L²−L)` for each product; break at the documented de-levering date |
| GARCH | Parameter recovery from simulated paths; Ljung–Box on squared standardised residuals; comparison with `arch` where installable |
| EVT | Parameter recovery from simulated GPD samples; mean-excess linearity; threshold-stability grid; KS on the probability-integral transform |
| HAR | Look-ahead test that perturbs post-cutoff data and requires earlier forecasts to be bit-identical; Mincer–Zarnowitz regression |
| Backtest | Timing audit (every input lagged), turnover sanity, cost sweep, subsample stability, and a deliberately broken variant that *does* use same-day information, to show how much the leak would have been worth |
| Data | Row counts, date coverage, duplicate checks, zero-price screens, split-adjustment cross-check against an independent reconstruction, SHA-256 manifest |

---

## 6. Expected outputs

- `reports/` — an 8–10 page report and a one-page summary
- `reports/figures/` — index reconstruction vs products; term structure and carry;
  rebalancing flow vs open interest; mean-excess and QQ diagnostics; survival curves
  by leverage; Kelly curve with the offered leverage marked; strategy equity curve,
  drawdowns and rolling Sharpe; cost-sensitivity and subsample tables
- `reports/tables/` — tracking error, decay regressions, tail parameters and
  probabilities, strategy performance in and out of sample, stress windows, alpha
  regression
- `docs/` — literature review, data sources, methodology, validation, limitations,
  project log, final audit

---

## 7. Principal risks to the design

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Assets outstanding are not cleanly observable** | The flow estimate (H2) scales linearly with them | Bound by scenario from 10-K disclosures and shares-outstanding data; require the conclusion at both bounds; report the flow as a range, never a point |
| **One event drives the tail result** | The EVT fit above a 95th-percentile threshold has few exceedances, and 5 Feb 2018 is the largest | Estimate the pre-2018 model separately; report threshold-stability grid; jackknife the single largest observation and report how much the answer moves |
| **Roll convention ambiguity** | A one-day error biases every downstream return | Build both conventions, select on tracking error, report both |
| **VIX3M starts only in Sep 2009** | Truncates the contango signal in the design window | Use the interpolated `cm30/cm90` slope as primary, VIX3M as robustness; demonstrate agreement on the overlap |
| **Strategy overfitting** | Several thresholds could be tuned to the event | Parameters fixed on 2008–2015 and never revisited; full grid of alternatives reported, not just the chosen one; the honest test is the spread of outcomes across the grid, not the best cell |
| **Transaction costs in a crisis** | 1 tick is optimistic on 5 Feb 2018 | Sweep 0–4 ticks; report the breakeven cost at which the out-of-sample Sharpe reaches zero |
| **Survivorship in the product set** | XIV is gone; using only surviving products would flatter the asset class | XIV is included for its whole life and its termination is modelled explicitly, not dropped |

---

## 8. Reproducibility

- Single entry point per stage (`scripts/fetch_data.py`, then `scripts/run_pipeline.py`),
  with `make all` wiring them together.
- All parameters in `config/config.yaml`; nothing tunable is hard-coded.
- Every downloaded file recorded with URL, timestamp and SHA-256 in
  `data/raw/_manifest.json`, verifiable with `svcarry.data.http.verify_manifest`.
- All randomness seeded from `config.yaml`.
- Estimators implemented in-repo and unit-tested rather than imported, so a reader can
  see exactly what was computed; where `statsmodels` or `arch` are available the tests
  additionally cross-check against them.
- Raw data is not redistributed (see `docs/data_sources.md` for the licensing
  reasoning); the acquisition script reproduces it from the original sources.

---

## 9. What the evidence supports, after Phase 12

Added 23 September 2026. **Nothing above this line has been edited**: the hypotheses
and their rejection criteria are left exactly as they were written before any data was
retrieved, so that this section can be read against them. What follows is the claim
each one supports *now*, at the confidence the robustness work leaves it.

| | As stated | As the evidence leaves it |
|---|---|---|
| **H1** | The index tracks VIXY and VXX within 10 bp/day | **Rejected.** Tracking error is dominated by a dated settlement-time change, not by reconstruction error (V6, V9) |
| **H2** | Rebalancing demand exceeded 10% of front-month open interest | **Not rejected**, at the lower asset bound (25.0%), for SVXY and UVXY only, on 3 of 10 candidate days with 7 indeterminate, and two of the three clear 10% by under a quarter of a point (V13, L10, final audit F-A2) |
| **H3** | P(+80%) at least 10x P(+160%), stable across thresholds | **Not rejected, magnitude unmet**: 8.7x, not 10x. The ordering and the survival gap are stable (V16, V17) |
| **H4** | Kelly-optimal short strictly below 1.0 | **Rejected**: the interval contains 1.0, and pre-2018 it was centred above it (V18) |
| **H5** | Positive out-of-sample Sharpe, alpha indistinguishable from zero | **Not rejected**, and weaker than that sentence sounds: Sharpe 0.20 with a standard error of 0.31 at the chosen configuration, **0.06 at the median of the 144-cell grid**; alpha -2.2% a year (t = -0.77) (V28, V30, V31) |

Three claims that the design implied and the evidence does **not** support, stated
here so they are not carried into the report:

1. **That the entry rules add return.** A constant-weight short at the same average
   exposure earns a higher Sharpe out of sample (0.40 against 0.20) and a higher CAGR.
   What the rules buy is the tail: worst day -11.7% against -16.6% (L19).
2. **That crash budgeting alone makes the trade survivable.** The February 2018 escape
   came from the entry filter, one day ahead and by a margin of 0.72%, and it
   disappears if the same rule is rebalanced weekly (-31.7%) or the threshold is 2.5%
   higher (-24.3%) (L18, L23). The budget's demonstrated contribution is narrower and
   real: Sharpe 0.20 against -0.03 for volatility targeting alone, drawdown -27%
   against -44%.
3. **That the strategy is an attractive standalone investment.** Out of sample it is
   beaten on Sharpe by the PutWrite index (0.53) and by the S&P 500 (0.75), it earns
   nothing at two ticks of cost, and its result is not robust to plausible changes in
   the rebalance interval or the threshold.

The project's research question asked whether crash budgeting "turns it into something
an investor could hold". The answer this evidence supports is: it turns a position that
would have been destroyed into one that survives - which is not the same as one worth
holding.
