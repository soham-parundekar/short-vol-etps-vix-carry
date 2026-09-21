"""Termination probabilities and survival under a GARCH-filtered EVT tail.

The two-stage construction of McNeil and Frey (2000): a GJR-GARCH filter supplies the
time-varying scale ``sigma_t``, and a Generalised Pareto tail fitted to the
standardised residuals supplies the shape of the distribution beyond anything the
body of the data can speak to. The innovation law used here is **spliced**: the
fitted skewed-t below the EVT threshold ``u``, and the GPD above it, with the total
mass above ``u`` equal to the empirical exceedance rate.

Log and simple returns, kept apart deliberately
-----------------------------------------------
The GARCH model is fitted to **log** returns. The termination thresholds are defined
on **simple** returns: an 80% one-day index rise destroys 80% of a -1x product, and a
160% rise does the same to a -0.5x product. The conversion is

    R >= c   <=>   log(1 + R) >= log(1 + c)

so the log thresholds are ``log(1.8) = 0.588`` and ``log(2.6) = 0.956``. Using the
simple-return figure directly as a log threshold would place the bar too high and
understate the probability; every function here takes the SIMPLE threshold and
converts it internally, so the conversion lives in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .distributions import get_distribution
from .evt import GPDFit

__all__ = [
    "SplicedInnovations",
    "conditional_exceedance",
    "filter_sigma",
    "termination_table",
    "simulate_first_passage",
    "simulate_returns",
]


@dataclass
class SplicedInnovations:
    """Skewed-t body below ``gpd.threshold``, GPD above it (upper tail only).

    The lower tail is left to the skewed-t: for an inverse product the damaging shock
    is a large POSITIVE index move, and nothing in this module depends on the left
    tail beyond it being a proper distribution.
    """

    dist: str
    dist_params: np.ndarray
    gpd: GPDFit

    def __post_init__(self):
        if self.gpd.tail != "upper":
            raise ValueError("the spliced law needs an upper-tail GPD")
        self._d = get_distribution(self.dist)
        self._u = float(self.gpd.threshold)
        self._pu = float(self.gpd.exceed_rate)
        self._Fu = float(self._d.cdf(np.array([self._u]), self.dist_params)[0])

    def sf(self, x) -> np.ndarray:
        """P(z > x)."""
        x = np.atleast_1d(np.asarray(x, dtype=float))
        out = np.empty_like(x)
        hi = x > self._u
        out[hi] = np.asarray(self.gpd.exceedance_prob(x[hi]), dtype=float).reshape(-1) \
            if hi.any() else out[hi]
        if (~hi).any():
            # Body: the skewed-t, rescaled so the mass below u is exactly 1 - p_u and
            # the law is continuous at the join.
            Fb = self._d.cdf(x[~hi], self.dist_params) / self._Fu * (1.0 - self._pu)
            out[~hi] = 1.0 - Fb
        return out

    def ppf(self, p) -> np.ndarray:
        """Inverse CDF, for simulation."""
        p = np.asarray(p, dtype=float)
        out = np.empty_like(p)
        body = p < 1.0 - self._pu
        if body.any():
            out[body] = self._d.ppf(p[body] / (1.0 - self._pu) * self._Fu, self.dist_params)
        tail = ~body
        if tail.any():
            v = (p[tail] - (1.0 - self._pu)) / self._pu          # uniform on the tail
            v = np.clip(v, 0.0, 1.0 - 1e-15)
            xi, beta = self.gpd.xi, self.gpd.beta
            y = beta / xi * ((1.0 - v) ** (-xi) - 1.0) if abs(xi) > 1e-10 \
                else -beta * np.log(1.0 - v)
            out[tail] = self._u + y
        return out


def conditional_exceedance(simple_threshold: float, mu: float, sigma,
                           innov: SplicedInnovations) -> np.ndarray:
    """P(R_{t+1} >= c | F_t) for a one-day SIMPLE return threshold ``c``."""
    log_c = np.log1p(simple_threshold)
    x = (log_c - mu) / np.asarray(sigma, dtype=float)
    return innov.sf(x)


def filter_sigma(params: dict, returns: pd.Series, s2_init: float | None = None) -> pd.Series:
    """Run the GJR recursion with FIXED parameters over a return series.

    ``sigma[t]`` is the conditional sd of the return on date t, i.e. it uses
    information through t-1 only. This is how a model estimated on data ending
    2017-12-31 is carried forward to a date in February 2018 without re-estimating
    anything: the state is updated with each day's return as it arrives, the
    parameters are not.
    """
    r = np.asarray(returns, dtype=float)
    om, al, ga, be, mu = (params["omega"], params["alpha"], params["gamma"],
                          params["beta"], params["mu"])
    pers = al + be + 0.5 * ga
    s2 = np.empty(len(r) + 1)
    s2[0] = s2_init if s2_init is not None else om / (1.0 - pers)
    for t in range(len(r)):
        e = r[t] - mu
        s2[t + 1] = om + (al + (ga if e < 0 else 0.0)) * e * e + be * s2[t]
    return pd.Series(np.sqrt(s2[:-1]), index=getattr(returns, "index", None))


def termination_table(
    sigma: pd.Series, mu: float, innov: SplicedInnovations,
    thresholds: "dict[str, float]", calm_quantile: float = 0.20,
    periods_per_year: int = 252, at_dates: "list | None" = None,
) -> pd.DataFrame:
    """Daily, annualised and return-period probabilities, per threshold.

    ``unconditional`` averages the one-day conditional probability over every day of
    the sample - the probability on a day drawn at random from the history - rather
    than evaluating it at a single stationary sigma, which would understate it because
    the probability is convex in sigma.
    ``calm`` averages over the days in the lowest ``calm_quantile`` of conditional
    volatility. ``at_dates`` adds rows for specific days.
    """
    sig = sigma.dropna()
    calm_cut = sig.quantile(calm_quantile)
    rows = []

    def _row(state, s, extra=None):
        for name, c in thresholds.items():
            p_daily = float(np.mean(conditional_exceedance(c, mu, s, innov)))
            p_ann = 1.0 - (1.0 - p_daily) ** periods_per_year
            rows.append({
                "state": state, "design": name, "simple_threshold": c,
                "log_threshold": float(np.log1p(c)),
                "p_daily": p_daily, "p_annual": p_ann,
                "return_period_years": (1.0 / (p_daily * periods_per_year))
                if p_daily > 0 else np.inf,
                "sigma_daily": float(np.mean(s)),
                **(extra or {}),
            })

    _row("unconditional", sig.to_numpy())
    _row(f"calm (lowest {int(calm_quantile * 100)}% of sigma)",
         sig[sig <= calm_cut].to_numpy())
    for d in (at_dates or []):
        d = pd.Timestamp(d)
        if d in sigma.index:
            _row(f"on {d.date()}", np.array([float(sigma[d])]))
    return pd.DataFrame(rows)


def simulate_first_passage(
    params: dict, innov: SplicedInnovations, simple_thresholds: "dict[str, float]",
    n_paths: int, n_steps: int, seed: int, sigma0: float | None = None,
    chunk: int = 5000, sigma_cap: float | None = None,
) -> pd.DataFrame:
    """Survival curves: share of paths with no one-day return at or above each
    threshold by day t, with binomial standard errors.

    Paths are simulated from the GJR recursion with spliced innovations, starting
    from ``sigma0`` (default: the unconditional sd). Chunked so twenty thousand
    five-year paths fit in memory.

    ``sigma_cap`` bounds the conditional sd. Unbounded, the fitted pre-2018 model
    (alpha about 0.28, GPD innovations) produces volatility spirals far outside
    anything observed - a simulated daily sd of 7, against an in-sample maximum of
    0.16 - and most simulated wipeouts occur inside them. Running once unbounded and
    once capped at the in-sample maximum brackets survival between "the model's own
    dynamics" and "only volatility states the data has visited". Neither is the
    answer; the pair is.
    """
    rng = np.random.default_rng(seed)
    om, al, ga, be, mu = (params["omega"], params["alpha"], params["gamma"],
                          params["beta"], params["mu"])
    s2_0 = sigma0 ** 2 if sigma0 is not None else om / (1.0 - (al + be + 0.5 * ga))
    log_th = {k: np.log1p(v) for k, v in simple_thresholds.items()}
    first = {k: np.full(n_paths, np.inf) for k in simple_thresholds}
    done = 0
    while done < n_paths:
        m = min(chunk, n_paths - done)
        s2 = np.full(m, s2_0)
        e_prev = np.zeros(m)
        for t in range(n_steps):
            s2 = om + (al + ga * (e_prev < 0.0)) * e_prev ** 2 + be * s2
            if sigma_cap is not None:
                s2 = np.minimum(s2, sigma_cap ** 2)
            z = innov.ppf(rng.random(m))
            e = np.sqrt(s2) * z
            r = mu + e
            for k, lt in log_th.items():
                hit = (r >= lt) & ~np.isfinite(first[k][done:done + m])
                if hit.any():
                    first[k][done:done + m][hit] = t + 1
            e_prev = e
        done += m
    days = np.arange(1, n_steps + 1)
    out = pd.DataFrame({"day": days, "years": days / 252.0})
    for k, fp in first.items():
        S = np.array([(fp > d).mean() for d in days])
        out[f"survival_{k}"] = S
        out[f"se_{k}"] = np.sqrt(S * (1.0 - S) / n_paths)
    out.attrs["n_paths"] = n_paths
    out.attrs["seed"] = seed
    out.attrs["sigma_cap"] = sigma_cap
    return out


def simulate_returns(params: dict, innov: SplicedInnovations, n_paths: int,
                     n_steps: int, seed: int, sigma_cap: float | None = None) -> np.ndarray:
    """Simulated daily SIMPLE index returns, shape (n_paths, n_steps), for the
    model-based Kelly calculation. Same recursion and cap as the survival paths."""
    rng = np.random.default_rng(seed)
    om, al, ga, be, mu = (params["omega"], params["alpha"], params["gamma"],
                          params["beta"], params["mu"])
    s2 = np.full(n_paths, om / (1.0 - (al + be + 0.5 * ga)))
    e_prev = np.zeros(n_paths)
    out = np.empty((n_paths, n_steps))
    for t in range(n_steps):
        s2 = om + (al + ga * (e_prev < 0.0)) * e_prev ** 2 + be * s2
        if sigma_cap is not None:
            s2 = np.minimum(s2, sigma_cap ** 2)
        e = np.sqrt(s2) * innov.ppf(rng.random(n_paths))
        out[:, t] = np.expm1(mu + e)
        e_prev = e
    return out
