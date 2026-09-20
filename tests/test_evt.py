"""Tests for the peaks-over-threshold / GPD tail estimator.

The headline numbers of this project (the probability of an 80% one-day move in the
index, and the survival curves that follow from it) are entirely determined by this
code, so it is tested against samples drawn from distributions whose tail behaviour
is known analytically.
"""

from __future__ import annotations

import numpy as np
import pytest

from svcarry.econometrics.evt import (
    fit_gpd,
    hill_estimator,
    mean_excess,
    threshold_stability,
)


def _rgpd(n, xi, beta, rng):
    u = rng.random(n)
    if abs(xi) < 1e-12:
        return -beta * np.log(1 - u)
    return beta / xi * ((1 - u) ** (-xi) - 1)


def test_recovers_gpd_parameters():
    rng = np.random.default_rng(0)
    for xi_true, beta_true in [(0.25, 1.0), (0.4, 2.0), (0.05, 0.5)]:
        x = _rgpd(60_000, xi_true, beta_true, rng)
        fit = fit_gpd(x, threshold=0.0, tail="upper")
        assert fit.xi == pytest.approx(xi_true, abs=0.03), (xi_true, fit.xi)
        assert fit.beta == pytest.approx(beta_true, rel=0.08), (beta_true, fit.beta)


def test_quantile_and_exceedance_probability_are_inverses():
    rng = np.random.default_rng(1)
    x = _rgpd(20_000, 0.3, 1.0, rng)
    fit = fit_gpd(x, q=0.95)
    for p in (0.99, 0.999, 0.9999):
        q = float(fit.quantile(p))
        assert float(fit.exceedance_prob(q)) == pytest.approx(1 - p, rel=1e-8)


def test_tail_probability_beats_empirical_frequency_out_of_sample():
    """A high quantile estimated on half the sample should be roughly right on the
    other half. This is the property that justifies extrapolating at all."""
    rng = np.random.default_rng(2)
    x = _rgpd(80_000, 0.25, 1.0, rng)
    a, b = x[:40_000], x[40_000:]
    fit = fit_gpd(a, q=0.95)
    q999 = float(fit.quantile(0.999))
    realised = float((b > q999).mean())
    assert 0.0004 < realised < 0.0025, realised


def test_lower_tail_orientation():
    rng = np.random.default_rng(3)
    x = -_rgpd(40_000, 0.3, 1.0, rng)          # heavy LEFT tail
    fit = fit_gpd(x, q=0.95, tail="lower")
    assert fit.xi == pytest.approx(0.3, abs=0.04)
    assert fit.threshold < 0
    q = float(fit.quantile(0.999))              # deep left quantile
    assert q < fit.threshold
    assert float(fit.exceedance_prob(q)) == pytest.approx(0.001, rel=1e-6)


def test_mean_excess_slope_matches_theory():
    """For a GPD tail, mean excess is linear in u with slope xi / (1 - xi)."""
    rng = np.random.default_rng(4)
    xi = 0.3
    x = _rgpd(200_000, xi, 1.0, rng)
    us, me, se = mean_excess(x, q_lo=0.80, q_hi=0.99, n_points=40)
    ok = np.isfinite(me)
    slope = np.polyfit(us[ok], me[ok], 1)[0]
    assert slope == pytest.approx(xi / (1 - xi), rel=0.15), slope


def test_hill_estimator_recovers_pareto_index():
    rng = np.random.default_rng(5)
    alpha = 3.0
    x = (1 - rng.random(200_000)) ** (-1.0 / alpha)   # Pareto(1, alpha)
    assert hill_estimator(x, k=4000) == pytest.approx(1.0 / alpha, rel=0.12)


def test_expected_shortfall_exceeds_var():
    rng = np.random.default_rng(6)
    x = _rgpd(40_000, 0.25, 1.0, rng)
    fit = fit_gpd(x, q=0.95)
    for p in (0.99, 0.999):
        assert float(fit.expected_shortfall(p)) > float(fit.quantile(p))


def test_threshold_stability_reports_a_grid():
    rng = np.random.default_rng(7)
    x = _rgpd(30_000, 0.3, 1.0, rng)
    rows = threshold_stability(x)
    assert len(rows) >= 6
    xis = [r["xi"] for r in rows if "xi" in r]
    assert np.std(xis) < 0.08, xis         # genuinely stable for a true GPD sample


def test_too_few_exceedances_raises():
    rng = np.random.default_rng(8)
    with pytest.raises(ValueError):
        fit_gpd(rng.normal(size=100), q=0.99)


def test_normal_sample_gives_non_heavy_shape():
    """A Gaussian tail is in the Gumbel domain (xi = 0 in the limit), so the fitted
    shape must not come out heavy-tailed.

    Convergence to the limit is famously slow for the normal: at any threshold a
    practitioner would actually use, the POT estimate of xi is *negative*, typically
    -0.1 to -0.2 at the 98th percentile. The test therefore checks the economically
    relevant property - the estimator does not manufacture a heavy tail where there
    is none - rather than pretending the finite-sample bias is absent.
    """
    rng = np.random.default_rng(9)
    fit = fit_gpd(rng.normal(size=100_000), q=0.98)
    assert -0.35 < fit.xi < 0.05, fit.xi
