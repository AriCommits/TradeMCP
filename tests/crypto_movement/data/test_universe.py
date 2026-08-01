from __future__ import annotations

from pathlib import Path

from crypto_movement.data.universe import (
    ExclusionReason,
    build_universe_snapshot,
    load_universe_config,
    write_universe_snapshot,
)

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config/crypto_movement/universe.yaml"


def test_snapshot_includes_pilot_and_records_every_exclusion_reason() -> None:
    snapshot = build_universe_snapshot(load_universe_config(CONFIG))
    assert tuple(item.canonical_asset for item in snapshot.included) == (
        "AVAX",
        "BTC",
        "ETC",
        "ETH",
        "SOL",
    )
    reasons = {item.reason for item in snapshot.exclusions}
    assert reasons == set(ExclusionReason)
    assert len(snapshot.exclusions) == 6
    assert "not_point_in_time" in snapshot.membership_basis


def test_snapshot_identity_and_file_are_immutable(tmp_path) -> None:
    config = load_universe_config(CONFIG)
    first = build_universe_snapshot(config)
    second = build_universe_snapshot(config)
    assert first == second
    path = write_universe_snapshot(first, tmp_path)
    before = (path.stat().st_mtime_ns, path.read_bytes())
    replay = write_universe_snapshot(second, tmp_path)
    assert replay == path
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before
