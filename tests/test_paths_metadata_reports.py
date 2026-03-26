from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from trading.backtest import export_artifacts
from trading.metadata import build_run_metadata
from trading.paths import resolve_paths
from trading.reports import write_markdown_report


def test_resolve_paths_discovers_repo_root_from_nested_path() -> None:
    nested = Path(__file__).resolve()
    paths = resolve_paths(nested)
    assert (paths.repo_root / "pyproject.toml").exists()
    assert paths.adapters == paths.repo_root / "config/integrations/adapters"


def test_build_run_metadata_keeps_user_meta_and_stable_hash() -> None:
    cfg = {"seed": 42, "risk": {"max_position_abs": 0.1}}
    meta = build_run_metadata(
        config=cfg,
        seed=42,
        run_id="run_fixed",
        config_path="config/markets/stocks_base.yaml",
        user_meta={"owner": "qa", "ticket": 123},
        repo_root=Path(__file__).resolve().parents[1],
    )
    meta2 = build_run_metadata(
        config=cfg,
        seed=42,
        run_id="run_fixed_2",
        config_path="config/markets/stocks_base.yaml",
        user_meta={"owner": "qa", "ticket": 123},
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert meta.user_meta["owner"] == "qa"
    assert meta.config_hash == meta2.config_hash


def test_export_artifacts_writes_metadata_and_report_for_empty_orders(tmp_path: Path) -> None:
    result = {
        "processed": pd.DataFrame(),
        "regime_assignments": pd.DataFrame(),
        "vi_scores": pd.DataFrame(),
        "predictions": pd.DataFrame(),
        "vol_forecasts": pd.DataFrame(),
        "orders": pd.DataFrame(),
        "executed_orders": pd.DataFrame(columns=["symbol", "executed_pnl"]),
        "metrics": {"approval_rate": 0.0, "pre_exec": {}, "post_exec": {}},
    }
    metadata = build_run_metadata(
        config={"seed": 42},
        seed=42,
        run_id="run_test_export",
        user_meta={"env": "test"},
    )

    export_artifacts(result, tmp_path, run_metadata=metadata)

    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "run_metadata.json").exists()
    assert (tmp_path / "report.md").exists()

    payload = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_test_export"
    assert payload["user_meta"]["env"] == "test"
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "No executed orders were found for this run." in report


def test_write_markdown_report_renders_html_table_for_ranked_symbols(tmp_path: Path) -> None:
    executed = pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL", "MSFT"],
            "executed_pnl": [0.2, -0.1, 0.5],
        }
    )
    report_path = write_markdown_report(
        output_dir=tmp_path,
        metrics={"approval_rate": 1.0},
        executed_orders=executed,
        top_n=2,
        title="Edge Report",
    )
    content = report_path.read_text(encoding="utf-8")
    assert "<table" in content
    assert "MSFT" in content
