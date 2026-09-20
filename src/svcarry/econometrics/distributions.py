"""Standardised innovation distributions for the GARCH likelihood.

Every distribution here is parameterised to have **mean zero and unit variance**, so
that the conditional variance of the GARCH recursion is the conditional variance of
the return. That normalisation is what makes ``sigma_t`` interpretable and what lets
the same fitted model be used for simulation, quantiles and the EVT threshold step.

Implemented
-----------
``Normal``      standard normal
``StudentT``    standardised Student-t, ``nu > 2``
``SkewT``       Hansen (1994) skewed Student-t, ``nu > 2``, ``-1 < lam < 1``

Hansen's skewed t is the workhorse for equity-style innovations because it adds left
skew without giving up the fat tails of the t. Its density is

    f(z) = b c (1 + (1/(nu-2)) ((b z + a)/(1 - lam))^2)^(-(nu+1)/2),   z <  -a/b
    f(z) = b c (1 + (1/(nu-2)) ((b z + a)/(1 + lam))^2)^(-(nu+1)/2),   z >= -a/b

with

    c = Gamma((nu+1)/2) / (sqrt(pi (nu-2)) Gamma(nu/2))
    a = 4 lam c (nu - 2)/(nu - 1)
    b = sqrt(1 + 3 lam^2 - a^2)

The closed-form CDF and quantile function are implemented too, because the
simulation and VaR steps need them and numerical inversion of the density would be
both slower and less accurate in the far tail.

``tests/test_distributions.py`` checks, for a grid of parameters, that the density
integrates to one, that mean and variance are 0 and 1, that the CDF is the integral
of the PDF, and that the quantile function inverts the CDF.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import special, stats

__all__ = ["Normal", "StudentT", "SkewT", "get_distribution"]


@dataclass(frozen=True)
class Normal:
    """Standard normal innovations. No shape parameters."""

    n_params: int = 0
    name: str = "normal"

    @staticmethod
    def start_params() -> list[float]:
        return []

    @staticmethod
    def bounds() -> list[tuple[float, float]]:
        return []

    @staticmethod
    def loglik(z: np.ndarray, params: np.ndarray) -> np.ndarray:
        return -0.5 * (np.log(2.0 * np.pi) + z ** 2)

    @staticmethod
    def ppf(u, params) -> np.ndarray:
        return stats.norm.ppf(u)

    @staticmethod
    def cdf(z, params) -> np.ndarray:
        return stats.norm.cdf(z)


@dataclass(frozen=True)
class StudentT:
    """Standardised Student-t: unit variance for any ``nu > 2``."""

    n_params: int = 1
    name: str = "t"

    @staticmethod
    def start_params() -> list[float]:
        return [8.0]

    @staticmethod
    def bounds() -> list[tuple[float, float]]:
        return [(2.05, 200.0)]

    @staticmethod
    def loglik(z: np.ndarray, params: np.ndarray) -> np.ndarray:
        nu = float(params[0])
        s = np.sqrt(nu / (nu - 2.0))          # scale so that Var(z) = 1
        return (
            special.gammaln((nu + 1.0) / 2.0)
            - special.gammaln(nu / 2.0)
            - 0.5 * np.log(np.pi * nu)
            + np.log(s)
            - (nu + 1.0) / 2.0 * np.log1p((z * s) ** 2 / nu)
        )

    @staticmethod
    def ppf(u, params) -> np.ndarray:
        nu = float(params[0])
        return stats.t.ppf(u, nu) * np.sqrt((nu - 2.0) / nu)

    @staticmethod
    def cdf(z, params) -> np.ndarray:
        nu = float(params[0])
        return stats.t.cdf(np.asarray(z) * np.sqrt(nu / (nu - 2.0)), nu)


def _skewt_abc(nu: float, lam: float) -> tuple[float, float, float]:
    c = np.exp(
        special.gammaln((nu + 1.0) / 2.0)
        - special.gammaln(nu / 2.0)
        - 0.5 * np.log(np.pi * (nu - 2.0))
    )
    a = 4.0 * lam * c * (nu - 2.0) / (nu - 1.0)
    b = np.sqrt(1.0 + 3.0 * lam ** 2 - a ** 2)
    return float(a), float(b), float(c)


@dataclass(frozen=True)
class SkewT:
    """Hansen (1994) skewed Student-t, standardised to mean 0 / variance 1."""

    n_params: int = 2
    name: str = "skewt"

    @staticmethod
    def start_params() -> list[float]:
        return [8.0, -0.1]

    @staticmethod
    def bounds() -> list[tuple[float, float]]:
        return [(2.05, 200.0), (-0.95, 0.95)]

    @staticmethod
    def loglik(z: np.ndarray, params: np.ndarray) -> np.ndarray:
        nu, lam = float(params[0]), float(params[1])
        a, b, c = _skewt_abc(nu, lam)
        denom = np.where(z < -a / b, 1.0 - lam, 1.0 + lam)
        inner = 1.0 + ((b * z + a) / denom) ** 2 / (nu - 2.0)
        return np.log(b) + np.log(c) - (nu + 1.0) / 2.0 * np.log(inner)

    @staticmethod
    def cdf(z, params) -> np.ndarray:
        nu, lam = float(params[0]), float(params[1])
        a, b, c = _skewt_abc(nu, lam)
        z = np.asarray(z, dtype=float)
        scale = np.sqrt(nu / (nu - 2.0))
        left = (1.0 - lam) * stats.t.cdf((b * z + a) / (1.0 - lam) * scale, nu)
        right = (1.0 - lam) / 2.0 + (1.0 + lam) * (
            stats.t.cdf((b * z + a) / (1.0 + lam) * scale, nu) - 0.5
        )
        return np.where(z < -a / b, left, right)

    @staticmethod
    def ppf(u, params) -> np.ndarray:
        nu, lam = float(params[0]), float(params[1])
        a, b, c = _skewt_abc(nu, lam)
        u = np.asarray(u, dtype=float)
        thresh = (1.0 - lam) / 2.0
        scale = np.sqrt((nu - 2.0) / nu)
        lo = (1.0 - lam) * scale * stats.t.ppf(np.clip(u / (1.0 - lam), 1e-15, 1 - 1e-15), nu)
        hi = (1.0 + lam) * scale * stats.t.ppf(
            np.clip(0.5 + (u - thresh) / (1.0 + lam), 1e-15, 1 - 1e-15), nu
        )
        return (np.where(u < thresh, lo, hi) - a) / b


_REGISTRY = {"normal": Normal(), "t": StudentT(), "skewt": SkewT()}


def get_distribution(name: str):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown distribution {name!r}; choose from {sorted(_REGISTRY)}")
