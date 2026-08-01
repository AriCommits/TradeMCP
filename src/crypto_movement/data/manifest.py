"""Checksummed download manifests with request and provider provenance."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from crypto_movement.data.collector import CollectionResult
from crypto_movement.data.storage import PartitionWrite, sha256_file


class ManifestIntegrityError(RuntimeError):
    """Raised when manifest content or a referenced partition fails verification."""


@dataclass(frozen=True, slots=True)
class ManifestPartition:
    schema_version: int
    checksum_algorithm: str
    relative_path: str
    checksum_sha256: str
    semantic_id: str
    row_count: int
    first_open: datetime
    last_close: datetime

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ManifestIntegrityError("partition record schema_version must be 1")
        if self.checksum_algorithm != "sha256":
            raise ManifestIntegrityError("partition checksum algorithm must be sha256")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checksum_algorithm": self.checksum_algorithm,
            "relative_path": self.relative_path,
            "checksum_sha256": self.checksum_sha256,
            "semantic_id": self.semantic_id,
            "row_count": self.row_count,
            "first_open": self.first_open.isoformat(),
            "last_close": self.last_close.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DownloadManifest:
    manifest_id: str
    created_at: datetime
    provider_name: str
    universe_snapshot_id: str
    request: dict[str, Any]
    page_response_ids: tuple[str, ...]
    cache_hits: int
    provider_fetches: int
    partitions: tuple[ManifestPartition, ...]

    def identity_payload(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "universe_snapshot_id": self.universe_snapshot_id,
            "request": self.request,
            "page_response_ids": list(self.page_response_ids),
            "partitions": [item.to_dict() for item in self.partitions],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "manifest_id": self.manifest_id,
            "created_at": self.created_at.isoformat(),
            **self.identity_payload(),
            "cache_hits": self.cache_hits,
            "provider_fetches": self.provider_fetches,
        }


def _identity(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(
    collection: CollectionResult,
    *,
    provider_name: str,
    universe_snapshot_id: str,
    partition_root: str | Path,
    partitions: tuple[PartitionWrite, ...],
) -> DownloadManifest:
    """Create a stable manifest; operational cache counters do not alter identity."""

    if not provider_name.strip() or not universe_snapshot_id.strip():
        raise ValueError("provider_name and universe_snapshot_id cannot be blank")
    root = Path(partition_root).resolve()
    records: list[ManifestPartition] = []
    for item in sorted(partitions, key=lambda value: str(value.path)):
        resolved = item.path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("manifest partition must remain inside partition_root") from exc
        records.append(
            ManifestPartition(
                schema_version=1,
                checksum_algorithm="sha256",
                relative_path=relative,
                checksum_sha256=item.checksum_sha256,
                semantic_id=item.semantic_id,
                row_count=item.row_count,
                first_open=item.first_open,
                last_close=item.last_close,
            )
        )
    request = collection.request
    request_payload = {
        "request_id": request.request_id,
        "venue": request.symbol.venue.venue,
        "instrument_type": request.symbol.venue.instrument_type.value,
        "canonical_asset": request.symbol.canonical_asset,
        "quote_asset": request.symbol.quote_asset,
        "venue_symbol": request.symbol.venue_symbol,
        "interval": request.interval.value,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "page_size": request.page_size,
    }
    provisional = DownloadManifest(
        manifest_id="pending",
        created_at=max(
            (bar.downloaded_at for bar in collection.bars),
            default=request.end,
        ),
        provider_name=provider_name,
        universe_snapshot_id=universe_snapshot_id,
        request=request_payload,
        page_response_ids=collection.page_response_ids,
        cache_hits=collection.cache_hits,
        provider_fetches=collection.provider_fetches,
        partitions=tuple(records),
    )
    return DownloadManifest(
        manifest_id=_identity(provisional.identity_payload()),
        created_at=provisional.created_at,
        provider_name=provider_name,
        universe_snapshot_id=universe_snapshot_id,
        request=request_payload,
        page_response_ids=collection.page_response_ids,
        cache_hits=collection.cache_hits,
        provider_fetches=collection.provider_fetches,
        partitions=tuple(records),
    )


def write_manifest(manifest: DownloadManifest, root: str | Path) -> Path:
    directory = Path(root).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"download-{manifest.manifest_id}.json"
    content = json.dumps(manifest.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        existing.pop("cache_hits", None)
        existing.pop("provider_fetches", None)
        proposed = manifest.to_dict()
        proposed.pop("cache_hits", None)
        proposed.pop("provider_fetches", None)
        if existing != proposed:
            raise ManifestIntegrityError(f"refusing to mutate download manifest: {target}")
        return target
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def verify_manifest(manifest: DownloadManifest, partition_root: str | Path) -> None:
    """Raise if identity, path containment, size, or content checksum was altered."""

    if _identity(manifest.identity_payload()) != manifest.manifest_id:
        raise ManifestIntegrityError("manifest identity does not match its provenance")
    root = Path(partition_root).resolve()
    for record in manifest.partitions:
        if record.schema_version != 1:
            raise ManifestIntegrityError("partition record schema_version must be 1")
        if record.checksum_algorithm != "sha256":
            raise ManifestIntegrityError("partition checksum algorithm must be sha256")
        path = (root / record.relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ManifestIntegrityError("manifest partition escapes partition root") from exc
        if not path.is_file():
            raise ManifestIntegrityError(f"manifest partition is missing: {record.relative_path}")
        actual = sha256_file(path)
        if actual != record.checksum_sha256:
            raise ManifestIntegrityError(
                f"manifest checksum mismatch: {record.relative_path}"
            )


def load_manifest(path: str | Path) -> DownloadManifest:
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestIntegrityError(f"manifest is unreadable: {manifest_path}") from exc
    expected = {
        "schema_version",
        "manifest_id",
        "created_at",
        "provider_name",
        "universe_snapshot_id",
        "request",
        "page_response_ids",
        "cache_hits",
        "provider_fetches",
        "partitions",
    }
    if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != 1:
        raise ManifestIntegrityError("manifest schema is invalid")
    try:
        partitions = tuple(
            ManifestPartition(
                schema_version=item["schema_version"],
                checksum_algorithm=item["checksum_algorithm"],
                relative_path=item["relative_path"],
                checksum_sha256=item["checksum_sha256"],
                semantic_id=item["semantic_id"],
                row_count=item["row_count"],
                first_open=datetime.fromisoformat(item["first_open"]),
                last_close=datetime.fromisoformat(item["last_close"]),
            )
            for item in value["partitions"]
        )
        manifest = DownloadManifest(
            manifest_id=value["manifest_id"],
            created_at=datetime.fromisoformat(value["created_at"]),
            provider_name=value["provider_name"],
            universe_snapshot_id=value["universe_snapshot_id"],
            request=value["request"],
            page_response_ids=tuple(value["page_response_ids"]),
            cache_hits=value["cache_hits"],
            provider_fetches=value["provider_fetches"],
            partitions=partitions,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestIntegrityError("manifest content is invalid") from exc
    if _identity(manifest.identity_payload()) != manifest.manifest_id:
        raise ManifestIntegrityError("manifest identity does not match its content")
    return manifest
