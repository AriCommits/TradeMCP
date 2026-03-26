from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level mapping in config: {path}")
    return data


def env_or_none(name: str | None) -> str | None:
    if not name:
        return None
    value = os.environ.get(name)
    return value if value not in {"", None} else None
