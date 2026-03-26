from __future__ import annotations

from dataclasses import dataclass

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
        return ForecastResult(predictions=pd.DataFrame(columns=["date", "symbol", "prediction", "target"]))

    for i in range(train_min_days, len(dates) - test_step_days + 1, test_step_days):
        train_cutoff = dates[i]
        test_dates = dates[i : i + test_step_days]

        train = model_df[model_df["date"] < train_cutoff]
        test = model_df[model_df["date"].isin(test_dates)]
        if train.empty or test.empty:
            continue

        model = _new_model(model_name)
        model.fit(train[feature_cols], train["next_return"])
        test_pred = model.predict(test[feature_cols])

        fold = test[["date", "symbol", "next_return"]].copy()
        fold["prediction"] = test_pred
        fold = fold.rename(columns={"next_return": "target"})
        preds.append(fold)

    if not preds:
        return ForecastResult(predictions=pd.DataFrame(columns=["date", "symbol", "prediction", "target"]))

    out = pd.concat(preds, ignore_index=True)
    return ForecastResult(predictions=out)
