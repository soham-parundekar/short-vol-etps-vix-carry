"""Position sizing: volatility targeting, bounded by an explicit crash budget.

The central claim of this project is that volatility targeting is the wrong sizing
rule for a short-volatility position, and that the failure is structural rather than
a matter of calibration.

Volatility targeting sets ``w = sigma* / sigma_hat``, where ``sigma_hat`` is recent
realised volatility. For most assets that is sensible. For an inverse volatility
exposure it is close to the worst possible rule, because the *quietest* periods —
when ``sigma_hat`` is smallest and the rule therefore sizes largest — are precisely
the periods from which the largest volatility spikes start. Realised volatility of
the short-term VIX futures index in January 2018 was near its historical lows; a
volatility-targeting rule would have been at maximum size going into 5 February.

The fix implemented here is a second, binding constraint: size is also capped so that
a *stated* crash scenario costs no more than a stated fraction of capital,

    w_t = min( sigma* / sigma_hat_t ,  l_max / StressLoss_t ,  w_max ),

where ``StressLoss_t`` is the loss a unit short position would take under the larger
of (i) the fitted conditional 99.9% one-day index move and (ii) a historical
reference move (5 February 2018 by default). The second term does not adapt to calm:
if the scenario says the index can rise 90% in a day, a 20% loss budget caps the
position at 0.22 regardless of how quiet the last month was.

This is a *budget*, not a forecast. It does not claim to know when a crash comes; it
claims to know what one would cost.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "realised_vol",
    "ewma_vol",
    "stress_move",
    "stress_loss",
    "target_weight",
]


def realised_vol(
    returns: pd.Series, window: int = 21, periods_per_year: int = 252,
    min_periods: int | None = None,
) -> pd.Series:
    """Trailing annualised realised volatility, observable at each day's close."""
    r = pd.Series(returns).astype(float)
    mp = min_periods if min_periods is not None else max(window // 2, 5)
    return (r.rolling(window, min_periods=mp).std(ddof=1)
            * np.sqrt(periods_per_year)).rename("realised_vol")


def ewma_vol(
    returns: pd.Series, halflife: float = 21.0, periods_per_year: int = 252
) -> pd.Series:
    """Exponentially weighted annualised volatility (RiskMetrics style)."""
    r = pd.Series(returns).astype(float)
    return (r.ewm(halflife=halflife, min_periods=10).std(bias=False)
            * np.sqrt(periods_per_year)).rename("ewma_vol")


def stress_move(
    model_quantile: pd.Series | float | None = None,
    historical_floor: float = 0.96,
) -> pd.Series | float:
    """The one-day index simple return used as the crash scenario.

    Takes the larger of a model-implied conditional quantile and a historical
    reference move. The floor exists so that a quiet-period model fit cannot shrink
    the scenario below something that has actually happened — which is exactly the
    mistake the whole exercise is about.

    ``historical_floor`` defaults to the 5 February 2018 move of the short-term VIX
    futures index. The value in ``config/config.yaml`` is resolved from the
    reconstructed index at run time rather than hard-coded, so it is a measured
    number and not a remembered one.
    """
    if model_quantile is None:
        return historical_floor
    if np.isscalar(model_quantile):
        return max(float(model_quantile), historical_floor)
    q = pd.Series(model_quantile).astype(float)
    return q.clip(lower=historical_floor).rename("stress_move")


def stress_loss(weight, move) -> np.ndarray:
    """Loss on a short position of size ``weight`` if the index rises by ``move``.

    A short position of ``w`` loses ``w * move`` (as a fraction of capital) when the
    index rises by ``move``. Linear because the position is a futures exposure, not
    an option.
    """
    return np.asarray(weight, dtype=float) * np.asarray(move, dtype=float)


def target_weight(
    vol_estimate: pd.Series,
    vol_target: float = 0.15,
    stress: "pd.Series | float | None" = None,
    max_stress_loss: float = 0.20,
    max_weight: float = 1.0,
    min_weight: float = 0.0,
    signal: pd.Series | None = None,
) -> pd.DataFrame:
    """Combine the volatility target, the crash budget and the entry signal.

    Returns a frame with the two candidate weights, the binding constraint on each
    day, and the final weight. Reporting *which constraint binds* is not decoration:
    the share of days on which the crash budget is the binding one is the headline
    statistic of the sizing section, and it should be highest in exactly the calm
    periods where volatility targeting would have been largest.
    """
    v = pd.Series(vol_estimate).astype(float)
    idx = v.index

    with np.errstate(divide="ignore", invalid="ignore"):
        w_vol = pd.Series(vol_target / v, index=idx)

    if stress is None:
        w_stress = pd.Series(np.inf, index=idx)
        stress_s = pd.Series(np.nan, index=idx)
    else:
        stress_s = (pd.Series(float(stress), index=idx) if np.isscalar(stress)
                    else pd.Series(stress).reindex(idx).astype(float))
        with np.errstate(divide="ignore", invalid="ignore"):
            w_stress = max_stress_loss / stress_s

    w = pd.concat([w_vol, w_stress], axis=1).min(axis=1)
    w = w.clip(lower=min_weight, upper=max_weight)

    binding = pd.Series("vol_target", index=idx, dtype=object)
    binding[w_stress < w_vol] = "stress_budget"
    binding[(w >= max_weight - 1e-12)] = "max_weight"
    binding[w_vol.isna()] = "no_estimate"

    if signal is not None:
        s = pd.Series(signal).reindex(idx).astype(float)
        w = w * s
        binding[s.fillna(0) == 0] = "signal_off"

    out = pd.DataFrame(
        {"w_vol_target": w_vol, "w_stress_budget": w_stress,
         "stress_move": stress_s, "weight": w, "binding": binding}
    )
    out.attrs["vol_target"] = vol_target
    out.attrs["max_stress_loss"] = max_stress_loss
    return out
