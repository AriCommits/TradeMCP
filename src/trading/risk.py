from __future__ import annotations

import numpy as np
import pandas as pd


def _rolling_zscore(group: pd.Series, window: int) -> pd.Series:
    mean = group.rolling(window, min_periods=max(5, window // 4)).mean()
    std = group.rolling(window, min_periods=max(5, window // 4)).std()
    z = (group - mean) / (std + 1e-9)
    return z.fillna(0.0)


def build_orders(
    predictions: pd.DataFrame,
    vol_forecasts: pd.DataFrame,
    signal_z_window: int,
    vol_gate_quantile: float,
    target_portfolio_risk: float,
    max_position_abs: float,
) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()

    merged = predictions.merge(vol_forecasts[["date", "symbol", "vol_forecast", "regime"]], on=["date", "symbol"], how="left")
    merged["vol_forecast"] = merged["vol_forecast"].fillna(merged["target"].rolling(20, min_periods=5).std().fillna(0.01))
    merged["signal_z"] = merged.groupby("symbol")["prediction"].transform(
        lambda s: _rolling_zscore(s, signal_z_window)
    )

    merged["date_vol_gate"] = merged.groupby("date")["vol_forecast"].transform(
        lambda s: s.quantile(vol_gate_quantile)
    )
    merged["trade_allowed"] = merged["vol_forecast"] <= merged["date_vol_gate"]

    merged["raw_weight"] = np.where(
        merged["trade_allowed"],
        merged["signal_z"] / (merged["vol_forecast"].abs() + 1e-6),
        0.0,
    )

    gross = merged.groupby("date")["raw_weight"].transform(lambda s: s.abs().sum())
    merged["position"] = np.where(gross > 0, target_portfolio_risk * merged["raw_weight"] / gross, 0.0)
    merged["position"] = merged["position"].clip(-max_position_abs, max_position_abs)

    merged["expected_edge_bps"] = merged["prediction"] * 10_000.0
    merged["realized_pnl"] = merged["position"] * merged["target"]
    return merged


def summarize_performance(orders: pd.DataFrame) -> dict[str, float]:
    if orders.empty:
        return {"mean_daily_return": 0.0, "vol_daily_return": 0.0, "sharpe": 0.0, "cum_return": 0.0}

    pnl = orders["realized_pnl"]
    if isinstance(pnl, pd.DataFrame):
        pnl = pnl.iloc[:, 0]
    daily = orders.assign(_realized_pnl=pnl).groupby("date")["_realized_pnl"].sum().sort_index()
    mean = float(daily.mean())
    vol = float(daily.std())
    sharpe = float((mean / (vol + 1e-12)) * np.sqrt(252.0))
    cum = float((1.0 + daily).prod() - 1.0)

    return {
        "mean_daily_return": mean,
        "vol_daily_return": vol,
        "sharpe": sharpe,
        "cum_return": cum,
    }
