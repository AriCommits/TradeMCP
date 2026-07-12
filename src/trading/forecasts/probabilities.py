"""Path excursion, barrier-touch, and horizon-finish forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.forecasts._outputs import make_record
from trading.forecasts.base import ForecastRequest, horizon_steps, point_in_time_bars
from trading.forecasts.calibration import distribution_metrics, probability_metrics
from trading.forecasts.targets import ForecastRecord, ForecastTarget


def excursion_samples(bars: pd.DataFrame, steps: int, *, upward: bool) -> np.ndarray:
    if len(bars) <= steps:
        return np.array([], dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    values: list[float] = []
    for index in range(len(bars) - steps):
        entry = close[index]
        if upward:
            values.append(float(np.max(high[index + 1 : index + steps + 1]) / entry - 1.0))
        else:
            values.append(float(1.0 - np.min(low[index + 1 : index + steps + 1]) / entry))
    return np.asarray(values, dtype=float)


class ExcursionForecaster:
    model_id = "historical_excursion"

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord:
        if request.target not in {ForecastTarget.MAX_UP_MOVE, ForecastTarget.MAX_DOWN_MOVE}:
            raise ValueError("excursion model supports max_up_move and max_down_move")
        bars = point_in_time_bars(history, request)
        steps = horizon_steps(request.horizon, request.decision_at_utc)
        samples = excursion_samples(
            bars,
            steps,
            upward=request.target is ForecastTarget.MAX_UP_MOVE,
        )
        return make_record(
            request,
            model_id=self.model_id,
            samples=samples,
            calibration_metrics=distribution_metrics(samples),
        )


def barrier_outcomes(
    bars: pd.DataFrame, steps: int, *, relative_barrier: float, direction: str, touch: bool
) -> np.ndarray:
    close = bars["close"].to_numpy(dtype=float)
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    outcomes: list[float] = []
    for index in range(len(bars) - steps):
        barrier = close[index] * relative_barrier
        if touch and direction == "above":
            event = np.max(high[index + 1 : index + steps + 1]) >= barrier
        elif touch:
            event = np.min(low[index + 1 : index + steps + 1]) <= barrier
        elif direction == "above":
            event = close[index + steps] >= barrier
        else:
            event = close[index + steps] <= barrier
        outcomes.append(float(event))
    return np.asarray(outcomes, dtype=float)


class BarrierProbabilityForecaster:
    """Empirical probability at the requested barrier, scaled by current moneyness."""

    model_id = "empirical_barrier_probability"

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord:
        supported = {ForecastTarget.TOUCH_PROBABILITY, ForecastTarget.EXPIRATION_ITM_PROBABILITY}
        if request.target not in supported:
            raise ValueError("barrier model supports touch and expiration ITM probabilities")
        if request.barrier is None or request.barrier <= 0.0:
            raise ValueError("a positive barrier is required")
        bars = point_in_time_bars(history, request)
        steps = horizon_steps(request.horizon, request.decision_at_utc)
        relative_barrier = request.barrier / float(bars["close"].iloc[-1])
        touch = request.target is ForecastTarget.TOUCH_PROBABILITY
        outcomes = barrier_outcomes(
            bars,
            steps,
            relative_barrier=relative_barrier,
            direction=request.barrier_direction,
            touch=touch,
        )
        probability = float(np.mean(outcomes)) if outcomes.size else 0.0
        name = "touch" if touch else "finish_beyond_barrier"
        return make_record(
            request,
            model_id=self.model_id,
            samples=outcomes,
            point_estimate=probability,
            probabilities={name: probability},
            calibration_metrics=probability_metrics(outcomes),
        )
