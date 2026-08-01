from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "options" / "mcp_tools.yaml"


def test_mcp_config_disables_submission_and_requires_auditable_artifacts() -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "options-mcp-tools.v1alpha1"
    assert payload["registration"]["expected_tool_count"] == 13
    assert payload["safety"]["default_dry_run"] is True
    assert payload["safety"]["live_order_submission_enabled"] is False
    assert payload["safety"]["require_go_review_for_order_intent"] is True
    assert payload["artifacts"]["required_for_long_running_tools"] is True
    assert payload["artifacts"]["formats"] == ["json", "markdown"]
