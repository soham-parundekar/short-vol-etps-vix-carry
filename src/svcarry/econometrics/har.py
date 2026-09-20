"""Heterogeneous Autoregressive (HAR) model of realised variance.

Corsi (2009). The model regresses future average realised variance on realised
variance measured over three horizons - daily, weekly, monthly - which is a
parsimonious way of reproducing the long-memory behaviour of volatility without
fitting a fractionally integrated process.

    RV_{t+1:t+h} = b0 + bd RV_{t} + bw RV_{t-4:t} + bm RV_{t-21:t} + e_{t+h}

Two implementation details matter for this project and are handled explicitly.

**Overlapping horizons.** With h > 1 the dependent variable overlaps across
consecutive observations, so residuals are autocorrelated by construction. All
inference uses Newey-West standard errors with a bandwidth of at least ``h - 1``;
ignoring this inflates t-statistics by a factor of roughly sqrt(h).

**Real-time forecasting.** A forecast formed on date ``t`` may only use
(a) predictors observable at the close of ``t`` and (b) coefficients estimable from
observations whose dependent variable had *already been realised* by ``t``. The
second condition is the one that is usually violated: the most recent usable
training row is dated ``t - h``, not ``t``. :func:`har_oos_forecast` enforces this
and ``tests/test_har.py`` includes a leakage test that fails if it is relaxed.

A log specification is also provided. Volatility is strongly right-skewed, so the
log model is better behaved; forecasts are retransformed with the standard
lognormal (Jensen) correction ``exp(mu + sigma^2 / 2)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .hac import RegressionResult, newey_west_lags, ols

__all__ = ["har_features", "fit_har", "har_oos_forecast", "HARForecast"]


def har_features(
    rv: pd.Series,
    horizon: int = 21,
    lags: tuple[int, int, int] = (1, 5, 22),
    log: bool = False,
    floor: float | None = 1e-10,
) -> pd.DataFrame:
    """Build the HAR design matrix and target.

    Parameters
    ----------
    rv
        Daily variance series (not annualised, not square-rooted).
    horizon
        ``h``. The target is the *average* daily variance over ``t+1 .. t+h``.
    lags
        Averaging windows for the daily, weekly and monthly components. All windows
        end at ``t`` inclusive, so every predictor is observable at the close of
        ``t``.
    log
        Work in logs. Requires strictly positive values; see ``floor``.
    floor
        Non-positive variances (possible with range estimators on degenerate bars)
        are floored at this value before taking logs. Applied *only* in the log
        specification, and the number of affected observations is attached to the
        returned frame's ``.attrs``.

    Returns
    -------
    DataFrame with columns ``y, rv_d, rv_w, rv_m`` indexed by the date ``t`` at which
    the forecast would be made. Rows with any missing value are dropped.
    """
    rv = pd.Series(rv).astype(float).sort_index()
    d, w, m = lags
    x = rv.copy()
    n_floored = 0
    if log:
        n_floored = int((x <= 0).sum())
        if floor is not None:
            x = x.clip(lower=floor)
        x = np.log(x)

    rv_d = x.rolling(d).mean()
    rv_w = x.rolling(w).mean()
    rv_m = x.rolling(m).mean()

    # forward average over t+1 .. t+h, aligned to date t
    fwd = x.rolling(horizon).mean().shift(-horizon)

    out = pd.DataFrame(
        {"y": fwd, "rv_d": rv_d, "rv_w": rv_w, "rv_m": rv_m}
    ).dropna()
    out.attrs["log"] = log
    out.attrs["horizon"] = horizon
    out.attrs["n_floored"] = n_floored
    return out


def fit_har(
    features: pd.DataFrame, cov_type: str = "HAC", lags: int | None = None
) -> RegressionResult:
    """Fit the HAR regression on a prepared feature frame."""
    h = int(features.attrs.get("horizon", 21))
    if cov_type == "HAC" and lags is None:
        lags = max(h - 1, newey_west_lags(len(features)))
    res = ols(
        features["y"].to_numpy(),
        features[["rv_d", "rv_w", "rv_m"]].to_numpy(),
        names=["rv_d", "rv_w", "rv_m"],
        add_const=True,
        cov_type=cov_type,
        lags=lags,
    )
    res._extras["horizon"] = h
    res._extras["log"] = bool(features.attrs.get("log", False))
    return res


@dataclass
class HARForecast:
    """Out-of-sample HAR forecasts and the diagnostics needed to judge them."""

    forecast: pd.Series           # E_t[ average daily variance over t+1..t+h ]
    realised: pd.Series           # the eventual realised value (NaN at the sample end)
    coefficients: pd.DataFrame    # coefficient path, indexed by refit date
    horizon: int
    log: bool
    train_min: int
    refit_every: int

    def errors(self) -> pd.Series:
        return (self.realised - self.forecast).dropna()

    def summary(self) -> dict:
        e = self.errors()
        y = self.realised.reindex(e.index)
        f = self.forecast.reindex(e.index)
        ss_res = float((e ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        # Mincer-Zarnowitz: y = a + b f + u, with HAC errors for the overlap
        mz = ols(y.to_numpy(), f.to_numpy(), names=["forecast"], cov_type="HAC",
                 lags=max(self.horizon - 1, 1))
        return {
            "n": int(len(e)),
            "rmse": float(np.sqrt((e ** 2).mean())),
            "mae": float(e.abs().mean()),
            "oos_r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan,
            "mz_alpha": float(mz.params[0]),
            "mz_beta": float(mz.params[1]),
            "mz_beta_t_vs_1": float((mz.params[1] - 1.0) / mz.bse[1]),
            "mz_r2": float(mz.rsquared),
        }


def har_oos_forecast(
    rv: pd.Series,
    horizon: int = 21,
    lags: tuple[int, int, int] = (1, 5, 22),
    log: bool = True,
    train_min: int = 1000,
    refit_every: int = 21,
    start: str | pd.Timestamp | None = None,
) -> HARForecast:
    """Strictly real-time expanding-window HAR forecasts.

    On each forecast date ``t``:

    1. The training sample is every feature row dated ``s`` with
       ``s <= t - horizon``, so that ``y_s`` (which spans ``s+1 .. s+h``) was fully
       observed on or before ``t``. **This is the step that prevents look-ahead.**
    2. Coefficients are re-estimated every ``refit_every`` trading days and reused in
       between, mimicking a research process that does not refit daily.
    3. The forecast uses predictors dated ``t``.

    Returns a :class:`HARForecast` with the forecast series on the *original*
    (variance, not log) scale, including the lognormal retransformation correction
    when ``log=True``.
    """
    feats = har_features(rv, horizon=horizon, lags=lags, log=log)
    if start is not None:
        first_idx = feats.index.searchsorted(pd.Timestamp(start))
    else:
        first_idx = train_min
    if first_idx < 50:
        raise ValueError("not enough burn-in for an out-of-sample exercise")

    dates = feats.index
    X = feats[["rv_d", "rv_w", "rv_m"]].to_numpy()
    y = feats["y"].to_numpy()

    preds: dict[pd.Timestamp, float] = {}
    coefs: dict[pd.Timestamp, np.ndarray] = {}
    beta = None
    sigma2 = 0.0
    last_fit = -10 ** 9

    for i in range(first_idx, len(dates)):
        t = dates[i]
        # usable training rows: dependent variable already realised by t
        cutoff = dates.searchsorted(t) - horizon
        if cutoff < 50:
            continue
        if (i - last_fit) >= refit_every or beta is None:
            Xtr, ytr = X[:cutoff], y[:cutoff]
            Xd = np.column_stack([np.ones(len(Xtr)), Xtr])
            beta, *_ = np.linalg.lstsq(Xd, ytr, rcond=None)
            resid = ytr - Xd @ beta
            sigma2 = float(resid @ resid) / max(len(ytr) - Xd.shape[1], 1)
            coefs[t] = beta.copy()
            last_fit = i
        xt = np.concatenate([[1.0], X[i]])
        mu = float(xt @ beta)
        preds[t] = float(np.exp(mu + 0.5 * sigma2)) if log else mu

    fc = pd.Series(preds, name="har_forecast").sort_index()
    real = feats["y"].reindex(fc.index)
    if log:
        real = np.exp(real)
    return HARForecast(
        forecast=fc,
        realised=real.rename("realised"),
        coefficients=pd.DataFrame.from_dict(
            coefs, orient="index", columns=["const", "rv_d", "rv_w", "rv_m"]
        ),
        horizon=horizon,
        log=log,
        train_min=train_min,
        refit_every=refit_every,
    )
