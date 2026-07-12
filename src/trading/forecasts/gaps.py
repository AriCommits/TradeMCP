"""Overnight and weekend gap distributions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.forecasts._outputs import make_record
from trading.forecasts.base import ForecastRequest, point_in_time_bars
from trading.forecasts.calibration import distribution_metrics
from trading.forecasts.targets import ForecastRecord, ForecastTarget
from trading.options.contracts import TimeHorizonKind


class GapForecaster:
    def __init__(self, weekend_only: bool = False) -> None:
        self.weekend_only = weekend_only
        self.model_id = "weekend_gap" if weekend_only else "overnight_gap"

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord:
        if request.target is not ForecastTarget.GAP_RETURN:
            raise ValueError("gap model requires gap_return target")
        if (
            request.horizon.kind is not TimeHorizonKind.OVERNIGHT_INTERVALS
            or request.horizon.count != 1
        ):
            raise ValueError("gap forecasts currently require one overnight interval")
        bars = point_in_time_bars(history, request)
        previous_close = bars["close"].shift(1)
        gaps = bars["open"] / previous_close - 1.0
        if self.weekend_only:
            previous_timestamp = bars["timestamp"].shift(1)
            elapsed = bars["timestamp"] - previous_timestamp
            gaps = gaps.loc[elapsed >= pd.Timedelta(days=2)]
        samples = gaps.dropna().to_numpy(dtype=float)
        metrics = distribution_metrics(samples)
        return make_record(
            request,
            model_id=self.model_id,
            samples=samples,
            calibration_metrics=metrics,
            probabilities={
                "gap_up": float(np.mean(samples > 0.0)),
                "gap_down": float(np.mean(samples < 0.0)),
            },
        )
