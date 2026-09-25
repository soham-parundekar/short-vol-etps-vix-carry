"""Extreme value theory: peaks-over-threshold with the Generalised Pareto Distribution.

The central quantitative question of this project - *how likely was the move that
killed XIV?* - is a question about the far tail of a distribution, in a region where
there are, by construction, almost no observations. Reading the answer off the
empirical distribution would give either zero or one, depending on whether the day
in question is inside the sample. EVT gives a principled interpolation: the
Pickands-Balkema-de Haan theorem says that for a wide class of distributions the
*excesses* over a high threshold converge to a Generalised Pareto Distribution, so
the tail can be estimated from the handful of observations that do exceed it.

    P(X > u + y | X > u)  ->  (1 + xi y / beta)^(-1/xi),    y > 0

and the unconditional tail probability and quantiles follow:

    P(X > x)   = (N_u / n) (1 + xi (x - u) / beta)^(-1/xi)
    VaR_p      = u + (beta / xi) [ ((n / N_u)(1 - p))^(-xi) - 1 ]
    ES_p       = (VaR_p + beta - xi u) / (1 - xi)              for xi < 1

``xi > 0`` is the heavy-tailed (Frechet) case and is what volatility data should
show; ``xi`` close to 0 is exponential-tailed; ``xi < 0`` means a finite upper
bound, which for an index return would be a red flag worth investigating rather
than accepting.

Conditional EVT
---------------
McNeil & Frey (2000) apply the above not to raw returns but to the **standardised
residuals** of a fitted GARCH model, which are much closer to i.i.d. than the raw
series. The conditional quantile is then

    VaR_{t+1}(p) = mu + sigma_{t+1} * z_p,

with ``z_p`` the GPD-based quantile of the residual distribution. That two-stage
structure - GARCH for the time-varying scale, EVT for the shape of the tail - is
what :func:`conditional_evt_quantile` implements.

Threshold choice is the weak point of any POT analysis, so this module deliberately
exposes the diagnostics (mean-excess plot, stability of ``xi`` across thresholds)
rather than hiding a default, and the sensitivity of every headline number to the
threshold is reported in ``docs/validation.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize, stats

__all__ = [
    "choose_threshold",
    "gpd_ks",
    "GPDFit",
    "fit_gpd",
    "mean_excess",
    "threshold_stability",
    "hill_estimator",
    "conditional_evt_quantile",
]


def _orient(x: np.ndarray, tail: str) -> np.ndarray:
    """Return a series whose *upper* tail is the tail of interest."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if tail == "upper":
        return x
    if tail == "lower":
        return -x
    raise ValueError("tail must be 'upper' or 'lower'")


@dataclass
class GPDFit:
    """Fitted Generalised Pareto tail."""

    xi: float
    beta: float
    threshold: float
    n_exceed: int
    n_total: int
    tail: str
    loglik: float
    se_xi: float = np.nan
    se_beta: float = np.nan
    converged: bool = True
    _extras: dict = field(default_factory=dict)

    @property
    def exceed_rate(self) -> float:
        return self.n_exceed / self.n_total

    # ---------------------------------------------------------------- tail maths
    def exceedance_prob(self, x) -> np.ndarray:
        """P(X > x) in the *original orientation* of the data."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        xs = x if self.tail == "upper" else -x
        y = xs - self.threshold
        out = np.full_like(xs, np.nan, dtype=float)
        below = y <= 0
        # below the threshold the GPD does not apply; report the empirical rate
        out[below] = np.nan
        yy = y[~below]
        if self.xi == 0:
            tailp = np.exp(-yy / self.beta)
        else:
            base = 1.0 + self.xi * yy / self.beta
            tailp = np.where(base > 0, base ** (-1.0 / self.xi), 0.0)
        out[~below] = self.exceed_rate * tailp
        return out if out.size > 1 else float(out[0])

    def return_period(self, x, periods_per_year: float = 252.0):
        """Expected years between exceedances of ``x``."""
        p = np.atleast_1d(self.exceedance_prob(x)).astype(float)
        with np.errstate(divide="ignore"):
            rp = 1.0 / (p * periods_per_year)
        return rp if rp.size > 1 else float(rp[0])

    def quantile(self, p) -> np.ndarray:
        """Quantile at probability ``p`` (``p`` close to 1 for the upper tail)."""
        p = np.atleast_1d(np.asarray(p, dtype=float))
        arg = (1.0 - p) / self.exceed_rate
        if self.xi == 0:
            q = self.threshold - self.beta * np.log(arg)
        else:
            q = self.threshold + (self.beta / self.xi) * (arg ** (-self.xi) - 1.0)
        out = q if self.tail == "upper" else -q
        return out if out.size > 1 else float(out[0])

    def expected_shortfall(self, p) -> np.ndarray:
        """Expected shortfall beyond the ``p`` quantile. Requires ``xi < 1``."""
        if self.xi >= 1.0:
            return np.nan
        q = np.atleast_1d(np.asarray(self.quantile(p), dtype=float))
        qq = q if self.tail == "upper" else -q
        es = (qq + self.beta - self.xi * self.threshold) / (1.0 - self.xi)
        out = es if self.tail == "upper" else -es
        return out if out.size > 1 else float(out[0])

    def summary(self) -> str:
        return (
            f"GPD ({self.tail} tail)  u={self.threshold:.6f}  "
            f"N_u={self.n_exceed}/{self.n_total} ({self.exceed_rate:.2%})\n"
            f"  xi   = {self.xi:+.4f}  (se {self.se_xi:.4f})"
            f"   -> {'heavy-tailed' if self.xi > 0.02 else 'exponential/bounded'}\n"
            f"  beta = {self.beta:.6f}  (se {self.se_beta:.6f})\n"
            f"  loglik = {self.loglik:.3f}"
            + ("" if self.converged else "\n  WARNING: optimiser did not converge")
        )


def _gpd_nll(theta: np.ndarray, y: np.ndarray) -> float:
    xi, log_beta = theta
    beta = np.exp(log_beta)
    if beta <= 0:
        return 1e12
    if abs(xi) < 1e-8:
        return float(len(y) * log_beta + (y / beta).sum())
    z = 1.0 + xi * y / beta
    if np.any(z <= 1e-12):
        return 1e12
    return float(len(y) * log_beta + (1.0 + 1.0 / xi) * np.log(z).sum())


def fit_gpd(
    x,
    threshold: float | None = None,
    q: float = 0.95,
    tail: str = "upper",
) -> GPDFit:
    """Fit a GPD to the excesses above a threshold by maximum likelihood.

    Parameters
    ----------
    x
        The data (any orientation; ``tail`` says which end is of interest).
    threshold
        Threshold in the data's own units and orientation. If ``None``, the
        empirical ``q`` quantile of the oriented series is used.
    q
        Quantile used to set the threshold when ``threshold`` is ``None``.
    """
    xo = _orient(x, tail)
    n = len(xo)
    if threshold is None:
        u = float(np.quantile(xo, q))
    else:
        u = float(threshold if tail == "upper" else -threshold)
    y = xo[xo > u] - u
    if len(y) < 20:
        raise ValueError(
            f"only {len(y)} exceedances above the threshold; lower it or get more data"
        )

    # Moment-based start (Hosking & Wallis)
    m, v = float(y.mean()), float(y.var(ddof=1))
    xi0 = 0.5 * (1.0 - m ** 2 / v) if v > 0 else 0.1
    xi0 = float(np.clip(xi0, -0.4, 0.8))
    beta0 = max(0.5 * m * (m ** 2 / v + 1.0), 1e-8) if v > 0 else m

    best, best_val, ok = None, np.inf, False
    for st in (
        np.array([xi0, np.log(beta0)]),
        np.array([0.1, np.log(m)]),
        np.array([0.3, np.log(m)]),
        np.array([-0.1, np.log(m)]),
    ):
        try:
            res = optimize.minimize(
                _gpd_nll, st, args=(y,), method="Nelder-Mead",
                options={"maxiter": 5000, "xatol": 1e-10, "fatol": 1e-10},
            )
        except Exception:
            continue
        if res.fun < best_val:
            best, best_val, ok = res.x, float(res.fun), bool(res.success)
    if best is None:
        raise RuntimeError("GPD maximum likelihood failed")

    xi, beta = float(best[0]), float(np.exp(best[1]))

    # numerical Hessian in (xi, beta)
    def nll_ab(p):
        return _gpd_nll(np.array([p[0], np.log(max(p[1], 1e-12))]), y)

    p0 = np.array([xi, beta])
    h = np.maximum(np.abs(p0) * 1e-4, 1e-7)
    H = np.zeros((2, 2))
    for i in range(2):
        for j in range(i, 2):
            a, b, c, d = (p0.copy() for _ in range(4))
            a[i] += h[i]; a[j] += h[j]
            b[i] += h[i]; b[j] -= h[j]
            c[i] -= h[i]; c[j] += h[j]
            d[i] -= h[i]; d[j] -= h[j]
            H[i, j] = H[j, i] = (nll_ab(a) - nll_ab(b) - nll_ab(c) + nll_ab(d)) / (
                4 * h[i] * h[j]
            )
    try:
        cov = np.linalg.pinv(H)
        se = np.sqrt(np.clip(np.diag(cov), 0, np.inf))
    except Exception:
        se = np.array([np.nan, np.nan])

    fit = GPDFit(
        xi=xi, beta=beta,
        threshold=u if tail == "upper" else -u,
        n_exceed=len(y), n_total=n, tail=tail,
        loglik=-best_val, se_xi=float(se[0]), se_beta=float(se[1]), converged=ok,
    )
    # Kolmogorov-Smirnov goodness of fit on the PIT of the excesses
    if abs(xi) < 1e-8:
        u_pit = 1.0 - np.exp(-y / beta)
    else:
        u_pit = 1.0 - np.clip(1.0 + xi * y / beta, 1e-12, None) ** (-1.0 / xi)
    ks = stats.kstest(u_pit, "uniform")
    fit._extras["ks_stat"] = float(ks.statistic)
    fit._extras["ks_pvalue"] = float(ks.pvalue)
    fit._extras["excesses"] = y
    return fit


def mean_excess(x, tail: str = "upper", n_points: int = 60,
                q_lo: float = 0.70, q_hi: float = 0.995) -> "tuple[np.ndarray, np.ndarray, np.ndarray]":
    """Mean-excess function with pointwise standard errors.

    For a GPD tail the mean excess ``E[X - u | X > u]`` is *linear* in ``u`` with
    slope ``xi / (1 - xi)``. A plot that is linear above some level is the
    conventional justification for choosing that level as the threshold.

    Returns ``(thresholds, mean_excess, standard_error)`` in the oriented scale.
    """
    xo = _orient(x, tail)
    us = np.quantile(xo, np.linspace(q_lo, q_hi, n_points))
    me, se = [], []
    for u in us:
        y = xo[xo > u] - u
        if len(y) < 10:
            me.append(np.nan); se.append(np.nan); continue
        me.append(float(y.mean()))
        se.append(float(y.std(ddof=1) / np.sqrt(len(y))))
    return us, np.array(me), np.array(se)


def threshold_stability(x, tail: str = "upper", qs=None) -> "list[dict]":
    """Refit the GPD across a grid of thresholds and report parameter stability.

    A tail estimate that swings wildly with the threshold is not an estimate, and
    this is the honest way to show it.
    """
    if qs is None:
        qs = [0.90, 0.925, 0.95, 0.96, 0.97, 0.975, 0.98, 0.99]
    out = []
    for q in qs:
        try:
            f = fit_gpd(x, q=q, tail=tail)
            out.append(
                dict(q=q, threshold=f.threshold, n_exceed=f.n_exceed, xi=f.xi,
                     se_xi=f.se_xi, beta=f.beta, ks_p=f._extras.get("ks_pvalue"))
            )
        except Exception as exc:  # pragma: no cover - diagnostic path
            out.append(dict(q=q, error=str(exc)))
    return out


def hill_estimator(x, k: int, tail: str = "upper") -> float:
    """Hill estimator of the tail index using the ``k`` largest observations.

    Only valid for ``xi > 0`` (strictly Pareto-type tails). Reported alongside the
    GPD estimate as an independent check, not as the headline number.
    """
    xo = np.sort(_orient(x, tail))[::-1]
    xo = xo[xo > 0]
    if k >= len(xo):
        raise ValueError(f"k={k} exceeds the {len(xo)} positive observations available")
    top = xo[: k + 1]
    return float(np.mean(np.log(top[:k]) - np.log(top[k])))


def conditional_evt_quantile(
    std_resid: np.ndarray,
    sigma_next: float,
    mu: float,
    p: float,
    q_threshold: float = 0.95,
    tail: str = "upper",
) -> dict:
    """McNeil-Frey conditional VaR.

    Fits the GPD to the *standardised residuals* of a GARCH filter and scales the
    resulting residual quantile by the one-step-ahead conditional volatility.
    """
    fit = fit_gpd(std_resid, q=q_threshold, tail=tail)
    z_p = float(fit.quantile(p))
    return {
        "var": mu + sigma_next * z_p,
        "z_quantile": z_p,
        "gpd": fit,
    }


# ---------------------------------------------------------------- threshold rule
# Moved here from scripts/run_pipeline.py (Phase 11) so that the design-window model
# used for position sizing applies exactly the rule the Phase 09 tail model did.


def gpd_ks(z, g):
    """KS p-value of the excesses over ``g.threshold`` against the fitted GPD."""
    y = z[z > g.threshold] - g.threshold
    c = (1 - (1 + g.xi * y / g.beta) ** (-1 / g.xi)) if abs(g.xi) > 1e-8 \
        else 1 - np.exp(-y / g.beta)
    return float(stats.kstest(c, "uniform").pvalue)


def me_xi(z, lo_q, hi_q):
    """Shape implied by a straight-line fit to the mean-excess plot between two
    quantiles: slope s gives xi = s / (1 + s)."""
    th, me, _ = mean_excess(z, tail="upper", n_points=60, q_lo=0.80, q_hi=0.99)
    qs = np.array([(z <= t).mean() for t in th])
    m = (qs >= lo_q) & (qs <= hi_q)
    if m.sum() < 3:
        return np.nan
    s = np.polyfit(th[m], me[m], 1)[0]
    return s / (1 + s)


def choose_threshold(z, grid):
    """Pick the peaks-over-threshold level by the rule fixed before any data was
    retrieved (docs/preregistration.md, section 3): the lowest threshold with >= 50
    exceedances, xi within one se of the next two, KS on the excesses p > 0.10, and
    inside the linear region of the mean excess - taken here as the lower and upper
    halves of [q, 0.99] implying xi within one se of each other."""
    rows = []
    fits = {q: fit_gpd(z, q=q, tail="upper") for q in grid}
    for i, q in enumerate(grid):
        g = fits[q]
        nxt = [fits[grid[j]].xi for j in (i + 1, i + 2) if j < len(grid)]
        stable = len(nxt) == 2 and all(abs(g.xi - x) <= g.se_xi for x in nxt)
        mid = q + (0.99 - q) / 2.0
        a, b = me_xi(z, q, mid), me_xi(z, mid, 0.99)
        linear = bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) <= g.se_xi)
        ks = gpd_ks(z, g)
        rows.append({"q": q, "threshold": g.threshold, "n_exceed": g.n_exceed,
                     "xi": g.xi, "se_xi": g.se_xi, "beta": g.beta, "ks_p": ks,
                     "me_xi_lower_half": a, "me_xi_upper_half": b,
                     "ok_n": g.n_exceed >= 50, "ok_stable": stable,
                     "ok_ks": ks > 0.10, "ok_linear": linear})
    t = pd.DataFrame(rows)
    t["passes"] = t[["ok_n", "ok_stable", "ok_ks", "ok_linear"]].all(axis=1)
    chosen = float(t.loc[t["passes"], "q"].min()) if t["passes"].any() else np.nan
    t["chosen"] = t["q"] == chosen
    return t, fits, chosen
