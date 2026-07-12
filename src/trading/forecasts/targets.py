"""Horizon-indexed, strategy-neutral forecast output contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite

from trading.options.contracts import TimeHorizon, VersionedRecord, require_utc


class ForecastTarget(str, Enum):
    RETURN = "return"
    REALIZED_VOLATILITY = "realized_volatility"
    ABSOLUTE_RETURN = "absolute_return"
    MAX_UP_MOVE = "max_up_move"
    MAX_DOWN_MOVE = "max_down_move"
    GAP_RETURN = "gap_return"
    IV_CHANGE = "iv_change"
    SKEW_CHANGE = "skew_change"
    BID_ASK_SPREAD = "bid_ask_spread"
    TOUCH_PROBABILITY = "touch_probability"
    EXPIRATION_ITM_PROBABILITY = "expiration_itm_probability"


@dataclass(frozen=True)
class ForecastDistribution(VersionedRecord):
    """Distribution summary; quantile keys are probabilities such as ``"0.05"``."""

    point_estimate: float | None
    quantiles: dict[str, float]
    probabilities: dict[str, float]
    sample_count: int | None = None

    def __post_init__(self) -> None:
        values = list(self.quantiles.values()) + list(self.probabilities.values())
        if self.point_estimate is not None:
            values.append(self.point_estimate)
        if not all(isfinite(value) for value in values):
            raise ValueError("forecast values must be finite")
        for key in self.quantiles:
            probability = float(key)
            if not 0.0 <= probability <= 1.0:
                raise ValueError("quantile keys must be probabilities in [0, 1]")
        if any(not 0.0 <= value <= 1.0 for value in self.probabilities.values()):
            raise ValueError("named probabilities must be in [0, 1]")
        if self.sample_count is not None and self.sample_count <= 0:
            raise ValueError("sample_count must be positive when supplied")


@dataclass(frozen=True)
class ForecastRecord(VersionedRecord):
    forecast_id: str
    decision_at_utc: datetime
    symbol: str
    target: ForecastTarget
    horizon: TimeHorizon
    distribution: ForecastDistribution
    model_id: str
    model_version: str
    training_cutoff_utc: datetime
    feature_version: str
    calibration_metrics: dict[str, float]

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        require_utc(self.training_cutoff_utc, "training_cutoff_utc")
        if self.training_cutoff_utc >= self.decision_at_utc:
            raise ValueError("training_cutoff_utc must strictly precede the decision timestamp")
        required = (
            self.forecast_id,
            self.symbol,
            self.model_id,
            self.model_version,
            self.feature_version,
        )
        if not all(required):
            raise ValueError("forecast identifiers and versions are required")
        if not all(isfinite(value) for value in self.calibration_metrics.values()):
            raise ValueError("calibration metrics must be finite")


@dataclass(frozen=True)
class ForecastBundle(VersionedRecord):
    bundle_id: str
    decision_at_utc: datetime
    symbol: str
    forecasts: tuple[ForecastRecord, ...]

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        if not self.bundle_id or not self.symbol:
            raise ValueError("bundle_id and symbol are required")
        if any(item.symbol != self.symbol for item in self.forecasts):
            raise ValueError("all forecasts must match the bundle symbol")
        if any(item.decision_at_utc != self.decision_at_utc for item in self.forecasts):
            raise ValueError("all forecasts must match the bundle decision timestamp")
        ids = {item.forecast_id for item in self.forecasts}
        if len(ids) != len(self.forecasts):
            raise ValueError("forecast_id values must be unique within a bundle")
