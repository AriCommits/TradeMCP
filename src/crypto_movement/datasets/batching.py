"""Chronological anchor-time block batching with reproducible membership."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import overload

from crypto_movement.artifacts import stable_digest
from crypto_movement.datasets.cache import CachedWindowDataset
from crypto_movement.datasets.windows import BarWindow, LazyBarWindowDataset, WindowIndexEntry
from crypto_movement.splits.manifests import (
    BatchManifest,
    BatchManifestRow,
    ManifestProvenance,
    build_batch_manifest,
)
from crypto_movement.splits.walk_forward import Partition

WindowDataset = LazyBarWindowDataset | CachedWindowDataset
IndexedEntry = tuple[int, WindowIndexEntry]
AnchorBlock = tuple[IndexedEntry, ...]


@dataclass(frozen=True, slots=True)
class WindowBatch:
    batch_id: str
    ordinal: int
    partition: Partition
    windows: tuple[BarWindow, ...]

    def __post_init__(self) -> None:
        if not self.windows:
            raise ValueError("batch must contain windows")
        order = tuple(
            (window.entry.anchor_timestamp, window.entry.symbol.canonical_id)
            for window in self.windows
        )
        if order != tuple(sorted(order)):
            raise ValueError("batch rows must be anchor-first then symbol")

    @property
    def anchor_timestamps(self) -> tuple[datetime, ...]:
        return tuple(dict.fromkeys(window.entry.anchor_timestamp for window in self.windows))


class SequentialBlockBatcher(Sequence[WindowBatch]):
    """Yield contiguous anchor blocks without a random row sampler."""

    def __init__(
        self,
        dataset: WindowDataset,
        *,
        partition_by_window: Mapping[str, Partition],
        partition: Partition,
        anchors_per_batch: int,
        fold_id: str,
        manifest_provenance: ManifestProvenance,
    ) -> None:
        if partition not in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST):
            raise ValueError("batches require a train, validation, or test partition")
        if isinstance(anchors_per_batch, bool) or not isinstance(anchors_per_batch, int):
            raise TypeError("anchors_per_batch must be an integer")
        if anchors_per_batch <= 0:
            raise ValueError("anchors_per_batch must be positive")
        self.dataset = dataset
        self.partition = partition
        self.anchors_per_batch = anchors_per_batch
        if not fold_id.strip():
            raise ValueError("fold_id cannot be blank")
        self.fold_id = fold_id
        self.manifest_provenance = manifest_provenance
        source = dataset.source if isinstance(dataset, CachedWindowDataset) else dataset
        self._dataset_identity = source.identity
        self._entries = source.entries
        all_ids = {entry.window_id for entry in self._entries}
        if set(partition_by_window) != all_ids:
            raise ValueError("partition mapping must cover every dataset window exactly")
        selected = [
            (index, entry)
            for index, entry in enumerate(self._entries)
            if partition_by_window[entry.window_id] is partition
        ]
        self._blocks = self._build_blocks(selected, source.spec.anchor_stride)
        self._manifest = self._build_manifest()

    def _build_blocks(
        self, selected: list[IndexedEntry], stride: timedelta
    ) -> tuple[AnchorBlock, ...]:
        by_anchor: dict[datetime, list[IndexedEntry]] = defaultdict(list)
        for item in selected:
            by_anchor[item[1].anchor_timestamp].append(item)
        anchors = sorted(by_anchor)
        blocks: list[AnchorBlock] = []
        current: list[IndexedEntry] = []
        current_anchor_count = 0
        previous: datetime | None = None
        for anchor in anchors:
            if previous is not None and (
                anchor != previous + stride or current_anchor_count >= self.anchors_per_batch
            ):
                blocks.append(tuple(current))
                current = []
                current_anchor_count = 0
            current.extend(sorted(by_anchor[anchor], key=lambda item: item[1].symbol.canonical_id))
            current_anchor_count += 1
            previous = anchor
        if current:
            blocks.append(tuple(current))
        return tuple(blocks)

    def _batch_id(self, ordinal: int, block: AnchorBlock) -> str:
        return stable_digest(
            {
                "dataset_identity": self._dataset_identity,
                "fold_id": self.fold_id,
                "partition": self.partition,
                "ordinal": ordinal,
                "window_ids": tuple(entry.window_id for _, entry in block),
            }
        )

    def _build_manifest(self) -> BatchManifest:
        rows = []
        for ordinal, block in enumerate(self._blocks):
            entries = tuple(entry for _, entry in block)
            rows.append(
                BatchManifestRow(
                    batch_id=self._batch_id(ordinal, block),
                    fold_id=self.fold_id,
                    batch_ordinal=ordinal,
                    partition=self.partition,
                    anchor_start=entries[0].anchor_timestamp,
                    anchor_end=entries[-1].anchor_timestamp,
                    sequence_start=min(entry.sequence_start for entry in entries),
                    feature_end=max(entry.feature_end for entry in entries),
                    label_end=max(entry.label_end for entry in entries),
                    symbol_ids=tuple(sorted({entry.symbol.canonical_id for entry in entries})),
                    row_count=len(entries),
                    window_ids=tuple(entry.window_id for entry in entries),
                    dataset_identity=self._dataset_identity,
                )
            )
        if not rows:
            raise ValueError(f"no windows belong to partition {self.partition.value}")
        return build_batch_manifest(rows, provenance=self.manifest_provenance)

    @property
    def manifest(self) -> BatchManifest:
        return self._manifest

    def __len__(self) -> int:
        return len(self._blocks)

    @overload
    def __getitem__(self, index: int) -> WindowBatch: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[WindowBatch]: ...

    def __getitem__(self, index: int | slice) -> WindowBatch | Sequence[WindowBatch]:
        if isinstance(index, slice):
            return tuple(self[item] for item in range(*index.indices(len(self))))
        block = self._blocks[index]
        return WindowBatch(
            batch_id=self._batch_id(index, block),
            ordinal=index,
            partition=self.partition,
            windows=tuple(self.dataset[dataset_index] for dataset_index, _ in block),
        )

    def __iter__(self) -> Iterator[WindowBatch]:
        for index in range(len(self)):
            yield self[index]
