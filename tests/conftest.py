"""Test-suite wide setup.

The suite is written as ordinary pytest tests and also runs under the zero-dependency
shim in ``scripts/run_tests.py``. This file covers the pytest path; the shim does the
same work in ``_reset_global_state``.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every pyplot figure after each test.

    A test that builds a figure and does not save it leaves it registered with pyplot,
    which retains figures until closed. The suite used to accumulate them and matplotlib
    warned partway through ``test_viz`` (final audit A-04). Doing it here means the
    harness guarantees the isolation rather than each test remembering to.
    """
    yield
    mod = sys.modules.get("matplotlib.pyplot")
    if mod is not None:
        mod.close("all")
