# Research question

## The question

> **Was the short-volatility trade of the 2010s a harvestable risk premium, or
> leveraged compensation for a crash that the products' own design helped to
> create — and does bounding position size by an explicitly estimated crash loss
> turn it into something an investor could actually hold?**

The question is deliberately framed so that it can come out either way. "Short
volatility earns a premium" and "short volatility earns nothing once you price the
tail" are both admissible answers, and the design below commits in advance to the
tests that separate them.

## Why this question and not the obvious one

The obvious project on this topic is *"XIV blew up, here is a chart of it"*. That is
a description, not research: the outcome is known, the sample contains exactly one
event, and no decision follows from it.

Three choices turn the topic into a question with content.

**1. Treat product design as the object of study, not the backdrop.**
Four products — XIV, SVXY, UVXY and SVIX — reference the same underlying index and
differ only in wrapper (ETN vs commodity-pool ETF), leverage (−1×, −0.5×, +2×,
+1.5×) and the presence of an acceleration clause. That is close to a controlled
experiment in contract design. On 5 February 2018 the same index shock hit all of
them; one was terminated by contract, one survived and was subsequently de-levered.
Asking *which design features determined survival, and by how much* is a question
about financial engineering rather than about a historical episode.

**2. Ask for a probability, not a narrative.**
"Volmageddon was a once-in-a-lifetime event" is untestable as stated. "Under a
GJR-GARCH model with conditional extreme-value tails fitted only to data available
before 2018, the annualised probability of an index move large enough to trigger
XIV's acceleration clause was *p*" is testable, is sensitive to assumptions that can
be stated and varied, and yields a comparison across designs: the same model says
what the −0.5× product would have needed.

**3. Separate the premium from the leverage.**
A −1× product is two decisions bundled together: *be short volatility* and *be short
volatility at one times net assets, rebalanced daily, forever*. The variance risk
premium literature is about the first. The 2018 failure is about the second. The
Kelly criterion is the natural instrument for separating them, because it answers
exactly the question "given this return distribution, what exposure maximises
long-run growth?" — and the answer can be compared with the exposure the products
actually offered.

## Sub-questions

| # | Question | Resolved by | Falsifiable how |
|---|----------|-------------|-----------------|
| Q1 | Can the common underlying index be rebuilt from raw Cboe settlement data, and how closely does the rebuild track the traded products once fees are added back? | Index reconstruction validated against VIXY, VXX and SVXY | Tracking error is reported; a rebuild that cannot match the products within a stated tolerance invalidates everything downstream and is reported as such |
| Q2 | How large was the mechanical end-of-day rebalancing demand created by leveraged and inverse products, relative to the front-month VIX futures market that had to absorb it? | `dE = L(L−1) A r` applied to estimated product assets, converted to contract equivalents and scaled by open interest | The flow estimate depends on assets outstanding; bounds are computed under best and worst assumptions and the conclusion must survive both |
| Q3 | Under a heavy-tailed conditional model estimated on pre-event data only, how probable was an index move large enough to terminate a −1× product, and how much does de-levering to −0.5× change survival? | GJR-GARCH with skewed-t innovations, conditional EVT on standardised residuals, Monte Carlo survival | Probabilities are reported across a grid of EVT thresholds and model specifications; a result that only holds at one threshold is not a result |
| Q4 | Is the leverage these products offered above or below the growth-optimal (Kelly) exposure to the same index? | Kelly fraction under the fitted distribution and under the empirical distribution | Estimated with confidence intervals; if −1× lies inside the interval, the product-design critique fails |
| Q5 | Once position size is capped by an ex-ante stress loss, does short volatility earn a positive risk-adjusted return out of sample — and is that return alpha or compensation for crash risk? | Strategy with parameters fixed on 2008–2015, evaluated from 2016; alpha regression on the Cboe PutWrite index, S&P 500 and VXX | Reported out-of-sample only, with cost sensitivity from 0 to 4 ticks; a strategy that survives only at zero costs has not survived |

## What this project does *not* claim

- **Not a causal claim about 5 February 2018.** The rebalancing-flow analysis shows
  that the mechanical demand was large relative to the market. It does not establish
  that this demand *caused* the size of the move; daily data cannot resolve the
  intraday sequence, and the analysis says so.
- **Not an investable strategy.** The backtest trades a futures index with stylised
  costs. It is an empirical test of whether a premium survives realistic frictions
  and explicit tail budgeting, not a claim about implementable returns.
- **Not a prediction.** Every probability is conditional on a fitted model and on a
  sample; the reported sensitivity to those choices is part of the result rather than
  an appendix to it.

## Relationship to existing work

Augustin, Cheng and Van den Bergen (*Financial Analysts Journal*, 2021) document the
February 2018 episode and the rebalancing feedback in detail. This project takes
that mechanism as established and asks the forward-looking questions the episode
raises: what probability an ex-ante model would have assigned to the triggering
event, how much of the fragility was removed by de-levering rather than by luck, how
the offered leverage compares with the growth-optimal one, and whether the premium
survives when size is bounded by the tail rather than by volatility alone. The
contribution is the combination of an ex-ante survival framework across product
designs with a crash-budgeted strategy evaluated strictly out of sample.

See `docs/literature_review.md` for the full treatment of prior work and
`docs/research_design.md` for the methodology, hypotheses and test plan.
