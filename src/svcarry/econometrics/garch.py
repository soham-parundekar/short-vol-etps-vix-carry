"""GJR-GARCH(1,1) with selectable innovation distribution, estimated by MLE.

Model
-----
    r_t     = mu + eps_t
    eps_t   = sigma_t z_t,      z_t ~ D(0, 1)
    sigma_t^2 = omega + (alpha + gamma * 1{eps_{t-1} < 0}) eps_{t-1}^2
                + beta sigma_{t-1}^2

Glosten, Jagannathan & Runkle (1993). The ``gamma`` term is the asymmetry: for
equity returns it is positive (negative shocks raise variance more). For the
*inverse* volatility index studied in this project the sign is expected to flip -
the damaging shock is a large **positive** index move - which is a useful sanity
check on the fit rather than a nuisance.

Why hand-rolled
---------------
``arch`` is not installable in the execution environment for this project, and in
any case writing the recursion out makes three things explicit that a library call
hides: the variance initialisation, the stationarity constraint, and the fact that
the standardised residuals fed to the EVT step are exactly ``(r_t - mu)/sigma_t``
from this filter.

Estimation details
------------------
* Parameters are estimated by maximising the exact conditional log-likelihood with
  ``scipy.optimize.minimize`` (L-BFGS-B), from several starting values, taking the
  best. Returns are rescaled by 100 internally for numerical conditioning and the
  reported ``omega`` is converted back.
* ``sigma_0^2`` is initialised at the sample variance of the estimation window;
  ``eps_0 < 0`` is assumed with probability 1/2, i.e. the first asymmetry indicator
  uses 0.5. The sensitivity of the fit to this choice is checked in
  ``tests/test_garch.py``.
* Stationarity is imposed as ``alpha + beta + gamma/2 < 1`` (the condition for a
  finite unconditional variance when ``P(eps < 0) = 1/2``).
* Standard errors are reported both from the numerical Hessian and from the
  Bollerslev-Wooldridge robust sandwich, since the latter remains valid if the
  innovation distribution is misspecified.

Validated in ``tests/test_garch.py`` by (a) recovering known parameters from long
simulated samples, (b) checking the analytic likelihood against a brute-force loop,
and (c) where ``arch`` happens to be importable, comparing estimates to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import optimize, stats

from .distributions import get_distribution

__all__ = ["GJRGarch", "GarchFit"]

_SCALE = 100.0  # returns are fitted in percent for conditioning


def _recursion(
    eps: np.ndarray, omega: float, alpha: float, gamma: float, beta: float, s2_init: float
) -> np.ndarray:
    """Conditional variance path. Pure loop; NumPy cannot vectorise the recursion."""
    n = eps.shape[0]
    s2 = np.empty(n + 1)
    s2[0] = s2_init
    for t in range(n):
        e = eps[t]
        s2[t + 1] = omega + (alpha + (gamma if e < 0.0 else 0.0)) * e * e + beta * s2[t]
        if not np.isfinite(s2[t + 1]) or s2[t + 1] <= 0.0:
            s2[t + 1] = 1e-12
    return s2


@dataclass
class GarchFit:
    """Result of a GJR-GARCH fit."""

    params: dict[str, float]
    loglik: float
    sigma: np.ndarray            # conditional sd, same length as the input returns
    std_resid: np.ndarray        # (r - mu) / sigma
    dist: str
    dist_params: np.ndarray
    se_hessian: dict[str, float]
    se_robust: dict[str, float]
    converged: bool
    index: object = None
    _extras: dict = field(default_factory=dict)

    @property
    def persistence(self) -> float:
        p = self.params
        return p["alpha"] + p["beta"] + 0.5 * p["gamma"]

    @property
    def uncond_var(self) -> float:
        return self.params["omega"] / (1.0 - self.persistence)

    def aic(self) -> float:
        k = len(self.params) + len(self.dist_params)
        return -2.0 * self.loglik + 2.0 * k

    def bic(self) -> float:
        k = len(self.params) + len(self.dist_params)
        return -2.0 * self.loglik + k * np.log(len(self.std_resid))

    def summary(self) -> str:
        lines = [
            f"GJR-GARCH(1,1) / {self.dist}   loglik={self.loglik:,.2f}   "
            f"AIC={self.aic():,.1f}   BIC={self.bic():,.1f}   n={len(self.std_resid)}",
            "-" * 78,
            f"{'':<10s}{'estimate':>14s}{'se(Hess)':>14s}{'se(robust)':>14s}{'t(robust)':>12s}",
        ]
        allp = dict(self.params)
        dist_names = {"t": ["nu"], "skewt": ["nu", "lam"], "normal": []}[self.dist]
        for i, nm in enumerate(dist_names):
            allp[nm] = float(self.dist_params[i])
        for nm, v in allp.items():
            sh = self.se_hessian.get(nm, np.nan)
            sr = self.se_robust.get(nm, np.nan)
            t = v / sr if (sr and np.isfinite(sr) and sr > 0) else np.nan
            lines.append(f"{nm:<10s}{v:>14.6f}{sh:>14.6f}{sr:>14.6f}{t:>12.2f}")
        lines.append("-" * 78)
        lines.append(
            f"persistence (a + b + g/2) = {self.persistence:.5f}    "
            f"implied annualised uncond. vol = "
            f"{np.sqrt(self.uncond_var * 252):.2%}"
        )
        if not self.converged:
            lines.append("WARNING: optimiser did not report convergence")
        return "\n".join(lines)

    def forecast_var(self, horizon: int = 1) -> np.ndarray:
        """Multi-step-ahead variance forecast from the end of the sample."""
        p = self.params
        pers = self.persistence
        s2 = self.sigma[-1] ** 2
        e2 = (self.std_resid[-1] * self.sigma[-1]) ** 2
        neg = 1.0 if self.std_resid[-1] < 0 else 0.0
        out = np.empty(horizon)
        out[0] = p["omega"] + (p["alpha"] + p["gamma"] * neg) * e2 + p["beta"] * s2
        for h in range(1, horizon):
            out[h] = p["omega"] + pers * out[h - 1]
        return out

    def simulate(
        self, n_paths: int, n_steps: int, seed: int | None = None,
        start_from_end: bool = True,
    ) -> np.ndarray:
        """Simulate return paths from the fitted model.

        Returns an array of shape ``(n_paths, n_steps)`` of simulated **returns**
        (same units as the data the model was fitted on). Innovations are drawn from
        the fitted distribution by inverse-CDF sampling.
        """
        rng = np.random.default_rng(seed)
        dist = get_distribution(self.dist)
        p = self.params
        omega, alpha, gamma, beta, mu = (
            p["omega"], p["alpha"], p["gamma"], p["beta"], p["mu"]
        )
        if start_from_end:
            s2 = np.full(n_paths, self.sigma[-1] ** 2)
            e_prev = np.full(n_paths, self.std_resid[-1] * self.sigma[-1])
        else:
            s2 = np.full(n_paths, self.uncond_var)
            e_prev = np.zeros(n_paths)

        u = rng.random((n_paths, n_steps))
        z = dist.ppf(u, self.dist_params)
        out = np.empty((n_paths, n_steps))
        for t in range(n_steps):
            s2 = omega + (alpha + gamma * (e_prev < 0.0)) * e_prev ** 2 + beta * s2
            s2 = np.maximum(s2, 1e-16)
            e = np.sqrt(s2) * z[:, t]
            out[:, t] = mu + e
            e_prev = e
        return out


class GJRGarch:
    """GJR-GARCH(1,1) estimator."""

    def __init__(self, dist: str = "skewt", mean: str = "constant"):
        if mean not in ("constant", "zero"):
            raise ValueError("mean must be 'constant' or 'zero'")
        self.dist_name = dist
        self.dist = get_distribution(dist)
        self.mean = mean

    # ------------------------------------------------------------------ likelihood
    def _neg_loglik(self, theta: np.ndarray, r: np.ndarray, s2_init: float) -> float:
        mu = theta[0] if self.mean == "constant" else 0.0
        omega, alpha, gamma, beta = theta[1], theta[2], theta[3], theta[4]
        dpar = theta[5:]
        if omega <= 0 or alpha < 0 or beta < 0 or (alpha + gamma) < 0:
            return 1e12
        if alpha + beta + 0.5 * gamma >= 0.99999:
            return 1e12
        eps = r - mu
        s2 = _recursion(eps, omega, alpha, gamma, beta, s2_init)[:-1]
        if not np.all(np.isfinite(s2)) or np.any(s2 <= 0):
            return 1e12
        z = eps / np.sqrt(s2)
        ll = self.dist.loglik(z, dpar) - 0.5 * np.log(s2)
        if not np.all(np.isfinite(ll)):
            return 1e12
        return -float(ll.sum())

    # ------------------------------------------------------------------------ fit
    def fit(self, returns, n_starts: int = 4, seed: int = 0) -> GarchFit:
        """Maximum-likelihood estimation.

        ``returns`` may be a Series (the index is carried through) or an array.
        Non-finite observations are dropped and counted.
        """
        index = getattr(returns, "index", None)
        r_raw = np.asarray(returns, dtype=float).ravel()
        ok = np.isfinite(r_raw)
        n_dropped = int((~ok).sum())
        r_raw = r_raw[ok]
        if index is not None:
            index = index[ok]
        if len(r_raw) < 250:
            raise ValueError(f"need at least 250 usable observations, got {len(r_raw)}")

        r = r_raw * _SCALE
        s2_init = float(np.var(r, ddof=1))

        mu0 = float(np.mean(r))
        base = [mu0, 0.05 * s2_init, 0.05, 0.05, 0.88] + list(self.dist.start_params())
        bounds = [
            (-10.0, 10.0) if self.mean == "constant" else (0.0, 0.0),
            (1e-8, 10.0 * s2_init),
            (0.0, 0.99),
            (-0.5, 0.99),
            (0.0, 0.9999),
        ] + self.dist.bounds()

        rng = np.random.default_rng(seed)
        starts = [np.array(base, dtype=float)]
        for _ in range(max(n_starts - 1, 0)):
            pert = np.array(base, dtype=float).copy()
            pert[1] *= float(rng.uniform(0.3, 3.0))
            pert[2] = float(rng.uniform(0.01, 0.15))
            pert[3] = float(rng.uniform(-0.10, 0.20))
            pert[4] = float(rng.uniform(0.70, 0.94))
            for j in range(5, len(pert)):
                lo, hi = bounds[j]
                pert[j] = float(np.clip(pert[j] * rng.uniform(0.6, 1.6), lo + 1e-6, hi - 1e-6))
            starts.append(pert)

        best, best_val, converged = None, np.inf, False
        for st in starts:
            st = np.array(
                [float(np.clip(v, lo + 1e-9, hi - 1e-9)) for v, (lo, hi) in zip(st, bounds)]
            )
            try:
                res = optimize.minimize(
                    self._neg_loglik, st, args=(r, s2_init), method="L-BFGS-B",
                    bounds=bounds, options={"maxiter": 2000, "ftol": 1e-12},
                )
            except Exception:
                continue
            if res.fun < best_val:
                best, best_val, converged = res.x, float(res.fun), bool(res.success)

        if best is None:
            raise RuntimeError("GJR-GARCH estimation failed from every starting value")

        theta = best
        mu_s, omega_s, alpha, gamma, beta = theta[:5]
        dpar = theta[5:]
        eps = r - (mu_s if self.mean == "constant" else 0.0)
        s2 = _recursion(eps, omega_s, alpha, gamma, beta, s2_init)[:-1]
        z = eps / np.sqrt(s2)

        # --- standard errors --------------------------------------------------
        se_h, se_r = self._standard_errors(theta, r, s2_init)

        names = ["mu", "omega", "alpha", "gamma", "beta"]
        params = {
            "mu": mu_s / _SCALE,
            "omega": omega_s / _SCALE ** 2,
            "alpha": alpha,
            "gamma": gamma,
            "beta": beta,
        }
        dist_names = {"t": ["nu"], "skewt": ["nu", "lam"], "normal": []}[self.dist_name]
        scale_map = {"mu": 1.0 / _SCALE, "omega": 1.0 / _SCALE ** 2}
        se_hessian = {
            nm: se_h[i] * scale_map.get(nm, 1.0) for i, nm in enumerate(names)
        }
        se_robust = {nm: se_r[i] * scale_map.get(nm, 1.0) for i, nm in enumerate(names)}
        for j, nm in enumerate(dist_names):
            se_hessian[nm] = se_h[5 + j]
            se_robust[nm] = se_r[5 + j]

        fit = GarchFit(
            params=params,
            loglik=-best_val + len(r) * np.log(_SCALE),  # Jacobian of the rescaling
            sigma=np.sqrt(s2) / _SCALE,
            std_resid=z,
            dist=self.dist_name,
            dist_params=np.asarray(dpar, dtype=float),
            se_hessian=se_hessian,
            se_robust=se_robust,
            converged=converged,
            index=index,
        )
        fit._extras["n_dropped"] = n_dropped
        fit._extras["s2_init_pct"] = s2_init
        return fit

    # ------------------------------------------------------------- standard errors
    def _standard_errors(self, theta, r, s2_init):
        k = len(theta)
        eps_step = np.maximum(np.abs(theta) * 1e-4, 1e-6)

        def f(th):
            return self._neg_loglik(th, r, s2_init)

        H = np.zeros((k, k))
        f0 = f(theta)
        for i in range(k):
            for j in range(i, k):
                tpp, tpm, tmp, tmm = (theta.copy() for _ in range(4))
                tpp[i] += eps_step[i]; tpp[j] += eps_step[j]
                tpm[i] += eps_step[i]; tpm[j] -= eps_step[j]
                tmp[i] -= eps_step[i]; tmp[j] += eps_step[j]
                tmm[i] -= eps_step[i]; tmm[j] -= eps_step[j]
                H[i, j] = H[j, i] = (f(tpp) - f(tpm) - f(tmp) + f(tmm)) / (
                    4.0 * eps_step[i] * eps_step[j]
                )
        try:
            Hinv = np.linalg.pinv(H)
            se_h = np.sqrt(np.clip(np.diag(Hinv), 0.0, np.inf))
        except Exception:
            se_h = np.full(k, np.nan)

        # outer product of gradients for the robust sandwich
        def score_contrib(th):
            mu = th[0] if self.mean == "constant" else 0.0
            om, al, ga, be = th[1], th[2], th[3], th[4]
            dp = th[5:]
            e = r - mu
            s2 = _recursion(e, om, al, ga, be, s2_init)[:-1]
            z = e / np.sqrt(s2)
            return self.dist.loglik(z, dp) - 0.5 * np.log(s2)

        G = np.zeros((len(r), k))
        for i in range(k):
            tp, tm = theta.copy(), theta.copy()
            tp[i] += eps_step[i]; tm[i] -= eps_step[i]
            try:
                G[:, i] = (score_contrib(tp) - score_contrib(tm)) / (2.0 * eps_step[i])
            except Exception:
                G[:, i] = np.nan
        try:
            J = G.T @ G
            Hinv = np.linalg.pinv(H)
            V = Hinv @ J @ Hinv
            se_r = np.sqrt(np.clip(np.diag(V), 0.0, np.inf))
        except Exception:
            se_r = np.full(k, np.nan)
        return se_h, se_r


def ljung_box(x: np.ndarray, lags: int = 20) -> tuple[float, float]:
    """Ljung-Box Q statistic and p-value for serial correlation in ``x``."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    xc = x - x.mean()
    denom = float(xc @ xc)
    q = 0.0
    for k in range(1, lags + 1):
        rk = float(xc[k:] @ xc[:-k]) / denom
        q += rk ** 2 / (n - k)
    q *= n * (n + 2.0)
    return q, float(stats.chi2.sf(q, lags))
