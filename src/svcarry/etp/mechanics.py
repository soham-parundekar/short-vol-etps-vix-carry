"""Mechanics of daily-rebalanced leveraged and inverse exchange-traded products.

Three pieces of arithmetic drive everything this project says about product design.

**1. The wrapper's NAV recursion.** A product targeting daily leverage ``L`` on an
index ``I``, charging an annual fee ``phi`` and crediting a cash accrual ``a_t``,
evolves as

    V_t = V_{t-1} (1 + a_t + L r_t) - V_{t-1} phi (d_t / 365)

which is exactly the "Daily ETN Performance minus Daily Investor Fee" construction
in the VelocityShares pricing supplement, and is also how the ProShares funds behave
net of expenses. :func:`etp_nav` implements it.

**2. The rebalancing trade.** Holding leverage ``L`` constant requires trading at
every close. If the index returns ``r`` on day ``t``, assets go from ``A`` to
``A(1 + L r)`` while the existing exposure drifts to ``L A (1 + r)``, so the trade
needed to restore the target is

    dE_t = L A_{t-1} (1 + L r_t) - L A_{t-1} (1 + r_t) = L (L - 1) A_{t-1} r_t.

The coefficient ``L(L-1)`` is positive for **every** ``L`` outside ``[0, 1]``: both a
2x long fund and a -1x inverse fund must *buy* after the index rises. That is the
feedback mechanism, and it is a property of the product design rather than of
anybody's behaviour. :func:`rebalancing_trade` returns it; ``L = -1`` gives ``2 A r``
and the post-2018 ``L = -0.5`` gives ``0.75 A r``, a 62.5% reduction in the trade for
the same shock.

**3. Leverage decay.** Under continuous rebalancing with the index following a
geometric Brownian motion of volatility ``sigma``,

    V_T / V_0 = (I_T / I_0)^L exp( -(1/2)(L^2 - L) sigma^2 T ).

The drag ``(1/2)(L^2 - L) sigma^2`` is zero only for ``L in {0, 1}``; for ``L = -1``
it is ``sigma^2``, i.e. a -1x product on a 60%-volatility index bleeds about 36% a
year from rebalancing alone, before fees, *even if the index is unchanged*.
:func:`decay_regression` tests the identity on real product data by regressing
``ln(V_T/V_0) - L ln(I_T/I_0)`` on realised variance and comparing the slope with
``-(1/2)(L^2 - L)``.

**Termination thresholds.** A product loses a fraction ``k`` of its value in one day
when ``1 + L r = 1 - k``, i.e. when the index simple return is ``r = k / (-L)`` for
inverse products. With ``k = 0.80``: ``L = -1`` needs an 80% index move, ``L = -0.5``
needs 160%. :func:`wipeout_threshold` returns this.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..econometrics.hac import ols

__all__ = [
    "etp_nav",
    "rebalancing_trade",
    "wipeout_threshold",
    "theoretical_decay",
    "decay_regression",
    "contracts_equivalent",
    "aggregate_rebalancing_flow",
]


def etp_nav(
    index_returns: pd.Series,
    leverage: float,
    fee: float = 0.0,
    accrual: pd.Series | None = None,
    initial: float = 100.0,
    day_count: int = 365,
    floor_at_zero: bool = True,
) -> pd.DataFrame:
    """Simulate a daily-rebalanced product's net asset value.

    Parameters
    ----------
    index_returns
        Daily **simple** returns of the underlying index.
    leverage
        Daily target multiple ``L`` (e.g. ``-1.0``, ``-0.5``, ``2.0``).
    fee
        Annual fee as a decimal, accrued on calendar days.
    accrual
        Daily cash accrual credited on the notional (the ETN "Daily Accrual"). Pass
        ``None`` for a fund whose expense ratio already nets this out.
    floor_at_zero
        If the daily move would drive NAV negative - possible for ``|L| > 1`` - the
        value is floored at zero and the product is treated as dead from that point.
        A leveraged product cannot have negative NAV; allowing one would produce
        nonsense returns afterwards.

    Returns a frame with ``nav``, ``ret``, ``gross_ret``, ``fee_drag`` and ``alive``.
    """
    r = pd.Series(index_returns).astype(float)
    idx = r.index
    days = pd.Series(idx, index=idx).diff().dt.days.fillna(1).astype(float)
    a = (accrual.reindex(idx).fillna(0.0) if accrual is not None
         else pd.Series(0.0, index=idx))

    fee_drag = fee * days / day_count
    gross = a + leverage * r.fillna(0.0)
    nav = np.empty(len(r))
    alive = np.ones(len(r), dtype=bool)
    v = initial
    dead = False
    for i in range(len(r)):
        if dead:
            nav[i] = 0.0
            alive[i] = False
            continue
        v = v * (1.0 + gross.iat[i]) - v * fee_drag.iat[i]
        if floor_at_zero and v <= 0.0:
            v = 0.0
            dead = True
            alive[i] = False
        nav[i] = v
    out = pd.DataFrame(
        {"nav": nav, "gross_ret": gross.to_numpy(), "fee_drag": fee_drag.to_numpy(),
         "alive": alive},
        index=idx,
    )
    out["ret"] = out["nav"].pct_change()
    out.attrs["leverage"] = leverage
    out.attrs["fee"] = fee
    return out


def rebalancing_trade(leverage: float, assets, index_return) -> np.ndarray:
    """End-of-day change in index exposure required to restore daily leverage.

        dE = L (L - 1) A_{t-1} r_t

    Positive means the product must **buy** exposure. Units follow ``assets``.
    """
    a = np.asarray(assets, dtype=float)
    r = np.asarray(index_return, dtype=float)
    return leverage * (leverage - 1.0) * a * r


def wipeout_threshold(leverage: float, wipeout_fraction: float = 0.80) -> float:
    """One-day index **simple** return that destroys ``wipeout_fraction`` of NAV.

    Solves ``1 + L r = 1 - k``. Returns a positive number for inverse products (the
    index must rise) and a negative one for long-leveraged products.
    """
    if leverage == 0:
        raise ValueError("leverage must be non-zero")
    return -wipeout_fraction / leverage


def theoretical_decay(leverage: float) -> float:
    """Coefficient on realised variance in the continuous-rebalancing identity.

    ``ln(V_T/V_0) = L ln(I_T/I_0) - (1/2)(L^2 - L) sigma^2 T``, so the coefficient
    returned here is ``-(1/2)(L^2 - L)``: 0 for ``L`` of 0 or 1, ``-1`` for ``L=-1``,
    ``-1`` for ``L=2``, ``-0.375`` for ``L=-0.5``, ``-0.375`` for ``L=1.5``.
    """
    return -0.5 * (leverage ** 2 - leverage)


@dataclass
class DecayResult:
    leverage: float
    slope: float
    slope_se: float
    theoretical: float
    t_vs_theory: float
    intercept_annual: float
    n: int
    rsquared: float
    horizon: int

    def summary(self) -> str:
        return (
            f"L = {self.leverage:+.2f}   horizon = {self.horizon}d   n = {self.n}\n"
            f"  estimated variance coefficient : {self.slope:+.4f} "
            f"(se {self.slope_se:.4f})\n"
            f"  theoretical -(L^2 - L)/2       : {self.theoretical:+.4f}\n"
            f"  t-statistic against theory     : {self.t_vs_theory:+.2f}\n"
            f"  intercept (annualised)         : {self.intercept_annual:+.2%}  "
            f"[fees, roll costs, tracking]\n"
            f"  R^2                            : {self.rsquared:.3f}"
        )


def decay_regression(
    product_returns: pd.Series,
    index_returns: pd.Series,
    leverage: float,
    horizon: int = 21,
    realised_var: pd.Series | None = None,
    periods_per_year: int = 252,
) -> DecayResult:
    """Test the leverage-decay identity on realised product data.

    Regresses, over non-overlapping ``horizon``-day blocks,

        ln(V_T/V_0) - L ln(I_T/I_0)   on   realised variance over the block

    The slope should equal ``-(1/2)(L^2 - L)`` and the intercept should be close to
    minus the fee. Non-overlapping blocks are used so the observations are
    independent; with overlapping blocks the point estimate is unchanged but the
    standard errors need a HAC correction, which is applied in the robustness
    section as a cross-check.

    ``realised_var`` defaults to the sum of squared daily log index returns within
    each block, which is the quantity the identity is written in terms of.
    """
    pr = pd.Series(product_returns).astype(float)
    ir = pd.Series(index_returns).astype(float)
    df = pd.DataFrame({"p": pr, "i": ir}).dropna()
    if len(df) < 5 * horizon:
        raise ValueError(f"need at least {5*horizon} overlapping observations")

    lp = np.log1p(df["p"])
    li = np.log1p(df["i"])
    rv = (li ** 2) if realised_var is None else realised_var.reindex(df.index)

    n_blocks = len(df) // horizon
    cut = n_blocks * horizon
    grp = np.repeat(np.arange(n_blocks), horizon)
    blocks = pd.DataFrame(
        {"lp": lp.iloc[:cut].to_numpy(), "li": li.iloc[:cut].to_numpy(),
         "rv": np.asarray(rv)[:cut], "g": grp}
    ).groupby("g").sum()

    y = (blocks["lp"] - leverage * blocks["li"]).to_numpy()
    x = blocks["rv"].to_numpy()
    res = ols(y, x, names=["realised_var"], cov_type="HC1")

    theo = theoretical_decay(leverage)
    slope, se = float(res.params[1]), float(res.bse[1])
    return DecayResult(
        leverage=leverage,
        slope=slope,
        slope_se=se,
        theoretical=theo,
        t_vs_theory=(slope - theo) / se if se > 0 else np.nan,
        intercept_annual=float(res.params[0]) * periods_per_year / horizon,
        n=int(res.nobs),
        rsquared=float(res.rsquared),
        horizon=horizon,
    )


def contracts_equivalent(
    notional, front_price, multiplier: float = 1000.0
) -> np.ndarray:
    """Convert a dollar exposure change into VIX futures contract equivalents.

    The VX contract multiplier is $1,000 per index point, so a $1 notional buys
    ``1 / (1000 * F)`` contracts at a futures price ``F``.
    """
    n = np.asarray(notional, dtype=float)
    f = np.asarray(front_price, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return n / (multiplier * f)


def aggregate_rebalancing_flow(
    assets: pd.DataFrame,
    leverages: "dict[str, float] | pd.DataFrame",
    index_returns: pd.Series,
    front_price: pd.Series,
    open_interest: pd.Series | None = None,
    multiplier: float = 1000.0,
) -> pd.DataFrame:
    """Total end-of-day rebalancing demand across a set of products.

    Parameters
    ----------
    assets
        Net assets by product (columns) and date (index), in dollars.
    leverages
        Either a constant per product, or a DataFrame of the same shape as
        ``assets`` when a product's target leverage changes mid-sample (SVXY and
        UVXY both do, on 2018-02-28).
    open_interest
        Front-month open interest in contracts. When supplied, the flow is also
        expressed as a share of it, which is the number that says whether the
        mechanical trade is large relative to the market that has to absorb it.

    Returns per-product dollar flows, the aggregate, its contract equivalent, and
    the share of open interest.
    """
    idx = assets.index
    r = pd.Series(index_returns).reindex(idx)
    out = pd.DataFrame(index=idx)
    total = pd.Series(0.0, index=idx)
    for col in assets.columns:
        if isinstance(leverages, pd.DataFrame):
            L = leverages[col].reindex(idx).astype(float)
        else:
            L = pd.Series(float(leverages[col]), index=idx)
        flow = L * (L - 1.0) * assets[col].reindex(idx) * r
        out[f"flow_{col}"] = flow
        total = total.add(flow.fillna(0.0), fill_value=0.0)
    out["flow_total"] = total
    out["contracts"] = contracts_equivalent(
        total, front_price.reindex(idx), multiplier=multiplier
    )
    if open_interest is not None:
        oi = open_interest.reindex(idx).astype(float)
        out["open_interest"] = oi
        with np.errstate(divide="ignore", invalid="ignore"):
            out["share_of_oi"] = out["contracts"] / oi
    return out
