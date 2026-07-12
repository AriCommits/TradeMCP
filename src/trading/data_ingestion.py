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
        # Keep missing observations missing. Bidirectional interpolation can use
        # a quote that had not arrived yet; model-compatible imputation belongs
        # inside each walk-forward training fold.
        work[col] = (
            pd.to_numeric(work[col], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .astype(float)
        )
        work[f"{col}_missing"] = work[col].isna().astype("int8")

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


def causal_robust_scale(
    df: pd.DataFrame,
    columns: list[str],
    date_col: str = "date",
) -> pd.DataFrame:
    """Robust-scale each date using observations available through that date."""
    work = df.copy()
    if work.empty:
        for col in columns:
            work[f"{col}_scaled"] = pd.Series(dtype=float)
        return work

    dates = pd.to_datetime(work[date_col])
    for col in columns:
        values = pd.to_numeric(work[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        scaled = pd.Series(np.nan, index=work.index, dtype=float)
        for date in sorted(dates.dropna().unique()):
            history = values[dates <= date]
            median = history.median()
            q75 = history.quantile(0.75)
            q25 = history.quantile(0.25)
            iqr = q75 - q25
            if not np.isfinite(median):
                median = 0.0
            if not np.isfinite(iqr) or abs(iqr) < 1e-9:
                iqr = 1.0
            current = dates == date
            scaled.loc[current] = (values.loc[current] - median) / iqr
        work[f"{col}_scaled"] = scaled
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

    base_cols = ["realized_vol", "dollar_volume", "log_return"]
    feature_cols.extend(base_cols)
    if extra_feature_cols:
        feature_cols.extend([c for c in extra_feature_cols if c in df.columns])

    feature_cols = list(dict.fromkeys(feature_cols))
    missing_cols: list[str] = []
    for col in feature_cols:
        missing_col = f"{col}_missing"
        if missing_col not in work:
            work[missing_col] = work[col].isna().astype("int8")
        missing_cols.append(missing_col)

    all_features = [*feature_cols, *missing_cols]
    model_df = (
        work[["date", "symbol", *all_features, "next_return"]]
        .dropna(subset=["date", "symbol", "next_return"])
        .reset_index(drop=True)
    )
    return model_df, all_features


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
