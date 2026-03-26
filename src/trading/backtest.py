from __future__ import annotations

import json
import os
from pathlib import Path
import random
from typing import Any

import numpy as np
import pandas as pd

from .data_ingestion import build_model_table, preprocess_ohlcv, robust_scale
from .execution_client import apply_execution_filter
from .forecasting import walk_forward_forecast
from .indicators import add_indicators, select_model_indicator_features
from .metadata import RunMetadata, build_run_metadata
from .regime import discover_regimes
from .reports import write_markdown_report
from .risk import build_orders, summarize_performance
from .volatility import forecast_cluster_volatility

try:
    import mlflow
except Exception:  # pragma: no cover
    mlflow = None


def _forward_fill_regime(base: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    if assignments.empty:
        out = base.copy()
        out["regime"] = -1
        return out

    out_parts = []
    for symbol, sdf in base.groupby("symbol"):
        a = assignments[assignments["symbol"] == symbol].sort_values("date")
        b = sdf.sort_values("date")
        if a.empty:
            b = b.copy()
            b["regime"] = -1
            out_parts.append(b)
            continue

        merged = pd.merge_asof(
            b,
            a[["date", "regime"]].sort_values("date"),
            on="date",
            direction="backward",
        )
        merged["regime"] = merged["regime"].fillna(-1).astype(int)
        out_parts.append(merged)

    return pd.concat(out_parts, ignore_index=True)


def _align_vol_to_predictions(predictions: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(columns=["date", "symbol", "vol_forecast", "regime"])
    if vol.empty:
        out = predictions[["date", "symbol"]].copy()
        out["vol_forecast"] = predictions["target"].rolling(20, min_periods=5).std().fillna(0.01).values
        out["regime"] = -1
        return out

    out_parts = []
    for symbol, pdf in predictions.groupby("symbol"):
        v = vol[vol["symbol"] == symbol].sort_values("date")
        p = pdf.sort_values("date")
        if v.empty:
            tmp = p[["date", "symbol"]].copy()
            tmp["vol_forecast"] = p["target"].rolling(20, min_periods=5).std().fillna(0.01).values
            tmp["regime"] = -1
            out_parts.append(tmp)
            continue
        merged = pd.merge_asof(p[["date", "symbol"]], v[["date", "vol_forecast", "regime"]], on="date", direction="backward")
        merged["symbol"] = symbol
        merged["vol_forecast"] = merged["vol_forecast"].fillna(0.01)
        merged["regime"] = merged["regime"].fillna(-1).astype(int)
        out_parts.append(merged)

    return pd.concat(out_parts, ignore_index=True)


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def run_pipeline(
    ohlcv: pd.DataFrame,
    config: dict[str, Any],
    output_dir: str | Path | None = None,
    run_metadata: RunMetadata | None = None,
) -> dict[str, Any]:
    seed = int(config.get("seed", 42))
    _seed_everything(seed)

    processed = preprocess_ohlcv(ohlcv, vol_window=config["features"]["vol_window"])

    ind_cfg = config.get("indicators", {})
    processed, indicator_cols = add_indicators(
        processed,
        enabled=bool(ind_cfg.get("enabled", False)),
        source=str(ind_cfg.get("source", "native")),
        columns=ind_cfg.get("columns"),
    )

    scale_cols = list(config["features"]["robust_scale_cols"])
    if indicator_cols and bool(ind_cfg.get("scale", True)):
        scale_cols.extend(indicator_cols)
    scale_cols = sorted(set(scale_cols))
    processed = robust_scale(processed, columns=scale_cols)

    regime_result = discover_regimes(
        processed.dropna(subset=["log_return_scaled", "realized_vol_scaled", "dollar_volume_scaled"]),
        rebalance_days=config["regime"]["rebalance_days"],
        lookback_days=config["regime"]["lookback_days"],
        pca_components=config["regime"]["pca_components"],
        ica_components=config["regime"]["ica_components"],
        umap_components=config["regime"]["umap_components"],
        min_cluster_size=config["regime"]["min_cluster_size"],
    )

    with_regime = _forward_fill_regime(processed, regime_result.assignments)
    indicator_features = select_model_indicator_features(
        with_regime,
        indicator_cols=indicator_cols,
        use_scaled=bool(ind_cfg.get("scale", True)),
    )
    model_df, feature_cols = build_model_table(
        with_regime,
        return_lags=config["features"]["return_lags"],
        extra_feature_cols=indicator_features,
    )
    if "regime" in with_regime.columns:
        model_df = model_df.merge(with_regime[["date", "symbol", "regime"]], on=["date", "symbol"], how="left")
        model_df["regime"] = model_df["regime"].fillna(-1)
        feature_cols = [*feature_cols, "regime"]

    forecast_result = walk_forward_forecast(
        model_df,
        feature_cols=feature_cols,
        train_min_days=config["forecast"]["train_min_days"],
        test_step_days=config["forecast"]["test_step_days"],
        model_name=config["forecast"]["model"],
    )

    vol = forecast_cluster_volatility(
        with_regime,
        assignments=regime_result.assignments,
        lookback_days=config["volatility"]["lookback_days"],
        horizon_days=config["volatility"]["forecast_horizon_days"],
        model=config["volatility"]["model"],
        ewma_lambda=config["volatility"]["ewma_lambda"],
    )
    aligned_vol = _align_vol_to_predictions(forecast_result.predictions, vol)

    orders = build_orders(
        forecast_result.predictions,
        aligned_vol,
        signal_z_window=config["risk"]["signal_z_window"],
        vol_gate_quantile=config["risk"]["vol_gate_quantile"],
        target_portfolio_risk=config["risk"]["target_portfolio_risk"],
        max_position_abs=config["risk"]["max_position_abs"],
    )
    pre_exec_metrics = summarize_performance(orders)

    executed = apply_execution_filter(
        orders,
        backend_bin=config["execution"]["backend_bin"],
        max_shortfall_bps=config["execution"]["max_shortfall_bps"],
    )

    if executed.empty:
        post_exec_metrics = pre_exec_metrics
        approval_rate = 0.0
    else:
        exec_perf_df = executed[["date", "executed_pnl"]].rename(columns={"executed_pnl": "realized_pnl"})
        post_exec_metrics = summarize_performance(exec_perf_df)
        approval_rate = float(executed["approve"].mean())

    metrics = {
        "avg_vi": float(regime_result.vi_scores["vi"].mean()) if not regime_result.vi_scores.empty else np.nan,
        "approval_rate": approval_rate,
        "pre_exec": pre_exec_metrics,
        "post_exec": post_exec_metrics,
    }

    if mlflow is not None and config.get("mlflow_tracking_uri"):
        try:
            mlflow.set_tracking_uri(config["mlflow_tracking_uri"])
            mlflow.set_experiment(config.get("experiment_name", "swing_pipeline"))
            with mlflow.start_run(run_name="pipeline_run"):
                mlflow.log_metrics(
                    {
                        "avg_vi": 0.0 if np.isnan(metrics["avg_vi"]) else metrics["avg_vi"],
                        "approval_rate": metrics["approval_rate"],
                        "pre_sharpe": metrics["pre_exec"]["sharpe"],
                        "post_sharpe": metrics["post_exec"]["sharpe"],
                    }
                )
        except Exception:
            # Metrics export to local CSV/JSON is the hard requirement; MLflow is best effort.
            pass

    result = {
        "processed": processed,
        "regime_assignments": regime_result.assignments,
        "vi_scores": regime_result.vi_scores,
        "predictions": forecast_result.predictions,
        "vol_forecasts": aligned_vol,
        "orders": orders,
        "executed_orders": executed,
        "metrics": metrics,
    }
    metadata = run_metadata or build_run_metadata(config=config, seed=seed)
    result["run_metadata"] = metadata.to_dict()

    if output_dir is not None:
        export_artifacts(result, output_dir, run_metadata=metadata)

    return result


def export_artifacts(
    result: dict[str, Any],
    output_dir: str | Path,
    run_metadata: RunMetadata | None = None,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for key in [
        "processed",
        "regime_assignments",
        "vi_scores",
        "predictions",
        "vol_forecasts",
        "orders",
        "executed_orders",
    ]:
        df = result[key]
        if isinstance(df, pd.DataFrame):
            df.to_csv(out / f"{key}.csv", index=False)

    with open(out / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(result["metrics"], f, indent=2)

    metadata_payload = run_metadata.to_dict() if run_metadata is not None else result.get("run_metadata", {})
    with open(out / "run_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2)

    write_markdown_report(
        output_dir=out,
        metrics=result["metrics"],
        executed_orders=result["executed_orders"],
        title="Pipeline Report",
    )

    if os.environ.get("TRADING_ENABLE_MPL_PLOTS", "0") == "1":
        from .viz import save_equity_curve_plot, save_regime_vi_plot

        save_regime_vi_plot(result["vi_scores"], out / "regime_vi.png")
        save_equity_curve_plot(result["executed_orders"], out / "equity_curve.png")
