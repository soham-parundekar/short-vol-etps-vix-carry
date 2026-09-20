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
