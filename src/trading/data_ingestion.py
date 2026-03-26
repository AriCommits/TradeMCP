from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED_COLS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def read_ohlcv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert(None)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    return df


def preprocess_ohlcv(df: pd.DataFrame, vol_window: int) -> pd.DataFrame:
    work = df.copy()
    num_cols = ["open", "high", "low", "close", "volume"]

    for col in num_cols:
        work[col] = (
            work.groupby("symbol")[col]
            .transform(lambda s: s.interpolate(method="linear", limit_direction="both"))
            .astype(float)
        )

    work["log_close"] = np.log(work["close"].clip(lower=1e-12))
    work["log_return"] = work.groupby("symbol")["log_close"].diff()
    work["realized_vol"] = work.groupby("symbol")["log_return"].transform(
        lambda s: s.rolling(vol_window, min_periods=max(5, vol_window // 4)).std()
    )
    work["dollar_volume"] = work["close"] * work["volume"]
    work["next_return"] = work.groupby("symbol")["log_return"].shift(-1)
    return work


def robust_scale(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    work = df.copy()
    for col in columns:
        median = work[col].median()
        q75 = work[col].quantile(0.75)
        q25 = work[col].quantile(0.25)
        iqr = q75 - q25
        if not np.isfinite(iqr) or abs(iqr) < 1e-9:
            iqr = 1.0
        work[f"{col}_scaled"] = (work[col] - median) / iqr
    return work


def build_model_table(
    df: pd.DataFrame,
    return_lags: list[int],
    extra_feature_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    work = df.copy()
    feature_cols: list[str] = []

    for lag in return_lags:
        col = f"ret_lag_{lag}"
        work[col] = work.groupby("symbol")["log_return"].shift(lag)
        feature_cols.append(col)

    base_cols = [
        "realized_vol_scaled",
        "dollar_volume_scaled",
        "log_return_scaled",
    ]
    feature_cols.extend(base_cols)
    if extra_feature_cols:
        feature_cols.extend([c for c in extra_feature_cols if c in df.columns])

    model_df = work[["date", "symbol", *feature_cols, "next_return"]].dropna().reset_index(drop=True)
    return model_df, feature_cols


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
