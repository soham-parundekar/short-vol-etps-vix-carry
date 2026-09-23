# Figure index

Every figure in the report, the question it answers, and what it is built
from. Regenerate all of them with `python scripts/make_figures.py`; the
registry in that script is the source of this table.

Inputs marked *(raw)* need the product price history, which is reproduced by
`scripts/fetch_data.py` rather than redistributed (`docs/data_sources.md`);
*(GARCH refit)* means the figure refits the pre-2018 model from the committed
index, which takes a few seconds.

| Figure | Question it answers | Built from |
|---|---|---|
| `index_vs_products.png` | Does the rebuilt index track the products it is supposed to, and how does the difference behave through time? (H1) | index_daily.csv; product prices (raw) |
| `term_structure.png` | What does the futures curve look like through time, and when is it inverted enough to switch the strategy off? | curve_constant_maturity.csv, signals_daily.csv |
| `decay_regression.png` | Do the products decay at the rate the leverage identity predicts? (H2, mechanical part) | index_daily.csv; product prices (raw) |
| `decay_blocks.png` | What do the decay regression's own observations look like, and how much of the -1x result is the single block holding 5-6 February 2018? (H2) | index_daily.csv; product prices (raw) |
| `flow_vs_open_interest.png` | How large was mechanical rebalancing demand against the open interest that had to absorb it, at both asset bounds? (H2) | rebalancing_flows.csv |
| `product_assets_with_anchors.png` | How wide is the band on assets outstanding between the disclosed anchors, and where are the anchors? | product_assets_bounds.csv, product_asset_anchors.csv |
| `mean_excess.png` | Where does the tail of the standardised residuals become straight - i.e. where may a GPD be fitted? (H3) | index_daily.csv (GARCH refit), evt_thresholds.csv |
| `qq_gpd.png` | Does the fitted GPD describe the exceedances it was fitted to? (H3) | index_daily.csv (GARCH refit), evt_thresholds.csv |
| `shape_across_thresholds.png` | Does the tail-shape estimate depend on where the tail is declared to start? (H3) | evt_thresholds.csv |
| `survival_curves.png` | How much more likely was a -1x product to survive five years than a -0.5x one, under the pre-2018 model? (H3) | survival_curves.csv |
| `kelly_growth_curve.png` | Where does expected log growth peak, and how far is the offered -1x from it? (H4) | index_daily.csv, kelly.csv |
| `exante_warning.png` | What did a model fitted before the event say, day by day, going into 5 February 2018? (H3) | exante_warning_path.csv |
| `vrp_timeseries.png` | How large is the variance risk premium, and how often is it negative - the state in which the strategy stands aside? | signals_daily.csv |
| `har_forecast_vs_realised.png` | Do the real-time variance forecasts have out-of-sample skill, and is the trailing-RV benchmark worse? | har_oos_forecasts.csv, har_oos_diagnostics.csv |
| `signal_state.png` | When is the strategy allowed in, and which filter keeps it out when it is not? | signals_daily.csv |
| `equity_curve.png` | How did the strategy compound against every benchmark, including the passive products it is supposed to improve on? (H5) | benchmarks_daily.csv |
| `drawdowns.png` | What did holding each of these cost at the worst moment? | benchmarks_daily.csv |
| `rolling_sharpe.png` | Is the strategy's risk-adjusted return a property of the whole sample or of a few stretches? (H5) | benchmarks_daily.csv |
| `weight_and_binding_constraint.png` | How large was the position, and which of the three constraints set it on each day - with the stress windows shaded? | backtest_daily.csv |
| `feb2018_detail.png` | What happened to the index, the traded products, the strategy's exposure and its equity through the February 2018 event? | backtest_daily.csv, benchmarks_daily.csv; product prices (raw) |
| `cost_sensitivity.png` | At what transaction cost does the out-of-sample Sharpe reach zero? | robustness_costs.csv |
| `parameter_heatmap.png` | How does the result move across the threshold and crash-budget grid, and where does the pre-registered cell sit in it? | specification_distribution.csv |
| `specification_distribution.png` | How much of the headline is the choice of specification? (the median cell against the chosen one) | specification_distribution.csv |
| `subsample_stability.png` | Does the result hold in every subsample, or is it carried by particular years? | robustness_subsamples.csv, specification_distribution.csv |

## Conventions

- One shared style module (`svcarry.viz.style`): the same palette, line styles,
  date formatting and source note on every figure.
- Colour is never the only carrier of meaning. The palette has seven hue pairs
  whose luminance is within 0.07 of each other (`style.greyscale_check`), so
  every multi-series figure also varies line style or marker, and the signal-
  state strip puts each state in its own horizontal band.
- Log scales wherever a series compounds over the full sample.
- Uncertainty is drawn where it exists (simulation error bands on the survival
  curves, one standard error on the EVT shape and the subsample Sharpes, the
  asset-bound band on the flow figure).
- No axis is truncated to exaggerate a difference; where a series is clipped to
  stay legible the caption says so and counts the clipped points.
