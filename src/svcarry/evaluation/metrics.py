"""Performance and risk statistics.

Short-volatility returns are the textbook case where the usual summary statistics
mislead. The distribution is left-skewed with a thin, profitable body and a very fat
loss tail, so a Sharpe ratio computed over a sample that happens to exclude a crash
can look excellent while describing a strategy that is one bad day from ruin. Every
table this module produces therefore reports the moments and the tail alongside the
ratio, and the Sharpe ratio comes with a standard error that accounts for
non-normality and autocorrelation rather than the naive ``sqrt(T)`` one.

The Lo (2002) correction is used for the Sharpe standard error: under i.i.d. but
non-normal returns,

    Var(SR_hat) ~ (1 + SR^2/2 - SR*skew + SR^2 (kurt - 3)/4) / T,

which for a strategy with skew of -3 and excess kurtosis of 20 is several times the
naive variance. Serial correlation is handled separately by a Newey-West standard
error on the mean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ..econometrics.hac import newey_west_lags, ols

__all__ = [
    "drawdown",
    "max_drawdown",
    "performance_stats",
    "performance_table",
    "rolling_sharpe",
    "window_returns",
    "sharpe_standard_error",
]

TRADING_DAYS = 252


def drawdown(returns: pd.Series) -> pd.DataFrame:
    """Drawdown path, running peak and underwater duration."""
    r = pd.Series(returns).astype(float).fillna(0.0)
    eq = (1.0 + r).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1.0
    underwater = (dd < 0).astype(int)
    grp = (underwater.diff() == 1).cumsum()
    dur = underwater.groupby(grp).cumsum() * underwater
    return pd.DataFrame({"equity": eq, "peak": peak, "drawdown": dd,
                         "days_underwater": dur})


def max_drawdown(returns: pd.Series) -> float:
    return float(drawdown(returns)["drawdown"].min())


def sharpe_standard_error(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Lo (2002) standard error of the annualised Sharpe ratio under non-normality."""
    r = pd.Series(returns).astype(float).dropna()
    n = len(r)
    if n < 30 or r.std(ddof=1) == 0:
        return np.nan
    sr = float(r.mean() / r.std(ddof=1))          # per-period
    sk = float(stats.skew(r, bias=False))
    ku = float(stats.kurtosis(r, fisher=False, bias=False))
    var = (1.0 + 0.5 * sr ** 2 - sr * sk + 0.25 * sr ** 2 * (ku - 3.0)) / n
    return float(np.sqrt(max(var, 0.0)) * np.sqrt(periods))


def performance_stats(
    returns: pd.Series,
    periods: int = TRADING_DAYS,
    rf: pd.Series | float = 0.0,
    turnover: pd.Series | None = None,
    weight: pd.Series | None = None,
    name: str = "strategy",
) -> dict:
    """Full statistics for one return series.

    ``returns`` are *total* returns (collateral included). ``rf`` is subtracted to
    form excess returns for the Sharpe ratio; pass the same T-bill accrual used in
    the backtest so that the Sharpe is on excess returns rather than on total ones.
    """
    r = pd.Series(returns).astype(float).dropna()
    if len(r) < 20:
        return {"name": name, "n": len(r)}

    rf_s = (pd.Series(rf).reindex(r.index).fillna(0.0) if not np.isscalar(rf)
            else pd.Series(float(rf), index=r.index))
    ex = r - rf_s

    years = len(r) / periods
    total_growth = float((1.0 + r).prod())
    cagr = total_growth ** (1.0 / years) - 1.0 if total_growth > 0 else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(periods))
    sharpe = float(ex.mean() / ex.std(ddof=1) * np.sqrt(periods)) if ex.std(ddof=1) > 0 else np.nan

    downside = ex[ex < 0]
    dsd = float(downside.std(ddof=1) * np.sqrt(periods)) if len(downside) > 2 else np.nan
    sortino = float(ex.mean() * periods / dsd) if dsd and dsd > 0 else np.nan

    dd = drawdown(r)
    mdd = float(dd["drawdown"].min())

    # HAC t-statistic on the mean excess return
    lags = newey_west_lags(len(ex))
    mean_reg = ols(ex.to_numpy(), np.zeros((len(ex), 1)), names=["_"],
                   add_const=True, cov_type="HAC", lags=lags)

    out = {
        "name": name,
        "n": int(len(r)),
        "years": round(years, 2),
        "cagr": cagr,
        "ann_vol": vol,
        "sharpe": sharpe,
        "sharpe_se_lo": sharpe_standard_error(ex, periods),
        "mean_t_hac": float(mean_reg.tvalues[0]),
        "sortino": sortino,
        "max_drawdown": mdd,
        "calmar": (cagr / abs(mdd)) if mdd < 0 else np.nan,
        "skew": float(stats.skew(r, bias=False)),
        "excess_kurtosis": float(stats.kurtosis(r, bias=False)),
        "var_95": float(np.quantile(r, 0.05)),
        "cvar_95": float(r[r <= np.quantile(r, 0.05)].mean()),
        "var_99": float(np.quantile(r, 0.01)),
        "cvar_99": float(r[r <= np.quantile(r, 0.01)].mean()),
        "worst_day": float(r.min()),
        "worst_week": float((1.0 + r).rolling(5).apply(np.prod, raw=True).min() - 1.0),
        "best_day": float(r.max()),
        "hit_rate": float((r > 0).mean()),
        "longest_drawdown_days": int(dd["days_underwater"].max()),
    }
    if turnover is not None:
        t = pd.Series(turnover).reindex(r.index).fillna(0.0)
        out["ann_turnover"] = float(t.sum() / years)
    if weight is not None:
        w = pd.Series(weight).reindex(r.index)
        out["avg_weight"] = float(w.mean())
        out["max_weight"] = float(w.max())
        out["time_invested"] = float((w.fillna(0) > 0).mean())
    return out


def performance_table(
    series: "dict[str, pd.Series]",
    rf: pd.Series | float = 0.0,
    extras: "dict[str, dict] | None" = None,
    periods: int = TRADING_DAYS,
) -> pd.DataFrame:
    """Statistics for several series side by side."""
    rows = []
    for nm, s in series.items():
        kw = (extras or {}).get(nm, {})
        rows.append(performance_stats(s, periods=periods, rf=rf, name=nm, **kw))
    return pd.DataFrame(rows).set_index("name")


def rolling_sharpe(
    returns: pd.Series, window: int = 252, rf: pd.Series | float = 0.0,
    periods: int = TRADING_DAYS,
) -> pd.Series:
    r = pd.Series(returns).astype(float)
    rf_s = (pd.Series(rf).reindex(r.index).fillna(0.0) if not np.isscalar(rf)
            else pd.Series(float(rf), index=r.index))
    ex = r - rf_s
    m = ex.rolling(window).mean()
    s = ex.rolling(window).std(ddof=1)
    return (m / s * np.sqrt(periods)).rename(f"rolling_sharpe_{window}")


def window_returns(
    series: "dict[str, pd.Series]", windows: "dict[str, tuple]"
) -> pd.DataFrame:
    """Cumulative return of each series within each named window.

    Used for the stress table. Windows that fall entirely outside a series' life
    (XIV after February 2018, SVIX before March 2022) come back as NaN rather than
    as zero, so the table cannot be misread as "the product was flat".
    """
    rows = {}
    for wname, (lo, hi) in windows.items():
        row = {}
        for sname, s in series.items():
            s = pd.Series(s).astype(float)
            seg = s[(s.index >= pd.Timestamp(lo)) &
                    (s.index <= (pd.Timestamp(hi) if hi else s.index.max()))]
            seg = seg.dropna()
            row[sname] = float((1.0 + seg).prod() - 1.0) if len(seg) else np.nan
        rows[wname] = row
    return pd.DataFrame(rows).T
