from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading.execution_controls import ExecutionControlService, ExecutionControlsConfig
from trading.pnl import PnLConfig, PnLService
from trading.review import ReviewConfig, ReviewService
from trading.adapters import build_router_from_config_dir


def test_review_service_flags_no_go() -> None:
    orders = pd.DataFrame({"date": ["2026-01-01"], "symbol": ["AAPL"], "position": [0.5]})
    executed = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "symbol": ["AAPL", "MSFT"],
            "approve": [False, False],
            "predicted_shortfall_bps": [25.0, 30.0],
            "executed_pnl": [-0.04, -0.01],
            "exec_position": [0.3, 0.2],
        }
    )
    service = ReviewService(
        ReviewConfig(
            min_approval_rate=0.6,
            max_predicted_shortfall_bps=20.0,
            max_daily_loss=0.03,
            max_symbol_exposure=0.25,
            require_orders=True,
        )
    )

    report = service.build_report(orders, executed)
    assert report.go_no_go is False
    assert report.decision == "NO_GO"
    assert "shortfall_limit_exceeded" in report.breached_checks


def test_pnl_service_snapshot_has_expected_fields() -> None:
    executed = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "symbol": ["AAPL", "MSFT"],
            "executed_pnl": [0.01, -0.02],
            "exec_position": [0.2, -0.1],
        }
    )
    positions = [{"symbol": "AAPL", "unrealized_pnl": 0.03, "quantity": 1.0, "mark_price": 100.0}]
    service = PnLService(PnLConfig(fee_bps=1.0, quote_staleness_seconds=30, mark_source="last"))

    snapshot = service.snapshot(executed_orders=executed, positions_payload=positions)
    assert set(snapshot.to_dict()) == {
        "as_of_utc",
        "realized_pnl",
        "unrealized_pnl",
        "daily_pnl",
        "fees",
        "net_pnl",
        "by_symbol",
        "exposure_by_symbol",
    }


def test_execution_control_service_terminate_dry_run(tmp_path: Path) -> None:
    cfg_dir = Path(__file__).resolve().parents[1] / "config/integrations/adapters"
    router = build_router_from_config_dir(cfg_dir)
    service = ExecutionControlService(
        router,
        ExecutionControlsConfig(),
        audit_log_path=tmp_path / "audit.jsonl",
        terminated_runs_path=tmp_path / "terminated.json",
    )

    out = service.terminate_strategy_run("run_test_001", dry_run=True, live=False, confirmed=False)
    assert out["dry_run"] is True
    assert out["run_id"] == "run_test_001"
