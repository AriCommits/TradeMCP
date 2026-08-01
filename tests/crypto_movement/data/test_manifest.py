from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pyarrow")

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.collector import MarketDataCollector, PageCache
from crypto_movement.data.manifest import (
    ManifestIntegrityError,
    build_manifest,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from crypto_movement.data.providers import DataRequest, DeterministicFixtureProvider
from crypto_movement.data.storage import ParquetBarStore


def _collection(tmp_path):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.SPOT),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    request = DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + 3 * timedelta(minutes=15),
        2,
    )
    provider = DeterministicFixtureProvider()
    return MarketDataCollector(provider, PageCache(tmp_path / "cache")).collect(request)


def test_manifest_records_provenance_round_trips_and_is_stable(tmp_path) -> None:
    collection = _collection(tmp_path)
    raw_root = tmp_path / "raw"
    partitions = ParquetBarStore(raw_root).write_bars(collection.bars)
    manifest = build_manifest(
        collection,
        provider_name="deterministic-fixture-v1",
        universe_snapshot_id="snapshot-1",
        partition_root=raw_root,
        partitions=partitions,
    )
    assert manifest.request["venue_symbol"] == "BTCUSDT"
    assert manifest.request["request_id"] == collection.request.request_id
    assert manifest.partitions[0].checksum_algorithm == "sha256"
    verify_manifest(manifest, raw_root)

    path = write_manifest(manifest, tmp_path / "manifests")
    loaded = load_manifest(path)
    assert loaded == manifest

    operational_replay = replace(collection, cache_hits=99, provider_fetches=0)
    replay_manifest = build_manifest(
        operational_replay,
        provider_name="deterministic-fixture-v1",
        universe_snapshot_id="snapshot-1",
        partition_root=raw_root,
        partitions=partitions,
    )
    assert replay_manifest.manifest_id == manifest.manifest_id


def test_manifest_checksum_detects_partition_tampering(tmp_path) -> None:
    collection = _collection(tmp_path)
    raw_root = tmp_path / "raw"
    partitions = ParquetBarStore(raw_root).write_bars(collection.bars)
    manifest = build_manifest(
        collection,
        provider_name="deterministic-fixture-v1",
        universe_snapshot_id="snapshot-1",
        partition_root=raw_root,
        partitions=partitions,
    )
    with partitions[0].path.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ManifestIntegrityError, match="checksum mismatch"):
        verify_manifest(manifest, raw_root)
