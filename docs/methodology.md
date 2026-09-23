# Methodology

Method notes that the code's docstrings point to. Each section states what is done,
why, and what it assumes. Validation of each step is in `docs/validation.md`; what
remains imperfect is in `docs/limitations.md`.

---

## M1. The futures panel

Built by `svcarry.data.cboe.load_vx_panel` from two Cboe archives: the modern
per-expiry files and a legacy archive for contracts expiring January 2008 to August
2014. Rules, in the order they are applied:

1. A file that cannot be parsed raises; it is never skipped silently.
2. A header row is located explicitly, because fourteen legacy files carry a
   disclaimer line above it.
3. Non-positive settlement prices are placeholders and become missing **before**
   de-duplication.
4. Where both archives price the same contract on the same day, the row with a
   settlement price wins; between two rows with prices, the modern archive wins.
5. Rows dated after the contract's own expiry are dropped.
6. Nothing is forward-filled.

## M2. Index reconstruction

`svcarry.index.reconstruct`. Two nearest monthly contracts; roll weight
`w1 = dr/dt` (S&P Dow Jones convention, selected on evidence over a one-day-shifted
alternative, `docs/validation.md` V5); daily return priced on the contracts held at
t-1. Excess return; the total-return variant adds a T-bill accrual when supplied.

The index is struck at the futures settlement. Until 26 October 2020 that was
3:15 p.m. CT (4:15 p.m. ET), fifteen minutes after the products' closing price; from
that date it is 3:00 p.m. CT (4:00 p.m. ET). This timing is the dominant source of the
index's tracking error against traded prices before October 2020 (V6, V9).

## M3. Leverage decay

For each product and leverage regime, over non-overlapping 21-day blocks,

    y_b = sum ln(1 + p_t) - L sum ln(1 + i_t)      x_b = sum ln(1 + i_t)^2

and `y_b = a + beta x_b`, with theory `beta = -(L^2 - L)/2`. Cross-checks: 63-day
blocks, and overlapping 21-day windows with Newey-West errors at 42 lags. The block
holding 5-6 February 2018 is reported both included and excluded, with the
leave-one-block-out influence and the identity's approximation error over that block
alongside (V12a). The February 2018 de-levering is tested as a pooled regression with
an interaction on a post-2018-02-28 dummy.

## M4. Bounding assets outstanding

The flow estimate is linear in assets, and assets are not observed daily. They are
therefore **bounded, never point-estimated**, from directly disclosed anchors.

**Anchors** (`data/reference/product_asset_anchors.csv`, all quoted from the ProShares
Trust II 10-K for FY2017): net assets and shares outstanding for SVXY, UVXY and VIXY at
the ends of 2014, 2015, 2016 and 2017, and the share count for SVXY and UVXY on
26 February 2018.

**Construction**, in `svcarry.etp.assets.asset_bounds`:

1. Each anchor is placed on the last trading session on or before its date, because
   a fund strikes NAV only on trading days; a year-end falling on a weekend is the
   preceding session's NAV.
2. The anchor's share count is expressed in the price series' (fully split-adjusted)
   share basis as `net assets / adjusted price`. This needs no split arithmetic. The
   filing's own share counts are used only to check that every valued anchor implies
   the same basis, and to place an anchor that states a count but no value - which is
   permitted only when no split falls between it and the valued anchors.
3. Between two consecutive anchors, the adjusted share count is taken to lie between
   the two anchor values: **lower** bound = the smaller, **upper** = the larger,
   **central** = linear interpolation. Assets are the share path times the adjusted
   price.
4. Outside the first and last anchor, nothing is claimed: dates are flagged
   `extrapolated` and excluded from every flow result.
5. Checks that raise: every disclosed anchor must lie inside its own band; valued
   anchors must imply one share basis to within 5%.

**The assumption.** Step 3 assumes the share count did not travel outside the range
of the two anchors and back between them. It is the weakest assumption that gives a
usable band, it is exact at every anchor, and a daily shares-outstanding source would
remove it.

**How wide the band is.** Narrow where the share count was stable between year-ends,
and very wide where it was not: SVXY's adjusted share count rose 9.6-fold between
29 December 2017 and 26 February 2018, so in the weeks around 5 February the upper
bound applies post-crash share counts to pre-crash prices. That is why the claim is
stated at the lower bound.

## M5. Rebalancing flows

`Delta E_t = L(L - 1) A_{t-1} r_t` per fund, summed over SVXY and UVXY, at each asset
bound. Converted to contracts at `$1,000 x F1`, where F1 is the front-month
settlement, and expressed against the open interest of the front-month contract and,
separately, of the front two. Only the lower bound supports a claim; the upper bound
is reported and plotted but exceeds the entire front-month contract on 7 sessions.

Scope: SVXY and UVXY only, because they are the only geared products with disclosed
anchors in the archived filings. XIV (-1x) and the other ETNs are excluded, so the
estimate understates the complex. VIXY and VXX, at +1x, generate no rebalancing flow.

## M6. Tail model, termination probabilities and survival

**Filter.** Skewed-*t* GJR-GARCH(1,1) on daily index **log** returns (`svcarry.econometrics.garch`),
with the asymmetry indicator on negative shocks. Fitted on data ending 2017-12-31 (the
ex-ante model) and on the full sample (descriptive only). Four starts from each of two
seeds; the two optima must agree.

**Tail.** A Generalised Pareto distribution fitted to the upper tail of the standardised
residuals, above a threshold chosen on pre-2018 residuals only by the rule in
`prompts/tasks/choose_evt_threshold.md` (V15). The innovation law is spliced: the fitted
skewed-*t*, rescaled, below the threshold; the GPD above it, carrying exactly the
empirical exceedance mass (`svcarry.econometrics.tailrisk.SplicedInnovations`).

**Termination.** A one-day index **simple** return of `w / |L|` removes a share `w` of a
product at leverage `L`; with `w = 0.8`, that is 80% for -1x and 160% for -0.5x. The
conversion to the model's log scale is done once, inside
`conditional_exceedance`: `log(1.8) = 0.588`, `log(2.6) = 0.956`.

- *Unconditional* probability: the one-day conditional probability averaged over every
  day of the fitting sample - not evaluated at the average volatility, which would
  understate it because the probability is convex in volatility.
- *Calm*: the same average over the lowest quintile of conditional volatility.
- *On a date*: parameters frozen at 2017-12-31, the volatility state filtered forward
  through the previous close (`filter_sigma`), so every such number could have been
  computed that morning.
- Return period = 1 / (252 x one-day probability).

**Survival.** First passage to a wipeout-sized day over five years, 20,000 paths, seed
from configuration, run twice: with the model's own volatility dynamics, and with
conditional volatility capped at its 2008-2017 maximum. The pair brackets the answer
(V17). The grid comparison uses 10,000 paths per threshold.

**Kelly.** `argmax E[ln(1 - f R)]` over short exposure `f` on daily simple returns, with
`f < 1 / max R`; 1,000-replication stationary bootstrap, mean block 21 days. No
model-based estimate is offered: with an unbounded fitted tail the model-implied
optimum is exactly zero (V18).

**Jackknife.** The largest day of each sample removed and every step refitted,
threshold quantile held at the chosen value (V19).

## M7. Realised variance, HAR forecasts and the entry signals

**The variance proxy.** Daily variance is `o_t^2 + RS_t`: the squared overnight log
return `ln(O_t / C_{t-1})` plus the Rogers-Satchell intraday range estimator, on
**SPY** OHLC (`svcarry.econometrics.realized.daily_variance_proxy`, method
`rs_overnight`, fixed in configuration before any data was retrieved). Three
decisions, each with its evidence in `reports/tables/variance_proxy_comparison.csv`:

1. *SPY, not the S&P 500 index.* The phase prompt says "SPX OHLC". The index's opening
   print equals the previous close on 14% of days (SPY: 0.9%), because it is computed
   from constituents that have not yet traded; its overnight return is therefore
   mostly missing, and `rs_overnight` on the index averages 64% of close-to-close
   variance. SPY's opening auction is a real price. SPY's dividends put a small drop
   into the overnight return on ex-dates; removing it changes mean annual variance by
   0.01%.
2. *A range estimator, not squared returns.* Squared close-to-close returns are
   unbiased but very noisy: the daily log-variance has a standard deviation of 2.49
   against 1.25 for `rs_overnight`, and first-order autocorrelation 0.28 against 0.57
   (measurement noise attenuates the autocorrelation of a persistent series).
   `parkinson_overnight` and `gk_overnight` score marginally better on that criterion
   (0.60, 0.59); the drift-independent Rogers-Satchell choice was fixed in advance and
   the differences are small, so it is kept.
3. *Not Yang-Zhang.* Yang-Zhang is a window estimator with no single-day value; the
   daily series uses its components - overnight plus Rogers-Satchell - directly. A
   21-day Yang-Zhang on the same data correlates 0.999 with the 21-day average of the
   proxy, at a 0.8% lower level.

The proxy averages 19.1% annualised, 4.6% above close-to-close variance. The gap is in
the intraday leg (Rogers-Satchell exceeds the squared open-to-close return by 14%),
consistent with intraday mean reversion or microstructure in highs and lows; the cause
is not established. Its direction understates the premium (L16).

**The HAR model.** Corsi's HAR with daily, weekly and monthly components (1, 5, 22
days), horizon `h = 21` trading days, estimated in logs. The **target** is the log of
the *arithmetic* average variance over `t+1 .. t+h`; the predictors are averages of
daily log variance. Forecasts are retransformed by `exp(mu + sigma^2 / 2)`, with
`sigma^2` the training residual variance. (Log-target correction: see V20a.)

- *In sample* (`har_fit.csv`): descriptive only, Newey-West errors at 20 lags
  (`max(h - 1, rule of thumb)`), since consecutive targets share 20 of 21 days.
- *Real time* (`svcarry.econometrics.har.har_oos_forecast`): expanding window from
  1,000 feature rows (first forecast 25 January 2008), refit every 21 trading days,
  trained only on rows dated at least `h + 1` rows before the forecast date, so every
  training target was fully realised. Forecasts run to the last day of the sample,
  since a real-time forecast needs only today's predictors.

**Evaluation** (`svcarry.econometrics.forecast_eval`; `har_oos_diagnostics.csv`). Out-of-
sample R^2 against the evaluation-sample mean (a hindsight constant, so a conservative
bar) and against the real-time expanding mean; RMSE and MAE in annualised variance;
Patton's QLIKE; a Mincer-Zarnowitz regression with HAC errors; Diebold-Mariano tests
against the trailing 21-day RV on both losses. Benchmarks: trailing 21-day RV (the
no-change forecast of the monthly average), today's RV (the no-change forecast of the
daily series), the expanding mean, and two variants - a level HAR and a smearing
retransformation. Full sample and three sub-periods.

**The variance risk premium.**

    VRP_t = (VIX_t / 100)^2 - 252 * forecast_t

in annualised variance. Converted in one place (`svcarry.strategy.signals.vrp`), tested
by hand in a unit test and on a real date against the raw Cboe file (V22). VIX is a
30-calendar-day measure annualised on 365 days; the forecast covers 21 trading days
annualised on 252. Over 30 calendar days the equivalent multiplier is
`21 x 365 / 30 = 255.5`, 1.4% above 252, so the premium is overstated by about 0.0005
in annualised variance at typical levels, against a median VRP of 0.0077. Not adjusted;
stated, with the proxy's opposite and larger effect, in L16.

**The term-structure signal.** `cm30 / cm90` from the interpolated futures curve is the
primary measure (fixed in the phase prompt, committed 3db0269 before any data was
retrieved), because VIX3M begins only on 18 September 2009. `VIX / VIX3M` is the
robustness variant.

The interpolated curve leaves `cm30` missing whenever no listed contract is shorter
than 30 days - the few sessions after each monthly expiry that is followed by a
five-week cycle, 234 sessions in all (5.0%). On those days `cm30` is interpolated
between the curve's observable zero-maturity point, spot VIX (a future expiring today
settles to it), and the front contract (`spot_anchored_front`). Only missing values are
filled, each is flagged in `cm30_spot_anchored`, and the two slope measures agree on
91.5% of filled days against 91.7% overall. Left unfilled, coverage would sit at 95.0%,
the edge of the prompt's pass band, and the strategy would be forced flat on a
calendar pattern rather than a market state.

**Signals.** Contango on when `slope < 1.0`; VRP on when `VRP > 0.0`; combined by
requiring both. Thresholds from `config/config.yaml`, fixed in commit 2bdeb31
(07:40:36 UTC, 20 September 2026), 50 minutes before the first data retrieval
(08:30:04 UTC). A missing input gives a missing signal - no position - never a default.
Every signal is indexed by the date it is observable and is lagged by the backtest
(`signal_lag = 1`), never pre-lagged here.

## M8. The strategy, and one amendment made before it was run

**Position.** A collateralised short in the reconstructed index, entered only when both
Phase 10 signals are on, sized by

    w_t = min( sigma* / sigma_hat_t ,  l_max / StressLoss_t ,  w_max ),

with `sigma* = 0.15`, `sigma_hat` the trailing 21-day realised volatility of the index,
`l_max = 0.20`, `w_max = 1.0` and `StressLoss_t = w * move_t` for a one-day index rise
`move_t`. Every input is formed at the close of `t`; the engine applies the one-day lag
(`svcarry.strategy.backtest.run_backtest`), so the weight earning the return of `t+1`
was computed from data through `t`.

**The crash scenario.** `move_t = max(q_t, floor_t)`:

- `q_t` is the fitted **conditional 99.9% one-day move** for the next session, from a
  skewed-*t* GJR-GARCH(1,1) with a spliced GPD upper tail estimated on index log returns
  **to 31 December 2015 only** - the design window - with the EVT threshold chosen by
  the Phase 09 rule on those residuals. Parameters are then frozen and only the
  volatility state is filtered forward (`one_step_ahead_sigma`), so no post-2015
  observation enters the model that sizes a post-2015 position. Inside the design
  window the model is in sample, and the design-window performance is reported as such.
- `floor_t` is the **largest one-day index rise observed through `t`**
  (`running_max_floor`).

*The amendment.* The configuration and the phase prompt set the floor to the
5 February 2018 move (96.1%). Applied from 2008, that sizes every pre-2018 position
with a day that had not happened yet: by this project's own look-ahead rule
(`prompts/tasks/lookahead_audit.md`, "any row where use precedes availability is a
leak"), it is a leak, and the research design asks for an *ex-ante* stress loss
(§4.5). The running maximum is the real-time form of the same idea - the largest move
that has actually happened - and is exact from 5 February 2018 onwards, where it equals
the configured value. The amendment was written into `config/config.yaml` and committed
**before any backtest was run**; the event floor is still run, and reported beside the
honest version, as a calibration of what knowing the answer in advance is worth. It
sizes larger before 2018 (floor 0.14-0.33 rather than 0.96), so the honest version is
the one that takes the bigger loss on 5 February 2018.

**Costs.** Both sources of trading, at 1 tick (0.05 VIX points) per side on the weighted
futures price held: the rebalance back to target after the position drifts, and the
index's own daily roll on two legs (about twelve round trips a year). The engine
charged neither before Phase 11 - the drift and the re-entry after a gap were free, and
the roll was not charged at all - which understated the friction of a strategy that
holds a rolling futures basket. Fixed with the amendment, before the run.

**Collateral.** The T-bill accrual (S&P DJI convention, previous business day's
discount rate) is credited on the full capital, once: the index returns used are
excess returns, so nothing is double-counted. The same accrual is credited to every
benchmark that holds collateral, so the comparison isolates sizing rather than the
cash leg.

**Benchmarks.** Buy-and-hold -1x and -0.5x daily-rebalanced products on the same index
(XIV's and SVXY's fees), the Cboe PutWrite index, a constant-weight short sized to the
strategy's average exposure in the same window, and the S&P 500 (SPY, total return).

**Windows.** Design window to 31 December 2015, evaluation window from 1 January 2016,
reported separately and never pooled into a headline.
