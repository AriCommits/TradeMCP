from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "options"


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG_ROOT / name).read_text(encoding="utf-8"))


def test_simulation_config_never_substitutes_theoretical_fills() -> None:
    payload = _load("simulation.yaml")

    assert payload["schema_version"] == "options-simulation.v1alpha1"
    assert payload["fills"]["primary_policy"] == "executable_side"
    assert payload["fills"]["allow_theoretical_fill_for_missing_quote"] is False
    assert payload["lifecycle"]["unsupported_event_policy"] == "fail_closed"


def test_forecast_config_requires_point_in_time_baseline_comparisons() -> None:
    payload = _load("forecasts.yaml")

    assert payload["schema_version"] == "options-forecasts.v1alpha1"
    assert payload["calibration"]["require_naive_comparison"] is True
    assert payload["point_in_time"]["require_strict_training_cutoff"] is True
    assert payload["point_in_time"]["fold_local_transforms"] is True


def test_portfolio_config_fails_closed_and_labels_estimates() -> None:
    payload = _load("portfolio_limits.yaml")

    assert payload["schema_version"] == "options-portfolio-limits.v1alpha1"
    assert payload["capital"]["estimate_label_required"] is True
    assert payload["safety"]["require_account_snapshot"] is True
    assert payload["safety"]["fail_closed_on_missing_inputs"] is True
