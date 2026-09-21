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

**What the log model forecasts.** In the log specification the target is
``log`` of the *arithmetic* average variance over ``t+1 .. t+h`` - not the average
of the daily logs. The two differ by far more than a rounding error: the exponential
of an average of logs is a *geometric* mean, and for a noisy one-day range proxy
(daily log-variance sd about 1.25 on SPY) the arithmetic mean over 21 days is on
average 1.47 times the geometric one. A variance risk premium needs the expected
arithmetic average - integrated variance is a sum - so a geometric-mean target would
understate expected variance by about a third and overstate the premium by the same
amount. The predictors, being information rather than the quantity forecast, are
averages of daily log variance (robust to a single noisy day); only the target is on
the arithmetic scale.
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
    dropna_target: bool = True,
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
    dropna_target
        Drop rows whose target is not yet observable (the last ``horizon`` dates).
        Set to False to keep them - with ``y`` missing - so a real-time forecast can
        still be made on those dates from their predictors.

    Returns
    -------
    DataFrame with columns ``y, rv_d, rv_w, rv_m`` indexed by the date ``t`` at which
    the forecast would be made. In the log specification ``y`` is
    ``log(mean(rv[t+1 .. t+h]))``; see the module docstring for why it is not
    ``mean(log rv)``. Rows with a missing predictor are always dropped.
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

    # Forward ARITHMETIC average of variance over t+1 .. t+h, aligned to date t, and
    # logged afterwards in the log specification. (Averaging the logs instead would
    # target the geometric mean; see the module docstring.)
    level = rv.clip(lower=floor) if (log and floor is not None) else rv
    fwd = level.rolling(horizon).mean().shift(-horizon)
    if log:
        fwd = np.log(fwd)

    out = pd.DataFrame({"y": fwd, "rv_d": rv_d, "rv_w": rv_w, "rv_m": rv_m})
    out = out.dropna() if dropna_target else out.dropna(subset=["rv_d", "rv_w", "rv_m"])
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
    resid_var: "pd.Series | None" = None   # training residual variance, per refit

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
    retransform: str = "normal",
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
    (variance, not log) scale, including a retransformation correction when
    ``log=True``: ``retransform="normal"`` multiplies by ``exp(sigma^2 / 2)``, exact
    if the log residuals are normal; ``"smearing"`` multiplies by the mean of the
    exponentiated training residuals (Duan 1983), which needs no distributional
    assumption. Both use training residuals only. Forecasts run to the last date with predictors, including the
    final ``horizon`` dates whose outcome is not yet known (``realised`` is missing
    there), because a real-time forecast needs only today's predictors.
    """
    feats = har_features(rv, horizon=horizon, lags=lags, log=log, dropna_target=False)
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
    s2s: dict[pd.Timestamp, float] = {}
    beta = None
    sigma2 = 0.0
    smear = 1.0
    last_fit = -10 ** 9

    for i in range(first_idx, len(dates)):
        t = dates[i]
        # usable training rows: dependent variable already realised by t
        cutoff = dates.searchsorted(t) - horizon
        if cutoff < 50:
            continue
        if (i - last_fit) >= refit_every or beta is None:
            Xtr, ytr = X[:cutoff], y[:cutoff]
            # Rows before the cutoff have realised targets by construction; a missing
            # one can only come from a gap inside the variance series itself.
            ok = np.isfinite(ytr)
            Xtr, ytr = Xtr[ok], ytr[ok]
            Xd = np.column_stack([np.ones(len(Xtr)), Xtr])
            beta, *_ = np.linalg.lstsq(Xd, ytr, rcond=None)
            resid = ytr - Xd @ beta
            sigma2 = float(resid @ resid) / max(len(ytr) - Xd.shape[1], 1)
            smear = float(np.mean(np.exp(resid)))
            coefs[t] = beta.copy()
            s2s[t] = sigma2
            last_fit = i
        xt = np.concatenate([[1.0], X[i]])
        mu = float(xt @ beta)
        if not log:
            preds[t] = mu
        elif retransform == "normal":
            preds[t] = float(np.exp(mu + 0.5 * sigma2))
        elif retransform == "smearing":
            preds[t] = float(np.exp(mu) * smear)
        else:
            raise ValueError(f"unknown retransform {retransform!r}")

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
        resid_var=pd.Series(s2s, name="resid_var").sort_index(),
    )
