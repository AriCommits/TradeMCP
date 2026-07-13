from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "options"


def _load(name: str) -> dict:
    payload = yaml.safe_load((CONFIG_ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must contain a YAML mapping")
    return payload


def test_candidate_config_is_deterministic_and_fails_closed() -> None:
    payload = _load("candidates.yaml")

    assert payload["schema_version"] == "options-candidates.v1alpha1"
    assert payload["selection"]["retain_rejected_candidates"] is True
    assert payload["safety"]["require_account_snapshot"] is True
    assert payload["safety"]["fail_closed_on_missing_inputs"] is True


def test_strategy_config_requires_explicit_validated_registry() -> None:
    payload = _load("strategy_plugins.yaml")

    assert payload["schema_version"] == "options-strategy-plugins.v1alpha1"
    assert payload["discovery"]["mode"] == "explicit_registry"
    assert payload["validation"]["require_semantic_version"] is True
    assert payload["safety"]["allow_dynamic_filesystem_discovery"] is False


def test_objective_config_requires_explicit_decomposed_scores() -> None:
    payload = _load("objectives.yaml")

    assert payload["schema_version"] == "options-objectives.v1alpha1"
    assert payload["scoring"]["require_explicit_weights"] is True
    assert payload["scoring"]["keep_estimated_and_realized_scores_distinct"] is True
    assert payload["stress"]["axes"] == ["spot", "implied_volatility", "time", "liquidity"]
