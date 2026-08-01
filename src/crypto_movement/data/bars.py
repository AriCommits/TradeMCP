"""Exact causal 15-to-30-minute aggregation with constituent lineage."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_movement.contracts import CandleInterval, RawBar, ResampledBar
from crypto_movement.data.providers import raw_bar_to_dict


class BarConstructionError(ValueError):
    """Raised when causal cadence construction requirements are not met."""


class IncompleteBarPairError(BarConstructionError):
    """Raised when a half-hour does not contain exactly its two expected candles."""


@dataclass(frozen=True, slots=True)
class ConstituentProvenance:
    partition_path: str
    partition_checksum_sha256: str
    manifest_id: str

    def __post_init__(self) -> None:
        path = Path(self.partition_path)
        if path.is_absolute() or ".." in path.parts or not self.partition_path.strip():
            raise ValueError("partition_path must be a safe relative path")
        checksum = self.partition_checksum_sha256.lower()
        if len(checksum) != 64 or any(
            character not in "0123456789abcdef" for character in checksum
        ):
            raise ValueError("partition checksum must be SHA-256")
        if not self.manifest_id.strip():
            raise ValueError("manifest_id cannot be blank")
        object.__setattr__(self, "partition_path", path.as_posix())
        object.__setattr__(self, "partition_checksum_sha256", checksum)


@dataclass(frozen=True, slots=True)
class ConstituentIdentity:
    raw_bar_id: str
    symbol_id: str
    interval: str
    timestamp_open: datetime
    timestamp_close: datetime
    source: str
    partition_path: str
    partition_checksum_sha256: str
    manifest_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "raw_bar_id": self.raw_bar_id,
            "symbol_id": self.symbol_id,
            "interval": self.interval,
            "timestamp_open": self.timestamp_open.isoformat(),
            "timestamp_close": self.timestamp_close.isoformat(),
            "source": self.source,
            "partition_path": self.partition_path,
            "partition_checksum_sha256": self.partition_checksum_sha256,
            "manifest_id": self.manifest_id,
        }


@dataclass(frozen=True, slots=True)
class BarLineage:
    target_symbol_id: str
    target_interval: str
    target_open: datetime
    target_close: datetime
    constituents: tuple[ConstituentIdentity, ...]
    schema_version: int = 1
    lineage_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("bar lineage schema_version must be 1")
        if self.target_interval != CandleInterval.THIRTY_MINUTES.value:
            raise ValueError("lineage target interval must be 30m")
        if len(self.constituents) != 2:
            raise ValueError("30m lineage must contain exactly two constituents")
        first, second = self.constituents
        if first.interval != "15m" or second.interval != "15m":
            raise ValueError("30m lineage constituents must be 15m")
        if first.timestamp_open != self.target_open:
            raise ValueError("first constituent must open at target_open")
        if first.timestamp_close != second.timestamp_open:
            raise ValueError("constituents must be contiguous")
        if second.timestamp_close != self.target_close:
            raise ValueError("second constituent must close at target_close")
        payload = {
            "schema_version": self.schema_version,
            "target_symbol_id": self.target_symbol_id,
            "target_interval": self.target_interval,
            "target_open": self.target_open.isoformat(),
            "target_close": self.target_close.isoformat(),
            "constituents": [item.to_dict() for item in self.constituents],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "lineage_id", hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True, slots=True)
class LineagedResampledBar:
    bar: ResampledBar
    lineage: BarLineage

    def __post_init__(self) -> None:
        if self.bar.symbol.canonical_id != self.lineage.target_symbol_id:
            raise ValueError("bar and lineage symbol identities differ")
        if (
            self.bar.timestamp_open != self.lineage.target_open
            or self.bar.timestamp_close != self.lineage.target_close
        ):
            raise ValueError("bar and lineage boundaries differ")


@dataclass(frozen=True, slots=True)
class IncompleteBarPairExclusion:
    """Traceable exclusion for one target half-hour lacking an exact 15m pair."""

    target_symbol_id: str
    target_open: datetime
    target_close: datetime
    expected_constituent_opens: tuple[datetime, datetime]
    observed_constituents: tuple[ConstituentIdentity, ...]
    reason: str = "incomplete exact 15m pair"
    schema_version: int = 1
    exclusion_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("pair exclusion schema_version must be 1")
        if not self.target_symbol_id.strip() or not self.reason.strip():
            raise ValueError("pair exclusion identity and reason cannot be blank")
        expected = (
            self.target_open,
            self.target_open + timedelta(minutes=15),
        )
        if self.target_close != self.target_open + timedelta(minutes=30):
            raise ValueError("pair exclusion target must span exactly 30 minutes")
        if self.expected_constituent_opens != expected:
            raise ValueError("pair exclusion expected opens must be the exact half-hour pair")
        observed_opens = tuple(item.timestamp_open for item in self.observed_constituents)
        if observed_opens != tuple(sorted(observed_opens)):
            raise ValueError("pair exclusion constituents must be chronologically ordered")
        if any(item.symbol_id != self.target_symbol_id for item in self.observed_constituents):
            raise ValueError("pair exclusion constituents must share the target symbol")
        payload = {
            "schema_version": self.schema_version,
            "target_symbol_id": self.target_symbol_id,
            "target_open": self.target_open.isoformat(),
            "target_close": self.target_close.isoformat(),
            "expected_constituent_opens": [
                timestamp.isoformat() for timestamp in self.expected_constituent_opens
            ],
            "observed_constituents": [
                constituent.to_dict() for constituent in self.observed_constituents
            ],
            "reason": self.reason,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "exclusion_id", hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True, slots=True)
class BarPanelBuildResult:
    """Complete 30m panel rows and deterministic exclusions for incomplete pairs."""

    bars: tuple[LineagedResampledBar, ...]
    exclusions: tuple[IncompleteBarPairExclusion, ...]

    def __post_init__(self) -> None:
        bar_keys = {(item.bar.symbol.canonical_id, item.bar.timestamp_open) for item in self.bars}
        exclusion_keys = {(item.target_symbol_id, item.target_open) for item in self.exclusions}
        if bar_keys & exclusion_keys:
            raise ValueError("a half-hour cannot be both built and excluded")
        if len(bar_keys) != len(self.bars) or len(exclusion_keys) != len(self.exclusions):
            raise ValueError("panel result cannot contain duplicate target half-hours")


def constituent_key(bar: RawBar) -> tuple[str, datetime]:
    return bar.symbol.canonical_id, bar.timestamp_open


def raw_bar_identity(bar: RawBar) -> str:
    payload = raw_bar_to_dict(bar)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _target_open(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise BarConstructionError("source candle timestamp must be timezone-aware UTC")
    minute = 0 if timestamp.minute < 30 else 30
    return timestamp.astimezone(timezone.utc).replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


def _optional_sum(values: Sequence[float | None]) -> float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _constituent_identity(
    bar: RawBar,
    provenance: ConstituentProvenance,
) -> ConstituentIdentity:
    return ConstituentIdentity(
        raw_bar_id=raw_bar_identity(bar),
        symbol_id=bar.symbol.canonical_id,
        interval=bar.interval.value,
        timestamp_open=bar.timestamp_open,
        timestamp_close=bar.timestamp_close,
        source=bar.source,
        partition_path=provenance.partition_path,
        partition_checksum_sha256=provenance.partition_checksum_sha256,
        manifest_id=provenance.manifest_id,
    )


def build_30_minute_panel(
    bars: Sequence[RawBar],
    provenance_by_constituent: Mapping[
        tuple[str, datetime],
        ConstituentProvenance,
    ],
) -> BarPanelBuildResult:
    """Build every complete exact pair and record incomplete half-hours."""

    groups: dict[tuple[str, datetime], list[RawBar]] = defaultdict(list)
    seen: set[tuple[str, datetime]] = set()
    for bar in bars:
        if bar.interval is not CandleInterval.FIFTEEN_MINUTES:
            raise BarConstructionError("only 15m RawBar values may be resampled to 30m")
        key = constituent_key(bar)
        if key in seen:
            raise BarConstructionError("duplicate 15m constituent")
        seen.add(key)
        groups[(bar.symbol.canonical_id, _target_open(bar.timestamp_open))].append(bar)

    output: list[LineagedResampledBar] = []
    exclusions: list[IncompleteBarPairExclusion] = []
    for (symbol_id, opened_at), members in sorted(groups.items(), key=lambda item: item[0]):
        ordered = tuple(sorted(members, key=lambda item: item.timestamp_open))
        expected_opens = (opened_at, opened_at + timedelta(minutes=15))
        if len(ordered) != 2 or tuple(item.timestamp_open for item in ordered) != expected_opens:
            observed: list[ConstituentIdentity] = []
            for member in ordered:
                try:
                    source = provenance_by_constituent[constituent_key(member)]
                except KeyError as exc:
                    raise BarConstructionError(
                        "every constituent requires partition/checksum lineage"
                    ) from exc
                observed.append(_constituent_identity(member, source))
            exclusions.append(
                IncompleteBarPairExclusion(
                    target_symbol_id=symbol_id,
                    target_open=opened_at,
                    target_close=opened_at + timedelta(minutes=30),
                    expected_constituent_opens=expected_opens,
                    observed_constituents=tuple(observed),
                )
            )
            continue
        first, second = ordered
        if first.symbol != second.symbol:
            raise BarConstructionError("30m constituents must share an exact symbol identity")
        if first.source != second.source:
            raise BarConstructionError("30m constituents must share exact source semantics")
        if first.timestamp_close != second.timestamp_open:
            raise IncompleteBarPairError("30m constituents are not contiguous")
        provenance: list[ConstituentProvenance] = []
        for member in ordered:
            try:
                provenance.append(provenance_by_constituent[constituent_key(member)])
            except KeyError as exc:
                raise BarConstructionError(
                    "every constituent requires partition/checksum lineage"
                ) from exc

        target_close = opened_at + timedelta(minutes=30)
        resampled = ResampledBar(
            symbol=first.symbol,
            interval=CandleInterval.THIRTY_MINUTES,
            source_interval=CandleInterval.FIFTEEN_MINUTES,
            timestamp_open=opened_at,
            timestamp_close=target_close,
            open=first.open,
            high=max(first.high, second.high),
            low=min(first.low, second.low),
            close=second.close,
            constituent_count=2,
            generated_at=max(first.downloaded_at, second.downloaded_at),
            base_volume=_optional_sum((first.base_volume, second.base_volume)),
            quote_volume=_optional_sum((first.quote_volume, second.quote_volume)),
            trade_count=(
                first.trade_count + second.trade_count
                if first.trade_count is not None and second.trade_count is not None
                else None
            ),
            taker_buy_volume=_optional_sum((first.taker_buy_volume, second.taker_buy_volume)),
            open_interest=second.open_interest,
            funding_rate=second.funding_rate,
        )
        lineage = BarLineage(
            target_symbol_id=symbol_id,
            target_interval=CandleInterval.THIRTY_MINUTES.value,
            target_open=opened_at,
            target_close=target_close,
            constituents=tuple(
                _constituent_identity(member, source)
                for member, source in zip(ordered, provenance, strict=True)
            ),
        )
        output.append(LineagedResampledBar(bar=resampled, lineage=lineage))
    return BarPanelBuildResult(tuple(output), tuple(exclusions))


def build_30_minute_bars(
    bars: Sequence[RawBar],
    provenance_by_constituent: Mapping[
        tuple[str, datetime],
        ConstituentProvenance,
    ],
) -> tuple[LineagedResampledBar, ...]:
    """Strict compatibility API that rejects a panel containing any incomplete pair."""

    result = build_30_minute_panel(bars, provenance_by_constituent)
    if result.exclusions:
        first = result.exclusions[0]

        raise IncompleteBarPairError(
            f"incomplete 30m pair for {first.target_symbol_id} at {first.target_open.isoformat()}"
        )
    return result.bars
