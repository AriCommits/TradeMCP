"""Internal construction helpers for canonical forecast records."""

from __future__ import annotations

from hashlib import sha256

import numpy as np

from trading.forecasts.targets import ForecastDistribution, ForecastRecord
from trading.forecasts.base import ForecastRequest


def make_record(
    request: ForecastRequest,
    *,
    model_id: str,
    samples: np.ndarray,
    calibration_metrics: dict[str, float],
    point_estimate: float | None = None,
    probabilities: dict[str, float] | None = None,
) -> ForecastRecord:
    clean = samples[np.isfinite(samples)].astype(float)
    if clean.size == 0:
        raise ValueError("forecast requires at least one completed point-in-time outcome")
    quantiles = {
        format(probability, ".6g"): float(np.quantile(clean, probability))
        for probability in request.quantiles
    }
    point = float(np.median(clean)) if point_estimate is None else float(point_estimate)
    identity = "|".join(
        (
            request.symbol,
            request.target.value,
            request.decision_at_utc.isoformat(),
            request.training_cutoff_utc.isoformat(),
            request.horizon.to_json(),
            model_id,
        )
    )
    forecast_id = sha256(identity.encode("utf-8")).hexdigest()[:24]
    return ForecastRecord(
        forecast_id=forecast_id,
        decision_at_utc=request.decision_at_utc,
        symbol=request.symbol,
        target=request.target,
        horizon=request.horizon,
        distribution=ForecastDistribution(
            point_estimate=point,
            quantiles=quantiles,
            probabilities=probabilities or {},
            sample_count=int(clean.size),
        ),
        model_id=model_id,
        model_version="1.0",
        training_cutoff_utc=request.training_cutoff_utc,
        feature_version="daily-bars-v1",
        calibration_metrics=calibration_metrics,
    )
