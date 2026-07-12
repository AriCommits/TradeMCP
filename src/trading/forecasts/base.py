"""Common inputs and point-in-time helpers for strategy-neutral forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd

from trading.forecasts.targets import ForecastRecord, ForecastTarget
from trading.options.contracts import TimeHorizon, TimeHorizonKind, require_utc


@dataclass(frozen=True)
class ForecastRequest:
    """A forecast query whose information boundary is explicit."""

    decision_at_utc: datetime
    training_cutoff_utc: datetime
    symbol: str
    target: ForecastTarget
    horizon: TimeHorizon
    lookback: int | None = None
    barrier: float | None = None
    barrier_direction: str = "below"
    quantiles: tuple[float, ...] = (0.05, 0.5, 0.95)

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        require_utc(self.training_cutoff_utc, "training_cutoff_utc")
        if self.training_cutoff_utc >= self.decision_at_utc:
            raise ValueError("training_cutoff_utc must strictly precede decision_at_utc")
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.lookback is not None and self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if self.barrier_direction not in {"above", "below"}:
            raise ValueError("barrier_direction must be 'above' or 'below'")
        if any(not 0.0 <= value <= 1.0 for value in self.quantiles):
            raise ValueError("quantiles must be probabilities in [0, 1]")


class Forecaster(Protocol):
    model_id: str

    def forecast(self, history: pd.DataFrame, request: ForecastRequest) -> ForecastRecord: ...


REQUIRED_BAR_COLUMNS = ("timestamp", "symbol", "open", "high", "low", "close")


def point_in_time_bars(history: pd.DataFrame, request: ForecastRequest) -> pd.DataFrame:
    """Return sorted bars visible at the training cutoff, never at the decision time."""

    missing = [column for column in REQUIRED_BAR_COLUMNS if column not in history.columns]
    if missing:
        raise ValueError(f"history missing required columns: {missing}")
    work = history.loc[history["symbol"] == request.symbol].copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.loc[work["timestamp"] <= pd.Timestamp(request.training_cutoff_utc)]
    work = work.sort_values("timestamp", kind="stable").drop_duplicates("timestamp", keep="last")
    for column in ("open", "high", "low", "close"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["open", "high", "low", "close"])
    if request.lookback is not None:
        work = work.tail(request.lookback)
    if work.empty:
        raise ValueError("no point-in-time history is available")
    return work.reset_index(drop=True)


def horizon_steps(horizon: TimeHorizon, decision_at_utc: datetime) -> int:
    """Return daily-bar steps only when the horizon is explicitly trading-day based."""

    require_utc(decision_at_utc, "decision_at_utc")
    if horizon.kind is not TimeHorizonKind.TRADING_DAYS:
        raise ValueError(
            f"{horizon.kind.value} requires an exchange-calendar-specific conversion "
            "and cannot be treated as trading-day bars"
        )
    assert horizon.count is not None
    return horizon.count
