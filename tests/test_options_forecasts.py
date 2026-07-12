from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trading.forecasts.base import ForecastRequest
from trading.forecasts.distributions import HistoricalDistributionForecaster
from trading.forecasts.gaps import GapForecaster
from trading.forecasts.probabilities import BarrierProbabilityForecaster, ExcursionForecaster
from trading.forecasts.realized_volatility import RealizedVolatilityForecaster
from trading.forecasts.registry import ForecastRegistry
from trading.forecasts.targets import ForecastTarget
from trading.options.contracts import TimeHorizon, TimeHorizonKind


UTC = timezone.utc


def history() -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=90, tz="UTC")
    trend = np.linspace(100.0, 112.0, len(dates))
    wave = np.sin(np.arange(len(dates)) / 4.0)
    close = trend + wave
    prior = np.r_[close[0], close[:-1]]
    open_price = prior * (1.0 + 0.002 * np.cos(np.arange(len(dates))))
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": "SPY",
            "open": open_price,
            "high": np.maximum(open_price, close) * 1.01,
            "low": np.minimum(open_price, close) * 0.99,
            "close": close,
        }
    )


def request(target: ForecastTarget, *, barrier: float | None = None) -> ForecastRequest:
    horizon = (
        TimeHorizon(TimeHorizonKind.OVERNIGHT_INTERVALS, count=1)
        if target is ForecastTarget.GAP_RETURN
        else TimeHorizon(TimeHorizonKind.TRADING_DAYS, count=5)
    )
    return ForecastRequest(
        decision_at_utc=datetime(2025, 5, 20, 20, tzinfo=UTC),
        training_cutoff_utc=datetime(2025, 5, 5, 20, tzinfo=UTC),
        symbol="SPY",
        target=target,
        horizon=horizon,
        barrier=barrier,
    )


@pytest.mark.parametrize(
    ("model", "target"),
    [
        (HistoricalDistributionForecaster(), ForecastTarget.RETURN),
        (HistoricalDistributionForecaster(), ForecastTarget.ABSOLUTE_RETURN),
        (RealizedVolatilityForecaster("historical"), ForecastTarget.REALIZED_VOLATILITY),
        (RealizedVolatilityForecaster("ewma"), ForecastTarget.REALIZED_VOLATILITY),
        (GapForecaster(), ForecastTarget.GAP_RETURN),
        (ExcursionForecaster(), ForecastTarget.MAX_UP_MOVE),
        (ExcursionForecaster(), ForecastTarget.MAX_DOWN_MOVE),
    ],
)
def test_forecasts_are_canonical_and_include_naive_comparison(model, target) -> None:
    result = model.forecast(history(), request(target))
    assert result.training_cutoff_utc < result.decision_at_utc
    assert result.target is target
    assert result.distribution.sample_count and result.distribution.sample_count > 0
    assert result.distribution.quantiles.keys() == {"0.05", "0.5", "0.95"}
    assert "naive_mae" in result.calibration_metrics


def test_future_rows_cannot_change_a_prior_forecast() -> None:
    baseline = history()
    query = request(ForecastTarget.REALIZED_VOLATILITY)
    model = RealizedVolatilityForecaster("ewma")
    first = model.forecast(baseline, query)
    future = pd.DataFrame(
        {
            "timestamp": [datetime(2025, 5, 19, 20, tzinfo=UTC)],
            "symbol": ["SPY"],
            "open": [1_000.0],
            "high": [2_000.0],
            "low": [1.0],
            "close": [1_500.0],
        }
    )
    second = model.forecast(pd.concat([baseline, future], ignore_index=True), query)
    assert first == second


def test_touch_and_finish_probabilities_are_calibrated() -> None:
    data = history()
    cutoff_spot = float(
        data.loc[data["timestamp"] <= pd.Timestamp("2025-05-05T20:00:00Z"), "close"].iloc[-1]
    )
    model = BarrierProbabilityForecaster()
    touch = model.forecast(
        data, request(ForecastTarget.TOUCH_PROBABILITY, barrier=cutoff_spot * 0.98)
    )
    finish = model.forecast(
        data, request(ForecastTarget.EXPIRATION_ITM_PROBABILITY, barrier=cutoff_spot * 0.98)
    )
    assert 0.0 <= touch.distribution.probabilities["touch"] <= 1.0
    assert 0.0 <= finish.distribution.probabilities["finish_beyond_barrier"] <= 1.0
    assert "naive_brier" in touch.calibration_metrics


def test_weekend_gap_only_uses_multi_day_closures() -> None:
    result = GapForecaster(weekend_only=True).forecast(
        history(), request(ForecastTarget.GAP_RETURN)
    )
    assert result.model_id == "weekend_gap"
    assert result.distribution.sample_count and result.distribution.sample_count < 30


def test_garch_explicitly_reports_fallback_when_sample_is_too_short() -> None:
    result = RealizedVolatilityForecaster("garch").forecast(
        history().head(20), request(ForecastTarget.REALIZED_VOLATILITY)
    )
    assert result.calibration_metrics["model_available"] == 0.0
    assert result.calibration_metrics["fallback_used"] == 1.0


def test_registry_is_explicit_and_rejects_duplicates() -> None:
    registry = ForecastRegistry()
    model = HistoricalDistributionForecaster()
    registry.register(model)
    assert registry.get(model.model_id) is model
    with pytest.raises(ValueError, match="already registered"):
        registry.register(model)


def test_request_rejects_non_point_in_time_cutoff() -> None:
    with pytest.raises(ValueError, match="strictly precede"):
        ForecastRequest(
            decision_at_utc=datetime(2025, 1, 1, tzinfo=UTC),
            training_cutoff_utc=datetime(2025, 1, 1, tzinfo=UTC),
            symbol="SPY",
            target=ForecastTarget.RETURN,
            horizon=TimeHorizon(TimeHorizonKind.CALENDAR_DAYS, count=1),
        )


def test_daily_bar_models_do_not_treat_calendar_days_as_trading_days() -> None:
    query = ForecastRequest(
        decision_at_utc=datetime(2025, 5, 20, 20, tzinfo=UTC),
        training_cutoff_utc=datetime(2025, 5, 5, 20, tzinfo=UTC),
        symbol="SPY",
        target=ForecastTarget.RETURN,
        horizon=TimeHorizon(TimeHorizonKind.CALENDAR_DAYS, count=3),
    )
    with pytest.raises(ValueError, match="exchange-calendar-specific"):
        HistoricalDistributionForecaster().forecast(history(), query)
