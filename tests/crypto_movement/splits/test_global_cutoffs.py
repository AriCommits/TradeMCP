from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crypto_movement.contracts import InstrumentType, SymbolIdentity, VenueIdentity
from crypto_movement.splits.manifests import (
    ManifestIntegrityError,
    ManifestProvenance,
    SplitEndpointInventory,
    build_fold_manifest,
    read_fold_manifest_parquet,
    write_fold_manifest_parquet,
)
from crypto_movement.splits.walk_forward import (
    GlobalFoldCalendar,
    LockboxAccessError,
    Partition,
    TimeRange,
    WalkForwardSpec,
    build_global_fold_calendar,
    common_partition_assignments,
)
from crypto_movement.time import UTC


def symbols() -> tuple[SymbolIdentity, ...]:
    venue = VenueIdentity("fixture", InstrumentType.SPOT)
    return (
        SymbolIdentity(venue, "BTC", "USD", "BTC-USD"),
        SymbolIdentity(venue, "ETH", "USD", "ETH-USD"),
    )


def calendar() -> GlobalFoldCalendar:
    spec = WalkForwardSpec(
        symbols=symbols(),
        outer_tests=(
            TimeRange(
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 2, 1, tzinfo=UTC),
            ),
        ),
        validation_duration=timedelta(days=90),
        lockbox=TimeRange(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 4, 1, tzinfo=UTC),
        ),
        purge=timedelta(hours=12),
        embargo=timedelta(hours=6),
    )
    return build_global_fold_calendar(spec)


def test_global_calendar_builds_frozen_1_3_5_year_fold_identities() -> None:
    result = calendar()
    assert [cutoff.history_years for cutoff in result.cutoffs] == [1, 3, 5]
    assert all(cutoff.symbol_ids == result.symbol_ids for cutoff in result.cutoffs)
    for cutoff in result.cutoffs:
        fold = cutoff.fold
        assert fold.validation_start - fold.train_end == timedelta(hours=18)
        assert fold.test_start - fold.validation_end == timedelta(hours=18)
        assert fold.purge == timedelta(hours=12)
        assert fold.embargo == timedelta(hours=6)
        assert fold.train_end.year - fold.train_start.year == cutoff.history_years
        inner = cutoff.inner_fold
        assert inner.inner_fold_id == f"{fold.fold_id}:inner-000"
        assert inner.parent_fold_id == fold.fold_id
        assert inner.train == TimeRange(fold.train_start, fold.train_end)
        assert inner.validation == TimeRange(fold.validation_start, fold.validation_end)
        assert inner.validation.end <= fold.test_start
        assert inner.purge + inner.embargo == timedelta(hours=18)
    with pytest.raises(FrozenInstanceError):
        result.cutoffs[0].fold.fold_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.cutoffs[0].inner_fold.inner_fold_id = "changed"  # type: ignore[misc]


def test_common_cross_asset_cutoffs_never_use_asset_local_boundaries() -> None:
    cutoff = calendar().cutoffs[0]
    train_time = cutoff.fold.train_start + timedelta(days=1)
    test_time = cutoff.fold.test_start + timedelta(days=1)
    panel = {symbol_id: (train_time, test_time) for symbol_id in reversed(cutoff.symbol_ids)}
    assignments = common_partition_assignments(cutoff, panel)
    assert {assignments[(symbol_id, train_time)] for symbol_id in cutoff.symbol_ids} == {
        Partition.TRAIN
    }
    assert {assignments[(symbol_id, test_time)] for symbol_id in cutoff.symbol_ids} == {
        Partition.TEST
    }


def test_common_cross_asset_cutoffs_reject_duplicate_timestamps() -> None:
    cutoff = calendar().cutoffs[0]
    timestamp = cutoff.fold.train_start + timedelta(days=1)
    panel = {symbol_id: (timestamp,) for symbol_id in cutoff.symbol_ids}
    panel[cutoff.symbol_ids[0]] = (timestamp, timestamp)
    with pytest.raises(ValueError, match="duplicate timestamp"):
        common_partition_assignments(cutoff, panel)


def test_lockbox_access_is_denied_by_default() -> None:
    result = calendar()
    inside = result.lockbox.start + timedelta(days=1)
    with pytest.raises(LockboxAccessError, match="denied by default"):
        result.require_development_timestamp(inside)
    assert result.require_development_timestamp(inside, allow_lockbox=True) == inside
    assert result.require_development_timestamp(result.lockbox.start - timedelta(seconds=1))


def _inventory_for_calendar(result: GlobalFoldCalendar):
    inventories = {}
    for cutoff in result.cutoffs:
        fold = cutoff.fold
        inventories[fold.fold_id] = (
            SplitEndpointInventory(
                Partition.TRAIN,
                100,
                fold.train_start,
                fold.train_end - timedelta(hours=12),
                fold.train_end,
            ),
            SplitEndpointInventory(
                Partition.VALIDATION,
                20,
                fold.validation_start,
                fold.validation_end - timedelta(hours=12),
                fold.validation_end,
            ),
            SplitEndpointInventory(
                Partition.TEST,
                10,
                fold.test_start,
                fold.test_end - timedelta(hours=12),
                fold.test_end,
            ),
        )
    return inventories


def test_fold_manifest_contains_provenance_roles_counts_and_endpoints() -> None:
    result = calendar()
    provenance = ManifestProvenance(
        panel_checksum="sha256:panel",
        quarantine_checksum="sha256:quarantine",
        config_checksum="sha256:config",
        universe_snapshot_id="pilot-v1",
    )
    manifest = build_fold_manifest(
        result,
        provenance=provenance,
        inventory_by_fold=_inventory_for_calendar(result),
    )
    repeated = build_fold_manifest(
        result,
        provenance=provenance,
        inventory_by_fold=_inventory_for_calendar(result),
    )
    assert manifest == repeated
    assert manifest.rows[0].split_inventory[0].partition is Partition.TRAIN
    assert manifest.rows[0].split_inventory[0].row_count == 100
    assert manifest.rows[0].inner_fold_id.endswith(":inner-000")
    assert manifest.provenance.panel_checksum == "sha256:panel"
    changed = build_fold_manifest(
        result,
        provenance=replace(provenance, panel_checksum="sha256:changed"),
        inventory_by_fold=_inventory_for_calendar(result),
    )
    assert changed.manifest_id != manifest.manifest_id


def test_development_outer_window_cannot_overlap_lockbox() -> None:
    lockbox = TimeRange(
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 4, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="cannot enter the lockbox"):
        WalkForwardSpec(
            symbols=symbols(),
            outer_tests=(
                TimeRange(
                    datetime(2025, 12, 15, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                ),
            ),
            validation_duration=timedelta(days=30),
            lockbox=lockbox,
        )


def test_fold_manifest_parquet_round_trip_checksum_and_repeated_field_tamper() -> None:
    parquet = pytest.importorskip("pyarrow.parquet")
    arrow = pytest.importorskip("pyarrow")
    result = calendar()
    provenance = ManifestProvenance(
        "sha256:panel",
        "sha256:quarantine",
        "sha256:config",
        "pilot-v1",
    )
    manifest = build_fold_manifest(
        result,
        provenance=provenance,
        inventory_by_fold=_inventory_for_calendar(result),
    )
    first_path = Path("tests/crypto_movement/splits/.s0-fold-1-test.parquet")
    second_path = Path("tests/crypto_movement/splits/.s0-fold-2-test.parquet")
    try:
        first = write_fold_manifest_parquet(first_path, manifest)
        second = write_fold_manifest_parquet(second_path, manifest)
        assert first.checksum_sha256 == second.checksum_sha256
        assert (
            read_fold_manifest_parquet(first_path, expected_checksum=first.checksum_sha256)
            == manifest
        )
        with pytest.raises(ManifestIntegrityError, match="checksum"):
            read_fold_manifest_parquet(first_path, expected_checksum="0" * 64)

        table = parquet.read_table(first_path)
        records = table.to_pylist()
        records[1]["train_start"] = records[1]["train_start"] + 3_600_000_000
        parquet.write_table(arrow.Table.from_pylist(records, schema=table.schema), first_path)
        with pytest.raises(ManifestIntegrityError, match="inconsistent repeated metadata"):
            read_fold_manifest_parquet(first_path)
    finally:
        first_path.unlink(missing_ok=True)
        second_path.unlink(missing_ok=True)
