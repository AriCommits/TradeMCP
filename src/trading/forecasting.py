from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.neural_network import MLPRegressor


@dataclass
class ForecastResult:
    predictions: pd.DataFrame


def _new_model(model_name: str):
    model_name = model_name.lower()
    if model_name == "mlp":
        return MLPRegressor(hidden_layer_sizes=(64, 32), random_state=42, max_iter=300)
    return GradientBoostingRegressor(random_state=42)


def _fit_fold_preprocessor(
    train: pd.DataFrame,
    feature_cols: list[str],
) -> dict[str, tuple[float, float]]:
    """Fit imputation and robust-scaling statistics on one training fold."""
    params: dict[str, tuple[float, float]] = {}
    for col in feature_cols:
        values = pd.to_numeric(train[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if col.endswith("_missing"):
            params[col] = (1.0, 1.0)
            continue
        median = float(values.median())
        q75 = float(values.quantile(0.75))
        q25 = float(values.quantile(0.25))
        iqr = q75 - q25
        if not np.isfinite(median):
            median = 0.0
        if not np.isfinite(iqr) or abs(iqr) < 1e-9:
            iqr = 1.0
        params[col] = (median, iqr)
    return params


def _apply_fold_preprocessor(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    transformed = pd.DataFrame(index=frame.index)
    for col in feature_cols:
        values = pd.to_numeric(frame[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        median, iqr = params[col]
        if col.endswith("_missing"):
            transformed[col] = values.fillna(median)
        else:
            transformed[col] = (values.fillna(median) - median) / iqr
    return transformed


def walk_forward_forecast(
    model_df: pd.DataFrame,
    feature_cols: list[str],
    train_min_days: int,
    test_step_days: int,
    model_name: str,
) -> ForecastResult:
    dates = sorted(model_df["date"].unique())
    preds = []

    if len(dates) <= train_min_days + test_step_days:
        return ForecastResult(
            predictions=pd.DataFrame(columns=["date", "symbol", "prediction", "target"])
        )

    for i in range(train_min_days, len(dates) - test_step_days + 1, test_step_days):
        train_cutoff = dates[i]
        test_dates = dates[i : i + test_step_days]

        train = model_df[model_df["date"] < train_cutoff]
        test = model_df[model_df["date"].isin(test_dates)]
        if train.empty or test.empty:
            continue

        preprocessing = _fit_fold_preprocessor(train, feature_cols)
        train_features = _apply_fold_preprocessor(train, feature_cols, preprocessing)
        test_features = _apply_fold_preprocessor(test, feature_cols, preprocessing)

        model = _new_model(model_name)
        model.fit(train_features, train["next_return"])
        test_pred = model.predict(test_features)

        fold = test[["date", "symbol", "next_return"]].copy()
        fold["prediction"] = test_pred
        fold = fold.rename(columns={"next_return": "target"})
        preds.append(fold)

    if not preds:
        return ForecastResult(
            predictions=pd.DataFrame(columns=["date", "symbol", "prediction", "target"])
        )

    out = pd.concat(preds, ignore_index=True)
    return ForecastResult(predictions=out)
