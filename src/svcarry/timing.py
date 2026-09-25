"""When each input is struck, and therefore how long it has to be lagged.

Why this module exists
----------------------
Through Phase 16 the look-ahead audit was a table of ten then eighteen rows written by
hand in ``scripts/run_pipeline.py``, ending in

    timing["use_precedes_availability"] = False

The column was a literal, not a computation. The project then cited that table — "0 of
18 inputs have use preceding availability" — as *mechanical* evidence that nothing
leaks. It was an assertion wearing a table's clothes, and it hid a real overlap for
1,482 trading days (final audit Pass 1, A-02 and A-05).

What this module does instead is compare two clock times for every input, per date, and
count the days on which the comparison fails. A row can now come back ``True``.

The rule
--------
A position is booked at the price that defines the index return it earns. The index is
struck at the VX daily settlement, so the settlement is the execution reference. With
``signal_lag = L``, an input dated ``t`` is first used to hold a position that earns the
return of ``t + L``; that return runs from the settlement of ``t + L - 1`` to the
settlement of ``t + L``, so the position must exist at the settlement of ``t + L - 1``.

For ``L >= 2`` the execution settlement falls on a strictly later calendar date than the
input, and the time of day is irrelevant. For ``L == 1`` the execution settlement is on
date ``t`` itself, and the input is only observable in time if

    strike time of the input  <=  strike time of that date's settlement.

Both sides move. Cboe struck the VX daily settlement at 3:15 p.m. CT (4:15 p.m. ET)
through 23 October 2020 and at 3:00 p.m. CT (4:00 p.m. ET) from 26 October 2020
(notice: *Adjustment of Daily Settlement Time for Proprietary Index Products*; see
``docs/data_sources.md``). The VIX and VIX3M cash indices are struck at 4:15 p.m. ET
throughout. So a VIX-derived signal is simultaneous with the settlement before the
change and fifteen minutes *after* it from the change onward — which is the same
fifteen-minute gap this project's first headline finding is about, turned on the
project's own signal chain.

Inputs whose strike time is later than the execution settlement take one extra day of
lag. That is what :func:`extra_lag_required` reports and what
``build_signal_panel(vix_extra_lag_from=...)`` applies.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

__all__ = [
    "SETTLEMENT_CHANGE",
    "SETTLEMENT_ET_BEFORE",
    "SETTLEMENT_ET_FROM",
    "VIX_CASH_CLOSE_ET",
    "EQUITY_CLOSE_ET",
    "execution_strike_et",
    "extra_lag_required",
    "timing_audit_table",
    "verify_weight_alignment",
]

#: First date on which the VX daily settlement was struck at the later time.
SETTLEMENT_CHANGE = pd.Timestamp("2020-10-26")
#: VX daily settlement, 3:15 p.m. CT, through 23 October 2020.
SETTLEMENT_ET_BEFORE = time(16, 15)
#: VX daily settlement, 3:00 p.m. CT, from 26 October 2020.
SETTLEMENT_ET_FROM = time(16, 0)
#: Cboe VIX and VIX3M cash indices.
VIX_CASH_CLOSE_ET = time(16, 15)
#: US equity primary session close, which is when SPY's OHLC is final.
EQUITY_CLOSE_ET = time(16, 0)


def _as_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def execution_strike_et(
    dates,
    change=SETTLEMENT_CHANGE,
    before: time = SETTLEMENT_ET_BEFORE,
    after: time = SETTLEMENT_ET_FROM,
) -> pd.Series:
    """Clock time, in ET, at which each date's execution price is struck.

    The execution price is the VX daily settlement, because that is what the index
    return is measured on.
    """
    idx = pd.DatetimeIndex(pd.Index(dates))
    chg = pd.Timestamp(change)
    return pd.Series(np.where(idx < chg, _as_minutes(before), _as_minutes(after)),
                     index=idx, name="execution_strike_et_minutes")


def extra_lag_required(
    input_strike_et: time,
    dates,
    signal_lag: int = 1,
    change=SETTLEMENT_CHANGE,
    before: time = SETTLEMENT_ET_BEFORE,
    after: time = SETTLEMENT_ET_FROM,
) -> pd.Series:
    """Per date, the extra days of lag an input needs beyond ``signal_lag``.

    ``1`` where the input is struck after the settlement at which the position would be
    booked, ``0`` otherwise. With ``signal_lag >= 2`` the answer is always ``0``: the
    execution date is strictly later than the input date, so the time of day cannot
    matter.
    """
    idx = pd.DatetimeIndex(pd.Index(dates))
    if signal_lag >= 2:
        return pd.Series(0, index=idx, name="extra_lag_required")
    if signal_lag <= 0:
        # A zero lag books the position at the settlement that ends the very return it
        # is trying to earn. That is a whole day of look-ahead, not fifteen minutes.
        return pd.Series(1, index=idx, name="extra_lag_required")
    exec_et = execution_strike_et(idx, change=change, before=before, after=after)
    return (_as_minutes(input_strike_et) > exec_et).astype(int).rename("extra_lag_required")


#: Declarative registry of every input that reaches a position-sizing decision.
#:
#: ``strike_et``  clock time, ET, at which the value is final; ``None`` for inputs that
#:                are not clock-sensitive (fitted once on a closed window) or that never
#:                reach a decision.
#: ``lag``        ``"signal"`` for inputs the engine lags by ``signal_lag``; an integer
#:                for inputs used at a fixed offset; ``None`` for inputs never used in a
#:                decision.
#: ``extra_lag``  extra days already applied to this input by the pipeline, on the dates
#:                where :func:`extra_lag_required` says one is needed.
_REGISTRY = [
    dict(input="SPY open/high/low/close", indexed_by="t", strike_et=EQUITY_CLOSE_ET,
         lag="signal", extra_lag=0, available="close of t (4:00 pm ET)"),
    dict(input="rv_proxy (overnight + Rogers-Satchell)", indexed_by="t",
         strike_et=EQUITY_CLOSE_ET, lag="signal", extra_lag=0, available="close of t"),
    dict(input="HAR predictors rv_d, rv_w, rv_m", indexed_by="t",
         strike_et=EQUITY_CLOSE_ET, lag="signal", extra_lag=0,
         available="close of t (windows end at t)"),
    dict(input="HAR coefficients", indexed_by="refit date t", strike_et=EQUITY_CLOSE_ET,
         lag="signal", extra_lag=0, available="close of t; trained on rows s <= t-{H}-1, "
                                             "whose targets end by t-1"),
    dict(input="HAR forecast", indexed_by="t", strike_et=EQUITY_CLOSE_ET, lag="signal",
         extra_lag=0, available="close of t"),
    dict(input="VIX close", indexed_by="t", strike_et=VIX_CASH_CLOSE_ET, lag="signal",
         extra_lag=1, available="4:15 pm ET on t"),
    dict(input="VIX3M close", indexed_by="t", strike_et=VIX_CASH_CLOSE_ET, lag="signal",
         extra_lag=1, available="4:15 pm ET on t (robustness only)"),
    dict(input="VX settlements -> cm30, cm90", indexed_by="t", strike_et=None,
         lag="signal", extra_lag=0,
         available="the execution settlement itself: 3:15 pm CT to 2020-10-23, "
                   "3:00 pm CT after"),
    dict(input="VRP (VIX close less HAR forecast)", indexed_by="t",
         strike_et=VIX_CASH_CLOSE_ET, lag="signal", extra_lag=1,
         available="latest of its inputs: 4:15 pm ET on t"),
    dict(input="signal (contango and VRP)", indexed_by="t", strike_et=VIX_CASH_CLOSE_ET,
         lag="signal", extra_lag=1, available="latest of its inputs: 4:15 pm ET on t"),
    dict(input="realised_next_h (evaluation only)", indexed_by="t", strike_et=None,
         lag=None, extra_lag=0, available="close of t+{H}",
         first_used="never used in a decision"),
    dict(input="index return r_t", indexed_by="t", strike_et=None, lag=0, extra_lag=0,
         available="futures settlement on t", first_used="close of t (sizing inputs)"),
    dict(input="trailing 21-day realised volatility", indexed_by="t", strike_et=None,
         lag="signal", extra_lag=0, available="close of t (from settlement returns)"),
    dict(input="GJR-GARCH parameters + EVT tail", indexed_by="fitted once on data to {DE}",
         strike_et=None, lag=None, extra_lag=0, available="{DE}",
         first_used="first used {OS} out of sample; in sample before"),
    dict(input="conditional 99.9% move for t+1", indexed_by="t", strike_et=None,
         lag="signal", extra_lag=0, available="close of t (state filtered to t)"),
    dict(input="crash floor (running maximum)", indexed_by="t", strike_et=None,
         lag="signal", extra_lag=0, available="close of t"),
    dict(input="weight w", indexed_by="t", strike_et=None, lag="signal", extra_lag=0,
         available="close of t"),
    dict(input="T-bill accrual", indexed_by="t", strike_et=None, lag=0, extra_lag=0,
         available="previous business day's discount rate", first_used="return of t"),
    dict(input="futures price for costs", indexed_by="t", strike_et=None, lag=0,
         extra_lag=0, available="settlement on t", first_used="costs charged on t"),
]


def timing_audit_table(
    dates,
    signal_lag: int = 1,
    horizon: int = 21,
    design_end=None,
    oos_start=None,
    change=SETTLEMENT_CHANGE,
    before: time = SETTLEMENT_ET_BEFORE,
    after: time = SETTLEMENT_ET_FROM,
) -> pd.DataFrame:
    """The look-ahead audit, with the verdict computed rather than asserted.

    For every input that reaches a sizing decision, compare the clock time at which the
    input is struck against the clock time of the settlement at which the position it
    informs is booked, on each date in ``dates``. Report the number of dates on which
    the input would be used before it exists, after the extra lag the pipeline actually
    applies.

    ``use_precedes_availability`` is ``True`` for any input with at least one such date.
    """
    idx = pd.DatetimeIndex(pd.Index(dates))
    de = "" if design_end is None else str(pd.Timestamp(design_end).date())
    os_ = "" if oos_start is None else str(pd.Timestamp(oos_start).date())
    rows = []
    for spec in _REGISTRY:
        lag = spec["lag"]
        eff = signal_lag if lag == "signal" else lag
        applied_extra = int(spec["extra_lag"])
        if spec["strike_et"] is None or eff is None:
            need = pd.Series(0, index=idx)
        else:
            need = extra_lag_required(spec["strike_et"], idx, signal_lag=int(eff),
                                      change=change, before=before, after=after)
        short = (need - applied_extra).clip(lower=0)
        n_bad = int((short > 0).sum())
        first_used = spec.get("first_used")
        if first_used is None:
            total = int(eff) + applied_extra
            first_used = f"return of t+{total}" if total else "return of t"
        rows.append({
            "input": spec["input"].format(H=horizon, DE=de, OS=os_),
            "indexed_by": spec["indexed_by"].format(H=horizon, DE=de, OS=os_),
            "available": spec["available"].format(H=horizon, DE=de, OS=os_),
            "strike_et": ("" if spec["strike_et"] is None
                          else spec["strike_et"].strftime("%H:%M")),
            "first_used": first_used.format(H=horizon, DE=de, OS=os_),
            "extra_lag_applied": applied_extra,
            "dates_needing_extra_lag": int((need > 0).sum()),
            "n_dates_use_precedes_availability": n_bad,
            "use_precedes_availability": bool(n_bad > 0),
        })
    return pd.DataFrame(rows)


def verify_weight_alignment(
    weight_raw: pd.Series, weight_held: pd.Series, signal_lag: int = 1
) -> dict:
    """Check, from the artefacts, that the held weight really is the lagged raw weight.

    The relationship the whole timing argument rests on is that the weight emitted by
    the backtest for date ``t`` equals the weight computed from information available at
    ``t - signal_lag``. Nothing verified it before: the false-alarm entry in
    ``docs/final_audit.md`` §A shows an auditor shifting the emitted weight a second
    time and finding 2,567 phantom violations, which is what happens when the convention
    lives in prose.
    """
    a = pd.Series(weight_held).astype(float)
    b = pd.Series(weight_raw).astype(float).shift(signal_lag).reindex(a.index)
    dev = (a - b.fillna(0.0)).abs()
    worse = {}
    for L in (signal_lag - 1, signal_lag + 1):
        if L < 0:
            continue
        c = pd.Series(weight_raw).astype(float).shift(L).reindex(a.index).fillna(0.0)
        worse[L] = float((a - c).abs().max())
    return {
        "signal_lag": int(signal_lag),
        "max_abs_deviation": float(dev.max()),
        "aligned": bool(dev.max() < 1e-12),
        "max_abs_deviation_at_other_lags": worse,
    }
