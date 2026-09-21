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
