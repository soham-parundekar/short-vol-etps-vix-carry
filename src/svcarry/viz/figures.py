"""Figure functions, one per question the report needs answered.

Each function takes data and returns a matplotlib figure; none of them read from
disk or decide what to plot. That separation is what lets `scripts/make_figures.py`
regenerate every figure from committed data, and lets `tests/test_viz.py` exercise
them on synthetic inputs.

Every figure carries a title stating what it shows, a y-axis label with units, a
legend whenever there is more than one series, direct labels where there are four or
fewer, and a source note. Uncertainty is drawn as a band wherever an estimate has
one; a point estimate is never drawn as though it were exact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .style import (
    INK,
    PALETTE,
    add_source,
    diverging_cmap,
    direct_label,
    format_date_axis,
    new_figure,
    sequential_cmap,
    series_style,
    shade_windows,
)

__all__ = [
    "plot_index_vs_products",
    "plot_term_structure",
    "plot_decay_regression",
    "plot_flow_vs_open_interest",
    "plot_mean_excess",
    "plot_gpd_qq",
    "plot_survival_curves",
    "plot_kelly_growth_curve",
    "plot_equity_curves",
    "plot_drawdowns",
    "plot_weight_and_constraint",
    "plot_cost_sensitivity",
    "plot_parameter_heatmap",
    "plot_event_detail",
]

_SOURCE = "Source: Cboe VIX futures settlement data, Cboe index history, Yahoo Finance, FRED. Author's calculations."


# --------------------------------------------------------------- reconstruction
def plot_index_vs_products(
    index_level: pd.Series, product_levels: "dict[str, pd.Series]",
    residual: pd.Series | None = None, source: str = _SOURCE,
):
    """Rebuilt index against the traded products, with the tracking residual below.

    Log scale on the level panel: over eighteen years a short-term VIX futures index
    falls by several orders of magnitude, and a linear axis would compress the whole
    pre-2015 history into the baseline.
    """
    nrows = 2 if residual is not None else 1
    fig, axes = new_figure(
        "Reconstructed short-term VIX futures index and the products that track it",
        "Index level (rebased to 100 at the start of the sample, log scale)",
        figsize=(9.5, 6.0 if nrows == 2 else 4.6),
        nrows=nrows, height_ratios=[3, 1] if nrows == 2 else None,
    )
    ax = axes[0] if nrows == 2 else axes

    st = series_style(0)
    base = index_level / index_level.dropna().iloc[0] * 100.0
    ax.plot(base.index, base.values, label="Reconstructed index", **st)
    direct_label(ax, base.dropna().index[-1], base.dropna().iloc[-1],
                 "reconstructed", st["color"])

    for i, (name, lvl) in enumerate(product_levels.items(), start=1):
        st = series_style(i)
        s = lvl.dropna()
        if s.empty:
            continue
        s = s / s.iloc[0] * 100.0
        ax.plot(s.index, s.values, label=name, alpha=0.9, **st)
        if len(product_levels) <= 3:
            direct_label(ax, s.index[-1], s.iloc[-1], name, st["color"])

    ax.set_yscale("log")
    ax.legend(loc="upper right", ncol=2)
    format_date_axis(ax)

    if residual is not None:
        rax = axes[1]
        rax.axhline(0.0, color=INK["muted"], lw=0.8)
        rax.plot(residual.index, residual.values * 1e4, color=INK["secondary"], lw=0.9)
        rax.set_ylabel("Tracking\ndifference (bp/day)")
        format_date_axis(rax)
    add_source(fig, source)
    return fig


def plot_term_structure(
    cm: pd.DataFrame, slope: pd.Series | None = None, threshold: float | None = None,
    source: str = _SOURCE,
):
    """Constant-maturity futures curve through time, and the slope signal below."""
    nrows = 2 if slope is not None else 1
    fig, axes = new_figure(
        "VIX futures term structure, constant-maturity points",
        "Futures price (VIX index points)",
        figsize=(9.5, 6.0 if nrows == 2 else 4.6),
        nrows=nrows, height_ratios=[2, 1] if nrows == 2 else None,
    )
    ax = axes[0] if nrows == 2 else axes
    cols = [c for c in cm.columns if c.startswith("cm")][:6]
    for i, c in enumerate(cols):
        st = series_style(i)
        ax.plot(cm.index, cm[c].values, label=f"{c[2:]}-day", **st)
    ax.legend(loc="upper right", ncol=3, title="constant maturity")
    format_date_axis(ax)

    if slope is not None:
        sax = axes[1]
        sax.plot(slope.index, slope.values, color=PALETTE[0], lw=1.2)
        if threshold is not None:
            sax.axhline(threshold, color=INK["secondary"], lw=1.0, ls=(0, (4, 2)))
            sax.annotate(f"threshold {threshold:g}", xy=(slope.index[0], threshold),
                         xytext=(4, 4), textcoords="offset points",
                         fontsize=8.5, color=INK["secondary"])
        sax.set_ylabel("30d / 90d\nslope ratio")
        format_date_axis(sax)
    add_source(fig, source)
    return fig


# -------------------------------------------------------------------- mechanics
def plot_decay_regression(results: "dict[str, object]", source: str = _SOURCE):
    """Estimated variance coefficient against the closed-form value, per product.

    A dot plot rather than a bar chart: these are point estimates with standard
    errors, and a bar implies a magnitude measured from zero, which this is not.
    """
    fig, ax = new_figure(
        "Leverage decay: estimated variance coefficient against theory",
        "Coefficient on realised variance",
        xlabel="",
        figsize=(8.2, 4.4),
    )
    names = list(results)
    y = np.arange(len(names))[::-1]
    for k, (nm, r) in enumerate(results.items()):
        yy = y[k]
        ax.errorbar(r.slope, yy, xerr=1.96 * r.slope_se, fmt="o",
                    color=PALETTE[0], ecolor=INK["muted"], elinewidth=1.2,
                    capsize=3, markersize=7, zorder=3)
        ax.plot([r.theoretical], [yy], marker="|", markersize=16,
                color=PALETTE[1], mew=2.2, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.grid(axis="y", visible=False)
    ax.plot([], [], "o", color=PALETTE[0], label="estimated (95% CI)")
    ax.plot([], [], "|", color=PALETTE[1], markersize=12, mew=2.2,
            label=r"theoretical $-\frac{1}{2}(L^2-L)$")
    ax.legend(loc="lower right")
    add_source(fig, source)
    return fig


def plot_flow_vs_open_interest(
    share_lower: pd.Series, share_upper: pd.Series, index_return: pd.Series | None = None,
    windows: "dict[str, tuple] | None" = None, source: str = _SOURCE,
):
    """Mechanical rebalancing demand as a share of front-month open interest.

    Drawn as a band between the lower and upper asset bounds, because assets
    outstanding are inferred rather than observed for most of the sample. A single
    line here would claim a precision the inputs do not support.
    """
    fig, ax = new_figure(
        "End-of-day rebalancing demand from leveraged and inverse VIX products",
        "Implied trade as a share of front-month open interest",
        figsize=(9.5, 4.8),
    )
    if windows:
        shade_windows(ax, windows)
    ax.axhline(0.0, color=INK["muted"], lw=0.8)
    ax.fill_between(share_lower.index, share_lower.values, share_upper.values,
                    color=PALETTE[0], alpha=0.30, lw=0,
                    label="range implied by the asset bounds")
    mid = (share_lower + share_upper) / 2.0
    ax.plot(mid.index, mid.values, color=PALETTE[0], lw=1.0, label="midpoint")
    ax.legend(loc="upper left")
    format_date_axis(ax)
    add_source(fig, source + " Assets outstanding bounded between disclosed anchors; see docs/methodology.md.")
    return fig


# ------------------------------------------------------------------ tail model
def plot_mean_excess(u: np.ndarray, me: np.ndarray, se: np.ndarray,
                     chosen: float | None = None, source: str = _SOURCE):
    """Mean-excess plot with pointwise bands; linear region justifies the threshold."""
    fig, ax = new_figure(
        "Mean excess over threshold, with pointwise standard errors",
        "Mean excess (standardised residual units)",
        xlabel="Threshold (standardised residual units)",
        figsize=(8.2, 4.6),
    )
    ax.fill_between(u, me - 1.96 * se, me + 1.96 * se, color=PALETTE[0],
                    alpha=0.22, lw=0, label="95% band")
    ax.plot(u, me, color=PALETTE[0], lw=1.6, label="mean excess")
    if chosen is not None:
        ax.axvline(chosen, color=PALETTE[1], lw=1.2, ls=(0, (5, 2)))
        ax.annotate("chosen threshold", xy=(chosen, np.nanmax(me)),
                    xytext=(6, -4), textcoords="offset points",
                    fontsize=9, color=PALETTE[1])
    ax.legend(loc="upper left")
    add_source(fig, source + " A GPD tail implies a straight line with slope xi/(1-xi).")
    return fig


def plot_gpd_qq(empirical: np.ndarray, theoretical: np.ndarray, source: str = _SOURCE):
    """Quantile-quantile plot of the fitted GPD against the excesses."""
    fig, ax = new_figure(
        "Fitted Generalised Pareto tail against the observed excesses",
        "Empirical quantile of the excesses",
        xlabel="Quantile implied by the fitted GPD",
        figsize=(5.6, 5.4),
    )
    lim = [float(min(theoretical.min(), empirical.min())),
           float(max(theoretical.max(), empirical.max()))]
    ax.plot(lim, lim, color=INK["muted"], lw=1.0, ls=(0, (4, 2)), label="45 degrees")
    ax.plot(theoretical, empirical, "o", color=PALETTE[0], markersize=5,
            markeredgecolor=INK["surface"], markeredgewidth=0.6, label="excesses")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(loc="upper left")
    add_source(fig, source)
    return fig


def plot_survival_curves(curves: "dict[str, pd.Series]",
                         bands: "dict[str, tuple] | None" = None,
                         source: str = _SOURCE):
    """Simulated survival probability by product design, with simulation error."""
    fig, ax = new_figure(
        "Simulated survival probability by daily leverage",
        "Probability of surviving without an 80% single-day loss",
        xlabel="Years",
        figsize=(8.2, 4.8),
    )
    for i, (name, s) in enumerate(curves.items()):
        st = series_style(i)
        ax.plot(s.index, s.values, label=name, **st)
        if bands and name in bands:
            lo, hi = bands[name]
            ax.fill_between(s.index, lo, hi, color=st["color"], alpha=0.18, lw=0)
        direct_label(ax, s.index[-1], s.iloc[-1], name, st["color"])
    ax.set_ylim(0, 1.02)
    ax.legend(loc="lower left")
    add_source(fig, source + " Paths simulated from the GJR-GARCH / EVT model fitted to data ending 2017-12-31.")
    return fig


def plot_kelly_growth_curve(f_grid: np.ndarray, growth: np.ndarray,
                            f_star: float, marks: "dict[str, float] | None" = None,
                            source: str = _SOURCE):
    """Expected log growth against short exposure, with the offered leverage marked.

    The clearest single statement of the product-design argument: if the offered
    exposure sits to the right of the peak, the product was levered past the
    growth-optimal point for a long-horizon holder.
    """
    fig, ax = new_figure(
        "Growth-optimal short exposure against the leverage the products offered",
        "Expected log growth per year",
        xlabel="Short exposure to the index (fraction of capital)",
        figsize=(8.4, 4.8),
    )
    ok = np.isfinite(growth)
    ax.axhline(0.0, color=INK["muted"], lw=0.8)
    ax.plot(f_grid[ok], growth[ok] * 252, color=PALETTE[0], lw=1.8, label="expected growth")
    ax.axvline(f_star, color=PALETTE[2], lw=1.2, ls=(0, (1, 1.4)))
    ax.annotate(f"Kelly optimum {f_star:.2f}", xy=(f_star, 0),
                xytext=(6, 12), textcoords="offset points",
                fontsize=9, color=PALETTE[2])
    for k, (name, f) in enumerate((marks or {}).items()):
        ax.axvline(f, color=PALETTE[1], lw=1.2, ls=(0, (5, 2)))
        ax.annotate(name, xy=(f, 0), xytext=(6, -16 - 14 * k),
                    textcoords="offset points", fontsize=9, color=PALETTE[1])
    ax.legend(loc="lower left")
    add_source(fig, source)
    return fig


# -------------------------------------------------------------------- strategy
def plot_equity_curves(curves: "dict[str, pd.Series]",
                       oos_start=None, windows: "dict[str, tuple] | None" = None,
                       source: str = _SOURCE):
    """Strategy against its benchmarks, log scale, with the held-out period marked."""
    fig, ax = new_figure(
        "Cumulative growth of one unit of capital",
        "Growth of 1 unit (log scale)",
        figsize=(9.5, 5.2),
    )
    if windows:
        shade_windows(ax, windows)
    for i, (name, eq) in enumerate(curves.items()):
        st = series_style(i)
        s = eq.dropna()
        ax.plot(s.index, s.values, label=name, **st)
        if len(curves) <= 4:
            direct_label(ax, s.index[-1], s.iloc[-1], name, st["color"])
    if oos_start is not None:
        ax.axvline(pd.Timestamp(oos_start), color=INK["secondary"], lw=1.1,
                   ls=(0, (6, 3)))
        ax.annotate("out of sample", xy=(pd.Timestamp(oos_start), 1.0),
                    xycoords=("data", "axes fraction"), xytext=(5, -24),
                    textcoords="offset points", fontsize=9, color=INK["secondary"])
    ax.set_yscale("log")
    ax.legend(loc="upper left", ncol=2)
    format_date_axis(ax)
    add_source(fig, source + " Parameters fixed on 2008-2015; everything after the marked date is held out.")
    return fig


def plot_drawdowns(drawdowns: "dict[str, pd.Series]", source: str = _SOURCE):
    fig, ax = new_figure(
        "Drawdown from the running peak",
        "Drawdown (fraction of peak equity)",
        figsize=(9.5, 4.2),
    )
    for i, (name, dd) in enumerate(drawdowns.items()):
        st = series_style(i)
        ax.plot(dd.index, dd.values, label=name, **st)
    ax.legend(loc="lower left", ncol=2)
    format_date_axis(ax)
    add_source(fig, source)
    return fig


def plot_weight_and_constraint(weight: pd.Series, binding: pd.Series,
                               windows: "dict[str, tuple] | None" = None,
                               source: str = _SOURCE):
    """Position size through time, coloured by which constraint is binding.

    The headline of the sizing section: the crash budget should bind precisely in
    the calm stretches, which is where volatility targeting would have been largest.
    """
    fig, ax = new_figure(
        "Position size, and which constraint determines it",
        "Short exposure (fraction of capital)",
        figsize=(9.5, 4.6),
    )
    if windows:
        shade_windows(ax, windows)
    ax.plot(weight.index, weight.values, color=INK["secondary"], lw=0.8, zorder=2)
    order = ["stress_budget", "vol_target", "max_weight", "signal_off", "no_estimate"]
    present = [c for c in order if (binding == c).any()]
    for i, cat in enumerate(present):
        m = binding.reindex(weight.index) == cat
        ax.scatter(weight.index[m], weight[m], s=5, color=PALETTE[i],
                   label=cat.replace("_", " "), zorder=3, linewidths=0)
    ax.legend(loc="upper right", ncol=2, markerscale=2.6)
    format_date_axis(ax)
    add_source(fig, source)
    return fig


def plot_cost_sensitivity(costs: "Sequence[float]", sharpe: "Sequence[float]",
                          breakeven: float | None = None, source: str = _SOURCE):
    fig, ax = new_figure(
        "Out-of-sample Sharpe ratio against the transaction-cost assumption",
        "Sharpe ratio, out of sample",
        xlabel="Transaction cost (ticks per side, 1 tick = 0.05 VIX points)",
        figsize=(7.6, 4.4),
    )
    ax.axhline(0.0, color=INK["muted"], lw=0.8)
    ax.plot(costs, sharpe, "o-", color=PALETTE[0], markersize=6,
            markeredgecolor=INK["surface"], markeredgewidth=0.8)
    for x, y in zip(costs, sharpe):
        ax.annotate(f"{y:.2f}", xy=(x, y), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=9, color=INK["secondary"])
    if breakeven is not None:
        ax.axvline(breakeven, color=PALETTE[1], lw=1.2, ls=(0, (5, 2)))
        ax.annotate(f"breakeven {breakeven:.1f} ticks", xy=(breakeven, 0),
                    xytext=(6, 10), textcoords="offset points",
                    fontsize=9, color=PALETTE[1])
    add_source(fig, source)
    return fig


def plot_parameter_heatmap(grid: pd.DataFrame, chosen: "tuple | None" = None,
                           title: str = "Out-of-sample Sharpe across the parameter grid",
                           cbar_label: str = "Sharpe ratio, out of sample",
                           diverging: bool = True, source: str = _SOURCE):
    """Every specification that was run, not only the chosen one.

    Diverging map centred on zero, because the sign of a Sharpe ratio is the
    meaningful boundary; a sequential map would hide it.
    """
    import matplotlib.pyplot as plt

    fig, ax = new_figure(title, grid.index.name or "", xlabel=grid.columns.name or "",
                         figsize=(7.8, 5.0))
    vals = grid.to_numpy(dtype=float)
    if diverging:
        m = np.nanmax(np.abs(vals))
        im = ax.imshow(vals, cmap=diverging_cmap(), vmin=-m, vmax=m, aspect="auto")
    else:
        im = ax.imshow(vals, cmap=sequential_cmap(), aspect="auto")
    ax.set_xticks(range(grid.shape[1]), [str(c) for c in grid.columns])
    ax.set_yticks(range(grid.shape[0]), [str(i) for i in grid.index])
    ax.grid(visible=False)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if np.isfinite(vals[i, j]):
                ax.text(j, i, f"{vals[i, j]:.2f}", ha="center", va="center",
                        fontsize=8.5, color=INK["primary"])
    if chosen is not None:
        ax.add_patch(plt.Rectangle((chosen[1] - 0.5, chosen[0] - 0.5), 1, 1,
                                   fill=False, edgecolor=INK["primary"], lw=2.0))
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label(cbar_label, color=INK["secondary"])
    cb.outline.set_visible(False)
    add_source(fig, source + " The outlined cell is the pre-registered configuration.")
    return fig


def plot_event_detail(index_level: pd.Series, products: "dict[str, pd.Series]",
                      weight: pd.Series | None = None,
                      lo="2018-01-22", hi="2018-02-16", source: str = _SOURCE):
    """The event window in detail, on daily data - with that limitation stated."""
    nrows = 2 if weight is not None else 1
    fig, axes = new_figure(
        "The index and the products through the February 2018 event",
        "Rebased to 100 at the start of the window",
        figsize=(8.6, 5.6 if nrows == 2 else 4.4),
        nrows=nrows, height_ratios=[3, 1] if nrows == 2 else None,
    )
    ax = axes[0] if nrows == 2 else axes
    lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)

    def _seg(s):
        s = s[(s.index >= lo) & (s.index <= hi)].dropna()
        return s / s.iloc[0] * 100.0 if len(s) else s

    st = series_style(0)
    s = _seg(index_level)
    ax.plot(s.index, s.values, label="index", **st)
    direct_label(ax, s.index[-1], s.iloc[-1], "index", st["color"])
    for i, (name, p) in enumerate(products.items(), start=1):
        st = series_style(i)
        sp = _seg(p)
        if len(sp):
            ax.plot(sp.index, sp.values, label=name, **st)
            direct_label(ax, sp.index[-1], sp.iloc[-1], name, st["color"])
    ax.legend(loc="upper left")
    format_date_axis(ax, "%d %b")

    if weight is not None:
        wax = axes[1]
        w = weight[(weight.index >= lo) & (weight.index <= hi)]
        wax.plot(w.index, w.values, color=INK["secondary"], lw=1.4)
        wax.set_ylabel("Strategy\nexposure")
        format_date_axis(wax, "%d %b")
    add_source(
        fig,
        source + " Daily closes only: the intraday sequence on 5 February 2018, "
        "including the after-hours move that triggered XIV's acceleration, "
        "cannot be resolved at this frequency.",
    )
    return fig
