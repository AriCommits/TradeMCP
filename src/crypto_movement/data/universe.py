"""Deterministic universe eligibility and immutable snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from crypto_movement.contracts import InstrumentType, SymbolIdentity, VenueIdentity
from crypto_movement.time import as_utc


class UniverseConfigError(ValueError):
    """Raised when universe eligibility configuration is invalid."""


class CandidateCategory(str, Enum):
    STANDARD = "standard"
    STABLECOIN = "stablecoin"
    REDUNDANT_WRAPPER = "redundant_wrapper"
    TOKENIZED_ASSET = "tokenized_asset"


class ExclusionReason(str, Enum):
    STABLECOIN = "stablecoin"
    REDUNDANT_WRAPPER = "redundant_wrapper"
    TOKENIZED_ASSET = "tokenized_asset"
    INACTIVE = "inactive"
    INSUFFICIENT_HISTORY = "insufficient_history"
    ILLIQUID = "illiquid"


_CATEGORY_REASON = {
    CandidateCategory.STABLECOIN: ExclusionReason.STABLECOIN,
    CandidateCategory.REDUNDANT_WRAPPER: ExclusionReason.REDUNDANT_WRAPPER,
    CandidateCategory.TOKENIZED_ASSET: ExclusionReason.TOKENIZED_ASSET,
}


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    canonical_asset: str
    venue_symbol: str
    category: CandidateCategory
    active: bool
    history_days: int
    average_daily_quote_volume: float

    def __post_init__(self) -> None:
        asset = self.canonical_asset.strip().upper()
        if not asset or asset != self.canonical_asset:
            raise UniverseConfigError("candidate asset must be an uppercase canonical identifier")
        if not self.venue_symbol.strip():
            raise UniverseConfigError("candidate venue_symbol cannot be blank")
        if isinstance(self.history_days, bool) or self.history_days < 0:
            raise UniverseConfigError("candidate history_days cannot be negative")
        if self.average_daily_quote_volume < 0:
            raise UniverseConfigError("candidate liquidity cannot be negative")


@dataclass(frozen=True, slots=True)
class UniverseConfig:
    schema_version: int
    snapshot_name: str
    captured_at: datetime
    venue: VenueIdentity
    quote_asset: str
    membership_basis: str
    minimum_history_days: int
    minimum_average_daily_quote_volume: float
    candidates: tuple[UniverseCandidate, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise UniverseConfigError("universe schema_version must be 1")
        if not self.snapshot_name.strip() or not self.membership_basis.strip():
            raise UniverseConfigError("snapshot_name and membership_basis cannot be blank")
        object.__setattr__(self, "captured_at", as_utc(self.captured_at, field_name="captured_at"))
        quote = self.quote_asset.strip().upper()
        if not quote:
            raise UniverseConfigError("quote_asset cannot be blank")
        object.__setattr__(self, "quote_asset", quote)
        if self.minimum_history_days < 0:
            raise UniverseConfigError("minimum_history_days cannot be negative")
        if self.minimum_average_daily_quote_volume < 0:
            raise UniverseConfigError("minimum liquidity cannot be negative")
        assets = [item.canonical_asset for item in self.candidates]
        venue_symbols = [item.venue_symbol for item in self.candidates]
        if not assets or len(assets) != len(set(assets)):
            raise UniverseConfigError("candidate assets must be non-empty and unique")
        if len(venue_symbols) != len(set(venue_symbols)):
            raise UniverseConfigError("candidate venue symbols must be unique")


@dataclass(frozen=True, slots=True)
class UniverseExclusion:
    canonical_asset: str
    venue_symbol: str
    reason: ExclusionReason
    detail: str


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    snapshot_id: str
    snapshot_name: str
    captured_at: datetime
    venue: VenueIdentity
    quote_asset: str
    membership_basis: str
    minimum_history_days: int
    minimum_average_daily_quote_volume: float
    included: tuple[SymbolIdentity, ...]
    exclusions: tuple[UniverseExclusion, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "snapshot_id": self.snapshot_id,
            "snapshot_name": self.snapshot_name,
            "captured_at": self.captured_at.isoformat(),
            "venue": self.venue.venue,
            "instrument_type": self.venue.instrument_type.value,
            "quote_asset": self.quote_asset,
            "membership_basis": self.membership_basis,
            "criteria": {
                "minimum_history_days": self.minimum_history_days,
                "minimum_average_daily_quote_volume": self.minimum_average_daily_quote_volume,
            },
            "included": [
                {
                    "canonical_asset": item.canonical_asset,
                    "quote_asset": item.quote_asset,
                    "venue_symbol": item.venue_symbol,
                    "canonical_id": item.canonical_id,
                }
                for item in self.included
            ],
            "exclusions": [
                {
                    "canonical_asset": item.canonical_asset,
                    "venue_symbol": item.venue_symbol,
                    "reason": item.reason.value,
                    "detail": item.detail,
                }
                for item in self.exclusions
            ],
        }


_CONFIG_KEYS = {
    "schema_version",
    "snapshot_name",
    "captured_at",
    "venue",
    "instrument_type",
    "quote_asset",
    "membership_basis",
    "minimum_history_days",
    "minimum_average_daily_quote_volume",
    "candidates",
}
_CANDIDATE_KEYS = {
    "canonical_asset",
    "venue_symbol",
    "category",
    "active",
    "history_days",
    "average_daily_quote_volume",
}


def load_universe_config(path: str | Path) -> UniverseConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise UniverseConfigError(f"universe configuration does not exist: {config_path}")
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise UniverseConfigError(f"invalid universe configuration: {config_path}") from exc
    if not isinstance(loaded, Mapping) or set(loaded) != _CONFIG_KEYS:
        raise UniverseConfigError("universe configuration keys do not match schema")
    candidates_raw = loaded["candidates"]
    if not isinstance(candidates_raw, list):
        raise UniverseConfigError("candidates must be a list")
    candidates: list[UniverseCandidate] = []
    for index, item in enumerate(candidates_raw):
        if not isinstance(item, Mapping) or set(item) != _CANDIDATE_KEYS:
            raise UniverseConfigError(f"candidate {index} keys do not match schema")
        try:
            category = CandidateCategory(item["category"])
        except (TypeError, ValueError) as exc:
            raise UniverseConfigError(f"candidate {index} category is invalid") from exc
        if not isinstance(item["active"], bool):
            raise UniverseConfigError(f"candidate {index} active must be boolean")
        history = item["history_days"]
        liquidity = item["average_daily_quote_volume"]
        if isinstance(history, bool) or not isinstance(history, int):
            raise UniverseConfigError(f"candidate {index} history_days must be integer")
        if isinstance(liquidity, bool) or not isinstance(liquidity, (int, float)):
            raise UniverseConfigError(f"candidate {index} liquidity must be numeric")
        if not isinstance(item["canonical_asset"], str) or not isinstance(
            item["venue_symbol"], str
        ):
            raise UniverseConfigError(f"candidate {index} identifiers must be strings")
        candidates.append(
            UniverseCandidate(
                canonical_asset=item["canonical_asset"],
                venue_symbol=item["venue_symbol"],
                category=category,
                active=item["active"],
                history_days=history,
                average_daily_quote_volume=float(liquidity),
            )
        )
    try:
        captured_at = datetime.fromisoformat(str(loaded["captured_at"]).replace("Z", "+00:00"))
        venue = VenueIdentity(
            str(loaded["venue"]),
            InstrumentType(loaded["instrument_type"]),
        )
    except (TypeError, ValueError) as exc:
        raise UniverseConfigError("universe venue or captured_at is invalid") from exc
    minimum_history = loaded["minimum_history_days"]
    minimum_liquidity = loaded["minimum_average_daily_quote_volume"]
    if isinstance(minimum_history, bool) or not isinstance(minimum_history, int):
        raise UniverseConfigError("minimum_history_days must be an integer")
    if isinstance(minimum_liquidity, bool) or not isinstance(
        minimum_liquidity, (int, float)
    ):
        raise UniverseConfigError("minimum liquidity must be numeric")
    for key in ("snapshot_name", "quote_asset", "membership_basis"):
        if not isinstance(loaded[key], str):
            raise UniverseConfigError(f"{key} must be a string")
    return UniverseConfig(
        schema_version=loaded["schema_version"],
        snapshot_name=loaded["snapshot_name"],
        captured_at=captured_at,
        venue=venue,
        quote_asset=loaded["quote_asset"],
        membership_basis=loaded["membership_basis"],
        minimum_history_days=minimum_history,
        minimum_average_daily_quote_volume=float(minimum_liquidity),
        candidates=tuple(candidates),
    )


def build_universe_snapshot(config: UniverseConfig) -> UniverseSnapshot:
    """Apply one documented exclusion reason to every ineligible candidate."""

    included: list[SymbolIdentity] = []
    exclusions: list[UniverseExclusion] = []
    for candidate in sorted(config.candidates, key=lambda item: item.canonical_asset):
        reason = _CATEGORY_REASON.get(candidate.category)
        detail = f"classification={candidate.category.value}"
        if reason is None and not candidate.active:
            reason = ExclusionReason.INACTIVE
            detail = "active=false"
        if reason is None and candidate.history_days < config.minimum_history_days:
            reason = ExclusionReason.INSUFFICIENT_HISTORY
            detail = (
                f"history_days={candidate.history_days}; "
                f"required={config.minimum_history_days}"
            )
        if (
            reason is None
            and candidate.average_daily_quote_volume
            < config.minimum_average_daily_quote_volume
        ):
            reason = ExclusionReason.ILLIQUID
            detail = (
                f"average_daily_quote_volume={candidate.average_daily_quote_volume:g}; "
                f"required={config.minimum_average_daily_quote_volume:g}"
            )
        if reason is None:
            included.append(
                SymbolIdentity(
                    config.venue,
                    candidate.canonical_asset,
                    config.quote_asset,
                    candidate.venue_symbol,
                )
            )
        else:
            exclusions.append(
                UniverseExclusion(
                    candidate.canonical_asset,
                    candidate.venue_symbol,
                    reason,
                    detail,
                )
            )
    identity_payload = {
        "snapshot_name": config.snapshot_name,
        "captured_at": config.captured_at.isoformat(),
        "venue": config.venue.canonical_id,
        "quote_asset": config.quote_asset,
        "membership_basis": config.membership_basis,
        "criteria": [
            config.minimum_history_days,
            config.minimum_average_daily_quote_volume,
        ],
        "included": [item.canonical_id for item in included],
        "exclusions": [
            [item.canonical_asset, item.venue_symbol, item.reason.value, item.detail]
            for item in exclusions
        ],
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return UniverseSnapshot(
        snapshot_id=identity,
        snapshot_name=config.snapshot_name,
        captured_at=config.captured_at,
        venue=config.venue,
        quote_asset=config.quote_asset,
        membership_basis=config.membership_basis,
        minimum_history_days=config.minimum_history_days,
        minimum_average_daily_quote_volume=config.minimum_average_daily_quote_volume,
        included=tuple(included),
        exclusions=tuple(exclusions),
    )


def write_universe_snapshot(snapshot: UniverseSnapshot, root: str | Path) -> Path:
    directory = Path(root).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"universe-{snapshot.snapshot_id}.json"
    content = json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n"
    if target.exists():
        if target.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"refusing to mutate universe snapshot: {target}")
        return target
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
