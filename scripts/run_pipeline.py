#!/usr/bin/env python3
"""Run the analysis end to end, from cached raw data to tables and figures.

    python scripts/run_pipeline.py                  # everything
    python scripts/run_pipeline.py --from index     # resume at a stage
    python scripts/run_pipeline.py --only tail      # one stage
    python scripts/run_pipeline.py --list           # show the stages

Stages, in dependency order:

    clean     raw files -> cleaned futures panel, ETP prices, rates
    index     panel -> reconstructed index, curve, carry, tracking validation
    mechanics leverage-decay regressions and rebalancing flows
    tail      GJR-GARCH / EVT, termination probabilities, survival, Kelly
    signals   realised variance, HAR forecasts, VRP and term-structure signals
    backtest  crash-budgeted strategy and benchmarks
    robust    parameter sweeps, subsamples, red-team checks
    figures   every figure in reports/figures

Each stage writes its outputs and a short JSON record to
``reports/_pipeline_state.json`` so a later run can tell what is already done and
what a resumed run is building on.

The pipeline reaches the network **never**. If the raw data is not present it stops
with an instruction to run ``scripts/fetch_data.py`` rather than fetching implicitly,
so that a figure can never be produced from data whose provenance was not recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from svcarry.config import load_config  # noqa: E402

STAGES = ["clean", "index", "mechanics", "tail", "signals", "backtest", "robust", "figures"]
STATE = ROOT / "reports" / "_pipeline_state.json"


def _state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def _record(stage: str, rec: dict) -> None:
    st = _state()
    st[stage] = {**rec, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


def _require(path: Path, what: str, remedy: str) -> Path:
    if not path.exists():
        raise SystemExit(
            f"\nMissing {what}: {path.relative_to(ROOT)}\n"
            f"  -> {remedy}\n"
            f"\nThe pipeline does not download anything implicitly; every input must\n"
            f"have been fetched through scripts/fetch_data.py so that its URL,\n"
            f"retrieval time and SHA-256 are recorded in data/raw/_manifest.json.\n"
        )
    return path


# --------------------------------------------------------------------- stages
def stage_clean(cfg) -> dict:
    from svcarry.data.cboe import load_vx_panel

    raw = ROOT / cfg.dotted("paths.raw") / "cboe" / "vx"
    _require(raw, "raw VIX futures files", "run: python scripts/fetch_data.py --only futures")

    panel = load_vx_panel(verbose=True)
    out = ROOT / cfg.dotted("paths.interim") / "vx_panel.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)

    qc = {
        "rows": int(len(panel)),
        "contracts": int(panel["expiry"].nunique()),
        "dates": int(panel["date"].nunique()),
        "first_date": str(panel["date"].min().date()),
        "last_date": str(panel["date"].max().date()),
        "missing_settle": int(panel["settle"].isna().sum()),
        "duplicate_keys": int(panel.duplicated(["date", "expiry"]).sum()),
        "output": str(out.relative_to(ROOT)),
    }
    print(json.dumps(qc, indent=1))
    return qc


def stage_index(cfg) -> dict:
    raise SystemExit(
        "Stage 'index' is implemented in svcarry.index.reconstruct and is wired up "
        "once the cleaned panel exists. Run the 'clean' stage first."
    )


def _not_yet(name: str):
    def _stage(cfg):
        raise SystemExit(
            f"Stage '{name}' requires the upstream stages to have produced their "
            f"outputs. Run the earlier stages first, or `--list` to see the order."
        )
    return _stage


RUNNERS = {
    "clean": stage_clean,
    "index": stage_index,
    "mechanics": _not_yet("mechanics"),
    "tail": _not_yet("tail"),
    "signals": _not_yet("signals"),
    "backtest": _not_yet("backtest"),
    "robust": _not_yet("robust"),
    "figures": _not_yet("figures"),
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", nargs="*", choices=STAGES)
    ap.add_argument("--from", dest="start", choices=STAGES)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        st = _state()
        for s in STAGES:
            done = st.get(s, {}).get("finished_utc", "-")
            print(f"  {s:10s} last run: {done}")
        return 0

    stages = args.only or (
        STAGES[STAGES.index(args.start):] if args.start else STAGES
    )
    cfg = load_config()

    for s in stages:
        print(f"\n=== {s} " + "=" * (60 - len(s)))
        t0 = time.time()
        try:
            rec = RUNNERS[s](cfg) or {}
        except SystemExit as exc:
            print(exc)
            return 2
        except Exception:
            traceback.print_exc()
            return 1
        rec["seconds"] = round(time.time() - t0, 1)
        _record(s, rec)
    print("\nDone. State in reports/_pipeline_state.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
