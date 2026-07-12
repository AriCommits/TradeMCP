from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "options"


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG_ROOT / name).read_text(encoding="utf-8"))


def test_data_source_config_refuses_synthetic_executable_quotes() -> None:
    payload = _load("data_sources.yaml")

    assert payload["schema_version"] == "options-data-sources.v1alpha1"
    assert payload["providers"]["saved_parquet"]["query_engine"] == "duckdb"
    assert payload["quality"]["allow_synthetic_executable_quotes"] is False


def test_pricing_config_has_explicit_units_bounds_and_no_silent_clamps() -> None:
    payload = _load("pricing.yaml")

    assert payload["schema_version"] == "options-pricing.v1alpha1"
    assert payload["units"]["theta"] == "currency_per_calendar_day"
    assert payload["implied_volatility"]["lower_bound"] > 0
    assert payload["implied_volatility"]["upper_bound"] > 1
    assert payload["safety"]["allow_silent_input_clamping"] is False


def test_market_inputs_require_point_in_time_announcement_metadata() -> None:
    payload = _load("market_inputs.yaml")

    assert payload["schema_version"] == "options-market-inputs.v1alpha1"
    assert payload["dividends"]["require_announced_at"] is True
    assert payload["events"]["exclude_revisions_announced_after_decision"] is True
    assert payload["accounts"]["saved_fixture_only"] is True
