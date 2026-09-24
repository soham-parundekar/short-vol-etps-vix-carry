#!/usr/bin/env python3
"""Zero-dependency test runner.

The test suite is written as ordinary ``pytest`` tests. If ``pytest`` is installed,
use it (``pytest -q``) and this script simply delegates. If it is not — which is the
case in some locked-down environments — this script installs a minimal in-process
shim that provides the small slice of the pytest API the suite actually uses
(``mark.parametrize``, ``approx``, ``raises``, ``skip``, ``fixture``) and runs the
tests itself.

Usage
-----
    python scripts/run_tests.py                 # whole suite
    python scripts/run_tests.py test_calendar   # files matching a substring
    python scripts/run_tests.py -k roll         # test functions matching a substring
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import inspect
import math
import re
import shutil
import sys
import tempfile
import traceback
import types
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"


# --------------------------------------------------------------------------- shim
class _Approx:
    # Make NumPy defer ``ndarray == approx(...)`` to this class rather than
    # broadcasting an element-wise comparison.
    __array_ufunc__ = None
    __array_priority__ = 1000.0

    def __init__(self, expected, rel=1e-6, abs_=1e-12):
        self.expected, self.rel, self.abs = expected, rel, abs_

    def __eq__(self, other):
        try:
            import numpy as np

            a, b = np.asarray(other, dtype=float), np.asarray(self.expected, dtype=float)
            if a.shape != b.shape:
                return False
            return bool(
                np.all(np.isclose(a, b, rtol=self.rel, atol=self.abs, equal_nan=True))
            )
        except Exception:
            return math.isclose(float(other), float(self.expected),
                                rel_tol=self.rel, abs_tol=self.abs)

    def __repr__(self):
        return f"approx({self.expected!r}, rel={self.rel}, abs={self.abs})"


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match = exc, match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc}")
        if not issubclass(et, self.exc):
            return False
        self.value = ev
        if self.match is not None and not re.search(self.match, str(ev)):
            raise AssertionError(
                f"pattern {self.match!r} not found in {str(ev)!r}"
            )
        return True


class _Warns:
    """``pytest.warns`` for the shim: assert a warning of a category was issued."""

    def __init__(self, category, match=None):
        self.category, self.match = category, match
        self.list: list = []

    def __enter__(self):
        self._cm = warnings.catch_warnings(record=True)
        self.list = self._cm.__enter__()
        warnings.simplefilter("always")
        return self

    def __exit__(self, et, ev, tb):
        self._cm.__exit__(et, ev, tb)
        if et is not None:
            return False
        hits = [w for w in self.list if issubclass(w.category, self.category)]
        if not hits:
            raise AssertionError(
                f"DID NOT WARN {self.category.__name__}; got "
                f"{[w.category.__name__ for w in self.list]}"
            )
        if self.match is not None and not any(
            re.search(self.match, str(w.message)) for w in hits
        ):
            raise AssertionError(
                f"pattern {self.match!r} not found in "
                f"{[str(w.message) for w in hits]}"
            )
        return False


class _MonkeyPatch:
    """The slice of ``monkeypatch`` the suite uses, with an undo stack."""

    def __init__(self):
        self._undo: list = []

    def setattr(self, target, name, value=None, raising: bool = True):
        if value is None and isinstance(target, str):      # "mod.attr" form
            modname, _, name = target.rpartition(".")
            target = importlib.import_module(modname)
        old = getattr(target, name, _MISSING)
        if old is _MISSING and raising:
            raise AttributeError(f"{target!r} has no attribute {name!r}")
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def delattr(self, target, name, raising: bool = True):
        old = getattr(target, name, _MISSING)
        if old is _MISSING:
            if raising:
                raise AttributeError(name)
            return
        self._undo.append((target, name, old))
        delattr(target, name)

    def setenv(self, name, value):
        import os

        self._undo.append((os.environ, name, os.environ.get(name, _MISSING)))
        os.environ[name] = str(value)

    def undo(self):
        while self._undo:
            target, name, old = self._undo.pop()
            if isinstance(target, dict):
                if old is _MISSING:
                    target.pop(name, None)
                else:
                    target[name] = old
            elif old is _MISSING:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
            else:
                setattr(target, name, old)


_MISSING = object()


class _Skipped(Exception):
    pass


def _make_shim() -> types.ModuleType:
    mod = types.ModuleType("pytest")

    def parametrize(argnames, argvalues, ids=None):
        names = [a.strip() for a in argnames.split(",")] if isinstance(argnames, str) else list(argnames)

        def deco(fn):
            cases = getattr(fn, "_mini_cases", [])
            for vals in argvalues:
                vals = vals if isinstance(vals, (tuple, list)) else (vals,)
                cases.append(dict(zip(names, vals)))
            fn._mini_cases = cases
            return fn

        return deco

    _param = parametrize

    # allow arbitrary unknown marks (@pytest.mark.slow etc.) to be no-ops
    class _Mark:
        parametrize = staticmethod(_param)

        def __getattr__(self, _name):
            def _noop(*a, **k):
                if a and callable(a[0]):
                    return a[0]
                return lambda f: f
            return _noop

    mod.mark = _Mark()
    mod.approx = lambda expected, rel=1e-6, abs=1e-12: _Approx(expected, rel, abs)
    mod.raises = lambda exc, match=None, **_k: _Raises(exc, match)
    mod.warns = lambda category, match=None, **_k: _Warns(category, match)

    def skip(reason=""):
        raise _Skipped(reason)

    mod.skip = skip
    mod.fail = lambda msg="": (_ for _ in ()).throw(AssertionError(msg))

    def fixture(*a, **k):
        """Mark a function as a fixture so the runner can resolve it by name."""

        def tag(fn):
            fn._mini_fixture = True
            return fn

        if a and callable(a[0]):
            return tag(a[0])
        return tag

    mod.fixture = fixture
    mod.importorskip = lambda name, **k: __import__(name)
    mod._is_mini_shim = True
    return mod


# --------------------------------------------------------------------------- run
def _load(path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def _reset_global_state() -> None:
    """Drop process-wide state a test may have left behind.

    Only pyplot so far. A test that builds a figure and does not save it leaves it
    registered with pyplot, which retains figures until they are closed; the suite used
    to accumulate them and matplotlib warned about it partway through ``test_viz``
    (final audit A-04). Closing here rather than in twenty tests means the harness
    guarantees the isolation instead of each test remembering to. ``tests/conftest.py``
    does the same for a real pytest run.
    """
    mod = sys.modules.get("matplotlib.pyplot")
    if mod is not None:
        mod.close("all")


def _call_with_fixtures(fn, mod, kw: dict, stack: contextlib.ExitStack):
    """Resolve a test's fixture arguments and call it.

    Supports the two built-ins the suite needs (``tmp_path``, ``monkeypatch``) plus
    any module-level function decorated with ``@pytest.fixture``, including fixtures
    that themselves request fixtures and fixtures written as generators. Everything
    is torn down through ``stack`` when the test finishes.
    """
    cache: dict = {}

    def resolve(name):
        if name in kw:
            return kw[name]
        if name in cache:
            return cache[name]
        if name == "tmp_path":
            d = Path(tempfile.mkdtemp(prefix="svcarry-test-"))
            stack.callback(shutil.rmtree, d, ignore_errors=True)
            val = d
        elif name == "monkeypatch":
            mp = _MonkeyPatch()
            stack.callback(mp.undo)
            val = mp
        else:
            factory = getattr(mod, name, None)
            if factory is None or not getattr(factory, "_mini_fixture", False):
                raise AssertionError(f"unknown fixture {name!r}")
            args = {p: resolve(p) for p in inspect.signature(factory).parameters}
            out = factory(**args)
            if inspect.isgenerator(out):
                gen = out
                val = next(gen)
                stack.callback(lambda g=gen: next(g, None))
            else:
                val = out
        cache[name] = val
        return val

    args = {p: resolve(p) for p in inspect.signature(fn).parameters}
    return fn(**args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", nargs="?", default="", help="substring of test file name")
    ap.add_argument("-k", dest="kfilter", default="", help="substring of test function name")
    ap.add_argument("-v", dest="verbose", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(TESTS))

    try:
        import pytest  # noqa: F401  (real pytest present)
        have_real = not getattr(pytest, "_is_mini_shim", False)
    except ImportError:
        have_real = False
    if not have_real:
        sys.modules["pytest"] = _make_shim()
        print("[run_tests] pytest not installed - using built-in shim\n")

    files = sorted(p for p in TESTS.glob("test_*.py") if args.pattern in p.stem)
    if not files:
        print(f"no test files match {args.pattern!r}")
        return 1

    passed = failed = skipped = 0
    failures: list[tuple[str, str]] = []

    for f in files:
        try:
            mod = _load(f)
        except Exception:
            failed += 1
            failures.append((f.name, traceback.format_exc()))
            print(f"{f.name}: COLLECTION ERROR")
            continue

        names = [n for n in dir(mod) if n.startswith("test_")]
        names = [n for n in names if args.kfilter in n]
        line = f"{f.stem:28s} "
        for n in sorted(names):
            fn = getattr(mod, n)
            cases = getattr(fn, "_mini_cases", [{}])
            for kw in cases:
                label = f"{f.stem}::{n}" + (f"[{','.join(map(str, kw.values()))}]" if kw else "")
                try:
                    with contextlib.ExitStack() as stack:
                        _call_with_fixtures(fn, mod, kw, stack)
                    passed += 1
                    line += "."
                except _Skipped as e:
                    skipped += 1
                    line += "s"
                except Exception:
                    failed += 1
                    line += "F"
                    failures.append((label, traceback.format_exc()))
                _reset_global_state()
                if args.verbose:
                    pass
        print(line)

    print()
    for label, tb in failures:
        print("=" * 78)
        print("FAIL:", label)
        print(tb)
    total = passed + failed + skipped
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped  (of {total})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
