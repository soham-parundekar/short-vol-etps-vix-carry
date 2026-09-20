"""Tests for the performance statistics, Kelly sizing, bootstrap and attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.econometrics.bootstrap import (
    bootstrap_statistic,
    circular_block_bootstrap,
    stationary_bootstrap,
)
from svcarry.econometrics.kelly import growth_rate_curve, kelly_fraction
from svcarry.evaluation.metrics import (
    drawdown,
    max_drawdown,
    performance_stats,
    performance_table,
    rolling_sharpe,
    sharpe_standard_error,
    window_returns,
)
from svcarry.evaluation.regressions import alpha_regression, downside_beta_regression


def _idx(n, start="2010-01-04"):
    return pd.bdate_range(start, periods=n)


# -------------------------------------------------------------------- metrics
def test_drawdown_on_a_hand_computed_path():
    r = pd.Series([0.10, -0.20, 0.05, -0.10, 0.30], index=_idx(5))
    dd = drawdown(r)
    eq = (1 + r).cumprod()
    assert dd["equity"].iloc[-1] == pytest.approx(float(eq.iloc[-1]))
    # peak is 1.10 after day 1; the trough is 1.10*0.80*1.05*0.90 = 0.8316
    assert float(eq.iloc[3]) == pytest.approx(0.8316, rel=1e-12)
    assert dd["drawdown"].min() == pytest.approx(0.8316 / 1.10 - 1.0, rel=1e-9)
    assert max_drawdown(r) == pytest.approx(dd["drawdown"].min())


def test_drawdown_is_zero_for_a_monotone_path():
    r = pd.Series(0.001, index=_idx(100))
    assert max_drawdown(r) == pytest.approx(0.0)


def test_sharpe_recovers_the_population_value():
    rng = np.random.default_rng(0)
    mu, sig = 0.0005, 0.01
    r = pd.Series(rng.normal(mu, sig, 40_000), index=_idx(40_000))
    st = performance_stats(r)
    assert st["sharpe"] == pytest.approx(mu / sig * np.sqrt(252), rel=0.06)
    assert st["ann_vol"] == pytest.approx(sig * np.sqrt(252), rel=0.03)


def test_lo_standard_error_exceeds_the_naive_one_for_skewed_fat_tails():
    """The correction bites when the Sharpe is positive and the skew negative.

    That is the short-volatility case exactly: a respectable ratio earned by a
    series whose losses arrive in rare, enormous lumps. The naive sqrt(T) standard
    error ignores the third and fourth moments and therefore overstates how
    precisely the ratio has been measured.
    """
    rng = np.random.default_rng(1)
    n = 4000
    nasty = pd.Series(rng.normal(0.0012, 0.008, n), index=_idx(n))
    hits = rng.choice(n, 20, replace=False)
    nasty.iloc[hits] -= 0.12
    st = performance_stats(nasty)
    assert st["sharpe"] > 0.4 and st["skew"] < -3.0, st      # the intended shape
    se_naive = np.sqrt(1.0 / n) * np.sqrt(252)
    se_nasty = sharpe_standard_error(nasty)
    assert se_nasty > se_naive * 1.10, (se_nasty, se_naive)

    # and it does NOT inflate the error for a well-behaved series
    tame = pd.Series(rng.normal(0.0004, 0.01, n), index=_idx(n))
    assert sharpe_standard_error(tame) == pytest.approx(se_naive, rel=0.10)


def test_performance_stats_reports_the_tail_alongside_the_ratio():
    rng = np.random.default_rng(2)
    r = pd.Series(rng.normal(0.0005, 0.01, 2000), index=_idx(2000))
    r.iloc[500] = -0.35
    st = performance_stats(r, turnover=pd.Series(0.1, index=r.index),
                           weight=pd.Series(0.5, index=r.index))
    for k in ("sharpe", "skew", "excess_kurtosis", "cvar_99", "max_drawdown",
              "worst_day", "ann_turnover", "avg_weight", "time_invested"):
        assert k in st, k
    assert st["worst_day"] == pytest.approx(-0.35)
    assert st["skew"] < 0


def test_performance_table_and_rolling_sharpe_shapes():
    rng = np.random.default_rng(3)
    a = pd.Series(rng.normal(0.0004, 0.01, 800), index=_idx(800))
    b = pd.Series(rng.normal(0.0002, 0.02, 800), index=_idx(800))
    tab = performance_table({"a": a, "b": b})
    assert list(tab.index) == ["a", "b"]
    assert "sharpe" in tab.columns
    rs = rolling_sharpe(a, window=252)
    assert rs.notna().sum() == 800 - 251


def test_window_returns_is_nan_outside_a_series_life():
    idx = _idx(500, "2017-01-02")
    live = pd.Series(0.001, index=idx)
    dead = live.copy()
    dead[dead.index > pd.Timestamp("2018-02-21")] = np.nan
    out = window_returns(
        {"live": live, "dead": dead},
        {"before": ("2017-03-01", "2017-06-01"), "after": ("2018-06-01", "2018-09-01")},
    )
    assert np.isfinite(out.loc["before", "dead"])
    assert np.isnan(out.loc["after", "dead"])
    assert np.isfinite(out.loc["after", "live"])


# ---------------------------------------------------------------------- kelly
def test_kelly_matches_the_gaussian_approximation_for_thin_tails():
    """With Gaussian returns, f* must reproduce -mean/variance almost exactly.

    The comparison is against the *sample* moments, not the population ones: with
    200,000 draws the sample mean still carries a standard error of about 10% of
    itself, and the estimator's job is to be optimal for the data it was given.
    """
    rng = np.random.default_rng(4)
    mu, sig = -0.0008, 0.02          # index drifts down: shorting it pays
    r = rng.normal(mu, sig, 200_000)
    k = kelly_fraction(r)
    assert k.f_star > 0
    assert k.f_star == pytest.approx(k.f_gaussian_approx, rel=0.02)
    assert k.f_star == pytest.approx(-mu / sig ** 2, rel=0.15)
    # the optimum really is an optimum
    from svcarry.econometrics.kelly import _growth
    assert _growth(k.f_star, r) > _growth(k.f_star * 1.2, r)
    assert _growth(k.f_star, r) > _growth(k.f_star * 0.8, r)


def test_crash_risk_collapses_the_kelly_fraction():
    """Adding rare, enormous up-moves to the index must shrink the optimal short.

    Two comparisons are made, because they say different things. Against the same
    sample *without* the jumps, f* must fall sharply: that is the economic content.
    Against the Gaussian approximation computed on the jump-contaminated sample,
    f* must still be smaller: that is the statement that mean/variance sizing
    overstates the safe position even when the variance already reflects the jumps.
    """
    rng = np.random.default_rng(5)
    n = 60_000
    clean = rng.normal(-0.002, 0.03, n)
    dirty = clean.copy()
    hits = rng.choice(n, 120, replace=False)
    dirty[hits] = rng.uniform(0.35, 1.10, 120)

    k_clean = kelly_fraction(clean)
    k_dirty = kelly_fraction(dirty)
    assert k_dirty.f_star < 0.25 * k_clean.f_star, (k_clean.summary(), k_dirty.summary())
    assert k_dirty.f_star < k_dirty.f_gaussian_approx, k_dirty.summary()
    assert k_dirty.f_star < k_dirty.ruin_bound
    # the ruin bound alone is not what is binding - the optimum is well inside it
    assert k_dirty.f_star < 0.5 * k_dirty.ruin_bound


def test_kelly_respects_the_ruin_bound():
    rng = np.random.default_rng(6)
    r = np.r_[rng.normal(-0.001, 0.02, 5000), 0.95]     # one near-wipeout day
    k = kelly_fraction(r)
    assert k.ruin_bound == pytest.approx(1 / 0.95, rel=1e-9)
    assert k.f_star < k.ruin_bound
    # a position at the ruin bound must have -inf growth
    g = growth_rate_curve(r, np.array([k.ruin_bound]))[1]
    assert not np.isfinite(g[0])


def test_kelly_bootstrap_interval_brackets_the_point_estimate():
    rng = np.random.default_rng(7)
    r = rng.normal(-0.001, 0.025, 4000)
    k = kelly_fraction(r, bootstrap=60, seed=1)
    assert k.ci_low < k.f_star < k.ci_high


def test_growth_curve_peaks_at_f_star():
    rng = np.random.default_rng(8)
    r = rng.normal(-0.0015, 0.03, 20_000)
    k = kelly_fraction(r)
    f, g = growth_rate_curve(r)
    assert f[np.nanargmax(g)] == pytest.approx(k.f_star, abs=0.05)


# ------------------------------------------------------------------ bootstrap
def test_stationary_bootstrap_preserves_length_and_support():
    rng = np.random.default_rng(9)
    x = rng.normal(size=500)
    b = stationary_bootstrap(x, block_mean=21, rng=rng)
    assert len(b) == 500
    assert set(np.unique(b)).issubset(set(np.unique(x)))


def test_block_bootstrap_retains_autocorrelation_that_iid_resampling_destroys():
    rng = np.random.default_rng(10)
    n = 8000
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + rng.normal()
    def ac1(z):
        z = z - z.mean()
        return float(z[1:] @ z[:-1] / (z @ z))
    blk = np.mean([ac1(stationary_bootstrap(x, 50, rng=rng)) for _ in range(20)])
    iid = np.mean([ac1(rng.permutation(x)) for _ in range(20)])
    assert blk > 0.5
    assert abs(iid) < 0.1


def test_circular_block_bootstrap_length():
    rng = np.random.default_rng(11)
    x = rng.normal(size=300)
    assert len(circular_block_bootstrap(x, block_len=20, rng=rng)) == 300


def test_bootstrap_statistic_interval():
    rng = np.random.default_rng(12)
    x = rng.normal(0.5, 1.0, 3000)
    out = bootstrap_statistic(x, np.mean, n_boot=300, seed=2)
    assert out["ci_low"] < 0.5 < out["ci_high"]
    assert out["n_valid"] == 300


# ---------------------------------------------------------------- regressions
def test_alpha_regression_recovers_a_planted_alpha_and_beta():
    rng = np.random.default_rng(13)
    n = 3000
    idx = _idx(n)
    f1 = pd.Series(rng.normal(0.0003, 0.008, n), index=idx)
    f2 = pd.Series(rng.normal(0.0002, 0.011, n), index=idx)
    y = 0.0004 + 0.7 * f1 - 0.3 * f2 + pd.Series(rng.normal(0, 0.004, n), index=idx)
    out = alpha_regression(y, {"put": f1, "spx": f2})
    assert out["alpha_daily"] == pytest.approx(0.0004, abs=0.00015)
    assert out["betas"]["put"] == pytest.approx(0.7, abs=0.05)
    assert out["betas"]["spx"] == pytest.approx(-0.3, abs=0.05)
    assert out["alpha_annual"] == pytest.approx(out["alpha_daily"] * 252)


def test_alpha_regression_finds_no_alpha_when_there_is_none():
    rng = np.random.default_rng(14)
    n = 4000
    idx = _idx(n)
    f = pd.Series(rng.normal(0.0004, 0.01, n), index=idx)
    y = 0.8 * f + pd.Series(rng.normal(0, 0.003, n), index=idx)
    out = alpha_regression(y, {"put": f})
    assert abs(out["alpha_t"]) < 2.5, out["alpha_t"]


def test_downside_beta_detects_asymmetry():
    rng = np.random.default_rng(15)
    n = 4000
    idx = _idx(n)
    m = pd.Series(rng.normal(0.0003, 0.011, n), index=idx)
    y = 0.15 * m.clip(lower=0) + 1.2 * m.clip(upper=0) + \
        pd.Series(rng.normal(0, 0.003, n), index=idx)
    out = downside_beta_regression(y, m)
    assert out["beta_up"] == pytest.approx(0.15, abs=0.08)
    assert out["beta_down"] == pytest.approx(1.2, abs=0.10)
    assert out["asymmetry_p"] < 0.01


def test_regression_needs_enough_observations():
    idx = _idx(30)
    with pytest.raises(ValueError):
        alpha_regression(pd.Series(0.001, index=idx), {"f": pd.Series(0.001, index=idx)})
