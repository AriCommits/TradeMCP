from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt

from trading.data_ingestion import build_model_table, causal_robust_scale, preprocess_ohlcv
from trading.forecasting import walk_forward_forecast


def _ohlcv(periods: int = 36) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    close = 100.0 + np.linspace(0.0, 8.0, periods) + np.sin(np.arange(periods) / 3.0)
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": "SPY",
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000.0 + np.arange(periods) * 1_000.0,
        }
    )


def test_preprocessing_does_not_backfill_missing_market_values() -> None:
    raw = _ohlcv(12)
    raw.loc[0, "close"] = np.nan
    processed = preprocess_ohlcv(raw, vol_window=5)
    assert np.isnan(processed.loc[0, "close"])
    assert processed.loc[0, "close_missing"] == 1
    assert processed.loc[1, "close_missing"] == 0


def test_future_changes_do_not_change_earlier_causal_scaled_features() -> None:
    base = preprocess_ohlcv(_ohlcv(), vol_window=5)
    changed = base.copy()
    changed.loc[changed.index[-1], "volume"] *= 1_000_000
    changed["dollar_volume"] = changed["close"] * changed["volume"]
    cutoff = base["date"].iloc[-2]
    scaled_base = causal_robust_scale(base, ["dollar_volume", "log_return"])
    scaled_changed = causal_robust_scale(changed, ["dollar_volume", "log_return"])
    cols = ["dollar_volume_scaled", "log_return_scaled"]
    pdt.assert_frame_equal(
        scaled_base.loc[scaled_base["date"] <= cutoff, cols].reset_index(drop=True),
        scaled_changed.loc[scaled_changed["date"] <= cutoff, cols].reset_index(drop=True),
    )


def test_future_feature_changes_do_not_change_earlier_walk_forward_predictions() -> None:
    processed = preprocess_ohlcv(_ohlcv(), vol_window=5)
    model_df, features = build_model_table(processed, return_lags=[1, 2])
    kwargs = dict(
        feature_cols=features, train_min_days=12, test_step_days=3, model_name="gradient_boosting"
    )
    baseline = walk_forward_forecast(model_df, **kwargs).predictions
    changed = model_df.copy()
    future_start = sorted(changed["date"].unique())[-4]
    changed.loc[changed["date"] >= future_start, "dollar_volume"] *= 1_000_000
    revised = walk_forward_forecast(changed, **kwargs).predictions
    pdt.assert_frame_equal(
        baseline[baseline["date"] < future_start].reset_index(drop=True),
        revised[revised["date"] < future_start].reset_index(drop=True),
    )


def test_walk_forward_imputes_from_training_fold_only() -> None:
    processed = preprocess_ohlcv(_ohlcv(), vol_window=5)
    model_df, features = build_model_table(processed, return_lags=[1])
    first_test_date = sorted(model_df["date"].unique())[12]
    model_df.loc[model_df["date"] == first_test_date, "dollar_volume"] = np.nan
    model_df.loc[model_df["date"] == first_test_date, "dollar_volume_missing"] = 1
    result = walk_forward_forecast(
        model_df,
        feature_cols=features,
        train_min_days=12,
        test_step_days=2,
        model_name="gradient_boosting",
    ).predictions
    assert not result.empty
    assert np.isfinite(result["prediction"]).all()
