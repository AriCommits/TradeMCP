"""Historical rolling distributions for returns and absolute returns."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.forecasts._outputs import make_record
from trading.forecasts.base import ForecastRequest, horizon_steps, point_in_time_bars
from trading.forecasts.calibration import distribution_metrics
from trading.forecasts.targets import ForecastRecord, ForecastTarget


def forward_returns(close: np.ndarray, steps: int) -> np.ndarray:
    if close.size <= steps:
        return np.array([], dtype=float)
    result = np.asarray(close[steps:] / close[:-steps] - 1.0, dtype=float)
    return result


class HistoricalDistributionForecaster:
    """Empirical point-in-time distribution for horizon return or absolute return."""

    model_id = "historical_distribution"

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord:
        if request.target not in {ForecastTarget.RETURN, ForecastTarget.ABSOLUTE_RETURN}:
            raise ValueError("historical distribution supports return and absolute_return")
        bars = point_in_time_bars(history, request)
        steps = horizon_steps(request.horizon, request.decision_at_utc)
        samples = forward_returns(bars["close"].to_numpy(dtype=float), steps)
        if request.target is ForecastTarget.ABSOLUTE_RETURN:
            samples = np.abs(samples)
        metrics = distribution_metrics(samples)
        probability = float(np.mean(samples > 0.0)) if samples.size else 0.0
        return make_record(
            request,
            model_id=self.model_id,
            samples=samples,
            calibration_metrics=metrics,
            probabilities={"positive": probability},
        )
