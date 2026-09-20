"""Linear regression with heteroskedasticity- and autocorrelation-consistent errors.

Implemented from first principles (NumPy + SciPy only) rather than taken from
``statsmodels``, both because the execution environment for this project has no
access to a package index and because the estimator is small enough that writing it
out makes the inference assumptions explicit.

Provided
--------
``ols``           OLS with a choice of ``homoskedastic``, ``HC0``-``HC3`` or
                  ``HAC`` (Newey-West, Bartlett kernel) covariance.
``RegressionResult``  coefficients, standard errors, t/p values, R^2, F-test,
                  Durbin-Watson, and a formatted summary table.
``newey_west_lags``   Newey-West (1994) automatic bandwidth, and the common
                  ``floor(4 (T/100)^(2/9))`` rule of thumb.

Cross-checked against ``statsmodels`` in ``tests/test_hac.py`` when that package is
importable, and against closed-form OLS algebra when it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

import numpy as np
from scipy import stats

CovType = Literal["homoskedastic", "HC0", "HC1", "HC2", "HC3", "HAC"]

__all__ = ["ols", "RegressionResult", "newey_west_lags"]


def newey_west_lags(n_obs: int, rule: str = "rule_of_thumb") -> int:
    """Bandwidth for the Bartlett kernel.

    ``rule_of_thumb``  floor(4 (T/100)^(2/9))  - Newey & West (1994), widely used.
    ``schwert``        floor(12 (T/100)^(1/4)) - more conservative, longer lags.
    """
    if rule == "rule_of_thumb":
        return int(np.floor(4.0 * (n_obs / 100.0) ** (2.0 / 9.0)))
    if rule == "schwert":
        return int(np.floor(12.0 * (n_obs / 100.0) ** 0.25))
    raise ValueError(f"unknown rule {rule!r}")


@dataclass
class RegressionResult:
    """Container for an OLS fit with a chosen covariance estimator."""

    params: np.ndarray
    cov: np.ndarray
    names: list[str]
    nobs: int
    df_resid: int
    resid: np.ndarray
    fitted: np.ndarray
    y: np.ndarray
    cov_type: str
    lags: int | None = None
    _extras: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- inference
    @property
    def bse(self) -> np.ndarray:
        return np.sqrt(np.diag(self.cov))

    @property
    def tvalues(self) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            return self.params / self.bse

    @property
    def pvalues(self) -> np.ndarray:
        return 2.0 * stats.t.sf(np.abs(self.tvalues), self.df_resid)

    def conf_int(self, alpha: float = 0.05) -> np.ndarray:
        q = stats.t.ppf(1.0 - alpha / 2.0, self.df_resid)
        return np.column_stack([self.params - q * self.bse, self.params + q * self.bse])

    # ------------------------------------------------------------------- fit
    @property
    def rsquared(self) -> float:
        ss_res = float(self.resid @ self.resid)
        ss_tot = float(((self.y - self.y.mean()) ** 2).sum())
        return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    @property
    def rsquared_adj(self) -> float:
        k = len(self.params)
        return 1.0 - (1.0 - self.rsquared) * (self.nobs - 1) / (self.nobs - k)

    @property
    def durbin_watson(self) -> float:
        d = np.diff(self.resid)
        return float(d @ d / (self.resid @ self.resid))

    def wald(self, restriction: np.ndarray, value: np.ndarray | float = 0.0) -> tuple[float, float]:
        """Wald test of ``R beta = value``. Returns (chi2 statistic, p-value)."""
        R = np.atleast_2d(restriction)
        v = np.atleast_1d(value) * np.ones(R.shape[0])
        diff = R @ self.params - v
        mid = R @ self.cov @ R.T
        stat = float(diff @ np.linalg.solve(mid, diff))
        return stat, float(stats.chi2.sf(stat, R.shape[0]))

    def summary(self, title: str = "OLS") -> str:
        head = (
            f"{title}   n={self.nobs}  k={len(self.params)}  "
            f"R2={self.rsquared:.4f}  adjR2={self.rsquared_adj:.4f}  "
            f"cov={self.cov_type}" + (f"(L={self.lags})" if self.lags is not None else "")
        )
        lines = [head, "-" * max(len(head), 72)]
        lines.append(f"{'':<22s}{'coef':>12s}{'s.e.':>12s}{'t':>9s}{'p':>9s}")
        ci = self.conf_int()
        for i, nm in enumerate(self.names):
            lines.append(
                f"{nm:<22s}{self.params[i]:>12.6f}{self.bse[i]:>12.6f}"
                f"{self.tvalues[i]:>9.3f}{self.pvalues[i]:>9.4f}"
                f"   [{ci[i,0]:.4f}, {ci[i,1]:.4f}]"
            )
        lines.append("-" * max(len(head), 72))
        lines.append(f"Durbin-Watson: {self.durbin_watson:.3f}")
        return "\n".join(lines)


def _bartlett_weights(lags: int) -> np.ndarray:
    return 1.0 - np.arange(1, lags + 1) / (lags + 1.0)


def _sandwich(X: np.ndarray, u: np.ndarray, cov_type: str, lags: int | None,
              xtx_inv: np.ndarray) -> np.ndarray:
    n, k = X.shape
    if cov_type == "homoskedastic":
        s2 = float(u @ u) / (n - k)
        return s2 * xtx_inv

    if cov_type in ("HC0", "HC1", "HC2", "HC3"):
        h = np.einsum("ij,jk,ik->i", X, xtx_inv, X)  # leverage
        if cov_type == "HC0":
            w = u ** 2
        elif cov_type == "HC1":
            w = u ** 2 * n / (n - k)
        elif cov_type == "HC2":
            w = u ** 2 / (1.0 - h)
        else:
            w = u ** 2 / (1.0 - h) ** 2
        meat = (X * w[:, None]).T @ X
        return xtx_inv @ meat @ xtx_inv

    if cov_type == "HAC":
        L = int(lags)
        g = X * u[:, None]                      # n x k score contributions
        meat = g.T @ g                          # Gamma_0
        wts = _bartlett_weights(L)
        for j in range(1, L + 1):
            gj = g[j:].T @ g[:-j]               # Gamma_j
            meat += wts[j - 1] * (gj + gj.T)
        # small-sample correction, matching the usual n/(n-k) adjustment
        meat *= n / (n - k)
        return xtx_inv @ meat @ xtx_inv

    raise ValueError(f"unknown cov_type {cov_type!r}")


def ols(
    y,
    X,
    names: Sequence[str] | None = None,
    add_const: bool = True,
    cov_type: CovType = "HAC",
    lags: int | None = None,
    lag_rule: str = "rule_of_thumb",
) -> RegressionResult:
    """Ordinary least squares with a selectable covariance estimator.

    Parameters
    ----------
    y, X
        Array-like. ``X`` may be 1-d (single regressor) or 2-d ``(n, k)``. Rows with
        any non-finite value in ``y`` or ``X`` are dropped, and the number dropped is
        recorded in ``result._extras['n_dropped']`` so that silent sample changes are
        visible.
    add_const
        Prepend an intercept column named ``const``.
    cov_type
        ``homoskedastic``, ``HC0``-``HC3``, or ``HAC`` (Newey-West, Bartlett kernel).
    lags
        HAC bandwidth. If ``None``, chosen by ``newey_west_lags(n, lag_rule)``.
    """
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    if X.shape[0] != y.shape[0]:
        raise ValueError(f"y has {y.shape[0]} rows, X has {X.shape[0]}")

    if names is None:
        names = [f"x{i+1}" for i in range(X.shape[1])]
    names = list(names)
    if len(names) != X.shape[1]:
        raise ValueError("len(names) must match number of regressor columns")

    if add_const:
        X = np.column_stack([np.ones(len(X)), X])
        names = ["const"] + names

    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    n_dropped = int((~ok).sum())
    y, X = y[ok], X[ok]
    n, k = X.shape
    if n <= k:
        raise ValueError(f"not enough usable observations: n={n}, k={k}")

    xtx = X.T @ X
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ (X.T @ y)
    fitted = X @ beta
    u = y - fitted

    if cov_type == "HAC" and lags is None:
        lags = newey_west_lags(n, lag_rule)
    cov = _sandwich(X, u, cov_type, lags, xtx_inv)

    res = RegressionResult(
        params=beta, cov=cov, names=names, nobs=n, df_resid=n - k,
        resid=u, fitted=fitted, y=y, cov_type=cov_type,
        lags=lags if cov_type == "HAC" else None,
    )
    res._extras["n_dropped"] = n_dropped
    return res
