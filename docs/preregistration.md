# Pre-registration

Every hypothesis, rejection criterion and tunable parameter in this project was fixed
and committed before any data was retrieved. This file records what was fixed, when,
and — just as important — everything that changed afterwards, with the reason for each
change and what it did to the results.

The point of writing it down is narrow. It stops the analysis from being written
backwards from the answer. It does not make the answer right, and §5 says what it
leaves unprotected.

---

## 1. The timeline

All times UTC, 20 September 2026. Every hash below is in this repository's history and
can be checked with `git show`.

| Time | Commit | What it fixed |
|---|---|---|
| 07:40:36 | `2bdeb31` | `config/config.yaml`: sample windows, roll convention, product terms, EVT settings, HAR specification, every strategy threshold, the robustness grids |
| 07:42:40 | `ef232d4` | `docs/research_question.md` and `docs/research_design.md`: five hypotheses, each with its rejection criterion |
| 08:01:09 | `3db0269` | The remaining specification detail, including which term-structure measure is primary |
| **08:30:04** | — | **First data retrieval** (`data/raw/_manifest.json`, earliest `retrieved_utc`) |

Fifty minutes separate the configuration commit from the first byte of data. The margin
is thin in wall-clock terms and complete in the sense that matters: nothing in the
parameter set had seen a price.

To verify the claim rather than take it:

```bash
git show 2bdeb31:config/config.yaml        # the parameter set, before any data
git diff 2bdeb31 HEAD -- config/config.yaml
python -c "import json;m=json.load(open('data/raw/_manifest.json'));\
print(min(v['retrieved_utc'] for v in m.values()))"
```

---

## 2. The hypotheses

Stated in full, with their rejection criteria, in
[`docs/research_design.md`](research_design.md) §2. In short:

| | Claim | Rejected if | Verdict |
|---|---|---|---|
| H1 | The rebuilt index tracks VIXY and VXX within 10 bp/day net of fees | TE > 25 bp/day, or residuals correlate with the roll weight | **Rejected** |
| H2 | Mechanical rebalancing demand exceeded 10% of front-month open interest on the largest up-moves of 2016–18 | it fails at either bound on assets outstanding | **Not rejected** |
| H3 | P(+80% in a day) ≥ 10 × P(+160%) under a model fitted to data ending 2017-12-31, with a threshold-stable survival gap | the ordering reverses, the gap is threshold-dependent, or the event is not foreseeable at all | **Not rejected, magnitude unmet** |
| H4 | Kelly-optimal short exposure is below 1.0 in magnitude, interval excluding 1.0 | the interval contains 1.0 | **Rejected** |
| H5 | Crash-budgeted short volatility earns a positive out-of-sample Sharpe net of costs, **and** its alpha over PUT/SPX/VXX is indistinguishable from zero | either half fails | **Not rejected** |

H5 is the one that cost something to write. It is falsified by a *significant positive*
alpha as surely as by a negative Sharpe, so the pleasant outcome triggers a leak hunt
rather than a victory lap. A design in which every hypothesis predicts the flattering
result is a design that will find it.

---

## 3. The parameter set, as fixed

Reproduced from `git show 2bdeb31:config/config.yaml`. Values that are still in force
today are unmarked; the four that changed are flagged and explained in §4.

**Sample and split**

| Parameter | Value |
|---|---|
| `sample.start` | 2008-01-02 |
| `sample.design_end` | 2015-12-31 — every parameter fixed on this window and nothing after it |
| `sample.oos_start` | 2016-01-01 — contains Feb 2018, Mar 2020, Aug 2024 |

**Index**

| Parameter | Value |
|---|---|
| `index.roll_convention` | `sp_dji`, with a one-business-day-shifted variant built alongside and the choice made on tracking error |
| `index.constant_maturities` | 30, 60, 90, 120, 150, 180 calendar days |
| `index.min_open_interest` | 100 contracts |

**Tail model**

| Parameter | Value |
|---|---|
| `tail.threshold_quantile` | 0.95 |
| `tail.threshold_grid` | 0.90, 0.925, 0.95, 0.96, 0.97, 0.975, 0.98, 0.99 |
| `tail.garch_dist` | skewed-*t* |
| `tail.wipeout_fraction` | 0.80 |
| `tail.survival` | 20,000 paths, 5 years, seed 20260920 |

The threshold *selection rule* was fixed with them, and is implemented in
`svcarry.econometrics.evt.choose_threshold`: take the lowest threshold with at least 50
exceedances, `ξ` within one standard error of its value at the next two higher
thresholds, a KS p-value above 0.10 on the probability-integral transform of the
excesses, and a mean-excess plot that is plausibly linear above it. Prefer the lowest
qualifying threshold, because exceedances are what the standard errors are made of. If
no threshold qualifies, report a range rather than a point estimate. And if a headline
probability moves by more than a factor of three across the grid, the range is the
headline, not a footnote to a point estimate. The threshold for
the pre-2018 fit is chosen on pre-2018 residuals only — choosing it on the full sample
and applying it to an ex-ante claim would smuggle the event in through the back door.

**Forecasting**

| Parameter | Value |
|---|---|
| `forecast.har_horizon` | 21 days |
| `forecast.har_lags` | 1, 5, 22 |
| `forecast.har_log` | true |
| `forecast.har_train_min` | 1,000 observations |
| `forecast.har_refit_every` | 21 days |
| `forecast.rv_method` | `rs_overnight` — Rogers–Satchell plus the squared overnight log return |

**Strategy**

| Parameter | Value |
|---|---|
| `strategy.contango_threshold` | 1.0 |
| `strategy.vrp_min` | 0.0 |
| `strategy.vol_target` | 0.15 annualised |
| `strategy.vol_lookback` | 21 days |
| `strategy.max_stress_loss` | 0.20 |
| `strategy.stress_quantile` | 0.999 |
| `strategy.stress_floor_event` | 2018-02-05 — **amended, see §4.2** |
| `strategy.max_weight` | 1.0 |
| `strategy.cost_ticks` | 1.0 per side |
| `strategy.tick_value` | 0.05 VIX points |
| `strategy.rebalance` | daily |
| `strategy.signal_lag` | 1 |

The term-structure signal was fixed at `3db0269` as the interpolated `cm30/cm90` ratio
from the futures curve — available across the whole sample — with `VIX/VIX3M` carried
as a robustness variant, because the Cboe VIX3M history begins on 18 September 2009,
inside the design window. The `contango_threshold` comment in the configuration file
said `VIX/VIX3M` until Phase 10; the comment was wrong and the value was not, and the
comment is what got corrected.

**Robustness grids**

Fixed in the same commit, which matters more than it looks: the grid the pre-registered
cell is later ranked inside was not drawn after seeing where that cell landed.

| Grid | Values |
|---|---|
| `cost_ticks_grid` | 0, 1, 2, 4 |
| `contango_grid` | 0.95, 0.975, 1.0, 1.025 |
| `vol_target_grid` | 0.10, 0.15, 0.20 |
| `stress_loss_grid` | 0.10, 0.20, 0.30, 1.00 |
| `rebalance_grid` | 1, 5, 21 days |
| `subsamples` | 2008–12, 2013–17, 2018–21, 2022– |
| `stress_windows` | GFC 2008, euro 2011, Aug 2015, Volmageddon 2018, Covid 2020, yen carry 2024 |

---

## 4. What changed after data arrived

Four substantive changes, and no others. `git diff 2bdeb31 HEAD -- config/config.yaml`
is the complete list.

### 4.1 SVIX fee: 1.29% → 1.35%

**When.** `0391147`, 20 September, on reading the archived VS Trust 424B3 of
28 January 2022.

**Why.** 1.29% was carried in from a secondary source and could not be located anywhere
in the primary document, which says the sponsor fee is "1.35% per annum of its average
daily net assets".

**Effect.** 0.06% a year, about 0.24 bp a day, against an SVIX tracking error of 51 bp a
day. It moves the mean residual and no conclusion. The caveat that the archived filing
is the launch document, and that a later fee amendment has not been checked, is in
[`docs/limitations.md`](limitations.md).

### 4.2 Stress floor: the February 2018 move → a running maximum

**When.** `69b748d`, 23 September, committed **before any backtest was run**.

**Why.** The original setting floored the stress loss at the 5 February 2018 index move
of 96.1%. Applied from 2008, that sizes every pre-2018 position using a day that had not
happened — a leak by this project's own look-ahead rule, and flatly contrary to the
research design's requirement of an *ex-ante* stress loss.

**What replaced it.** `stress_floor: running_max`, the largest one-day index rise
observed through `t`. It is the real-time form of the same idea and coincides with the
original from 5 February 2018 onwards.

**Effect.** The event floor is still run, and reported beside the honest configuration
as a labelled hindsight calibration — never as the headline. Full argument in
[`docs/methodology.md`](methodology.md) M8.

### 4.3 A `timing` block, and one extra day of lag on VIX-derived signals

**When.** `aa9c8cf`, 24 September, during the recursive audit (issue A-02).

**Why.** From 26 October 2020 the VX settlement moved to 4:00 p.m. ET while the VIX and
VIX3M cash indices stayed at 4:15 p.m. ET. The VRP filter was therefore being set from a
price struck fifteen minutes *after* the price the position was booked at. The original
configuration had no way to express this, because the project had not yet discovered the
timing gap it is otherwise about.

**Effect.** This is the one post-data change that moved a headline number: the
out-of-sample Sharpe fell from 0.27 to 0.20. Every downstream table, figure and sentence
was recomputed. The finding and its blast radius are A-02 in
[`docs/final_audit_issue_register.md`](final_audit_issue_register.md).

### 4.4 Two comments, no values

`contango_threshold` and `signal_lag` both carried comments that described something
other than what the code did. Both were corrected against the implementation, and
neither value was touched. The `signal_lag` comment is the more serious of the two: it
described a two-day convention, and that wording is part of how A-02 survived sixteen
phases of review.

---

## 5. What this does not protect against

Pre-registration is a narrow instrument and it is worth being precise about its reach
here.

- **It does not stop a lucky draw.** The pre-registered cell earns an out-of-sample
  Sharpe of 0.20 against a grid median of 0.06, at the 74th percentile of 144 cells.
  Fixing the cell in advance rules out searching the grid for it. It does nothing about
  having happened to pick a good one, and both numbers belong in any honest summary.
- **It does not cover implementation choices.** A parameter can be fixed while the code
  that consumes it is wrong. A-02 is the demonstration: `signal_lag = 1` was
  pre-registered, correct, and implemented against a settlement convention that quietly
  did not hold after October 2020.
- **It does not make an unmet hypothesis met.** H3 asked for a factor of ten and got
  8.7. That is recorded as a magnitude miss rather than rounded into a pass.
- **It says nothing about the data.** The sample begins in 2008 and ends at the last
  session available when the project ran. Nothing about fixing parameters early makes
  that window representative of anything.

---

## 6. Where the rest of it lives

| | |
|---|---|
| Hypotheses in full, with rejection criteria | [`docs/research_design.md`](research_design.md) §2 |
| What the evidence leaves of each one | [`docs/research_design.md`](research_design.md) §9, [`docs/results.md`](results.md) |
| Estimator and signal specifications | [`docs/methodology.md`](methodology.md) |
| Every check run, and what it found | [`docs/validation.md`](validation.md) |
| Errors found after the fact, and their blast radius | [`docs/final_audit_issue_register.md`](final_audit_issue_register.md) |
| Dated development history | [`docs/project_log.md`](project_log.md) |
