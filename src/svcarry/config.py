"""Configuration loading and path resolution.

One YAML file (``config/config.yaml``) holds every parameter a reviewer might want
to vary. Code reads it through :func:`load_config`; nothing in ``src`` hard-codes a
sample window, a fee, a threshold or a transaction-cost assumption.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

__all__ = ["PROJECT_ROOT", "load_config", "Config", "resolve_path"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


class Config(dict):
    """Dict with attribute access and dotted lookup, e.g. ``cfg.get_path('paths.raw')``."""

    def __getattr__(self, item: str) -> Any:
        try:
            v = self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc
        return Config(v) if isinstance(v, dict) else v

    def dotted(self, key: str, default: Any = "__raise__") -> Any:
        node: Any = self
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif default != "__raise__":
                return default
            else:
                raise KeyError(f"{key!r} not found in configuration")
        return Config(node) if isinstance(node, dict) else node

    def get_path(self, key: str) -> Path:
        """Resolve a ``paths.*`` entry to an absolute path, creating the directory."""
        p = resolve_path(self.dotted(key))
        p.mkdir(parents=True, exist_ok=True)
        return p


def resolve_path(p: str | os.PathLike) -> Path:
    p = Path(p)
    return p if p.is_absolute() else PROJECT_ROOT / p


_CACHE: dict[str, Config] = {}


def load_config(path: str | os.PathLike | None = None, reload: bool = False) -> Config:
    """Load and cache the project configuration."""
    path = Path(path) if path is not None else DEFAULT_CONFIG
    key = str(path.resolve())
    if reload or key not in _CACHE:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        _CACHE[key] = Config(data)
    return Config(copy.deepcopy(dict(_CACHE[key])))
