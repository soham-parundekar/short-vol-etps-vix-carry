# Short-volatility ETPs, rebalancing feedback, and crash-budgeted VIX carry

**One page.** Full write-up: [`reports/report.md`](report.md). Verdicts and their
qualifications: [`docs/results.md`](../docs/results.md). Every number below is asserted
against a committed table by `python scripts/check_results_numbers.py`.

---

## The question

Was the short-volatility trade of the 2010s a harvestable risk premium, or leveraged
compensation for a crash the products' own design helped create — and does bounding
position size by an explicitly estimated crash loss turn it into something an investor
could hold?

## The method

The S&P 500 VIX Short-Term Futures index is rebuilt from raw Cboe VX settlement data
(2008–2026, 4,711 sessions), validated against VIXY, VXX, SVXY and UVXY. Product
mechanics come from the leverage identities and are checked against the funds' own SEC
filings. A GJR-GARCH(1,1) with skewed-*t* innovations and a spliced GPD tail, **fitted on
data ending 31 December 2017 and never refitted**, prices the probability of a
wipeout-sized day. A strategy shorts the index when the curve is in contango and the
variance risk premium is positive, sized by `w = min(σ*/σ̂, ℓ_max/StressLoss, 1)`, with
parameters fixed on 2008–2015 and evaluated out of sample from 2016. Five hypotheses with
their rejection criteria were committed 50 minutes before the first data retrieval.

## Three findings

1. **The index and the products were measured fifteen minutes apart, and that explains
   most of the apparent tracking failure.** VX futures settled at 3:15 p.m. CT until
   23 October 2020 and at 3:00 p.m. CT after; the products close at 4:00 p.m. ET.
   Tracking error against VIXY falls from **133.2 bp/day** (2011–2015) to **31.7 bp/day**
   from 26 October 2020, with the leverage-adjusted slope rising from 0.873 to 0.985.
   On 5 February 2018 the settlement-based index return is +96.1% while the products'
   4:00 p.m. closes imply +32.0% to +34.2%: **57.5% of that day's move, in log terms,
   happened after 4:00 p.m. ET.**

2. **Mechanical rebalancing demand on 5 February 2018 was at least a quarter of
   front-month open interest, and the 2018 de-levering would have cut it to under a
   tenth.** SVXY and UVXY together needed to buy an estimated **55,690 front-month
   contracts — 25.0% of that contract's open interest** — at the lower asset bound.
   Holding assets and the shock fixed and changing only the leverage coefficient from
   2.0 to 0.75 gives **20,884 contracts, 9.4%**. That is arithmetic from disclosed
   assets, not an estimate.

3. **Crash budgeting changes the shape of the loss distribution without creating
   return.** Out of sample the strategy earns a Sharpe of **0.20** (Lo standard error
   0.31), 4.1% a year, maximum drawdown −26.8%. Volatility targeting without the crash
   budget earns −0.03 with a −43.5% drawdown. But a **constant 0.173 short earns 0.40**,
   and the alpha over PUT, SPX and a VXX-like factor is **−2.2% a year (t = −0.77)**.
   The sizing rule buys a better tail, not a better return.

**Verdicts against the pre-registered criteria:** H1 rejected · H2 not rejected · H3 not
rejected but the stated 10× magnitude unmet at 8.7× · H4 rejected · H5 not rejected.

## The caveat that matters most

**The strategy result is specification-dependent.** Across 144 specifications the
out-of-sample Sharpe runs from −0.37 to 0.50 with a **median of 0.06**; the
pre-registered configuration's 0.20 sits at the 74th percentile. The parameters were
fixed before any data was retrieved and the commit history proves it
([`docs/preregistration.md`](../docs/preregistration.md)), so 0.20 is not a mined result
— but a pre-registered draw from a distribution whose median is 0.06 is still a draw.
The strategy earns nothing at 1.77 ticks of transaction cost per side, and its escape
from February 2018 rests on the contango filter clearing its threshold by 0.72% at the
previous close.
