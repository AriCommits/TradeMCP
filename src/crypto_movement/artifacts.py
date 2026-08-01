"""Deterministic artifact identities and provenance metadata."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from crypto_movement.contracts import (
    FoldIdentity,
    LabelHorizon,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.time import as_utc


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


def _immutable(value: Any) -> Any:
    """Copy common containers into recursively immutable equivalents."""

    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("provenance mapping keys must be strings")
            copied[key] = _immutable(item)
        return MappingProxyType(dict(sorted(copied.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_immutable(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("provenance floats must be finite")
    return value


def _canonical(value: Any) -> Any:
    """Convert supported values to a canonical JSON-compatible structure."""

    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical mapping keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        canonical_items = [_canonical(item) for item in value]
        return sorted(
            canonical_items,
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"), allow_nan=False
            ),
        )
    if isinstance(value, datetime):
        normalized = as_utc(value)
        return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, timedelta):
        return {
            "microseconds": (
                ((value.days * 86_400) + value.seconds) * 1_000_000 + value.microseconds
            )
        }
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("provenance floats must be finite")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported provenance value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a provenance value with deterministic ordering and encoding."""

    return json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def stable_digest(value: Any) -> str:
    """Return the SHA-256 digest of a canonical provenance value."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Model implementation plus all identity-relevant parameters."""

    name: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "model name"))
        object.__setattr__(self, "version", _nonempty(self.version, "model version"))
        object.__setattr__(self, "parameters", _immutable(self.parameters))


@dataclass(frozen=True, slots=True)
class PreprocessorIdentity:
    """Fold-local preprocessing package and fitted-parameter identity."""

    name: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "preprocessor name"))
        object.__setattr__(self, "version", _nonempty(self.version, "preprocessor version"))
        object.__setattr__(self, "parameters", _immutable(self.parameters))


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Human-readable typed wrapper around a provenance SHA-256 digest."""

    digest: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        digest = _nonempty(self.digest, "digest").lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("digest must be a 64-character hexadecimal SHA-256 value")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        object.__setattr__(self, "digest", digest)

    def __str__(self) -> str:
        return f"crypto-artifact-v{self.schema_version}-{self.digest}"


@dataclass(frozen=True, slots=True)
class ArtifactProvenance:
    """Complete scientific provenance used to derive an artifact identity."""

    artifact_kind: str
    venue: VenueIdentity
    instrument: SymbolIdentity
    universe_snapshot_id: str
    data_checksum: str
    config_checksum: str
    code_version: str
    fold: FoldIdentity
    model: ModelIdentity
    preprocessor: PreprocessorIdentity
    seed: int
    prediction_cutoff: datetime
    extra: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field_name in (
            "artifact_kind",
            "universe_snapshot_id",
            "data_checksum",
            "config_checksum",
            "code_version",
        ):
            object.__setattr__(
                self, field_name, _nonempty(getattr(self, field_name), field_name)
            )
        if not isinstance(self.venue, VenueIdentity):
            raise TypeError("venue must be a VenueIdentity")
        if not isinstance(self.instrument, SymbolIdentity):
            raise TypeError("instrument must be a SymbolIdentity")
        if self.instrument.venue != self.venue:
            raise ValueError("instrument venue must match provenance venue")
        if not isinstance(self.fold, FoldIdentity):
            raise TypeError("fold must be a FoldIdentity")
        if not isinstance(self.model, ModelIdentity):
            raise TypeError("model must be a ModelIdentity")
        if not isinstance(self.preprocessor, PreprocessorIdentity):
            raise TypeError("preprocessor must be a PreprocessorIdentity")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if self.seed < 0:
            raise ValueError("seed must be nonnegative")
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise TypeError("schema_version must be an integer")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        object.__setattr__(
            self,
            "prediction_cutoff",
            as_utc(self.prediction_cutoff, field_name="prediction_cutoff"),
        )
        object.__setattr__(self, "extra", _immutable(self.extra))

    @property
    def identity(self) -> ArtifactIdentity:
        return ArtifactIdentity(stable_digest(self), schema_version=self.schema_version)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Stored artifact metadata; storage details do not alter provenance identity."""

    provenance: ArtifactProvenance
    relative_path: str
    content_checksum: str
    byte_size: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, ArtifactProvenance):
            raise TypeError("provenance must be ArtifactProvenance")
        path_text = _nonempty(self.relative_path, "relative_path")
        path = Path(path_text)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("relative_path must remain inside the artifact root")
        object.__setattr__(self, "relative_path", path.as_posix())
        object.__setattr__(
            self, "content_checksum", _nonempty(self.content_checksum, "content_checksum")
        )
        if isinstance(self.byte_size, bool) or not isinstance(self.byte_size, int):
            raise TypeError("byte_size must be an integer")
        if self.byte_size < 0:
            raise ValueError("byte_size must be nonnegative")
        created = as_utc(self.created_at, field_name="created_at")
        if created < self.provenance.prediction_cutoff:
            raise ValueError("created_at cannot predate prediction_cutoff")
        object.__setattr__(self, "created_at", created)

    @property
    def identity(self) -> ArtifactIdentity:
        return self.provenance.identity


@dataclass(frozen=True, slots=True)
class PredictionMetadata:
    """Identity-bearing metadata for one horizon's prediction artifact."""

    provenance: ArtifactProvenance
    horizon: LabelHorizon
    earliest_anchor: datetime
    latest_anchor: datetime
    row_count: int
    generated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, ArtifactProvenance):
            raise TypeError("provenance must be ArtifactProvenance")
        if not isinstance(self.horizon, LabelHorizon):
            raise TypeError("horizon must be a LabelHorizon")
        earliest = as_utc(self.earliest_anchor, field_name="earliest_anchor")
        latest = as_utc(self.latest_anchor, field_name="latest_anchor")
        generated = as_utc(self.generated_at, field_name="generated_at")
        if latest < earliest:
            raise ValueError("latest_anchor must be at or after earliest_anchor")
        if latest > self.provenance.prediction_cutoff:
            raise ValueError("latest_anchor cannot exceed prediction_cutoff")
        if generated < latest:
            raise ValueError("generated_at cannot predate latest_anchor")
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int):
            raise TypeError("row_count must be an integer")
        if self.row_count < 0:
            raise ValueError("row_count must be nonnegative")
        object.__setattr__(self, "earliest_anchor", earliest)
        object.__setattr__(self, "latest_anchor", latest)
        object.__setattr__(self, "generated_at", generated)

    @property
    def identity(self) -> ArtifactIdentity:
        payload = {
            "provenance": self.provenance,
            "horizon": self.horizon,
            "earliest_anchor": self.earliest_anchor,
            "latest_anchor": self.latest_anchor,
            "row_count": self.row_count,
        }
        return ArtifactIdentity(
            stable_digest(payload), schema_version=self.provenance.schema_version
        )
