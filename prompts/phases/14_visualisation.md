# Phase 14 — Visualisation

## 1. Objective

Produce figures that answer the project's questions. Every figure must have a question
it answers; a figure that exists because the data was available does not go in.

## 2. Context

The project's arguments are mostly comparisons — rebuilt index against traded product,
one leverage against another, one sizing rule against another, one period against the
rest — and comparisons are what figures do better than tables. The figures that earn
their place here are the ones where the number alone does not convey the shape:
the survival curves, the growth-rate curve with the offered leverage marked, the
mean-excess plot, the weight series coloured by which constraint binds.

## 3. Inputs

All processed data and results from Phases 07–12.

## 4. Tasks

Build, at minimum:

1. Reconstructed index against VIXY and VXX, with the tracking residual beneath.
2. Term structure: the constant-maturity curve through time, and the slope with the
   signal threshold marked.
3. Leverage decay: realised versus theoretical, one panel per product, with the
   February 2018 break visible for SVXY and UVXY.
4. Rebalancing flow as a share of front-month open interest, with the asset bounds as
   a band rather than a line.
5. Tail diagnostics: mean-excess with confidence bands, GPD QQ plot, and the shape
   parameter across the threshold grid.
6. Survival curves for −1× and −0.5× with simulation error bands.
7. Kelly growth-rate curve with −1× and −0.5× marked on it.
8. Strategy equity curve against every benchmark, log scale.
9. Drawdown chart.
10. Weight through time, coloured by which constraint binds, with the stress windows
    shaded.
11. Cost sensitivity and the specification distribution.
12. February 2018 in detail: index, products, strategy weight and strategy equity.

Every figure gets: a title stating what it shows, axis labels with units, correct date
formatting, a legend where more than one series appears, and a source note.

## 5. Tools and methods

`matplotlib` through a single shared style module so that every figure in the report
looks like it came from the same project. No chart library that is not already a
dependency.

## 6. Execution instructions

Write one function per figure, taking data and returning a figure, so that each can be
regenerated independently and tested.

Use log scales for anything that compounds over a decade. A linear-scale equity curve
covering 2008–2026 for a volatility product is unreadable and, worse, misleading about
the early period.

Never truncate an axis in a way that exaggerates a difference. If a series must be
clipped to remain legible, say so in the caption and mark the clipped points.

Colour must not be the only carrier of meaning: use line style or markers as well.

## 7. Validation criteria

| Check | Pass | Warning | Failure |
|---|---|---|---|
| Purpose | every figure maps to a question in the design | a decorative figure, removed | a decorative figure retained |
| Labels | title, axes with units, legend, source on every figure | one missing | several missing |
| Scale | log used where appropriate; no truncated axes | — | a truncated axis that changes the impression |
| Uncertainty | error bands shown where they exist | — | a point estimate drawn as if exact |
| Reproducibility | every figure regenerates from committed data | — | a hand-edited figure |
| Accessibility | meaning survives in greyscale | — | colour-only encoding |

## 8. Self-review

- Does any figure imply more precision than the underlying estimate has?
- Does the flow figure show the asset-bound band, or a single line?
- Is the February 2018 detail figure honest about what daily data cannot show?
- Would each figure be interpretable with only its caption?

## 9. Deliverables

- `src/svcarry/viz/` — style module and figure functions
- `scripts/make_figures.py`
- `reports/figures/*.png` (and `.pdf` where the report needs vector output)
- A figure index listing each figure and the question it answers

## 10. Git requirements

Commit the figure code and the figure index. Commit the rendered figures if they are
small; otherwise regenerate from `make figures`. Commit message lists the figures
produced.

## 11. Completion gate

- [ ] Every figure maps to a research question
- [ ] Labels, units and sources complete
- [ ] Uncertainty shown where it exists
- [ ] All figures regenerate from a single script
- [ ] Greyscale-legible
- [ ] Figure index written

## 12. Handoff

Phase 15 consumes the figures and the index.
