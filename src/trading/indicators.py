from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_INDICATORS = ["rsi_14", "atr_14", "macd_line", "macd_signal", "macd_hist"]


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    return macd_line, macd_signal, macd_hist


def add_native_indicators(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    cols = set(columns)
    out_parts = []
    for _, sdf in df.groupby("symbol", sort=False):
        s = sdf.copy()
        if "rsi_14" in cols:
            s["rsi_14"] = _rsi(s["close"], period=14)
        if "atr_14" in cols:
            s["atr_14"] = _atr(s["high"], s["low"], s["close"], period=14)
        if {"macd_line", "macd_signal", "macd_hist"} & cols:
            line, signal, hist = _macd(s["close"])
            s["macd_line"] = line
            s["macd_signal"] = signal
            s["macd_hist"] = hist
        out_parts.append(s)
    return pd.concat(out_parts, ignore_index=True)


def add_indicators(
    df: pd.DataFrame,
    enabled: bool,
    source: str = "native",
    columns: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    if not enabled:
        return df, []

    cols = columns or DEFAULT_INDICATORS
    source = source.lower()

    if source == "native":
        return add_native_indicators(df, cols), cols

    # Placeholder for third-party indicator engines (ta-lib, ta, custom Rust bindings, etc.).
    # For now we safely fall back to native implementations.
    return add_native_indicators(df, cols), cols


def select_model_indicator_features(df: pd.DataFrame, indicator_cols: list[str], use_scaled: bool) -> list[str]:
    features: list[str] = []
    for col in indicator_cols:
        scaled = f"{col}_scaled"
        if use_scaled and scaled in df.columns:
            features.append(scaled)
        elif col in df.columns and np.isfinite(df[col]).any():
            features.append(col)
    return features
