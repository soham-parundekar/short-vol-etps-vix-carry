"""Growth-optimal (Kelly) exposure for a short position in a fat-tailed index.

For a position that is **short** a fraction ``f`` of the index, one period's wealth
multiple is ``1 - f R`` where ``R`` is the index simple return. The growth-optimal
fraction maximises expected log wealth,

    f* = argmax_f  E[ ln(1 - f R) ].

Three things make this the right instrument for the question at hand.

* It is defined on the **simple** return, so the constraint ``1 - f R > 0`` is exactly
  the solvency constraint: a −1× product is wiped out when ``R = 1``, and the Kelly
  objective is ``-inf`` there rather than merely unattractive. The criterion cannot be
  fooled by a distribution that assigns real probability to ruin.
* It requires no utility assumption beyond long-run growth, so comparing ``f*`` with
  the leverage a product actually offered is a statement about the product, not about
  a preference.
* It is easy to state honestly: the Gaussian approximation ``f* ≈ μ/σ²`` is reported
  alongside the exact numerical answer precisely to show how badly the approximation
  overstates the optimal size when the tail is fat.

Estimation uses the empirical distribution of returns (an equally weighted average of
``ln(1 - f R_i)``), which needs no parametric assumption, and optionally a set of
simulated returns from the fitted GARCH-EVT model. Confidence intervals come from a
stationary bootstrap, which preserves the volatility clustering that i.i.d.
resampling would destroy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize

from .bootstrap import stationary_bootstrap

__all__ = ["KellyResult", "kelly_fraction", "growth_rate_curve"]


@dataclass
class KellyResult:
    f_star: float
    growth_at_f_star: float
    growth_gaussian_approx: float
    f_gaussian_approx: float
    max_return: float
    ruin_bound: float
    ci_low: float = np.nan
    ci_high: float = np.nan
    n: int = 0
    note: str = ""

    def summary(self) -> str:
        s = (
            f"Kelly-optimal SHORT exposure  f* = {self.f_star:.3f}"
            f"   (growth {self.growth_at_f_star*252:+.2%} p.a.)\n"
            f"  Gaussian approximation mu/sigma^2 = {self.f_gaussian_approx:.3f}"
            f"  -> overstates by {self.f_gaussian_approx/max(self.f_star,1e-9):.1f}x\n"
            f"  largest one-day index return in sample = {self.max_return:+.1%};"
            f" a short position is wiped out at f = {self.ruin_bound:.3f}\n"
        )
        if np.isfinite(self.ci_low):
            s += f"  bootstrap 95% CI: [{self.ci_low:.3f}, {self.ci_high:.3f}]\n"
        if self.note:
            s += f"  {self.note}\n"
        return s


def _growth(f: float, r: np.ndarray) -> float:
    w = 1.0 - f * r
    if np.any(w <= 1e-12):
        return -np.inf
    return float(np.mean(np.log(w)))


def kelly_fraction(
    returns,
    f_max: float | None = None,
    bootstrap: int = 0,
    block_mean: float = 21.0,
    seed: int = 0,
    alpha: float = 0.05,
) -> KellyResult:
    """Growth-optimal short exposure to ``returns``.

    Parameters
    ----------
    returns
        Daily **simple** returns of the index being shorted.
    f_max
        Upper bound on the search. Defaults to just below the ruin bound
        ``1 / max(R)``: any larger short position is bankrupted by the worst day in
        the sample, so the objective is ``-inf`` there.
    bootstrap
        Number of stationary-bootstrap replications for a confidence interval.
        ``0`` skips it.
    block_mean
        Mean block length for the bootstrap, in days. The default of 21 keeps roughly
        a month of volatility clustering intact.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 100:
        raise ValueError(f"need at least 100 observations, got {len(r)}")

    rmax, rmin = float(r.max()), float(r.min())
    ruin = 1.0 / rmax if rmax > 0 else np.inf
    # The solvency constraint 1 - f R > 0 must hold for BOTH tails: a large short
    # position is bankrupted by the biggest up-move, a large *long* position by the
    # biggest down-move. Searching symmetrically around zero would put the optimiser
    # in a region where the objective is -inf at one end, which is exactly where a
    # bounded Brent search misbehaves.
    hi = f_max if f_max is not None else min(ruin * 0.999, 20.0)
    lo = -min(abs(1.0 / rmin) * 0.999, 20.0) if rmin < 0 else -20.0
    if f_max is not None:
        lo = max(lo, -abs(f_max))

    res = optimize.minimize_scalar(
        lambda f: -_growth(f, r), bounds=(lo, hi), method="bounded",
        options={"xatol": 1e-8},
    )
    f_star = float(res.x)

    mu, var = float(r.mean()), float(r.var(ddof=1))
    f_gauss = -mu / var if var > 0 else np.nan   # short position: f* ~ -mu/sigma^2

    out = KellyResult(
        f_star=f_star,
        growth_at_f_star=_growth(f_star, r),
        growth_gaussian_approx=_growth(f_gauss, r) if np.isfinite(f_gauss) else np.nan,
        f_gaussian_approx=f_gauss,
        max_return=rmax,
        ruin_bound=ruin,
        n=len(r),
    )
    if abs(f_star - hi) < 1e-6:
        out.note = "f* is at the search boundary; the ruin constraint is binding"

    if bootstrap > 0:
        rng = np.random.default_rng(seed)
        draws = np.empty(bootstrap)
        for b in range(bootstrap):
            rb = stationary_bootstrap(r, block_mean=block_mean, rng=rng)
            m, mn = float(rb.max()), float(rb.min())
            hb = min((1.0 / m) * 0.999 if m > 0 else 20.0, 20.0)
            lb = -min(abs(1.0 / mn) * 0.999, 20.0) if mn < 0 else -20.0
            rr = optimize.minimize_scalar(
                lambda f: -_growth(f, rb), bounds=(lb, hb), method="bounded",
                options={"xatol": 1e-6},
            )
            draws[b] = rr.x
        out.ci_low = float(np.quantile(draws, alpha / 2))
        out.ci_high = float(np.quantile(draws, 1 - alpha / 2))
    return out


def growth_rate_curve(returns, f_grid=None) -> "tuple[np.ndarray, np.ndarray]":
    """Expected log growth as a function of short exposure.

    Plotted in the report with the −1× and −0.5× product designs marked, which is the
    clearest way to show that the offered leverage sat past the peak.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if f_grid is None:
        rmax = float(r.max())
        hi = min(1.0 / rmax if rmax > 0 else 2.0, 5.0)
        f_grid = np.linspace(-0.2 * hi, hi, 400)
    g = np.array([_growth(float(f), r) for f in f_grid])
    return np.asarray(f_grid, dtype=float), g
