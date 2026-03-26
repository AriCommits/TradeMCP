from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PipelineConfig:
    raw: dict[str, Any]

    @property
    def features(self) -> dict[str, Any]:
        return self.raw["features"]

    @property
    def regime(self) -> dict[str, Any]:
        return self.raw["regime"]

    @property
    def volatility(self) -> dict[str, Any]:
        return self.raw["volatility"]

    @property
    def forecast(self) -> dict[str, Any]:
        return self.raw["forecast"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.raw["risk"]

    @property
    def execution(self) -> dict[str, Any]:
        return self.raw["execution"]


def load_config(path: str | Path) -> PipelineConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PipelineConfig(raw=raw)
