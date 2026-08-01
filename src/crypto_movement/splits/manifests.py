"""Stable fold and sequential-batch manifests with deterministic Parquet persistence."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, overload

from crypto_movement.artifacts import stable_digest
from crypto_movement.splits.walk_forward import GlobalFoldCalendar, Partition
from crypto_movement.time import UTC, as_utc


class ManifestIntegrityError(RuntimeError):
    """Raised when a persisted manifest fails identity or checksum verification."""


@dataclass(frozen=True, slots=True)
class ManifestProvenance:
    panel_checksum: str
    quarantine_checksum: str
    config_checksum: str
    universe_snapshot_id: str

    def __post_init__(self) -> None:
        for name in (
            "panel_checksum",
            "quarantine_checksum",
            "config_checksum",
            "universe_snapshot_id",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be blank")


@dataclass(frozen=True, slots=True)
class SplitEndpointInventory:
    partition: Partition
    row_count: int
    sequence_start: datetime | None
    feature_end: datetime | None
    label_end: datetime | None

    def __post_init__(self) -> None:
        if self.partition not in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST):
            raise ValueError("inventory partition must be train, validation, or test")
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int):
            raise TypeError("row_count must be an integer")
        if self.row_count < 0:
            raise ValueError("row_count must be nonnegative")
        endpoints = (self.sequence_start, self.feature_end, self.label_end)
        if self.row_count == 0:
            if any(value is not None for value in endpoints):
                raise ValueError("empty inventory endpoints must be None")
            return
        if any(value is None for value in endpoints):
            raise ValueError("non-empty inventory requires every endpoint")
        assert self.sequence_start is not None
        assert self.feature_end is not None
        assert self.label_end is not None
        sequence_start = as_utc(self.sequence_start, field_name="sequence_start")
        feature_end = as_utc(self.feature_end, field_name="feature_end")
        label_end = as_utc(self.label_end, field_name="label_end")
        if sequence_start > feature_end or feature_end >= label_end:
            raise ValueError("inventory endpoints must satisfy sequence <= feature < label")
        object.__setattr__(self, "sequence_start", sequence_start)
        object.__setattr__(self, "feature_end", feature_end)
        object.__setattr__(self, "label_end", label_end)


@dataclass(frozen=True, slots=True)
class FoldManifestRow:
    fold_id: str
    inner_fold_id: str
    outer_index: int
    history_years: int
    symbol_ids: tuple[str, ...]
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    purge_seconds: int
    embargo_seconds: int
    lockbox_start: datetime
    lockbox_end: datetime
    split_inventory: tuple[SplitEndpointInventory, ...]

    def __post_init__(self) -> None:
        roles = tuple(item.partition for item in self.split_inventory)
        if roles != (Partition.TRAIN, Partition.VALIDATION, Partition.TEST):
            raise ValueError("split_inventory must contain train, validation, and test in order")


@dataclass(frozen=True, slots=True)
class FoldManifest:
    schema_version: int
    provenance: ManifestProvenance
    rows: tuple[FoldManifestRow, ...]
    manifest_id: str


def _fold_manifest_identity(
    provenance: ManifestProvenance,
    rows: tuple[FoldManifestRow, ...],
) -> str:
    return stable_digest({"schema_version": 1, "provenance": provenance, "rows": rows})


def build_fold_manifest(
    calendar: GlobalFoldCalendar,
    *,
    provenance: ManifestProvenance,
    inventory_by_fold: Mapping[str, tuple[SplitEndpointInventory, ...]],
) -> FoldManifest:
    expected_ids = {cutoff.fold.fold_id for cutoff in calendar.cutoffs}
    if set(inventory_by_fold) != expected_ids:
        raise ValueError("inventory_by_fold must cover every fold exactly")
    rows = tuple(
        FoldManifestRow(
            fold_id=cutoff.fold.fold_id,
            inner_fold_id=cutoff.inner_fold.inner_fold_id,
            outer_index=cutoff.outer_index,
            history_years=cutoff.history_years,
            symbol_ids=cutoff.symbol_ids,
            train_start=cutoff.fold.train_start,
            train_end=cutoff.fold.train_end,
            validation_start=cutoff.fold.validation_start,
            validation_end=cutoff.fold.validation_end,
            test_start=cutoff.fold.test_start,
            test_end=cutoff.fold.test_end,
            purge_seconds=int(cutoff.fold.purge.total_seconds()),
            embargo_seconds=int(cutoff.fold.embargo.total_seconds()),
            lockbox_start=calendar.lockbox.start,
            lockbox_end=calendar.lockbox.end,
            split_inventory=inventory_by_fold[cutoff.fold.fold_id],
        )
        for cutoff in calendar.cutoffs
    )
    return FoldManifest(1, provenance, rows, _fold_manifest_identity(provenance, rows))


@dataclass(frozen=True, slots=True)
class BatchManifestRow:
    batch_id: str
    fold_id: str
    batch_ordinal: int
    partition: Partition
    anchor_start: datetime
    anchor_end: datetime
    sequence_start: datetime
    feature_end: datetime
    label_end: datetime
    symbol_ids: tuple[str, ...]
    row_count: int
    window_ids: tuple[str, ...]
    dataset_identity: str

    def __post_init__(self) -> None:
        if not self.fold_id.strip():
            raise ValueError("fold_id cannot be blank")
        names = ("anchor_start", "anchor_end", "sequence_start", "feature_end", "label_end")
        for name in names:
            object.__setattr__(self, name, as_utc(getattr(self, name), field_name=name))
        if self.anchor_end < self.anchor_start:
            raise ValueError("anchor_end cannot precede anchor_start")
        if self.sequence_start > self.feature_end or self.feature_end > self.anchor_end:
            raise ValueError("batch feature endpoints are not causal")
        if self.label_end <= self.anchor_end:
            raise ValueError("batch label_end must be after the last anchor")
        if self.row_count != len(self.window_ids) or self.row_count <= 0:
            raise ValueError("row_count must match non-empty window_ids")
        if tuple(sorted(set(self.symbol_ids))) != self.symbol_ids:
            raise ValueError("symbol_ids must be unique and sorted")


@dataclass(frozen=True, slots=True)
class BatchManifest:
    schema_version: int
    provenance: ManifestProvenance
    rows: tuple[BatchManifestRow, ...]
    manifest_id: str


def _batch_manifest_identity(
    provenance: ManifestProvenance,
    rows: tuple[BatchManifestRow, ...],
) -> str:
    return stable_digest({"schema_version": 1, "provenance": provenance, "rows": rows})


def build_batch_manifest(
    rows: Iterable[BatchManifestRow],
    *,
    provenance: ManifestProvenance,
) -> BatchManifest:
    materialized = tuple(rows)
    if not materialized:
        raise ValueError("batch manifest must contain rows")
    ordinals = tuple(row.batch_ordinal for row in materialized)
    if ordinals != tuple(range(len(materialized))):
        raise ValueError("batch ordinals must be contiguous from zero")
    if len({row.fold_id for row in materialized}) != 1:
        raise ValueError("batch manifest rows must belong to one fold")
    if any(
        left.anchor_end >= right.anchor_start for left, right in zip(materialized, materialized[1:])
    ):
        raise ValueError("batch anchor blocks must have strictly later, non-overlapping starts")
    return BatchManifest(
        1,
        provenance,
        materialized,
        _batch_manifest_identity(provenance, materialized),
    )


@dataclass(frozen=True, slots=True)
class ManifestWrite:
    path: Path
    checksum_sha256: str
    manifest_id: str
    row_count: int


def _arrow_modules() -> tuple[Any, Any]:
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "manifest persistence requires the project dependency 'pyarrow'"
        ) from exc
    return pa, pq


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_table(path: str | Path, table: Any, manifest_id: str) -> ManifestWrite:
    _, pq = _arrow_modules()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        pq.write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
            version="2.6",
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return ManifestWrite(target, _sha256_file(target), manifest_id, table.num_rows)


def _verify_checksum(path: Path, expected_checksum: str | None) -> None:
    if expected_checksum is not None and _sha256_file(path) != expected_checksum:
        raise ManifestIntegrityError("manifest file checksum does not match")


def _utc_micros(value: datetime) -> int:
    normalized = as_utc(value)
    epoch = datetime(1970, 1, 1, tzinfo=normalized.tzinfo)
    delta = normalized - epoch
    return ((delta.days * 86_400) + delta.seconds) * 1_000_000 + delta.microseconds


def _optional_utc_micros(value: datetime | None) -> int | None:
    return _utc_micros(value) if value is not None else None


@overload
def _datetime_from_micros(value: int) -> datetime: ...


@overload
def _datetime_from_micros(value: None) -> None: ...


def _datetime_from_micros(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=value)


def _provenance_from_row(row: dict[str, Any]) -> ManifestProvenance:
    return ManifestProvenance(
        row["panel_checksum"],
        row["quarantine_checksum"],
        row["config_checksum"],
        row["universe_snapshot_id"],
    )


def write_fold_manifest_parquet(path: str | Path, manifest: FoldManifest) -> ManifestWrite:
    pa, _ = _arrow_modules()
    records = []
    for row in manifest.rows:
        for inventory in row.split_inventory:
            records.append(
                {
                    "schema_version": manifest.schema_version,
                    "manifest_id": manifest.manifest_id,
                    "panel_checksum": manifest.provenance.panel_checksum,
                    "quarantine_checksum": manifest.provenance.quarantine_checksum,
                    "config_checksum": manifest.provenance.config_checksum,
                    "universe_snapshot_id": manifest.provenance.universe_snapshot_id,
                    "fold_id": row.fold_id,
                    "inner_fold_id": row.inner_fold_id,
                    "outer_index": row.outer_index,
                    "history_years": row.history_years,
                    "symbol_ids": list(row.symbol_ids),
                    "train_start": _utc_micros(row.train_start),
                    "train_end": _utc_micros(row.train_end),
                    "validation_start": _utc_micros(row.validation_start),
                    "validation_end": _utc_micros(row.validation_end),
                    "test_start": _utc_micros(row.test_start),
                    "test_end": _utc_micros(row.test_end),
                    "purge_seconds": row.purge_seconds,
                    "embargo_seconds": row.embargo_seconds,
                    "lockbox_start": _utc_micros(row.lockbox_start),
                    "lockbox_end": _utc_micros(row.lockbox_end),
                    "split_role": inventory.partition.value,
                    "row_count": inventory.row_count,
                    "sequence_start": _optional_utc_micros(inventory.sequence_start),
                    "feature_end": _optional_utc_micros(inventory.feature_end),
                    "label_end": _optional_utc_micros(inventory.label_end),
                }
            )
    metadata = {b"manifest_kind": b"fold", b"manifest_id": manifest.manifest_id.encode()}
    table = pa.Table.from_pylist(records).replace_schema_metadata(metadata)
    return _write_table(path, table, manifest.manifest_id)


def read_fold_manifest_parquet(
    path: str | Path,
    *,
    expected_checksum: str | None = None,
) -> FoldManifest:
    _, pq = _arrow_modules()
    source = Path(path)
    _verify_checksum(source, expected_checksum)
    records = pq.read_table(source).to_pylist()
    if not records:
        raise ManifestIntegrityError("fold manifest is empty")
    if any(record["schema_version"] != 1 for record in records):
        raise ManifestIntegrityError("unsupported fold manifest schema version")
    provenance = _provenance_from_row(records[0])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order = []
    for record in records:
        if _provenance_from_row(record) != provenance:
            raise ManifestIntegrityError("fold manifest provenance is inconsistent")
        if record["fold_id"] not in grouped:
            order.append(record["fold_id"])
        grouped[record["fold_id"]].append(record)
    rows = []
    role_order = {Partition.TRAIN: 0, Partition.VALIDATION: 1, Partition.TEST: 2}
    for fold_id in order:
        group = grouped[fold_id]
        first = group[0]
        repeated_fields = (
            "schema_version",
            "manifest_id",
            "fold_id",
            "inner_fold_id",
            "outer_index",
            "history_years",
            "symbol_ids",
            "train_start",
            "train_end",
            "validation_start",
            "validation_end",
            "test_start",
            "test_end",
            "purge_seconds",
            "embargo_seconds",
            "lockbox_start",
            "lockbox_end",
        )
        if any(any(item[field] != first[field] for field in repeated_fields) for item in group[1:]):
            raise ManifestIntegrityError("fold split rows have inconsistent repeated metadata")
        inventory = tuple(
            sorted(
                (
                    SplitEndpointInventory(
                        Partition(item["split_role"]),
                        item["row_count"],
                        _datetime_from_micros(item["sequence_start"]),
                        _datetime_from_micros(item["feature_end"]),
                        _datetime_from_micros(item["label_end"]),
                    )
                    for item in group
                ),
                key=lambda item: role_order[item.partition],
            )
        )
        rows.append(
            FoldManifestRow(
                fold_id,
                first["inner_fold_id"],
                first["outer_index"],
                first["history_years"],
                tuple(first["symbol_ids"]),
                _datetime_from_micros(first["train_start"]),
                _datetime_from_micros(first["train_end"]),
                _datetime_from_micros(first["validation_start"]),
                _datetime_from_micros(first["validation_end"]),
                _datetime_from_micros(first["test_start"]),
                _datetime_from_micros(first["test_end"]),
                first["purge_seconds"],
                first["embargo_seconds"],
                _datetime_from_micros(first["lockbox_start"]),
                _datetime_from_micros(first["lockbox_end"]),
                inventory,
            )
        )
    manifest_id = records[0]["manifest_id"]
    manifest = FoldManifest(1, provenance, tuple(rows), manifest_id)
    if any(record["manifest_id"] != manifest_id for record in records):
        raise ManifestIntegrityError("fold manifest IDs are inconsistent")
    if _fold_manifest_identity(provenance, manifest.rows) != manifest_id:
        raise ManifestIntegrityError("fold manifest identity does not match content")
    return manifest


def write_batch_manifest_parquet(path: str | Path, manifest: BatchManifest) -> ManifestWrite:
    pa, _ = _arrow_modules()
    records = [
        {
            "schema_version": manifest.schema_version,
            "manifest_id": manifest.manifest_id,
            "panel_checksum": manifest.provenance.panel_checksum,
            "quarantine_checksum": manifest.provenance.quarantine_checksum,
            "config_checksum": manifest.provenance.config_checksum,
            "universe_snapshot_id": manifest.provenance.universe_snapshot_id,
            "batch_id": row.batch_id,
            "fold_id": row.fold_id,
            "batch_ordinal": row.batch_ordinal,
            "partition": row.partition.value,
            "anchor_start": _utc_micros(row.anchor_start),
            "anchor_end": _utc_micros(row.anchor_end),
            "sequence_start": _utc_micros(row.sequence_start),
            "feature_end": _utc_micros(row.feature_end),
            "label_end": _utc_micros(row.label_end),
            "symbol_ids": list(row.symbol_ids),
            "row_count": row.row_count,
            "window_ids": list(row.window_ids),
            "dataset_identity": row.dataset_identity,
        }
        for row in manifest.rows
    ]
    metadata = {b"manifest_kind": b"batch", b"manifest_id": manifest.manifest_id.encode()}
    table = pa.Table.from_pylist(records).replace_schema_metadata(metadata)
    return _write_table(path, table, manifest.manifest_id)


def read_batch_manifest_parquet(
    path: str | Path,
    *,
    expected_checksum: str | None = None,
) -> BatchManifest:
    _, pq = _arrow_modules()
    source = Path(path)
    _verify_checksum(source, expected_checksum)
    records = pq.read_table(source).to_pylist()
    if not records:
        raise ManifestIntegrityError("batch manifest is empty")
    if any(record["schema_version"] != 1 for record in records):
        raise ManifestIntegrityError("unsupported batch manifest schema version")
    provenance = _provenance_from_row(records[0])
    rows = tuple(
        BatchManifestRow(
            item["batch_id"],
            item["fold_id"],
            item["batch_ordinal"],
            Partition(item["partition"]),
            _datetime_from_micros(item["anchor_start"]),
            _datetime_from_micros(item["anchor_end"]),
            _datetime_from_micros(item["sequence_start"]),
            _datetime_from_micros(item["feature_end"]),
            _datetime_from_micros(item["label_end"]),
            tuple(item["symbol_ids"]),
            item["row_count"],
            tuple(item["window_ids"]),
            item["dataset_identity"],
        )
        for item in records
    )
    manifest_id = records[0]["manifest_id"]
    if any(_provenance_from_row(item) != provenance for item in records):
        raise ManifestIntegrityError("batch manifest provenance is inconsistent")
    if any(item["manifest_id"] != manifest_id for item in records):
        raise ManifestIntegrityError("batch manifest IDs are inconsistent")
    manifest = BatchManifest(1, provenance, rows, manifest_id)
    if _batch_manifest_identity(provenance, rows) != manifest_id:
        raise ManifestIntegrityError("batch manifest identity does not match content")
    return manifest
