from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from crypto_movement.config import (
    ConfigError,
    FullDownloadBlockedError,
    PilotSource,
    load_pilot_config,
    load_project_config,
)

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "config/crypto_movement/project.yaml"
PILOT = ROOT / "config/crypto_movement/pilot.yaml"


def test_checked_in_project_is_deterministic_and_fail_closed(monkeypatch, tmp_path):
    first = load_project_config(PROJECT, root=ROOT)
    second = load_project_config(PROJECT, root=ROOT)
    assert first.canonical_json() == second.canonical_json()
    assert not first.full_download_gate.allowed
    assert "production_venue" in first.full_download_gate.blockers
    with pytest.raises(FullDownloadBlockedError, match="production_venue"):
        first.require_full_download_ready()

    monkeypatch.chdir(tmp_path)
    from_other_cwd = load_project_config(PROJECT)
    assert from_other_cwd.paths == first.paths
    for value in first.paths.__dict__.values():
        assert value.is_absolute()
        value.relative_to(ROOT)


def test_unknown_project_key_is_rejected(tmp_path):
    payload = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    payload["study"]["future_leakage_switch"] = True
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown keys"):
        load_project_config(path, root=ROOT)


def test_invalid_decision_status_is_rejected(tmp_path):
    payload = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    payload["decisions"]["production_venue"]["status"] = "UNKNOWN"
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="status is invalid"):
        load_project_config(path, root=ROOT)


@pytest.mark.parametrize("contents", ["- not\n- a\n- mapping\n", "null\n"])
def test_nonmapping_yaml_is_rejected(tmp_path, contents):
    path = tmp_path / "bad.yaml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_project_config(path, root=ROOT)


def test_missing_or_directory_config_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        load_project_config(tmp_path / "missing.yaml", root=ROOT)
    with pytest.raises(ConfigError, match="does not exist"):
        load_project_config(tmp_path, root=ROOT)


def test_checked_in_pilot_is_fixture_only_and_purged():
    pilot = load_pilot_config(PILOT, root=ROOT)
    assert pilot.source is PilotSource.FIXTURE
    assert pilot.assets == ("BTC", "ETH", "ETC", "AVAX", "SOL")
    assert pilot.start.utcoffset().total_seconds() == 0
    assert pilot.folds[0].purge_hours == 12


def test_naive_pilot_timestamp_is_rejected(tmp_path):
    payload = yaml.safe_load(PILOT.read_text(encoding="utf-8"))
    payload["start"] = "2024-01-01T00:00:00"
    path = tmp_path / "pilot.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        load_pilot_config(path, root=ROOT)


def test_purge_below_maximum_horizon_is_rejected(tmp_path):
    payload = yaml.safe_load(PILOT.read_text(encoding="utf-8"))
    payload["folds"][0]["purge_hours"] = 11
    path = tmp_path / "pilot.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="at least 12"):
        load_pilot_config(path, root=ROOT)


def test_fold_gap_must_cover_purge_plus_embargo(tmp_path):
    payload = yaml.safe_load(PILOT.read_text(encoding="utf-8"))
    payload["folds"][0]["embargo_hours"] = 1
    path = tmp_path / "pilot.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="purge and embargo"):
        load_pilot_config(path, root=ROOT)


def test_missing_required_download_decision_is_rejected(tmp_path):
    payload = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    del payload["decisions"]["production_venue"]
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="production_venue"):
        load_project_config(path, root=ROOT)


def test_confirmed_decision_requires_a_concrete_value(tmp_path):
    payload = yaml.safe_load(PROJECT.read_text(encoding="utf-8"))
    payload["decisions"]["production_venue"]["status"] = "CONFIRMED"
    payload["decisions"]["production_venue"]["value"] = None
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="concrete scalar"):
        load_project_config(path, root=ROOT)
