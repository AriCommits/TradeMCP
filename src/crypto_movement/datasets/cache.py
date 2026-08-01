"""Deterministic lazy window cache identities and index snapshots."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, overload

from crypto_movement.artifacts import stable_digest
from crypto_movement.datasets.windows import BarWindow, LazyBarWindowDataset


class WindowCacheIntegrityError(RuntimeError):
    """Raised when a cache snapshot does not reproduce dataset membership."""


@dataclass(frozen=True, slots=True)
class WindowIndexSnapshot:
    schema_version: int
    dataset_identity: str
    panel_identity: str
    approval_id: str
    window_ids: tuple[str, ...]
    exclusion_records: tuple[tuple[str, str, str], ...]
    cache_id: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_identity": self.dataset_identity,
            "panel_identity": self.panel_identity,
            "approval_id": self.approval_id,
            "window_ids": list(self.window_ids),
            "exclusion_records": [list(item) for item in self.exclusion_records],
        }


def build_window_index_snapshot(dataset: LazyBarWindowDataset) -> WindowIndexSnapshot:
    exclusion_records = tuple(
        (
            exclusion.symbol.canonical_id,
            exclusion.anchor_timestamp.isoformat(),
            exclusion.reason.value,
        )
        for exclusion in dataset.exclusions
    )
    provisional = WindowIndexSnapshot(
        schema_version=1,
        dataset_identity=dataset.identity,
        panel_identity=dataset.panel.identity,
        approval_id=dataset.panel.approval_id,
        window_ids=tuple(entry.window_id for entry in dataset.entries),
        exclusion_records=exclusion_records,
        cache_id="pending",
    )
    return WindowIndexSnapshot(
        schema_version=1,
        dataset_identity=provisional.dataset_identity,
        panel_identity=provisional.panel_identity,
        approval_id=provisional.approval_id,
        window_ids=provisional.window_ids,
        exclusion_records=provisional.exclusion_records,
        cache_id=stable_digest(provisional.payload()),
    )


def write_window_index_cache(path: str | Path, snapshot: WindowIndexSnapshot) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**snapshot.payload(), "cache_id": snapshot.cache_id}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(encoded + "\n", encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_window_index_cache(
    path: str | Path,
    dataset: LazyBarWindowDataset,
) -> WindowIndexSnapshot:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        snapshot = WindowIndexSnapshot(
            schema_version=payload["schema_version"],
            dataset_identity=payload["dataset_identity"],
            panel_identity=payload["panel_identity"],
            approval_id=payload["approval_id"],
            window_ids=tuple(payload["window_ids"]),
            exclusion_records=tuple(tuple(item) for item in payload["exclusion_records"]),
            cache_id=payload["cache_id"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WindowCacheIntegrityError("window cache content is invalid") from exc
    if snapshot.schema_version != 1 or stable_digest(snapshot.payload()) != snapshot.cache_id:
        raise WindowCacheIntegrityError("window cache identity is invalid")
    expected = build_window_index_snapshot(dataset)
    if snapshot != expected:
        raise WindowCacheIntegrityError("window cache does not match the approved dataset")
    return snapshot


class CachedWindowDataset(Sequence[BarWindow]):
    """On-demand in-memory cache over an identity-verified lazy dataset."""

    def __init__(
        self,
        source: LazyBarWindowDataset,
        snapshot: WindowIndexSnapshot | None = None,
    ) -> None:
        expected = build_window_index_snapshot(source)
        if snapshot is not None and snapshot != expected:
            raise WindowCacheIntegrityError("snapshot does not match source dataset")
        self.source = source
        self.snapshot = expected
        self._cache: dict[int, BarWindow] = {}

    @property
    def identity(self) -> str:
        return self.snapshot.cache_id

    @property
    def cached_window_count(self) -> int:
        return len(self._cache)

    def __len__(self) -> int:
        return len(self.source)

    @overload
    def __getitem__(self, index: int) -> BarWindow: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[BarWindow]: ...

    def __getitem__(self, index: int | slice) -> BarWindow | Sequence[BarWindow]:
        if isinstance(index, slice):
            return tuple(self[item] for item in range(*index.indices(len(self))))
        normalized = index if index >= 0 else len(self) + index
        if not 0 <= normalized < len(self):
            raise IndexError("window index out of range")
        if normalized not in self._cache:
            self._cache[normalized] = self.source[normalized]
        return self._cache[normalized]
