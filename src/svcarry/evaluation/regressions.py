"""Attribution regressions: is the return alpha, or payment for taking crash risk?

A strategy that sells volatility and then reports a positive average return has not
demonstrated skill. Selling volatility is itself a known risk exposure that has
historically been compensated, so the relevant question is whether the strategy earns
anything *beyond* that exposure. The test is a regression on factors that already
represent the compensated risks:

    r_strategy,t = alpha + b1 r_PUT,t + b2 r_SPX,t + b3 r_VXX,t + e_t

* **Cboe PutWrite (PUT)** is a fully collateralised short-put programme — the
  canonical "sell volatility, get paid, occasionally lose a lot" return stream. If
  the strategy is just a repackaged variance risk premium, PUT absorbs it.
* **S&P 500** captures the equity beta that any short-volatility position carries.
* **VXX** is the traded long-volatility leg: a significant negative loading says the
  strategy is short the same thing the products were.

Two refinements are applied because this is a negatively skewed strategy.

*Downside betas.* A single beta averages the relationship over calm and crisis. The
regression is also run with the market return split into positive and negative parts,
because a position whose beta rises exactly when the market falls is not described by
its average beta.

*Honest inference.* Newey-West standard errors throughout; the alpha is reported with
its t-statistic and the sample size, never as a bare number. Where the alpha is not
distinguishable from zero, that is reported as the finding, not buried.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..econometrics.hac import RegressionResult, newey_west_lags, ols

__all__ = ["alpha_regression", "downside_beta_regression", "regression_table"]


def _align(y: pd.Series, factors: "dict[str, pd.Series]") -> pd.DataFrame:
    df = pd.DataFrame({"y": pd.Series(y).astype(float)})
    for k, v in factors.items():
        df[k] = pd.Series(v).astype(float)
    return df.dropna()


def alpha_regression(
    strategy_returns: pd.Series,
    factors: "dict[str, pd.Series]",
    rf: pd.Series | float = 0.0,
    periods: int = 252,
    lags: int | None = None,
) -> dict:
    """Regress excess strategy returns on excess factor returns.

    ``rf`` is subtracted from the strategy and from any factor that is a total
    return. Factor series are passed already in the form the caller wants regressed;
    the only transformation applied here is the risk-free subtraction on ``y``.

    Returns a dict with the fitted :class:`RegressionResult`, the annualised alpha
    and its t-statistic, so that the calling code does not have to remember the
    annualisation factor.
    """
    y = pd.Series(strategy_returns).astype(float)
    rf_s = (pd.Series(rf).reindex(y.index).fillna(0.0) if not np.isscalar(rf)
            else pd.Series(float(rf), index=y.index))
    df = _align(y - rf_s, factors)
    if len(df) < 60:
        raise ValueError(f"only {len(df)} aligned observations; too few to regress")

    names = [c for c in df.columns if c != "y"]
    n = len(df)
    lags = lags if lags is not None else newey_west_lags(n)
    res = ols(df["y"].to_numpy(), df[names].to_numpy(), names=names,
              add_const=True, cov_type="HAC", lags=lags)

    return {
        "result": res,
        "n": n,
        "start": df.index.min(),
        "end": df.index.max(),
        "alpha_daily": float(res.params[0]),
        "alpha_annual": float(res.params[0]) * periods,
        "alpha_t": float(res.tvalues[0]),
        "alpha_p": float(res.pvalues[0]),
        "betas": {nm: float(res.params[i + 1]) for i, nm in enumerate(names)},
        "beta_t": {nm: float(res.tvalues[i + 1]) for i, nm in enumerate(names)},
        "rsquared": float(res.rsquared),
        "lags": lags,
    }


def downside_beta_regression(
    strategy_returns: pd.Series,
    market_returns: pd.Series,
    rf: pd.Series | float = 0.0,
    periods: int = 252,
) -> dict:
    """Split the market beta into up-market and down-market components.

    ``r_s = alpha + b_up * max(r_m, 0) + b_dn * min(r_m, 0) + e``

    For a short-volatility strategy the expectation is ``|b_dn| >> b_up``: it
    participates little in rallies and a great deal in selloffs. A single-beta
    regression that reports a small average beta while ``b_dn`` is large is
    describing a risk the average does not capture.
    """
    y = pd.Series(strategy_returns).astype(float)
    m = pd.Series(market_returns).astype(float)
    rf_s = (pd.Series(rf).reindex(y.index).fillna(0.0) if not np.isscalar(rf)
            else pd.Series(float(rf), index=y.index))
    df = pd.DataFrame({"y": y - rf_s, "m": m}).dropna()
    up = df["m"].clip(lower=0.0)
    dn = df["m"].clip(upper=0.0)
    res = ols(df["y"].to_numpy(), np.column_stack([up, dn]),
              names=["mkt_up", "mkt_down"], add_const=True, cov_type="HAC",
              lags=newey_west_lags(len(df)))
    b_up, b_dn = float(res.params[1]), float(res.params[2])
    diff_stat, diff_p = res.wald(np.array([[0.0, 1.0, -1.0]]), 0.0)
    return {
        "result": res,
        "n": int(len(df)),
        "alpha_annual": float(res.params[0]) * periods,
        "alpha_t": float(res.tvalues[0]),
        "beta_up": b_up,
        "beta_down": b_dn,
        "asymmetry": b_dn - b_up,
        "asymmetry_p": float(diff_p),
        "rsquared": float(res.rsquared),
    }


def regression_table(results: "dict[str, dict]") -> pd.DataFrame:
    """Collect several :func:`alpha_regression` outputs into one table."""
    rows = {}
    for nm, r in results.items():
        row = {
            "n": r["n"],
            "alpha (ann.)": r["alpha_annual"],
            "t(alpha)": r["alpha_t"],
            "R2": r["rsquared"],
        }
        for f, b in r["betas"].items():
            row[f"beta_{f}"] = b
            row[f"t_{f}"] = r["beta_t"][f]
        rows[nm] = row
    return pd.DataFrame(rows).T
