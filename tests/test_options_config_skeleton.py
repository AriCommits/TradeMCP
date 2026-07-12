from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "options" / "platform.yaml"


def test_options_platform_config_declares_versioned_units_and_safety_defaults() -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "options-platform.v1alpha1"
    assert payload["time"]["storage_timezone"] == "UTC"
    assert payload["time"]["distinguish_calendar_and_trading_days"] is True
    assert payload["units"]["volatility"] == "annualized_decimal"
    assert payload["units"]["theta"] == "currency_per_calendar_day"
    assert payload["data_quality"]["allow_synthetic_executable_quotes"] is False
    assert payload["pricing"]["allow_silent_input_clamping"] is False
    assert payload["research"]["point_in_time_required"] is True
    assert payload["research"]["default_dry_run"] is True
