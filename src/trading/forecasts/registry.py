"""Explicit registry for interchangeable market-state forecasters."""

from __future__ import annotations

from trading.forecasts.base import Forecaster


class ForecastRegistry:
    def __init__(self) -> None:
        self._models: dict[str, Forecaster] = {}

    def register(self, forecaster: Forecaster) -> None:
        if forecaster.model_id in self._models:
            raise ValueError(f"forecast model already registered: {forecaster.model_id}")
        self._models[forecaster.model_id] = forecaster

    def get(self, model_id: str) -> Forecaster:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown forecast model: {model_id}") from exc

    def model_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._models))
