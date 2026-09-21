"""Forecast evaluation: QLIKE, Mincer-Zarnowitz and Diebold-Mariano (Phase 10)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.econometrics.forecast_eval import diebold_mariano, forecast_metrics, qlike


def test_qlike_is_zero_at_a_perfect_forecast_and_penalises_under_forecasts_more():
    assert qlike([2.0], [2.0])[0] == 0.0
    under, over = qlike([2.0], [1.0])[0], qlike([2.0], [4.0])[0]
    assert under > over > 0, "QLIKE is asymmetric: forecasting too low costs more"
    assert np.isnan(qlike([1.0], [0.0])[0]) and np.isnan(qlike([1.0], [-1.0])[0])


def _pair(n=3000, seed=0, slope=1.0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-04", periods=n)
    f = pd.Series(np.exp(rng.normal(-9, 0.5, n)), index=idx)
    y = slope * f * np.exp(rng.normal(-0.02, 0.2, n))
    return f, y


def test_mincer_zarnowitz_recovers_the_slope_and_r2_needs_skill():
    f, y = _pair()
    m = forecast_metrics(f, y, horizon=1)
    assert m["mz_beta"] == pytest.approx(1.0, abs=0.05)
    assert m["oos_r2_vs_eval_mean"] > 0.5
    noise = pd.Series(np.random.default_rng(9).permutation(f.to_numpy()), index=f.index)
    assert forecast_metrics(noise, y, horizon=1)["oos_r2_vs_eval_mean"] < 0


def test_diebold_mariano_favours_the_better_forecast():
    f, y = _pair(seed=1)
    bad = f * 1.6
    dm = diebold_mariano((y - f) ** 2, (y - bad) ** 2, horizon=21)
    assert dm["mean_diff"] < 0 and dm["t_stat"] < -3
    same = diebold_mariano((y - f) ** 2, (y - f) ** 2 + 0.0, horizon=21)
    assert same["mean_diff"] == 0.0
