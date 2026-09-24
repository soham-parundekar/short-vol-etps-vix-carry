# When Carry Kills

**Short-volatility ETPs, rebalancing feedback, and a crash-aware VIX carry strategy**

On 5 February 2018 the VIX more than doubled in a single session. Two products
offering the same −1× daily exposure to the same index met different ends: Credit
Suisse terminated XIV under an acceleration clause in its pricing supplement, while
ProShares' SVXY survived and was de-levered to −0.5× three weeks later. This project
rebuilds the index both products tracked from raw Cboe settlement data, derives the
mechanics that made them fragile, estimates — from a model fitted only to pre-event
data — how probable the triggering move was, and asks whether the volatility risk
premium those products harvested can be captured once position size is bounded by
what a crash would cost.

---

## Key findings

**The reconstructed index and the products that tracked it were measured fifteen minutes
apart until October 2020, and that timing — not fee drag or tracking difficulty —
accounts for most of their apparent disagreement:** tracking error against VIXY falls from
**133.2 bp a day** in 2011–2015 to **31.7 bp a day** after the settlement time changed, and
on 5 February 2018 **57.5%** of the index's **+96.1%** move, in log terms, occurred after
the products' 4:00 p.m. close. On that day the mechanical rebalancing demand of SVXY and
UVXY alone was an estimated **55,690 front-month contracts, 25.0% of that contract's open
interest** at the lower asset bound, which the 2018 de-levering would have cut to **20,884
contracts and 9.4%** — arithmetic from disclosed assets, not an estimate. **Bounding
position size by an explicitly estimated crash loss does change the loss distribution** —
an out-of-sample Sharpe of **0.20** and a **−26.8%** drawdown against **−0.03** and
**−43.5%** for volatility targeting alone — **but it does not create return:** a constant
0.173 short earns **0.40**, the alpha over PUT/SPX/VXX is **−2.2% a year (t = −0.77)**, and
the median of the 144-specification grid the pre-registered configuration was drawn from is
**0.06**.

Full write-up: [`reports/report.md`](reports/report.md) ·
one page: [`reports/summary_one_page.md`](reports/summary_one_page.md) ·
verdicts and their qualifications: [`docs/results.md`](docs/results.md).

---

## Status

| | |
|---|---|
| **Research design** | Fixed and committed before any data was retrieved. Five hypotheses, each with a stated rejection criterion |
| **Analysis library** | Complete and tested — **258 tests passing**, 2 skipped (cross-checks against packages not installed) |
| **Data** | Retrieved by `scripts/fetch_data.py`; 338 files, each with URL, retrieval time and SHA-256 in `data/raw/_manifest.json`. 4,711 index sessions, 2008-01-02 to 2026-09-18 |
| **Phases complete** | 07 index validation · 08 mechanics and flows · 09 tail risk and survival · 10 forecasting and signals · 11 backtest and H5 · 12 robustness and red-team · 13 results · 14 figures · 15 documentation and report · 16 final audit · **recursive audit** (`docs/final_audit_issue_register.md`) |
| **Hypotheses** | H1 **rejected** · H2 **not rejected** (25.0% of front-month open interest at the lower asset bound) · H3 **not rejected, magnitude unmet** (8.7×, not 10×) · H4 **rejected** · H5 **not rejected** (out-of-sample Sharpe 0.20 ± 0.31; alpha −2.2% a year, t = −0.77) |
| **What the backtest does not show** | The dynamic rule does not beat a constant 0.173 short (Sharpe 0.40); what it buys is the tail (worst day −11.7% against −16.6%). Its escape from 5 February 2018 rests on one filter clearing its threshold by 0.72% the day before |
| **How robust** | Across 144 specifications the out-of-sample Sharpe runs −0.37 to 0.50, **median 0.06**; the pre-registered cell (0.20) is the 74th percentile. Breakeven cost 1.77 ticks per side. Rebalancing weekly instead of daily loses 31.7% in February 2018 |

`python scripts/check_results_numbers.py` re-reads the committed tables and asserts every
number quoted in this README, the report, the one-page summary and `docs/results.md`; it
exits non-zero on any disagreement. Each number is traced in `docs/validation.md`, with
what remains imperfect in `docs/limitations.md` and the sequence of work — including errors
caught and what they were worth — in `docs/project_log.md`.

The environment used to build this repository could not reach the data hosts or PyPI
through its egress proxy. The data was therefore fetched on the author's own machine by
the same script, and every file re-hashed against the manifest on arrival.

One consequence is visible throughout and is arguably an improvement: with `arch` and
`statsmodels` uninstallable, **every estimator is implemented in this repository** —
GJR-GARCH with Hansen skewed-*t* innovations, peaks-over-threshold GPD, HAR, Newey-West
HAC, range-based realised variance, Kelly, the stationary bootstrap — and each is
unit-tested against simulated data with known parameters. Where those packages *are*
available the suite cross-checks against them automatically.

---

## Research question

> Was the short-volatility trade of the 2010s a harvestable risk premium, or
> leveraged compensation for a crash that the products' own design helped create —
> and does bounding position size by an explicitly estimated crash loss turn it into
> something an investor could hold?

Five hypotheses, each falsifiable, stated in full in
[`docs/research_question.md`](docs/research_question.md) and
[`docs/research_design.md`](docs/research_design.md):

| | Hypothesis | Rejected if |
|---|---|---|
| H1 | The index rebuilt from Cboe data tracks VIXY and VXX within 10 bp/day net of fees | tracking error > 25 bp/day, or residuals correlate with the roll weight |
| H2 | Mechanical rebalancing demand exceeded 10% of front-month open interest on the largest up-moves of 2016–18 | it fails at either bound on assets outstanding |
| H3 | Under a GARCH-EVT model fitted to data ending 2017-12-31, P(index +80% in a day) is ≥ 10× P(+160%), and the −1× / −0.5× survival gap is stable across the EVT threshold grid | the ordering reverses, the gap is threshold-dependent, or the event is so improbable it cannot be called foreseeable |
| H4 | Kelly-optimal short exposure is strictly below 1.0 in magnitude, with a bootstrap interval excluding 1.0 | the interval contains 1.0 |
| H5 | Crash-budgeted short volatility earns a positive out-of-sample Sharpe net of costs, **but** its alpha over PUT / SPX / VXX is not distinguishable from zero | either half fails — and a *significant positive* alpha triggers a leak hunt, not a celebration |

H5 is deliberately uncomfortable in both directions. A design in which every hypothesis
predicts the flattering outcome is a design that will find it.

---

## What is actually novel here

The components are individually standard, and the review in
[`docs/literature_review.md`](docs/literature_review.md) says so: the term-structure
signal is Simon & Campasano (2014); the rebalancing identity is Cheng & Madhavan
(2009); the decay identity is Avellaneda & Zhang (2010); the February 2018 mechanism is
documented by Augustin, Cheng & Van den Bergen (2021). The contribution is the
combination and the discipline of the evaluation:

1. **An ex-ante survival comparison across product designs.** The tail model is
   estimated on data ending 31 December 2017, so the probability it assigns to
   Volmageddon is genuinely out of sample. The same model prices the −0.5× design,
   turning "de-levering helped" into a survival curve.
2. **Offered leverage against growth-optimal leverage.** The Kelly fraction on the same
   index, with a bootstrap interval, compared directly with the −1× the products sold.
3. **Crash-budgeted sizing.** `w = min(σ*/σ̂, ℓ_max/StressLoss)` — size capped by what a
   crash would cost rather than by recent volatility, which is the failure mode of
   volatility targeting in this asset, since the calmest periods are the ones the
   spikes start from.

---

## Methodology in one page

**Index reconstruction.** Two nearest monthly VX contracts, weights `w1 = dr/dt` linear
in business days across a roll period running from one settlement date to the next.
The daily return prices **the contracts held at `t−1`** on both days — differencing a
"front month" series instead books the calendar spread as a price move on every roll
date, which is the error that silently ruins most VIX index rebuilds. The settlement
calendar is derived from the contract specification and unit-tested against known
expiries. Both plausible roll conventions are built and the choice is made on tracking
error, not asserted.

**Product mechanics.** `ΔE = L(L−1)·A·r` for the rebalancing demand — positive for
every `L` outside `[0,1]`, so a 2× long and a −1× inverse fund both *buy* after the
index rises; de-levering to −0.5× cuts the coefficient from 2.0 to 0.75. And
`V_T/V_0 = (I_T/I_0)^L exp(−½(L²−L)σ²T)` for the decay, tested by regressing
`ln(V_T/V_0) − L·ln(I_T/I_0)` on realised variance, separately before and after the
documented February 2018 leverage change.

**Tail model.** GJR-GARCH(1,1) with skewed-*t* innovations, then a GPD fitted to
standardised residuals above a threshold chosen by a rule fixed in advance
(McNeil & Frey, 2000). Termination probabilities for an 80% index move (−1×) and a
160% move (−0.5×), unconditionally and conditional on calm; survival by Monte Carlo;
Kelly with a stationary-bootstrap interval.

**Strategy.** Short the reconstructed index when the curve is in contango and the
variance risk premium is positive, sized by the crash budget above. Signal at the close
of `t−1`, traded at the close of `t`. Costs of 1 tick per side by default (swept 0–4),
expressed relative to the futures price actually held. Collateral earns the 91-day bill
accrual on the S&P DJI convention — the same one the ETN "Daily Accrual" uses.
Parameters fixed on 2008–2015; evaluated from 2016, a window containing February 2018,
March 2020 and August 2024.

Full detail: [`docs/research_design.md`](docs/research_design.md).

---

## Data

| Dataset | Source | Role |
|---|---|---|
| VX futures settlement, OHLC, volume, open interest, per contract | Cboe, one CSV per expiry | Index rebuild, curve, flow denominator |
| VIX, VIX3M, VIX9D, VIX6M, VVIX, PUT, BXM | Cboe index history | Implied leg of the VRP; slope signal; PutWrite benchmark |
| VXX, VIXY, SVXY, UVXY, SVIX, SPY, ^GSPC | Yahoo Finance (Stooq fallback) | Tracking validation, decay test, realised variance |
| DTB3, DGS3MO | FRED | Total-return accrual and collateral |
| Product filings | SEC EDGAR | Every product term the project asserts |

Sample 2008-01-02 onwards, daily. All sources are free and public; none requires
registration. Raw data is **not** redistributed — `scripts/fetch_data.py` plus the
SHA-256 manifest in `data/raw/_manifest.json` reproduces it exactly.

Two hazards are handled explicitly rather than assumed away: VXX and UVXY have
reverse-split many times, so the split adjustment is reconstructed independently and
checked against the provider's; and the Cboe VIX3M history begins in September 2009,
inside the design window, so the interpolated `cm30/cm90` slope is the primary signal
with `VIX/VIX3M` as a robustness variant. Details in
[`docs/data_sources.md`](docs/data_sources.md).

---

## Repository

```
config/          config.yaml (every tunable parameter) and filings.yaml (primary sources)
data/            raw / interim / processed, with a provenance manifest
docs/            research question, design, literature, data sources, methodology,
                 results, validation, limitations, project log, figure index
prompts/         the phase, task and operational prompts used to build the project
references/      bibliography and archived SEC filings
reports/         report.md, summary_one_page.md, 24 figures and 42 tables
scripts/         fetch_data.py, run_pipeline.py, make_figures.py, run_tests.py,
                 check_results_numbers.py
src/svcarry/
  config.py      YAML-backed configuration
  data/          cached, throttled, hashed downloaders (Cboe, prices, FRED, EDGAR)
  index/         VIX futures settlement calendar; index reconstruction; carry
  etp/           NAV recursion, rebalancing identity, leverage decay, wipeout thresholds
  econometrics/  HAC/OLS, skewed-t, GJR-GARCH, GPD/EVT, HAR, realised variance,
                 Kelly, stationary bootstrap
  strategy/      signals, crash-budgeted sizing, backtest engine
  evaluation/    performance metrics, drawdowns, attribution regressions
  viz/           shared style and one function per figure
tests/           246 tests (244 pass, 2 skipped when optional packages are absent)
```

## Running it

```bash
git clone https://github.com/soham-parundekar/short-vol-etps-vix-carry
cd short-vol-etps-vix-carry
pip install -e .            # numpy, pandas, scipy, matplotlib, requests, PyYAML

make data                   # download everything (idempotent; cached and hashed)
make test                   # 246 tests; uses pytest if installed, else the bundled runner
make pipeline               # clean -> index -> mechanics -> tail -> signals -> backtest
make figures
make verify                 # re-hash every file against the manifest
```

`make test` needs no third-party test runner: `scripts/run_tests.py` supplies a minimal
pytest shim, and the tests are ordinary pytest tests that run unchanged under real
pytest.

The pipeline never reaches the network. If raw data is absent it stops and tells you to
run `make data`, so a figure can never be produced from data whose provenance was not
recorded.

---

## Main outputs

| Output | What it is |
|---|---|
| [`reports/report.md`](reports/report.md) | The full write-up: background and filings, data, methodology, results, robustness, discussion, limitations |
| [`reports/summary_one_page.md`](reports/summary_one_page.md) | Question, method, three findings, one caveat |
| [`docs/results.md`](docs/results.md) | The five verdicts against their pre-registered criteria, with each conclusion's qualification attached |
| `reports/tables/` | 42 CSVs. Every number in the prose is one of these |
| `reports/figures/` | 24 figures, each built by `scripts/make_figures.py` with the question it answers recorded in [`docs/figure_index.md`](docs/figure_index.md) |
| `data/processed/` | The reconstructed index, curve, signals, weights and backtest, daily |

```bash
python scripts/make_figures.py --list        # every figure and the question it answers
python scripts/make_figures.py --only equity_curve
python scripts/check_results_numbers.py      # assert the prose against the tables
```

---

## Validation

The tests that matter most, all of which currently pass:

- **Index reconstruction against a synthetic panel with a known answer.** A steeply
  sloped term structure in which every contract's *own* price is constant must produce
  exactly zero index return. It does — while a naive front-month `pct_change()` books a
  fake loss above 2% on every roll date.
- **Look-ahead, mechanically.** Perturb every input after a cut-off date and require
  each earlier forecast and strategy return to be **bit-identical**. Both the HAR
  forecaster and the backtest engine pass.
- **Leak calibration.** A deliberately leaked signal (same-day information) earns a
  Sharpe near 11; the engine's one-day lag reduces it to zero. The gap is what a leak
  would have been worth, and is reported so a reader can judge whether the honest
  result is plausibly contaminated.
- **Parameter recovery.** GJR-GARCH, GPD, HAR and the leverage-decay identity are each
  recovered from simulated data generated by the model they estimate.
- **Distributions.** Hansen's skewed-*t* density integrates to one, has mean 0 and
  variance 1, its CDF equals the integrated PDF, and its quantile function inverts the
  CDF — checked across six parameter sets.

Full record: [`docs/validation.md`](docs/validation.md) (populated as each phase runs).

---

## Limitations

Stated here rather than only in the report, because they bound what the project can
claim:

- **The strategy result is specification-dependent.** The pre-registered cell earns 0.20
  against a grid median of 0.06, at the 74th percentile of 144 cells. Pre-registration
  protects against searching the grid; it does not protect against having drawn a good
  cell. Both numbers belong in any honest summary of this project.
- **The strategy does not beat the naive alternative.** A constant 0.173 short earns a
  Sharpe of 0.40 against the dynamic rule's 0.20. What the rule buys is the tail — a
  worst day of −11.7% against −16.6% — not return. The alpha over PUT/SPX/VXX is −2.2% a
  year (t = −0.77).
- **Several alternative specifications beat the pre-registered one.** Not log-transforming
  the HAR earns 0.24, smearing retransformation 0.23, a Parkinson variance proxy 0.27, a
  63-day volatility lookback 0.30 and a 21-day rebalance 0.38, all against the chosen
  cell's 0.20. The configuration was fixed before any data existed and is not changed
  after the fact, but it is not the best cell and this project does not present it as one.
- **The escape from February 2018 rests on a 0.72% margin.** The contango filter cleared
  its threshold by that much at the close of 2 February. At a threshold of 1.025 the
  February return is −24.3%; rebalancing weekly instead of daily gives −31.7% with a worst
  day of −38.0%. And the VRP filter — the other half of the entry rule — was *on* that
  day, so only one of the two filters did any work.
- **Breakeven cost is 1.77 ticks per side** (0.088 VIX points). One tick is the quoted
  spread in calm markets and two is not unusual in a crisis, which is when this strategy
  trades most — so the breakeven sits inside the range of spreads the strategy would
  actually have faced.
- **A fifteen-minute timing overlap was found and corrected after the project was first
  declared complete.** From 26 October 2020 the VX settlement moved to 4:00 p.m. ET while
  the VIX cash close stayed at 4:15 p.m. ET, so the VRP filter had been set from a price
  struck after the one the position was booked at. Correcting it moved the out-of-sample
  Sharpe from 0.27 to 0.20. The mechanism is the same fifteen-minute gap this project's
  first finding is about; it is recorded as A-02 in
  [`docs/final_audit_issue_register.md`](docs/final_audit_issue_register.md).
- **Daily data only.** The intraday sequence on 5 February 2018 — including the
  after-hours move that triggered XIV's acceleration — cannot be resolved. The flow
  analysis shows mechanical demand was *large relative to* open interest; it does not
  establish that it caused the size of the move.
- **Assets outstanding are inferred**, not observed, for most of the sample. Results are
  reported as a range between bounds anchored on disclosed figures, and the H2 claim is
  stated at the lower bound. Scope is SVXY and UVXY only, so it understates the complex.
- **One day dominates the tail.** February 2018 is the largest observation in the sample,
  so every tail headline is reported across the EVT threshold grid and with that day
  jackknifed out. Five-year survival is reported as a pair (81.1% unbounded, 89.9% capped)
  because the model's own volatility dynamics cannot be extrapolated safely.
- **The stated H3 magnitude was not met.** The −0.5× design is 8.7 times safer on the
  headline threshold, between 5.3 and 9.4 across the grid — not the 10× the hypothesis
  claimed.
- **1–3% of the post-2020 tracking slope is unexplained** and daily data cannot allocate
  it between residual fee drag and index noise.
- **Futures only.** No free historical option data, so option-based implementations of
  the same premium are out of scope.
- **A backtest is not an expected return.** The strategy trades an index with stylised
  costs. It tests whether a premium survives frictions and a crash budget; it is not a
  claim about implementable returns.

---

## References

Selected; full bibliography with verification status in
[`references/references.bib`](references/references.bib).

Augustin, Cheng & Van den Bergen (2021), *Financial Analysts Journal* 77(3) ·
Avellaneda & Zhang (2010), *SIAM J. Financial Mathematics* 1 ·
Bollerslev, Tauchen & Zhou (2009), *RFS* 22(11) ·
Carr & Wu (2009), *RFS* 22(3) ·
Cheng (2019), *RFS* 32(1) ·
Cheng & Madhavan (2009), *J. Investment Management* ·
Corsi (2009), *J. Financial Econometrics* 7(2) ·
Eraker & Wu (2017), *JFE* 125(1) ·
Glosten, Jagannathan & Runkle (1993), *JF* 48(5) ·
Hansen (1994), *International Economic Review* 35(3) ·
Lo (2002), *FAJ* 58(4) ·
McNeil & Frey (2000), *J. Empirical Finance* 7(3–4) ·
Politis & Romano (1994), *JASA* 89(428) ·
Simon & Campasano (2014), *J. Derivatives* 21(3) ·
Yang & Zhang (2000), *J. Business* 73(3)

---

## Licence

MIT. See [`LICENSE`](LICENSE).
