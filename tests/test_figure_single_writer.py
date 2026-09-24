"""One writer per figure, checked rather than described.

Twenty of the twenty-four figures used to be drawn twice: once in the analysis stage
that produced their inputs, and once in ``scripts/make_figures.py``. The two
implementations had drifted, and six of the twenty came out byte-different depending on
which path ran last. A full pipeline run hid it, because ``stage_figures`` runs last and
overwrote the stage versions; a partial run such as ``--only tail`` left a committed
figure quietly modified.

``stage_figures``'s own docstring had claimed the figures were in one script throughout.
These tests make that claim checkable (recursive audit A-12).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "run_pipeline.py"
MAKE_FIGURES = ROOT / "scripts" / "make_figures.py"
FIGDIR = ROOT / "reports" / "figures"


def _make_figures_registry() -> set[str]:
    """Figure names registered in make_figures.FIGURES, read without importing it."""
    tree = ast.parse(MAKE_FIGURES.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FIGURES" for t in node.targets
        ):
            assert isinstance(node.value, ast.Dict)
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("FIGURES registry not found in make_figures.py")


def test_pipeline_does_not_write_figures_outside_stage_figures():
    """The only save_figure call in the pipeline is the one inside stage_figures."""
    src = PIPELINE.read_text(encoding="utf-8")
    calls = [m for m in re.finditer(r"(?<![\w.])save_figure\s*\(", src)]
    qualified = [m for m in re.finditer(r"\bmod\.save_figure\s*\(", src)]
    assert len(qualified) == 1, "stage_figures should call mod.save_figure exactly once"
    assert not calls, (
        "an analysis stage is drawing figures again; every figure belongs to "
        f"make_figures.py (found {len(calls)} unqualified save_figure call(s))"
    )


def test_no_figure_path_is_constructed_in_an_analysis_stage():
    """No stage builds a ``figdir / "...png"`` destination any more."""
    src = PIPELINE.read_text(encoding="utf-8")
    hits = re.findall(r'figdir\s*/\s*f?"[^"]+\.png"', src)
    assert not hits, f"figure destinations still built in the pipeline: {hits}"


def test_every_committed_figure_has_exactly_one_registered_builder():
    registry = _make_figures_registry()
    committed = {p.stem for p in FIGDIR.glob("*.png")}
    assert committed, "no committed figures found"
    assert committed == registry, (
        "committed figures and the make_figures registry disagree; "
        f"only committed: {sorted(committed - registry)}; "
        f"only registered: {sorted(registry - committed)}"
    )


def test_registry_has_no_duplicate_names():
    """A dict literal would silently swallow a repeated key, so check the source."""
    src = MAKE_FIGURES.read_text(encoding="utf-8")
    body = src[src.index("FIGURES"):]
    names = re.findall(r'^\s{4}"([a-z0-9_]+)":\s*\(', body, re.M)
    assert len(names) == len(set(names)), "duplicate figure name in the registry"
