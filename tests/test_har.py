"""Tests for the HAR realised-variance model, with an explicit look-ahead test.

The leakage test is the important one. It perturbs the realised-variance series
*after* a cut-off date and asserts that none of the forecasts made on or before that
date change. Any implementation that fits on the full sample, or that uses training
rows whose dependent variable had not yet been realised, fails it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.econometrics.har import fit_har, har_features, har_oos_forecast
from svcarry.econometrics.realized import (
    daily_variance_proxy,
    parkinson,
    rogers_satchell,
    yang_zhang,
)


def _rv_series(n=3000, seed=0):
    """A persistent, positive, HAR-like variance series."""
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    x[:22] = np.log(1e-4)
    for t in range(22, n):
        d, w, m = x[t - 1], x[t - 5:t].mean(), x[t - 22:t].mean()
        x[t] = -0.35 + 0.35 * d + 0.35 * w + 0.26 * m + 0.25 * rng.normal()
    idx = pd.bdate_range("2005-01-03", periods=n)
    return pd.Series(np.exp(x), index=idx, name="rv")


def test_feature_target_alignment_is_forward_looking():
    rv = _rv_series(400, seed=1)
    f = har_features(rv, horizon=5, log=False)
    t = f.index[100]
    pos = rv.index.get_loc(t)
    want = rv.iloc[pos + 1: pos + 6].mean()
    assert f.loc[t, "y"] == pytest.approx(want, rel=1e-12)
    # and the predictors use only information up to and including t
    assert f.loc[t, "rv_d"] == pytest.approx(rv.iloc[pos], rel=1e-12)
    assert f.loc[t, "rv_w"] == pytest.approx(rv.iloc[pos - 4: pos + 1].mean(), rel=1e-12)


def test_har_recovers_simulated_coefficients():
    rv = _rv_series(6000, seed=2)
    f = har_features(rv, horizon=1, log=True)
    res = fit_har(f)
    # sum of slopes should be close to the simulated persistence (0.96)
    assert sum(res.params[1:]) == pytest.approx(0.96, abs=0.06), res.params
    assert res.rsquared > 0.5


def test_overlapping_horizon_uses_long_hac_bandwidth():
    rv = _rv_series(2000, seed=3)
    f = har_features(rv, horizon=21, log=True)
    res = fit_har(f)
    assert res.lags >= 20
    naive = fit_har(f, cov_type="homoskedastic")
    # ignoring the overlap materially understates the standard errors
    assert (res.bse > naive.bse).sum() >= 3


def test_no_lookahead_in_oos_forecasts():
    rv = _rv_series(2500, seed=4)
    cut = rv.index[1800]

    base = har_oos_forecast(rv, horizon=21, log=True, train_min=900, refit_every=21)

    tampered = rv.copy()
    rng = np.random.default_rng(0)
    mask = tampered.index > cut
    tampered[mask] = tampered[mask] * rng.uniform(5.0, 50.0, size=int(mask.sum()))
    alt = har_oos_forecast(tampered, horizon=21, log=True, train_min=900, refit_every=21)

    common = base.forecast.index.intersection(alt.forecast.index)
    common = common[common <= cut]
    assert len(common) > 200
    assert np.allclose(
        base.forecast.reindex(common).to_numpy(),
        alt.forecast.reindex(common).to_numpy(),
        rtol=0, atol=0,
    ), "forecasts before the cut-off changed when only future data was altered"


def test_oos_forecast_has_predictive_power():
    rv = _rv_series(4000, seed=5)
    fc = har_oos_forecast(rv, horizon=21, log=True, train_min=1200, refit_every=21)
    s = fc.summary()
    assert s["n"] > 1500
    assert s["oos_r2"] > 0.2, s
    # Mincer-Zarnowitz slope should be near 1 for an unbiased forecast
    assert 0.6 < s["mz_beta"] < 1.4, s


def _noisy_proxy(n=4000, seed=7):
    """A persistent latent variance observed through a one-day proxy as noisy as a
    range estimator: log-proxy noise sd 1.0 around the latent log variance."""
    rng = np.random.default_rng(seed)
    lat = _rv_series(n, seed=seed).to_numpy()
    noise = np.exp(rng.normal(-0.5, 1.0, n))        # E[noise] = 1: unbiased proxy
    idx = pd.bdate_range("2005-01-03", periods=n)
    return pd.Series(lat * noise, index=idx, name="rv")


def test_log_target_is_log_of_the_arithmetic_average():
    """The log model must forecast the average VARIANCE, not the average log."""
    rv = _noisy_proxy(600)
    f = har_features(rv, horizon=21, log=True)
    t = f.index[200]
    pos = rv.index.get_loc(t)
    window = rv.iloc[pos + 1: pos + 22]
    assert f.loc[t, "y"] == pytest.approx(np.log(window.mean()), rel=1e-12)
    assert f.loc[t, "y"] > np.log(window).mean() + 0.1, \
        "on a noisy proxy the log of the mean is well above the mean of the logs"


def test_log_forecast_is_unbiased_for_the_level_of_average_variance():
    """Retransformed forecasts should match realised average variance on average.
    Targeting the geometric mean instead would fall short by roughly exp(sd^2/2)."""
    rv = _noisy_proxy(5000, seed=8)
    fc = har_oos_forecast(rv, horizon=21, log=True, train_min=1200, refit_every=21)
    e = fc.errors()
    ratio = fc.forecast.reindex(e.index).mean() / fc.realised.reindex(e.index).mean()
    assert 0.9 < ratio < 1.1, ratio
    gm = np.exp(np.log(rv).rolling(21).mean().shift(-21)).reindex(e.index)
    assert gm.mean() < 0.8 * fc.realised.reindex(e.index).mean()


def test_forecasts_run_to_the_end_of_the_sample():
    """A real-time forecast needs only today's predictors; the last h dates must get
    a forecast even though their outcome is not yet known."""
    rv = _rv_series(1500, seed=9)
    fc = har_oos_forecast(rv, horizon=21, log=True, train_min=900, refit_every=21)
    assert fc.forecast.index[-1] == rv.index[-1]
    assert fc.realised.iloc[-21:].isna().all()
    assert fc.realised.iloc[:-21].notna().all()


def test_no_lookahead_at_the_end_of_the_sample():
    """Appending future days must not change any forecast already made."""
    rv = _rv_series(2000, seed=10)
    short = har_oos_forecast(rv.iloc[:1700], horizon=21, log=True, train_min=900,
                             refit_every=21)
    full = har_oos_forecast(rv, horizon=21, log=True, train_min=900, refit_every=21)
    common = short.forecast.index
    assert np.array_equal(short.forecast.to_numpy(),
                          full.forecast.reindex(common).to_numpy())


def test_smearing_and_normal_retransforms_agree_under_normal_residuals():
    """On a series whose log residuals are normal the two corrections coincide;
    they may differ only when the residuals are not normal."""
    rv = _rv_series(3000, seed=11)            # Gaussian shocks in logs
    a = har_oos_forecast(rv, horizon=1, log=True, train_min=900, retransform="normal")
    b = har_oos_forecast(rv, horizon=1, log=True, train_min=900, retransform="smearing")
    assert np.allclose(a.forecast, b.forecast, rtol=0.01)
    with pytest.raises(ValueError):
        har_oos_forecast(rv, horizon=1, log=True, train_min=900, retransform="x")


def test_coefficients_are_refit_on_schedule():
    rv = _rv_series(2000, seed=6)
    fc = har_oos_forecast(rv, horizon=21, log=True, train_min=900, refit_every=50)
    assert len(fc.coefficients) >= 5
    assert list(fc.coefficients.columns) == ["const", "rv_d", "rv_w", "rv_m"]


# ----------------------------------------------------------------- realised vol
def _ohlc(n=1000, seed=0):
    rng = np.random.default_rng(seed)
    sigma = 0.012
    close = 100 * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    op = close * np.exp(rng.normal(0, sigma / 3, n))
    hi = np.maximum(op, close) * np.exp(np.abs(rng.normal(0, sigma / 2, n)))
    lo = np.minimum(op, close) * np.exp(-np.abs(rng.normal(0, sigma / 2, n)))
    return pd.DataFrame(
        {"open": op, "high": hi, "low": lo, "close": close},
        index=pd.bdate_range("2010-01-04", periods=n),
    )


def test_range_estimators_are_positive_and_ordered_sensibly():
    df = _ohlc(2000, seed=1)
    pk = parkinson(df).dropna()
    rs = rogers_satchell(df).dropna()
    assert (pk > 0).all()
    assert rs.mean() > 0
    # Parkinson is much less noisy than squared close-to-close
    cc = (np.log(df["close"]).diff() ** 2).dropna()
    assert pk.std() < cc.std()


def test_yang_zhang_runs_and_is_comparable_in_level():
    df = _ohlc(1500, seed=2)
    yz = yang_zhang(df, window=21).dropna()
    proxy = daily_variance_proxy(df, "rs_overnight").dropna()
    assert (yz > 0).all()
    assert yz.mean() == pytest.approx(proxy.mean(), rel=0.6)


def test_ohlc_validation_catches_impossible_bars():
    df = _ohlc(50)
    df.iloc[10, df.columns.get_loc("high")] = df["low"].iloc[10] * 0.5
    with pytest.raises(ValueError):
        parkinson(df)
