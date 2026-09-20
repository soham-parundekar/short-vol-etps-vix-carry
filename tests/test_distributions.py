"""Checks that every innovation distribution really is standardised and internally
consistent (pdf integrates to one, cdf is the integral of the pdf, ppf inverts cdf).

These are the assumptions the GARCH likelihood and the Monte Carlo both rely on, so
they are worth testing directly rather than trusting the algebra.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import integrate

from svcarry.econometrics.distributions import Normal, SkewT, StudentT, get_distribution

CASES = [
    ("normal", np.array([])),
    ("t", np.array([5.0])),
    ("t", np.array([12.0])),
    ("skewt", np.array([6.0, -0.3])),
    ("skewt", np.array([9.0, 0.25])),
    ("skewt", np.array([4.5, 0.0])),
]


@pytest.mark.parametrize("name,par", CASES)
def test_density_integrates_to_one(name, par):
    d = get_distribution(name)
    f = lambda z: np.exp(d.loglik(np.array([z]), par))[0]
    total, _ = integrate.quad(f, -np.inf, np.inf, limit=400)
    assert abs(total - 1.0) < 1e-6, (name, par, total)


@pytest.mark.parametrize("name,par", CASES)
def test_mean_zero_unit_variance(name, par):
    d = get_distribution(name)
    f = lambda z: np.exp(d.loglik(np.array([z]), par))[0]
    m, _ = integrate.quad(lambda z: z * f(z), -np.inf, np.inf, limit=400)
    v, _ = integrate.quad(lambda z: z * z * f(z), -np.inf, np.inf, limit=400)
    assert abs(m) < 1e-6, (name, par, m)
    assert abs(v - 1.0) < 1e-5, (name, par, v)


@pytest.mark.parametrize("name,par", CASES)
def test_cdf_matches_integrated_pdf(name, par):
    d = get_distribution(name)
    f = lambda z: np.exp(d.loglik(np.array([z]), par))[0]
    for z in (-3.0, -1.0, -0.2, 0.0, 0.7, 2.5):
        num, _ = integrate.quad(f, -np.inf, z, limit=400)
        assert abs(float(np.atleast_1d(d.cdf(z, par))[0]) - num) < 1e-6, (name, par, z)


@pytest.mark.parametrize("name,par", CASES)
def test_ppf_inverts_cdf(name, par):
    d = get_distribution(name)
    for u in (1e-4, 0.01, 0.1, 0.35, 0.5, 0.75, 0.99, 1 - 1e-4):
        z = float(np.atleast_1d(d.ppf(u, par))[0])
        back = float(np.atleast_1d(d.cdf(z, par))[0])
        assert abs(back - u) < 1e-8, (name, par, u, z, back)


def test_skewt_with_zero_skew_equals_student_t():
    z = np.linspace(-6, 6, 501)
    for nu in (4.0, 8.0, 30.0):
        a = SkewT.loglik(z, np.array([nu, 0.0]))
        b = StudentT.loglik(z, np.array([nu]))
        assert np.max(np.abs(a - b)) < 1e-10, nu


def test_skewt_negative_lambda_is_left_skewed():
    d = get_distribution("skewt")
    par = np.array([6.0, -0.4])
    lo = float(np.atleast_1d(d.ppf(0.01, par))[0])
    hi = float(np.atleast_1d(d.ppf(0.99, par))[0])
    assert abs(lo) > abs(hi), (lo, hi)


def test_simulated_moments_match():
    rng = np.random.default_rng(11)
    d = get_distribution("skewt")
    par = np.array([7.0, -0.25])
    z = d.ppf(rng.random(400_000), par)
    assert abs(z.mean()) < 0.02, z.mean()
    assert abs(z.std(ddof=1) - 1.0) < 0.02, z.std(ddof=1)


def test_unknown_distribution_raises():
    with pytest.raises(ValueError):
        get_distribution("cauchy")
