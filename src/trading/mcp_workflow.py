from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .adapters import build_router_from_config_dir
from .backtest import run_pipeline
from .config import load_config
from .data_ingestion import read_ohlcv
from .execution_controls import ExecutionControlService, ExecutionControlsConfig
from .pnl import PnLConfig, PnLService
from .research import ResearchOrchestrator
from .review import ReviewConfig, ReviewService


class TradingMCPWorkflow:
    """Thin orchestration layer exposing MCP-style callable workflow methods."""

    def __init__(
        self,
        *,
        adapters_dir: str = "config/integrations/adapters",
        execution_controls_path: str = "config/execution_controls.yaml",
        risk_controls_path: str = "config/risk_controls.yaml",
        pnl_config_path: str = "config/pnl.yaml",
    ) -> None:
        self.router = build_router_from_config_dir(adapters_dir)
        self.execution_service = ExecutionControlService(
            self.router,
            ExecutionControlsConfig.from_file(execution_controls_path),
        )
        self.review_service = ReviewService(ReviewConfig.from_file(risk_controls_path))
        self.pnl_service = PnLService(PnLConfig.from_file(pnl_config_path))
        self.research = ResearchOrchestrator()

    def research_asset(
        self,
        *,
        market: str,
        artifacts_dir: str = "artifacts",
        max_shortfall_bps: float = 20.0,
    ) -> list[dict[str, Any]]:
        artifacts = Path(artifacts_dir)
        predictions = pd.read_csv(artifacts / "predictions.csv") if (artifacts / "predictions.csv").exists() else pd.DataFrame()
        vol_forecasts = pd.read_csv(artifacts / "vol_forecasts.csv") if (artifacts / "vol_forecasts.csv").exists() else pd.DataFrame()
        vi_scores = pd.read_csv(artifacts / "vi_scores.csv") if (artifacts / "vi_scores.csv").exists() else pd.DataFrame()
        ranked = self.research.rank_strategies(
            market=market,
            predictions=predictions,
            vol_forecasts=vol_forecasts,
            vi_scores=vi_scores,
            max_shortfall_bps=max_shortfall_bps,
        )
        return [item.to_dict() for item in ranked]

    def rank_strategies(self, *, market: str, artifacts_dir: str = "artifacts") -> list[dict[str, Any]]:
        return self.research_asset(market=market, artifacts_dir=artifacts_dir)

    def run_walkforward(self, *, config: str, input: str, output: str = "artifacts") -> dict[str, Any]:
        cfg = load_config(config).raw
        ohlcv = read_ohlcv(input)
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)
        result = run_pipeline(ohlcv, cfg, output_dir=out)
        return result.get("metrics", {})

    def review_trade(self, *, artifacts_dir: str = "artifacts") -> dict[str, Any]:
        artifacts = Path(artifacts_dir)
        orders = pd.read_csv(artifacts / "orders.csv") if (artifacts / "orders.csv").exists() else pd.DataFrame()
        executed = pd.read_csv(artifacts / "executed_orders.csv") if (artifacts / "executed_orders.csv").exists() else pd.DataFrame()
        return self.review_service.build_report(orders, executed).to_dict()

    def submit_order_intent(self, *, adapter: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.router.submit_order(adapter, payload)
        return asdict(result)

    def get_current_pnl(self, *, adapter: str, artifacts_dir: str = "artifacts") -> dict[str, Any]:
        artifacts = Path(artifacts_dir)
        executed = pd.read_csv(artifacts / "executed_orders.csv") if (artifacts / "executed_orders.csv").exists() else pd.DataFrame()
        positions_payload: Any = {}
        try:
            positions_payload = self.router.get_positions(adapter).result
        except Exception:
            positions_payload = {}
        return self.pnl_service.snapshot(executed_orders=executed, positions_payload=positions_payload).to_dict()

    def close_positions(
        self,
        *,
        adapter: str,
        symbol: str,
        mode: str = "flatten",
        qty: float | str = "all",
        dry_run: bool = True,
        live: bool = False,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        return self.execution_service.close_symbol(
            adapter_name=adapter,
            symbol=symbol,
            mode=mode,
            qty=qty,
            dry_run=dry_run,
            live=live,
            confirmed=confirmed,
        )

    def terminate_run(
        self,
        *,
        run_id: str,
        reason: str = "manual_request",
        dry_run: bool = True,
        live: bool = False,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        return self.execution_service.terminate_strategy_run(
            run_id=run_id,
            dry_run=dry_run,
            live=live,
            confirmed=confirmed,
            reason=reason,
        )
