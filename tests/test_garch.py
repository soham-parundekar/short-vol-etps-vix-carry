"""Tests for the hand-rolled GJR-GARCH(1,1) estimator.

Three kinds of check:

1. **Mechanical** - the conditional-variance recursion matches a transparent manual
   loop, and the likelihood is what the formula says it is.
2. **Statistical** - parameters are recovered from long simulated samples drawn from
   the model itself, which is the only way to know the optimiser and the likelihood
   agree with the simulator.
3. **Comparative** - where ``arch`` is importable, estimates are compared with it.
"""

from __future__ import annotations

import numpy as np
import pytest

from svcarry.econometrics.garch import GJRGarch, _recursion, ljung_box


def _simulate(n, omega, alpha, gamma, beta, mu=0.0, seed=0, nu=None):
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n) if nu is None else rng.standard_t(nu, size=n) * np.sqrt((nu - 2) / nu)
    r = np.empty(n)
    s2 = omega / (1 - alpha - beta - 0.5 * gamma)
    e = 0.0
    for t in range(n):
        s2 = omega + (alpha + (gamma if e < 0 else 0.0)) * e * e + beta * s2
        e = np.sqrt(s2) * z[t]
        r[t] = mu + e
    return r


def test_recursion_matches_manual_loop():
    rng = np.random.default_rng(1)
    eps = rng.normal(size=500) * 0.01
    om, al, ga, be, s0 = 1e-6, 0.06, 0.08, 0.88, 1e-4
    got = _recursion(eps, om, al, ga, be, s0)
    want = [s0]
    for e in eps:
        want.append(om + (al + (ga if e < 0 else 0.0)) * e * e + be * want[-1])
    assert got == pytest.approx(np.array(want), rel=1e-12)


def test_recursion_asymmetry_direction():
    """A negative shock must raise next-period variance more than a positive one."""
    om, al, ga, be, s0 = 1e-6, 0.05, 0.10, 0.85, 1e-4
    up = _recursion(np.array([0.05]), om, al, ga, be, s0)[-1]
    dn = _recursion(np.array([-0.05]), om, al, ga, be, s0)[-1]
    assert dn > up


def test_parameter_recovery_normal():
    true = dict(omega=2e-6, alpha=0.04, gamma=0.08, beta=0.90)
    r = _simulate(12000, **true, mu=0.0003, seed=42)
    fit = GJRGarch(dist="normal").fit(r, n_starts=2)
    p = fit.params
    assert p["beta"] == pytest.approx(true["beta"], abs=0.05), p
    assert p["alpha"] == pytest.approx(true["alpha"], abs=0.035), p
    assert p["gamma"] == pytest.approx(true["gamma"], abs=0.06), p
    assert fit.persistence < 1.0
    # unconditional variance should be close to the sample variance
    assert np.sqrt(fit.uncond_var) == pytest.approx(r.std(ddof=1), rel=0.25)


def test_parameter_recovery_student_t():
    true = dict(omega=3e-6, alpha=0.06, gamma=0.06, beta=0.88)
    r = _simulate(12000, **true, seed=7, nu=6.0)
    fit = GJRGarch(dist="t").fit(r, n_starts=2)
    nu_hat = float(fit.dist_params[0])
    assert 4.0 < nu_hat < 10.0, nu_hat
    assert fit.params["beta"] == pytest.approx(true["beta"], abs=0.06)


def test_standardised_residuals_are_well_behaved():
    r = _simulate(6000, 2e-6, 0.05, 0.07, 0.88, seed=3)
    fit = GJRGarch(dist="normal").fit(r, n_starts=2)
    z = fit.std_resid
    assert abs(z.std(ddof=1) - 1.0) < 0.08, z.std(ddof=1)
    # no remaining ARCH effects in squared standardised residuals
    _, p = ljung_box(z ** 2 - (z ** 2).mean(), lags=10)
    assert p > 0.01, p


def test_ljung_box_detects_serial_correlation():
    rng = np.random.default_rng(5)
    iid = rng.normal(size=3000)
    _, p_iid = ljung_box(iid, lags=10)
    ar = iid.copy()
    for t in range(1, len(ar)):
        ar[t] += 0.5 * ar[t - 1]
    _, p_ar = ljung_box(ar, lags=10)
    assert p_iid > 0.05
    assert p_ar < 1e-8


def test_simulate_reproduces_unconditional_variance():
    r = _simulate(6000, 2e-6, 0.05, 0.06, 0.88, seed=11)
    fit = GJRGarch(dist="normal").fit(r, n_starts=2)
    paths = fit.simulate(n_paths=4000, n_steps=400, seed=1, start_from_end=False)
    # variance of simulated returns should be near the model's unconditional variance
    assert paths.var() == pytest.approx(fit.uncond_var, rel=0.45)
    assert paths.shape == (4000, 400)


def test_simulation_is_reproducible():
    r = _simulate(3000, 2e-6, 0.05, 0.06, 0.88, seed=2)
    fit = GJRGarch(dist="normal").fit(r, n_starts=1)
    a = fit.simulate(50, 30, seed=99)
    b = fit.simulate(50, 30, seed=99)
    assert np.array_equal(a, b)


def test_forecast_variance_converges_to_unconditional():
    r = _simulate(4000, 2e-6, 0.05, 0.06, 0.88, seed=4)
    fit = GJRGarch(dist="normal").fit(r, n_starts=1)
    fc = fit.forecast_var(horizon=2000)
    assert fc[-1] == pytest.approx(fit.uncond_var, rel=0.05)


def test_too_short_sample_raises():
    with pytest.raises(ValueError):
        GJRGarch().fit(np.random.default_rng(0).normal(size=100))


def test_matches_arch_package_when_available():
    try:
        from arch import arch_model
    except ImportError:
        pytest.skip("arch not installed")
    r = _simulate(5000, 2e-6, 0.05, 0.07, 0.88, seed=17)
    ref = arch_model(r * 100, p=1, o=1, q=1, dist="normal").fit(disp="off")
    mine = GJRGarch(dist="normal").fit(r, n_starts=3)
    assert mine.params["beta"] == pytest.approx(float(ref.params["beta[1]"]), abs=0.03)
    assert mine.params["alpha"] == pytest.approx(float(ref.params["alpha[1]"]), abs=0.03)
