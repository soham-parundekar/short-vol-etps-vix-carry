"""Block bootstrap methods for serially dependent financial data.

An i.i.d. bootstrap is the wrong tool for daily volatility data: resampling single
days destroys the volatility clustering, which means it systematically understates
the uncertainty around any statistic that depends on persistence — Sharpe ratios,
drawdowns, Kelly fractions, tail probabilities. The stationary bootstrap of Politis
and Romano (1994) resamples *blocks* of geometrically distributed length, which
preserves short-range dependence while keeping the resampled series stationary.

Also provided is the fixed-length circular block bootstrap, used as a robustness
check on the choice of scheme.
"""

from __future__ import annotations

import numpy as np

__all__ = ["stationary_bootstrap", "circular_block_bootstrap", "bootstrap_statistic"]


def stationary_bootstrap(
    x: np.ndarray, block_mean: float = 21.0, size: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """One stationary-bootstrap resample of ``x``.

    Blocks have geometric length with mean ``block_mean``; the series is wrapped
    circularly so every observation has equal probability of appearing.
    """
    rng = rng or np.random.default_rng()
    x = np.asarray(x)
    n = len(x)
    size = size or n
    p = 1.0 / float(block_mean)

    out = np.empty(size, dtype=x.dtype)
    i = int(rng.integers(n))
    for t in range(size):
        out[t] = x[i]
        if rng.random() < p:
            i = int(rng.integers(n))
        else:
            i = (i + 1) % n
    return out


def circular_block_bootstrap(
    x: np.ndarray, block_len: int = 21, size: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Fixed-length circular block bootstrap."""
    rng = rng or np.random.default_rng()
    x = np.asarray(x)
    n = len(x)
    size = size or n
    n_blocks = int(np.ceil(size / block_len))
    starts = rng.integers(0, n, size=n_blocks)
    idx = np.concatenate([(s + np.arange(block_len)) % n for s in starts])[:size]
    return x[idx]


def bootstrap_statistic(
    x: np.ndarray,
    statistic,
    n_boot: int = 1000,
    block_mean: float = 21.0,
    seed: int = 0,
    alpha: float = 0.05,
    method: str = "stationary",
) -> dict:
    """Bootstrap distribution of ``statistic(x)``.

    Returns the point estimate, the bootstrap standard error, a percentile interval
    and the full draw vector (so the report can show the distribution rather than
    only its summary).
    """
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    point = float(statistic(x))
    draws = np.empty(n_boot)
    for b in range(n_boot):
        xb = (
            stationary_bootstrap(x, block_mean=block_mean, rng=rng)
            if method == "stationary"
            else circular_block_bootstrap(x, block_len=int(block_mean), rng=rng)
        )
        try:
            draws[b] = float(statistic(xb))
        except Exception:
            draws[b] = np.nan
    ok = np.isfinite(draws)
    return {
        "point": point,
        "se": float(np.nanstd(draws, ddof=1)),
        "ci_low": float(np.nanquantile(draws, alpha / 2)),
        "ci_high": float(np.nanquantile(draws, 1 - alpha / 2)),
        "n_valid": int(ok.sum()),
        "draws": draws,
    }
