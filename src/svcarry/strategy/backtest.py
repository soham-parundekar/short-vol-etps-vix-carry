"""Backtest engine for a collateralised short position in the VIX futures index.

Accounting
----------
The strategy is a futures position, so cash is not consumed by taking it: the whole
capital sits in Treasury bills and the futures position generates a separate profit
and loss. One day's return is therefore

    R_t = a_t  -  w_{t-1} r_t  -  c_t

with ``a_t`` the T-bill accrual, ``w`` the *short* exposure as a fraction of capital
(positive ``w`` means short the index), ``r_t`` the index excess return, and ``c_t``
transaction costs. This is the same decomposition as the total-return version of the
index itself, which is what makes the strategy and its benchmarks comparable without
further adjustment.

Timing
------
``signal_lag`` days separate the date on which a weight is *computed* from the first
return it earns. With the default of 1, the weight derived from information available
at the close of ``t-1`` is applied to the return from ``t-1`` to ``t``. The engine
performs the lag itself and asserts that the supplied weights carry no later
information, so the timing convention lives in one place rather than being
re-implemented (and mis-implemented) at each call site.

Costs
-----
Charged on the trading the rule actually requires, at ``k_t = ticks * tick_size / P_t``
per unit of notional, where ``P_t`` is the weighted futures price held: a bid-offer
in VIX points is a larger fraction of a 12-point future (2017) than of a 40-point one
(March 2020), and a fixed basis-point cost would get that backwards. Two sources:

*Rebalancing.* A position at weight ``w`` does not stay at ``w``: after a day's move
it is ``w (1 + r) / (1 + R)`` of the new equity - a short grows as the index rises and
equity falls. Returning it to the next target is the trade,

    turnover_t = | w_t - w_{t-1} (1 + r_{t-1}) / (1 + R_{t-1}) |,

and a missing weight is a flat position, so leaving the market and coming back through
a data gap is charged. (Until Phase 11 turnover was ``|w_t - w_{t-1}|`` on the target
alone, which misses the drift and charged nothing for entries after a gap.)

*Rolling.* Holding the index means holding its basket, which moves a fraction
``w1_{t-1} - w1_t`` of the notional from the front to the second contract every day:
two legs, about 24 times the position a year. Charged as ``2 |w_t| roll_t k_t``
when ``roll_fraction`` is supplied.

Nothing here is netted, smoothed or annualised inside the engine. It returns the
daily series and :mod:`svcarry.evaluation.metrics` does the summarising, so that the
performance statistics are computed once, in one place, from the raw series.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["BacktestResult", "run_backtest", "buy_and_hold_etp"]


@dataclass
class BacktestResult:
    """Daily series produced by a backtest run, plus the settings that produced it."""

    returns: pd.Series            # net strategy return
    gross: pd.Series              # before costs, after collateral
    weight: pd.Series             # exposure actually applied to each day's return
    costs: pd.Series
    accrual: pd.Series
    equity: pd.Series
    turnover: pd.Series
    settings: dict = field(default_factory=dict)
    components: "pd.DataFrame | None" = None   # turnover and cost by source

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"weight": self.weight, "accrual": self.accrual, "gross": self.gross,
             "costs": self.costs, "ret": self.returns, "equity": self.equity,
             "turnover": self.turnover}
        )

    def slice(self, start=None, end=None) -> "BacktestResult":
        """Restrict to a window, rebasing the equity curve to 1.0 at the start."""
        f = self.frame()
        if start is not None:
            f = f[f.index >= pd.Timestamp(start)]
        if end is not None:
            f = f[f.index <= pd.Timestamp(end)]
        eq = (1.0 + f["ret"].fillna(0.0)).cumprod()
        return BacktestResult(
            returns=f["ret"], gross=f["gross"], weight=f["weight"], costs=f["costs"],
            accrual=f["accrual"], equity=eq, turnover=f["turnover"],
            settings={**self.settings, "window": (str(start), str(end))},
        )


def run_backtest(
    index_returns: pd.Series,
    weights: pd.Series,
    price_level: pd.Series | None = None,
    accrual: pd.Series | None = None,
    signal_lag: int = 1,
    cost_ticks: float = 1.0,
    tick_size: float = 0.05,
    cost_bps: float | None = None,
    direction: int = -1,
    initial_equity: float = 1.0,
    roll_fraction: pd.Series | None = None,
    drift_turnover: bool = True,
) -> BacktestResult:
    """Run the strategy.

    Parameters
    ----------
    index_returns
        Daily **excess** (futures-only) simple returns of the index.
    weights
        Exposure computed from information observable at the close of each date.
        The engine lags them by ``signal_lag`` days; do **not** pre-lag them.
    price_level
        Weighted futures price held on each date, used to convert a tick cost into a
        fraction of notional. If ``None``, ``cost_bps`` must be supplied instead.
    accrual
        Daily T-bill accrual on the collateral. Missing values are treated as zero
        and counted in ``settings['n_accrual_missing']`` rather than silently
        dropped.
    direction
        ``-1`` for a short index position (the default), ``+1`` for long.
    cost_bps
        Flat proportional cost in basis points per unit turnover, as an alternative
        to the tick model. Used in the robustness section to show the conclusion does
        not hinge on the cost specification.
    roll_fraction
        Share of the index basket rolled from the front to the second contract on each
        date (``max(w1_{t-1} - w1_t, 0)``). If given, the roll is charged on both legs.
    drift_turnover
        Charge the trade back to target after each day's drift (default). ``False``
        charges only changes in the target, which understates trading; kept for the
        cost-attribution table and for tests.

    Raises if a position is held on a date whose index return is missing: the day
    cannot be valued, and skipping it would drop a real profit or loss.
    """
    r = pd.Series(index_returns).astype(float)
    idx = r.index
    w_raw = pd.Series(weights).reindex(idx).astype(float)

    if signal_lag < 0:
        raise ValueError("signal_lag must be >= 0; a negative lag is look-ahead")
    w = w_raw.shift(signal_lag)
    w_pos = w.fillna(0.0)                      # a missing weight is a flat position
    held_undefined = (w_pos != 0) & r.isna()
    if held_undefined.any():
        raise ValueError(f"position held on {int(held_undefined.sum())} date(s) with no "
                         f"index return, first {r.index[held_undefined][0].date()}")

    a = (pd.Series(accrual).reindex(idx).astype(float) if accrual is not None
         else pd.Series(0.0, index=idx))
    n_acc_missing = int(a.isna().sum())
    a = a.fillna(0.0)

    if cost_bps is not None:
        k = pd.Series(cost_bps / 10_000.0, index=idx)
    else:
        if price_level is None:
            raise ValueError("supply price_level for the tick cost model, or cost_bps")
        p = pd.Series(price_level).reindex(idx).astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            k = (cost_ticks * tick_size) / p
        k = k.replace([np.inf, -np.inf], np.nan).ffill()

    # A day with no weight (before the first signal, or a data gap) is flat: it earns
    # the collateral accrual only. It is not dropped, because dropping it would quietly
    # shorten the sample and flatter the annualised statistics.
    gross = a + direction * w_pos * r.fillna(0.0)

    turnover_target = (w_pos - w_pos.shift(1).fillna(0.0)).abs()
    if drift_turnover:
        drifted = (w_pos.shift(1).fillna(0.0) * (1.0 + r.shift(1).fillna(0.0))
                   / (1.0 + gross.shift(1).fillna(0.0)))
        turnover = (w_pos - drifted).abs()
    else:
        turnover = turnover_target.copy()
    rebal_costs = (turnover * k).fillna(0.0)
    if roll_fraction is not None:
        rf_ = pd.Series(roll_fraction).reindex(idx).astype(float).fillna(0.0)
        roll_turnover = 2.0 * w_pos.abs() * rf_
    else:
        roll_turnover = pd.Series(0.0, index=idx)
    roll_costs = (roll_turnover * k).fillna(0.0)
    costs = rebal_costs + roll_costs
    net = gross - costs

    equity = (1.0 + net.fillna(0.0)).cumprod() * initial_equity

    res = BacktestResult(
        returns=net.rename("ret"),
        gross=gross.rename("gross"),
        weight=w_pos.rename("weight"),
        costs=costs.rename("costs"),
        accrual=a.rename("accrual"),
        equity=equity.rename("equity"),
        turnover=(turnover + roll_turnover).rename("turnover"),
        settings={
            "signal_lag": signal_lag,
            "cost_ticks": cost_ticks,
            "tick_size": tick_size,
            "cost_bps": cost_bps,
            "direction": direction,
            "n_days": int(len(idx)),
            "n_days_invested": int((w.fillna(0) != 0).sum()),
            "n_accrual_missing": n_acc_missing,
            "mean_cost_per_unit_turnover_bps": float(np.nanmean(k) * 10_000),
            "drift_turnover": drift_turnover,
            "roll_costed": roll_fraction is not None,
        },
    )
    res.components = pd.DataFrame({
        "turnover_target": turnover_target, "turnover_rebalance": turnover,
        "turnover_roll": roll_turnover, "cost_rebalance": rebal_costs,
        "cost_roll": roll_costs, "cost_per_unit": k})
    first = w.first_valid_index()
    res.settings["n_days_weight_missing_after_start"] = (
        int(w.loc[first:].isna().sum()) if first is not None else 0)
    return res


def buy_and_hold_etp(
    index_returns: pd.Series,
    leverage: float,
    fee: float,
    accrual: pd.Series | None = None,
    initial_equity: float = 1.0,
) -> BacktestResult:
    """The passive benchmark: hold a daily-rebalanced product and do nothing.

    This is the XIV / SVXY investor's experience, and it is the comparison that
    matters: any claim that crash budgeting helps has to be a claim relative to
    simply owning the product.
    """
    from ..etp.mechanics import etp_nav

    nav = etp_nav(index_returns, leverage=leverage, fee=fee, accrual=accrual,
                  initial=initial_equity)
    ret = nav["nav"].pct_change().fillna(nav["nav"].iloc[0] / initial_equity - 1.0)
    idx = ret.index
    return BacktestResult(
        returns=ret.rename("ret"),
        gross=ret.rename("gross"),
        weight=pd.Series(abs(leverage), index=idx, name="weight"),
        costs=pd.Series(0.0, index=idx, name="costs"),
        accrual=(pd.Series(accrual).reindex(idx).fillna(0.0) if accrual is not None
                 else pd.Series(0.0, index=idx)),
        equity=nav["nav"].rename("equity"),
        turnover=pd.Series(0.0, index=idx, name="turnover"),
        settings={"benchmark": f"buy-and-hold {leverage:+g}x", "fee": fee},
    )
