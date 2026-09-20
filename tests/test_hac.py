"""Tests for the hand-rolled OLS / HAC covariance estimator.

Where ``statsmodels`` happens to be importable the estimates are compared against it
directly; where it is not, the tests fall back on closed-form algebra and on
properties the estimator must satisfy (e.g. HAC standard errors must exceed OLS ones
when the errors are positively autocorrelated).
"""

from __future__ import annotations

import numpy as np
import pytest

from svcarry.econometrics.hac import newey_west_lags, ols


def _sim(n=2000, betas=(1.5, -0.8), rho=0.0, rho_x=0.0, seed=0):
    """Simulate y = 0.3 + X b + e, optionally with AR(1) errors and AR(1) regressors.

    HAC only matters for slope inference when *both* the regressors and the errors
    are serially correlated, so ``rho_x`` is separate from ``rho`` on purpose.
    """
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, len(betas)))
    if rho_x:
        for t in range(1, n):
            X[t] += rho_x * X[t - 1]
    e = rng.normal(size=n)
    if rho:
        for t in range(1, n):
            e[t] += rho * e[t - 1]
    y = 0.3 + X @ np.array(betas) + e
    return y, X


def test_recovers_known_coefficients():
    y, X = _sim(n=20000, seed=3)
    r = ols(y, X, cov_type="homoskedastic")
    assert r.params == pytest.approx([0.3, 1.5, -0.8], abs=0.03)
    assert r.nobs == 20000
    assert len(r.names) == 3 and r.names[0] == "const"


def test_homoskedastic_se_matches_closed_form():
    y, X = _sim(n=500, seed=7)
    r = ols(y, X, cov_type="homoskedastic")
    Xd = np.column_stack([np.ones(len(X)), X])
    beta = np.linalg.lstsq(Xd, y, rcond=None)[0]
    u = y - Xd @ beta
    s2 = u @ u / (len(y) - Xd.shape[1])
    cov = s2 * np.linalg.inv(Xd.T @ Xd)
    assert r.bse == pytest.approx(np.sqrt(np.diag(cov)), rel=1e-10)


def test_hac_inflates_se_under_positive_autocorrelation():
    y, X = _sim(n=3000, rho=0.8, rho_x=0.8, seed=5)
    plain = ols(y, X, cov_type="homoskedastic")
    hac = ols(y, X, cov_type="HAC", lags=20)
    # the slope standard errors should be materially larger under HAC
    assert (hac.bse[1:] > plain.bse[1:] * 1.5).all(), (plain.bse, hac.bse)


def test_hac_with_zero_lags_equals_hc0_up_to_dof():
    y, X = _sim(n=1000, seed=9)
    hac0 = ols(y, X, cov_type="HAC", lags=0)
    hc0 = ols(y, X, cov_type="HC0")
    n, k = hac0.nobs, len(hac0.params)
    assert hac0.cov == pytest.approx(hc0.cov * n / (n - k), rel=1e-10)


def test_white_se_differ_under_heteroskedasticity():
    rng = np.random.default_rng(2)
    n = 5000
    x = rng.normal(size=n)
    e = rng.normal(size=n) * (0.5 + 2.0 * np.abs(x))
    y = 1.0 + 2.0 * x + e
    plain = ols(y, x, cov_type="homoskedastic")
    white = ols(y, x, cov_type="HC1")
    assert white.bse[1] > plain.bse[1] * 1.2


def test_wald_test_on_true_and_false_restrictions():
    y, X = _sim(n=8000, betas=(1.0, 0.0), seed=13)
    r = ols(y, X, cov_type="HC1")
    # true restriction: second slope is zero
    stat, p = r.wald(np.array([[0.0, 0.0, 1.0]]), 0.0)
    assert p > 0.01
    # false restriction: first slope is zero
    stat, p = r.wald(np.array([[0.0, 1.0, 0.0]]), 0.0)
    assert p < 1e-10


def test_nonfinite_rows_are_dropped_and_counted():
    y, X = _sim(n=300, seed=1)
    y = y.copy(); X = X.copy()
    y[5] = np.nan
    X[7, 0] = np.inf
    r = ols(y, X, cov_type="HC1")
    assert r.nobs == 298
    assert r._extras["n_dropped"] == 2


def test_newey_west_bandwidth_rule():
    assert newey_west_lags(100) == 4
    assert newey_west_lags(1000) >= newey_west_lags(100)
    assert newey_west_lags(5000, "schwert") > newey_west_lags(5000)


def test_matches_statsmodels_when_available():
    try:
        import statsmodels.api as sm
    except ImportError:
        pytest.skip("statsmodels not installed")
    y, X = _sim(n=1500, rho=0.4, rho_x=0.5, seed=21)
    Xd = sm.add_constant(X)
    ref = sm.OLS(y, Xd).fit(cov_type="HAC", cov_kwds={"maxlags": 12, "use_correction": True})
    mine = ols(y, X, cov_type="HAC", lags=12)
    assert mine.params == pytest.approx(ref.params, rel=1e-8)
    assert mine.bse == pytest.approx(ref.bse, rel=5e-3)
