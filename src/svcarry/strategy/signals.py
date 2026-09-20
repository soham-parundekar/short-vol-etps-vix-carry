"""Entry signals for the short-volatility carry strategy.

Two signals, chosen because each has an economic story that does not depend on the
other being true.

**Term-structure (contango) filter.** A short position in a rolling front-two VIX
futures basket earns the roll down the curve when the curve slopes upward. When it
inverts - which is what happens in a stress episode - the same position pays the roll
instead of earning it, and does so at exactly the moment the spot move is against it.
Requiring an upward slope is therefore not a forecast; it is a refusal to hold the
position in the state where its two loss sources align.

**Variance risk premium.** ``VRP_t = IV_t^2 - E_t[RV_{t,t+h}]``: the compensation for
selling variance, measured as the gap between the option-implied variance and a
forecast of the variance that will actually be realised. Requiring it to be positive
is a refusal to sell variance when it is not being paid for.

Every series returned here is indexed by the date on which it is **observable**, so
the backtest can lag it by exactly one day without further reasoning. Nothing in this
module looks forward: the HAR forecast is produced by
:func:`svcarry.econometrics.har.har_oos_forecast`, which is itself constrained to use
only data whose dependent variable had already been realised.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["contango_signal", "vrp", "vrp_signal", "combine_signals", "SignalSet"]


def contango_signal(
    slope: pd.Series, threshold: float = 1.0, smooth: int = 1
) -> pd.Series:
    """1 when the volatility curve is upward sloping, 0 otherwise.

    ``slope`` is a ratio of a short-dated to a longer-dated volatility (``VIX/VIX3M``
    or the interpolated ``cm30/cm90``); values below ``threshold`` mean contango.
    ``smooth`` applies a trailing average to the *slope* before thresholding, which
    reduces whipsaw around the boundary without introducing any forward information.
    """
    s = pd.Series(slope).astype(float)
    if smooth > 1:
        s = s.rolling(smooth).mean()
    sig = (s < threshold).astype(float)
    sig[s.isna()] = np.nan
    return sig.rename("contango_signal")


def vrp(
    implied_vol: pd.Series,
    rv_forecast: pd.Series,
    iv_in_percent: bool = True,
    rv_annualised: bool = False,
    periods_per_year: int = 252,
) -> pd.Series:
    """Variance risk premium in annualised variance units.

    ``implied_vol``  VIX-style annualised volatility. If ``iv_in_percent`` it is
                     divided by 100 first, so ``VIX = 20`` becomes ``0.20``.
    ``rv_forecast``  forecast of *daily* variance over the horizon (the natural
                     output of the HAR model), unless ``rv_annualised`` is set.

    Both legs end up as annualised variances so that the difference is interpretable:
    ``VRP = 0.01`` means implied variance exceeds expected realised variance by one
    percentage point of annualised variance.
    """
    iv = pd.Series(implied_vol).astype(float)
    if iv_in_percent:
        iv = iv / 100.0
    rv = pd.Series(rv_forecast).astype(float)
    if not rv_annualised:
        rv = rv * periods_per_year
    idx = iv.index.union(rv.index)
    return (iv.reindex(idx) ** 2 - rv.reindex(idx)).rename("vrp")


def vrp_signal(vrp_series: pd.Series, minimum: float = 0.0) -> pd.Series:
    """1 when the variance risk premium exceeds ``minimum``."""
    v = pd.Series(vrp_series).astype(float)
    sig = (v > minimum).astype(float)
    sig[v.isna()] = np.nan
    return sig.rename("vrp_signal")


class SignalSet(dict):
    """Named signals plus the combination rule used, for reporting and robustness."""

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(dict(self))


def combine_signals(
    signals: "dict[str, pd.Series]", rule: str = "all", require: int | None = None
) -> pd.Series:
    """Combine 0/1 signals.

    ``all``  every signal must be on (the default; the conservative choice)
    ``any``  at least one signal on
    ``k``    at least ``require`` signals on
    ``mean`` the average of the signals, giving a partial position

    Missing values propagate: a day on which a signal cannot be computed produces no
    position rather than a default-on position, which is the difference between a
    strategy and a strategy that quietly assumes data it did not have.
    """
    df = pd.DataFrame(signals)
    n = df.shape[1]
    if rule == "all":
        out = (df.sum(axis=1) == n).astype(float)
    elif rule == "any":
        out = (df.sum(axis=1) >= 1).astype(float)
    elif rule == "k":
        if require is None:
            raise ValueError("rule='k' needs require=<int>")
        out = (df.sum(axis=1) >= require).astype(float)
    elif rule == "mean":
        out = df.mean(axis=1)
    else:
        raise ValueError(f"unknown rule {rule!r}")
    out[df.isna().any(axis=1)] = np.nan
    return out.rename("signal")
