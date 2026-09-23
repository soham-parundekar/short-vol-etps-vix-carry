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

__all__ = ["contango_signal", "vrp", "vrp_signal", "combine_signals", "SignalSet",
           "spot_anchored_front", "build_signal_panel", "signal_statistics"]


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


def spot_anchored_front(cm: pd.Series, spot: pd.Series, front_price: pd.Series,
                        front_days: pd.Series, maturity: int = 30) -> "tuple[pd.Series, pd.Series]":
    """Fill the constant-maturity point where no listed future is shorter than it.

    The interpolated curve leaves ``cm30`` missing when the shortest live contract
    is more than 30 days out - about three sessions after every monthly expiry that
    is followed by a five-week cycle, some twelve sessions a year. On those days the
    zero-maturity point of the curve is observable: a future expiring today settles
    to the VIX, so spot VIX is the curve at ``tau = 0``, and ``cm30`` is interpolated
    between it and the front contract,

        cm30 = VIX + (F1 - VIX) * 30 / tau1.

    Only missing values are touched; the second series flags them.
    """
    cm = pd.Series(cm, dtype=float)
    fill = cm.isna() & (front_days > maturity) & spot.notna() & front_price.notna()
    out = cm.copy()
    out[fill] = spot[fill] + (front_price[fill] - spot[fill]) * maturity / front_days[fill]
    return out, fill.rename("spot_anchored")


def build_signal_panel(
    rv: pd.Series, curve: pd.DataFrame, *, horizon: int = 21,
    lags: tuple = (1, 5, 22), log: bool = True, train_min: int = 1000,
    refit_every: int = 21, contango_threshold: float = 1.0, vrp_min: float = 0.0,
    periods_per_year: int = 252, retransform: str = "normal",
):
    """Every series that feeds the entry decision, on the index's trading calendar.

    ``rv``     daily variance proxy on the equity calendar.
    ``curve``  index-dated frame with ``vix, vix3m, cm30, cm90, f1, days_to_exp1``.

    Returns ``(panel, har)``. Each row of ``panel`` uses information available at
    that date's close and nothing later; the realised outcome the forecast is judged
    against lives only in ``har.realised`` and is deliberately kept out of the panel,
    so a later stage cannot pick it up by accident. Nothing is forward-filled: on a
    date when the equity market was shut but futures traded, the forecast is missing
    and so is the signal.
    """
    from svcarry.econometrics.har import har_oos_forecast

    har = har_oos_forecast(rv, horizon=horizon, lags=tuple(lags), log=log,
                           train_min=train_min, refit_every=refit_every,
                           retransform=retransform)
    idx = curve.index
    p = pd.DataFrame(index=idx)
    p["rv_proxy"] = rv.reindex(idx)
    p["har_forecast"] = har.forecast.reindex(idx)
    p["har_forecast_ann_var"] = p["har_forecast"] * periods_per_year
    p["har_forecast_vol_pct"] = np.sqrt(p["har_forecast_ann_var"]) * 100.0
    p["vix"] = curve["vix"]
    p["vix3m"] = curve.get("vix3m")
    p["iv_ann_var"] = (p["vix"] / 100.0) ** 2
    # the one place units are converted: VIX in percentage points, forecast daily
    p["vrp"] = vrp(p["vix"], p["har_forecast"], periods_per_year=periods_per_year).reindex(idx)
    cm30, anchored = spot_anchored_front(curve["cm30"], curve["vix"], curve["f1"],
                                         curve["days_to_exp1"])
    p["cm30"] = cm30
    p["cm30_spot_anchored"] = anchored
    p["cm90"] = curve["cm90"]
    p["slope_cm"] = p["cm30"] / p["cm90"]
    p["slope_vix3m"] = p["vix"] / p["vix3m"]
    p["sig_contango"] = contango_signal(p["slope_cm"], contango_threshold)
    p["sig_contango_vix3m"] = contango_signal(p["slope_vix3m"], contango_threshold)
    p["sig_vrp"] = vrp_signal(p["vrp"], vrp_min)
    p["signal"] = combine_signals({"c": p["sig_contango"], "v": p["sig_vrp"]}, rule="all")
    c, v = p["sig_contango"], p["sig_vrp"]
    bind = pd.Series("none", index=idx, dtype=object)
    bind[(c == 0) & (v == 1)] = "contango"
    bind[(c == 1) & (v == 0)] = "vrp"
    bind[(c == 0) & (v == 0)] = "both"
    bind[p["signal"].isna()] = "undefined"
    p["binding"] = bind
    return p, har


def signal_statistics(panel: pd.DataFrame, start=None) -> pd.DataFrame:
    """Fractions of days each signal is on, binds, and agrees, after ``start``."""
    p = panel.loc[start:] if start is not None else panel
    d = p.dropna(subset=["signal"])
    rows = [
        ("days after burn-in", len(p), np.nan),
        ("days with the combined signal defined", len(d), len(d) / len(p)),
        ("contango (cm30/cm90) on", int(d["sig_contango"].sum()), d["sig_contango"].mean()),
        ("VRP on", int(d["sig_vrp"].sum()), d["sig_vrp"].mean()),
        ("combined on (invested)", int(d["signal"].sum()), d["signal"].mean()),
        ("both signals agree", int((d["sig_contango"] == d["sig_vrp"]).sum()),
         (d["sig_contango"] == d["sig_vrp"]).mean()),
    ]
    for b in ("contango", "vrp", "both"):
        n = int((d["binding"] == b).sum())
        rows.append((f"off, binding constraint: {b}", n, n / len(d)))
    o = p.dropna(subset=["sig_contango", "sig_contango_vix3m"])
    agree = (o["sig_contango"] == o["sig_contango_vix3m"])
    rows.append(("cm30/cm90 and VIX/VIX3M agree (overlap)", int(agree.sum()), agree.mean()))
    rows.append(("VIX/VIX3M on (overlap)", int(o["sig_contango_vix3m"].sum()),
                 o["sig_contango_vix3m"].mean()))
    return pd.DataFrame(rows, columns=["statistic", "days", "fraction"])
