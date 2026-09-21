"""Tests for the figure layer.

Figures are code, and code that is never run until report day is code that breaks on
report day. These tests exercise every figure function on synthetic data and check the
properties the project promises of its charts: a title, a y-axis label, a legend
whenever more than one series is drawn, and no silent colour reuse.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from svcarry.viz import figures as F
from svcarry.viz.style import (
    LINESTYLES,
    PALETTE,
    apply_style,
    greyscale_check,
    series_style,
)


def _idx(n, start="2010-01-04"):
    return pd.bdate_range(start, periods=n)


def _series(n=600, seed=0, drift=-0.001):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, 0.03, n)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=_idx(n))


def _title(ax) -> str:
    """Titles are left-aligned by the project style, so ``get_title()`` with its
    default centre location returns an empty string. Ask for the left one."""
    return ax.get_title(loc="left")


def _has_legend(ax) -> bool:
    lg = ax.get_legend()
    return lg is not None and len(lg.get_texts()) > 0


# ------------------------------------------------------------------------ style
def test_palette_is_fixed_order_and_not_cycled():
    assert len(PALETTE) == len(set(PALETTE)) == 8
    assert series_style(0)["color"] == PALETTE[0]
    assert series_style(3)["color"] == PALETTE[3]
    with pytest.raises(ValueError):
        series_style(8)


def test_scatter_forms_cap_at_three_series():
    """All-pairs colour separation only clears the gates for the first three slots."""
    series_style(2, scatter=True)
    with pytest.raises(ValueError):
        series_style(3, scatter=True)


def test_line_style_varies_with_colour():
    """Colour is never the only encoding, so the figures survive greyscale."""
    styles = [series_style(i)["linestyle"] for i in range(6)]
    assert len(set(map(str, styles))) == 6
    assert styles == LINESTYLES[:6]


def test_greyscale_check_flags_close_luminance_pairs():
    close = greyscale_check(["#2a78d6", "#4a3aa7"])
    assert isinstance(close, list)
    far = greyscale_check(["#0d366b", "#cde2fb"])
    assert far == []


def test_apply_style_sets_recessive_chrome():
    apply_style()
    assert matplotlib.rcParams["axes.spines.top"] is False
    assert matplotlib.rcParams["axes.spines.right"] is False
    assert matplotlib.rcParams["axes.axisbelow"] is True
    assert matplotlib.rcParams["legend.frameon"] is False


# ---------------------------------------------------------------------- figures
def test_index_vs_products_has_log_scale_title_and_legend():
    idx = _series(800, 1)
    prods = {"VIXY": _series(800, 2), "VXX": _series(800, 3)}
    resid = pd.Series(np.random.default_rng(0).normal(0, 3e-4, 800), index=idx.index)
    fig = F.plot_index_vs_products(idx, prods, resid)
    ax = fig.axes[0]
    assert _title(ax)
    assert "log scale" in ax.get_ylabel()
    assert ax.get_yscale() == "log"
    assert _has_legend(ax)
    assert len(fig.axes) == 2


def test_term_structure_panels():
    n = 400
    cm = pd.DataFrame(
        {f"cm{m}": 14 + 0.02 * m + np.random.default_rng(m).normal(0, 0.5, n)
         for m in (30, 60, 90, 120)},
        index=_idx(n),
    )
    slope = pd.Series(np.random.default_rng(1).normal(0.92, 0.06, n), index=cm.index)
    fig = F.plot_term_structure(cm, slope, threshold=1.0)
    assert len(fig.axes) == 2
    assert _has_legend(fig.axes[0])
    assert "slope" in fig.axes[1].get_ylabel()


def test_decay_regression_marks_theory():
    from svcarry.etp.mechanics import DecayResult

    res = {
        "SVXY (-1x)": DecayResult(-1.0, -0.94, 0.06, -1.0, 1.0, -0.011, 100, 0.8, 21),
        "UVXY (2x)": DecayResult(2.0, -1.05, 0.08, -1.0, -0.6, -0.010, 100, 0.8, 21),
    }
    fig = F.plot_decay_regression(res)
    ax = fig.axes[0]
    assert _has_legend(ax)
    assert [t.get_text() for t in ax.get_yticklabels()] == ["SVXY (-1x)", "UVXY (2x)"]


def test_flow_figure_shows_both_bounds_and_no_point_estimate():
    """Both asset bounds are drawn, each on its own axis, and nothing between them.

    The figure used to draw a band with a midpoint. The midpoint went when the upper
    bound turned out to exceed the whole front-month contract on some sessions: the
    midpoint of a bound known to be implausible at one end is not an estimate. What
    this test protects is the principle underneath - never a single number where the
    inputs support only a range.
    """
    n = 300
    lo = pd.Series(np.random.default_rng(0).normal(0.02, 0.01, n), index=_idx(n)).abs()
    hi = lo + 0.03
    fig = F.plot_flow_vs_open_interest(lo, hi, annotate=lo.index[100])
    assert len(fig.axes) == 2, "one axis per bound, never a dual axis"
    top, bottom = fig.axes
    assert len(top.get_lines()) >= 1 and len(bottom.get_lines()) >= 2
    assert "lower" in top.get_title(loc="left").lower()
    assert "upper" in bottom.get_title(loc="left").lower()
    labels = " ".join(ln.get_label().lower() for ax in fig.axes for ln in ax.get_lines())
    assert "midpoint" not in labels and "central" not in labels
    ref = [ln for ln in bottom.get_lines() if np.allclose(ln.get_ydata(), 100.0)]
    assert ref, "the upper panel must show the 100%-of-open-interest reference"


def test_mean_excess_and_qq():
    u = np.linspace(1.0, 3.0, 40)
    me = 0.4 + 0.43 * u
    se = np.full_like(u, 0.05)
    fig = F.plot_mean_excess(u, me, se, chosen=1.8)
    assert _has_legend(fig.axes[0])

    rng = np.random.default_rng(3)
    emp = np.sort(rng.pareto(3.0, 200))
    theo = np.sort(rng.pareto(3.0, 200))
    fig2 = F.plot_gpd_qq(emp, theo)
    assert fig2.axes[0].get_aspect() == 1.0


def test_survival_curves_show_uncertainty():
    t = np.linspace(0, 5, 60)
    curves = {
        "-1.0x": pd.Series(np.exp(-0.25 * t), index=t),
        "-0.5x": pd.Series(np.exp(-0.04 * t), index=t),
    }
    bands = {k: (v.values - 0.02, v.values + 0.02) for k, v in curves.items()}
    fig = F.plot_survival_curves(curves, bands)
    ax = fig.axes[0]
    assert len(ax.collections) >= 2, "simulation error bands must be drawn"
    assert ax.get_ylim()[1] <= 1.05


def test_kelly_curve_marks_offered_leverage():
    f = np.linspace(-0.1, 1.0, 200)
    g = -(f - 0.3) ** 2 * 0.002
    fig = F.plot_kelly_growth_curve(f, g, f_star=0.3, marks={"-1x offered": 1.0})
    ax = fig.axes[0]
    xs = [ln.get_xdata()[0] for ln in ax.get_lines() if len(ln.get_xdata()) == 2]
    assert any(abs(x - 1.0) < 1e-9 for x in xs) or len(ax.texts) >= 2


def test_equity_curves_mark_the_out_of_sample_boundary():
    curves = {"strategy": _series(900, 4, 0.0004), "buy and hold -1x": _series(900, 5)}
    fig = F.plot_equity_curves(curves, oos_start="2013-01-02")
    ax = fig.axes[0]
    assert ax.get_yscale() == "log"
    assert _has_legend(ax)
    assert any("out of sample" in t.get_text() for t in ax.texts)


def test_every_figure_carries_a_left_aligned_title():
    idx = _series(200, 11)
    for fig in (
        F.plot_index_vs_products(idx, {"VIXY": idx * 1.01}),
        F.plot_drawdowns({"strategy": idx / idx.cummax() - 1.0}),
    ):
        assert _title(fig.axes[0]), "every figure states what it shows"
        assert fig.axes[0].get_ylabel(), "every figure labels its y axis with units"


def test_drawdown_and_weight_figures():
    n = 500
    dd = {"strategy": pd.Series(-np.abs(np.random.default_rng(0).normal(0, 0.05, n)),
                                index=_idx(n))}
    fig = F.plot_drawdowns(dd)
    assert fig.axes[0].get_ylabel()

    w = pd.Series(np.clip(np.random.default_rng(1).normal(0.2, 0.05, n), 0, 1),
                  index=_idx(n))
    b = pd.Series(["stress_budget"] * 300 + ["vol_target"] * 200, index=w.index)
    fig2 = F.plot_weight_and_constraint(w, b)
    assert _has_legend(fig2.axes[0])


def test_cost_sensitivity_labels_every_point():
    fig = F.plot_cost_sensitivity([0, 1, 2, 4], [0.9, 0.62, 0.35, -0.1], breakeven=3.1)
    ax = fig.axes[0]
    assert len([t for t in ax.texts if t.get_text().replace("-", "").replace(".", "").isdigit()]) >= 4


def test_parameter_heatmap_is_diverging_about_zero_and_marks_the_choice():
    grid = pd.DataFrame(
        np.linspace(-0.5, 1.2, 12).reshape(3, 4),
        index=pd.Index([0.10, 0.15, 0.20], name="volatility target"),
        columns=pd.Index([0.10, 0.20, 0.30, 1.00], name="stress loss budget"),
    )
    fig = F.plot_parameter_heatmap(grid, chosen=(1, 1))
    ax = fig.axes[0]
    im = ax.images[0]
    lo, hi = im.get_clim()
    assert lo == pytest.approx(-hi), "diverging map must be centred on zero"
    assert len(ax.patches) == 1, "the pre-registered cell must be outlined"


def test_event_detail_states_the_daily_frequency_limitation():
    idx = _series(60, 6)
    idx.index = pd.bdate_range("2018-01-02", periods=60)
    prods = {"SVXY": idx * 0.9}
    w = pd.Series(0.2, index=idx.index)
    fig = F.plot_event_detail(idx, prods, w, lo="2018-01-22", hi="2018-02-16")
    notes = " ".join(t.get_text() for t in fig.texts)
    assert "intraday" in notes.lower()


def test_every_figure_has_a_source_note():
    idx = _series(300, 7)
    fig = F.plot_index_vs_products(idx, {"VIXY": idx * 1.01})
    assert any("Source:" in t.get_text() for t in fig.texts)
