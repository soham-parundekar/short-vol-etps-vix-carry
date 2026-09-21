"""Out-of-sample evaluation of variance forecasts.

Every statistic here compares a forecast made at ``t`` with the value realised over
``t+1 .. t+h``. With ``h > 1`` consecutive forecast errors overlap by ``h - 1`` days,
so every standard error uses Newey-West with a bandwidth of at least ``h - 1``.

Two loss functions, because they answer different questions:

``MSE``    in variance units. Dominated by the few crisis months, when variance is
           largest; it tells you who was least wrong in 2008 and March 2020.
``QLIKE``  ``y/f - log(y/f) - 1`` (Patton 2011). Scale-free, so a calm month counts
           as much as a crisis month. Like MSE it belongs to Patton's family of loss
           functions whose ranking of forecasts is not distorted by noise in the
           realised-variance proxy. Requires a positive forecast.

``oos_r2`` is reported against two baselines: the mean of the realised series over
the evaluation sample (the best constant, chosen with hindsight, so a conservative
bar) and the expanding historical mean available in real time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .hac import ols

__all__ = ["qlike", "forecast_metrics", "diebold_mariano"]


def qlike(realised, forecast) -> np.ndarray:
    """Patton's QLIKE loss, normalised to zero at a perfect forecast."""
    y = np.asarray(realised, dtype=float)
    f = np.asarray(forecast, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = y / f
        out = r - np.log(r) - 1.0
    out[~(f > 0)] = np.nan
    return out


def forecast_metrics(forecast: pd.Series, realised: pd.Series, horizon: int,
                     baseline: "pd.Series | None" = None,
                     periods_per_year: int = 252) -> dict:
    """Accuracy and calibration of one forecast series against the realised one.

    ``baseline`` is a real-time benchmark forecast (e.g. the expanding mean) for the
    second out-of-sample R^2. Everything is evaluated on the dates where the forecast,
    the outcome and (if given) the baseline all exist.
    """
    df = pd.DataFrame({"f": forecast, "y": realised})
    if baseline is not None:
        df["b"] = baseline
    df = df.dropna()
    y, f = df["y"].to_numpy(), df["f"].to_numpy()
    e = y - f
    ss_res = float(e @ e)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    lags = max(horizon - 1, 1)
    mz = ols(y, f, names=["forecast"], cov_type="HAC", lags=lags)
    ql = qlike(y, f)
    out = {
        "n": int(len(df)),
        "first": str(df.index.min().date()),
        "last": str(df.index.max().date()),
        "rmse_ann_var": float(np.sqrt(np.mean(e ** 2)) * periods_per_year),
        "mae_ann_var": float(np.mean(np.abs(e)) * periods_per_year),
        "bias_ann_var": float(np.mean(f - y) * periods_per_year),
        "qlike": float(np.nanmean(ql)),
        "n_nonpositive_forecasts": int((f <= 0).sum()),
        "oos_r2_vs_eval_mean": 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan,
        "mz_alpha_ann_var": float(mz.params[0] * periods_per_year),
        "mz_beta": float(mz.params[1]),
        "mz_beta_se": float(mz.bse[1]),
        "mz_t_beta_eq_1": float((mz.params[1] - 1.0) / mz.bse[1]),
        "mz_r2": float(mz.rsquared),
        "hac_lags": lags,
    }
    if baseline is not None:
        eb = y - df["b"].to_numpy()
        out["oos_r2_vs_expanding_mean"] = 1.0 - ss_res / float(eb @ eb)
    return out


def diebold_mariano(loss_a: pd.Series, loss_b: pd.Series, horizon: int) -> dict:
    """Test of equal expected loss, ``d_t = L_a - L_b``, HAC bandwidth ``h - 1``.

    A negative mean differential favours ``a``. The t-statistic is a regression of
    ``d_t`` on a constant with Newey-West errors, which is the Diebold-Mariano
    statistic with a Bartlett kernel.
    """
    d = (pd.Series(loss_a) - pd.Series(loss_b)).dropna()
    fit = ols(d.to_numpy(), np.empty((len(d), 0)), names=[], add_const=True, cov_type="HAC",
              lags=max(horizon - 1, 1))
    return {"n": int(len(d)), "mean_diff": float(fit.params[0]),
            "t_stat": float(fit.tvalues[0]), "p_value": float(fit.pvalues[0])}
