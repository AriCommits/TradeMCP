from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    RawBar,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.datasets.batching import SequentialBlockBatcher
from crypto_movement.datasets.cache import CachedWindowDataset
from crypto_movement.datasets.windows import ApprovedBarPanel, LazyBarWindowDataset
from crypto_movement.splits.manifests import (
    ManifestIntegrityError,
    ManifestProvenance,
    build_batch_manifest,
    read_batch_manifest_parquet,
    write_batch_manifest_parquet,
)
from crypto_movement.splits.walk_forward import Partition
from crypto_movement.time import UTC


def make_dataset() -> LazyBarWindowDataset:
    venue = VenueIdentity("fixture", InstrumentType.SPOT)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for asset in ("ETH", "BTC"):
        symbol = SymbolIdentity(venue, asset, "USD", f"{asset}-USD")
        for index in range(160):
            opened = start + timedelta(minutes=15 * index)
            closed = opened + timedelta(minutes=15)
            bars.append(
                RawBar(
                    symbol,
                    CandleInterval.FIFTEEN_MINUTES,
                    opened,
                    closed,
                    100.0,
                    101.0,
                    99.0,
                    100.0,
                    "batch-fixture",
                    closed,
                )
            )
    return LazyBarWindowDataset(ApprovedBarPanel("quality-v1", tuple(bars), ("raw:fixture-v1",)))


def provenance() -> ManifestProvenance:
    return ManifestProvenance(
        "sha256:panel",
        "sha256:quarantine",
        "sha256:config",
        "pilot-v1",
    )


def mapping(dataset: LazyBarWindowDataset, partition: Partition = Partition.TRAIN):
    return {entry.window_id: partition for entry in dataset.entries}


def test_batches_count_unique_anchors_not_multi_asset_rows() -> None:
    dataset = make_dataset()
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=2,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    assert len(batcher) == 3
    assert [len(batch.anchor_timestamps) for batch in batcher] == [2, 2, 1]
    assert [len(batch.windows) for batch in batcher] == [4, 4, 2]
    assert all(
        [
            (window.entry.anchor_timestamp, window.entry.symbol.canonical_id)
            for window in batch.windows
        ]
        == sorted(
            (window.entry.anchor_timestamp, window.entry.symbol.canonical_id)
            for window in batch.windows
        )
        for batch in batcher
    )


def test_one_anchor_batch_never_splits_symbols_at_same_timestamp() -> None:
    dataset = make_dataset()
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=1,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    assert len(batcher) == 5
    assert all(len(batch.windows) == 2 for batch in batcher)
    assert all(len(batch.anchor_timestamps) == 1 for batch in batcher)


def test_gaps_in_selected_anchor_membership_start_a_new_block() -> None:
    dataset = make_dataset()
    partitions = mapping(dataset)
    anchors = sorted({entry.anchor_timestamp for entry in dataset.entries})
    for entry in dataset.entries:
        if entry.anchor_timestamp == anchors[2]:
            partitions[entry.window_id] = Partition.VALIDATION
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=partitions,
        partition=Partition.TRAIN,
        anchors_per_batch=10,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    assert len(batcher) == 2
    assert [len(batch.anchor_timestamps) for batch in batcher] == [2, 2]


def test_batch_manifest_reproduces_membership_endpoints_and_provenance() -> None:
    dataset = make_dataset()
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=2,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    manifest = batcher.manifest
    assert manifest.provenance == provenance()
    assert (
        tuple(window.entry.window_id for window in batcher[0].windows)
        == manifest.rows[0].window_ids
    )
    assert manifest.rows[0].row_count == 4
    assert manifest.rows[0].fold_id == "outer-000-1y"
    assert manifest.rows[0].sequence_start < manifest.rows[0].feature_end
    assert manifest.rows[0].feature_end < manifest.rows[0].label_end

    cached = CachedWindowDataset(dataset)
    cached_batcher = SequentialBlockBatcher(
        cached,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=2,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    assert cached_batcher.manifest == manifest


def test_batch_manifest_rejects_same_anchor_split_across_rows() -> None:
    dataset = make_dataset()
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=1,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    first = batcher.manifest.rows[0]
    duplicate_anchor = replace(
        first,
        batch_id="duplicate",
        batch_ordinal=1,
    )
    with pytest.raises(ValueError, match="strictly later"):
        build_batch_manifest((first, duplicate_anchor), provenance=provenance())


def test_partition_mapping_must_cover_every_window() -> None:
    dataset = make_dataset()
    incomplete = mapping(dataset)
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError, match="cover every"):
        SequentialBlockBatcher(
            dataset,
            partition_by_window=incomplete,
            partition=Partition.TRAIN,
            anchors_per_batch=2,
            fold_id="outer-000-1y",
            manifest_provenance=provenance(),
        )


def test_batch_manifest_parquet_round_trip_and_checksum() -> None:
    pytest.importorskip("pyarrow.parquet")
    dataset = make_dataset()
    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=mapping(dataset),
        partition=Partition.TRAIN,
        anchors_per_batch=2,
        fold_id="outer-000-1y",
        manifest_provenance=provenance(),
    )
    first_path = Path("tests/crypto_movement/datasets/.s0-batches-1-test.parquet")
    second_path = Path("tests/crypto_movement/datasets/.s0-batches-2-test.parquet")
    try:
        first = write_batch_manifest_parquet(first_path, batcher.manifest)
        second = write_batch_manifest_parquet(second_path, batcher.manifest)
        assert first.checksum_sha256 == second.checksum_sha256
        assert (
            read_batch_manifest_parquet(first_path, expected_checksum=first.checksum_sha256)
            == batcher.manifest
        )
        with pytest.raises(ManifestIntegrityError, match="checksum"):
            read_batch_manifest_parquet(first_path, expected_checksum="0" * 64)
    finally:
        first_path.unlink(missing_ok=True)
        second_path.unlink(missing_ok=True)
