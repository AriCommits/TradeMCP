"""Historical, EWMA, and optional GARCH strategy-neutral volatility forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading.forecasts._outputs import make_record
from trading.forecasts.base import ForecastRequest, horizon_steps, point_in_time_bars
from trading.forecasts.calibration import distribution_metrics
from trading.forecasts.targets import ForecastRecord, ForecastTarget

try:
    from arch import arch_model
except Exception:  # pragma: no cover - optional native dependency
    arch_model = None


def realized_volatility_samples(close: np.ndarray, steps: int) -> np.ndarray:
    returns = np.diff(np.log(close))
    if returns.size < steps:
        return np.array([], dtype=float)
    return np.asarray(
        [
            np.sqrt(np.mean(returns[index : index + steps] ** 2) * 252.0)
            for index in range(returns.size - steps + 1)
        ],
        dtype=float,
    )


def ewma_annualized(returns: np.ndarray, decay: float) -> float:
    if returns.size == 0:
        raise ValueError("EWMA requires at least one return")
    variance = float(np.var(returns))
    for value in returns:
        variance = decay * variance + (1.0 - decay) * float(value**2)
    return float(np.sqrt(max(variance, 0.0) * 252.0))


class RealizedVolatilityForecaster:
    def __init__(self, method: str = "historical", ewma_decay: float = 0.94) -> None:
        method = method.lower()
        if method not in {"historical", "ewma", "garch"}:
            raise ValueError("method must be historical, ewma, or garch")
        if not 0.0 < ewma_decay < 1.0:
            raise ValueError("ewma_decay must be in (0, 1)")
        self.method = method
        self.ewma_decay = ewma_decay
        self.model_id = f"realized_volatility_{method}"

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord:
        if request.target is not ForecastTarget.REALIZED_VOLATILITY:
            raise ValueError("realized volatility model requires realized_volatility target")
        bars = point_in_time_bars(history, request)
        close = bars["close"].to_numpy(dtype=float)
        steps = horizon_steps(request.horizon, request.decision_at_utc)
        samples = realized_volatility_samples(close, steps)
        metrics = distribution_metrics(samples)
        returns = np.diff(np.log(close))
        if self.method == "historical":
            point = float(np.median(samples)) if samples.size else 0.0
            metrics["model_available"] = 1.0
        elif self.method == "ewma":
            point = ewma_annualized(returns, self.ewma_decay)
            metrics["model_available"] = 1.0
        elif arch_model is None or returns.size < 30:
            point = ewma_annualized(returns, self.ewma_decay)
            metrics["model_available"] = 0.0
            metrics["fallback_used"] = 1.0
        else:
            fitted = arch_model(returns * 100.0, mean="Zero", vol="GARCH", p=1, q=1).fit(disp="off")
            variance = float(fitted.forecast(horizon=steps).variance.values[-1].mean()) / 10_000.0
            point = float(np.sqrt(max(variance, 0.0) * 252.0))
            metrics["model_available"] = 1.0
            metrics["fallback_used"] = 0.0
        return make_record(
            request,
            model_id=self.model_id,
            samples=samples,
            point_estimate=point,
            calibration_metrics=metrics,
        )
