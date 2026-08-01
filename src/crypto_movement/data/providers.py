"""Provider contracts and a deterministic offline market-data source."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

import yaml

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    RawBar,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.time import as_utc, require_interval_aligned


class ProviderError(RuntimeError):
    """Base error raised by a market-data provider."""


class VenueProviderUnavailable(ProviderError):
    """Raised because no real venue was selected or implemented."""


class DataConfigError(ValueError):
    """Raised when the collection configuration is invalid."""


class CollectionMode(str, Enum):
    FIXTURE = "fixture"
    VENUE = "venue"


@dataclass(frozen=True, slots=True)
class DataRequest:
    """One explicit, half-open candle request."""

    symbol: SymbolIdentity
    interval: CandleInterval
    start: datetime
    end: datetime
    page_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("symbol must be a SymbolIdentity")
        if not isinstance(self.interval, CandleInterval):
            raise TypeError("interval must be a CandleInterval")
        start = require_interval_aligned(
            as_utc(self.start, field_name="start"),
            self.interval.duration,
            field_name="start",
        )
        end = require_interval_aligned(
            as_utc(self.end, field_name="end"),
            self.interval.duration,
            field_name="end",
        )
        if start >= end:
            raise ValueError("request start must precede end")
        if isinstance(self.page_size, bool) or not isinstance(self.page_size, int):
            raise TypeError("page_size must be an integer")
        if self.page_size <= 0:
            raise ValueError("page_size must be positive")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def request_id(self) -> str:
        payload = {
            "symbol": self.symbol.canonical_id,
            "interval": self.interval.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "page_size": self.page_size,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderPage:
    """One provider response page with an opaque continuation cursor."""

    request_id: str
    cursor: str | None
    bars: tuple[RawBar, ...]
    next_cursor: str | None
    response_id: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        if not self.request_id or not self.response_id:
            raise ValueError("page identities cannot be blank")
        object.__setattr__(self, "fetched_at", as_utc(self.fetched_at, field_name="fetched_at"))
        timestamps = [bar.timestamp_open for bar in self.bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("provider page bars must be unique and chronological")
        if self.next_cursor == self.cursor and self.next_cursor is not None:
            raise ValueError("provider continuation cursor must advance")


@runtime_checkable
class MarketDataProvider(Protocol):
    """Strict boundary implemented by fixture and future venue providers."""

    @property
    def name(self) -> str: ...

    @property
    def minimum_request_interval_seconds(self) -> float: ...

    def fetch_page(self, request: DataRequest, cursor: str | None = None) -> ProviderPage: ...


@dataclass(frozen=True, slots=True)
class DataCollectionConfig:
    schema_version: int
    mode: CollectionMode
    provider_name: str
    venue: VenueIdentity
    quote_asset: str
    interval: CandleInterval
    page_size: int
    minimum_request_interval_seconds: float
    cache_path: Path
    raw_path: Path
    manifest_path: Path
    symbols: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise DataConfigError("data schema_version must be 1")
        if not self.provider_name.strip():
            raise DataConfigError("provider_name cannot be blank")
        quote = self.quote_asset.strip().upper()
        if not quote:
            raise DataConfigError("quote_asset cannot be blank")
        if self.page_size <= 0:
            raise DataConfigError("page_size must be positive")
        if self.minimum_request_interval_seconds < 0:
            raise DataConfigError("minimum request interval cannot be negative")
        normalized: dict[str, str] = {}
        for canonical, venue_symbol in self.symbols.items():
            if not isinstance(canonical, str):
                raise DataConfigError("symbol keys must be strings")
            asset = canonical.strip().upper()
            if not asset or asset != canonical:
                raise DataConfigError("symbol keys must be uppercase canonical assets")
            if not isinstance(venue_symbol, str) or not venue_symbol.strip():
                raise DataConfigError(f"venue symbol for {asset} cannot be blank")
            normalized[asset] = venue_symbol.strip()
        if len(normalized) != len(self.symbols) or not normalized:
            raise DataConfigError("symbol mapping must be non-empty and unique")
        object.__setattr__(self, "quote_asset", quote)
        object.__setattr__(self, "symbols", MappingProxyType(normalized))

    def symbol_identity(self, canonical_asset: str) -> SymbolIdentity:
        asset = canonical_asset.strip().upper()
        try:
            venue_symbol = self.symbols[asset]
        except KeyError as exc:
            raise DataConfigError(f"no explicit venue symbol mapping for {asset}") from exc
        return SymbolIdentity(self.venue, asset, self.quote_asset, venue_symbol)


_DATA_KEYS = {
    "schema_version",
    "mode",
    "provider_name",
    "venue",
    "instrument_type",
    "quote_asset",
    "interval",
    "page_size",
    "minimum_request_interval_seconds",
    "cache_path",
    "raw_path",
    "manifest_path",
    "symbols",
}


def _rooted_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DataConfigError(f"{label} must be a non-empty path")
    candidate = Path(value)
    resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DataConfigError(f"{label} must remain inside the project root") from exc
    return resolved


def load_data_config(path: str | Path, *, root: str | Path) -> DataCollectionConfig:
    """Load a strict data configuration without using the process CWD."""

    config_path = Path(path)
    if not config_path.is_file():
        raise DataConfigError(f"data configuration does not exist: {config_path}")
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DataConfigError(f"invalid data configuration: {config_path}") from exc
    if not isinstance(loaded, Mapping) or any(not isinstance(key, str) for key in loaded):
        raise DataConfigError("data config must be a string-keyed mapping")
    missing = _DATA_KEYS - set(loaded)
    unknown = set(loaded) - _DATA_KEYS
    if missing or unknown:
        raise DataConfigError(
            "data config keys do not match schema"
            + (f"; missing={sorted(missing)}" if missing else "")
            + (f"; unknown={sorted(unknown)}" if unknown else "")
        )
    project_root = Path(root).resolve()
    try:
        mode = CollectionMode(loaded["mode"])
        instrument = InstrumentType(loaded["instrument_type"])
        interval = CandleInterval(loaded["interval"])
    except (TypeError, ValueError) as exc:
        raise DataConfigError("mode, instrument_type, or interval is unsupported") from exc
    schema_version = loaded["schema_version"]
    page_size = loaded["page_size"]
    delay = loaded["minimum_request_interval_seconds"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise DataConfigError("schema_version must be an integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int):
        raise DataConfigError("page_size must be an integer")
    if isinstance(delay, bool) or not isinstance(delay, (int, float)):
        raise DataConfigError("minimum_request_interval_seconds must be numeric")
    symbols = loaded["symbols"]
    if not isinstance(symbols, Mapping):
        raise DataConfigError("symbols must be a mapping")
    venue_name = loaded["venue"]
    provider_name = loaded["provider_name"]
    quote_asset = loaded["quote_asset"]
    if not all(isinstance(value, str) for value in (venue_name, provider_name, quote_asset)):
        raise DataConfigError("venue, provider_name, and quote_asset must be strings")
    return DataCollectionConfig(
        schema_version=schema_version,
        mode=mode,
        provider_name=provider_name,
        venue=VenueIdentity(venue_name, instrument),
        quote_asset=quote_asset,
        interval=interval,
        page_size=page_size,
        minimum_request_interval_seconds=float(delay),
        cache_path=_rooted_path(project_root, loaded["cache_path"], "cache_path"),
        raw_path=_rooted_path(project_root, loaded["raw_path"], "raw_path"),
        manifest_path=_rooted_path(project_root, loaded["manifest_path"], "manifest_path"),
        symbols=dict(symbols),
    )


class DeterministicFixtureProvider:
    """Generate deterministic valid candles without network or credentials."""

    def __init__(
        self,
        *,
        name: str = "deterministic-fixture-v1",
        minimum_request_interval_seconds: float = 0.0,
    ) -> None:
        if not name.strip():
            raise ValueError("provider name cannot be blank")
        if minimum_request_interval_seconds < 0:
            raise ValueError("minimum request interval cannot be negative")
        self._name = name.strip()
        self._minimum_interval = float(minimum_request_interval_seconds)

    @property
    def name(self) -> str:
        return self._name

    @property
    def minimum_request_interval_seconds(self) -> float:
        return self._minimum_interval

    @staticmethod
    def _price(symbol: SymbolIdentity, tick: int) -> float:
        digest = hashlib.sha256(symbol.canonical_id.encode()).digest()
        base = 20.0 + int.from_bytes(digest[:4], "big") % 50_000
        cycle = math.sin(tick / 37.0) * 0.004 + math.cos(tick / 113.0) * 0.002
        drift = ((tick % 997) - 498) * 0.0000005
        return base * (1.0 + cycle + drift)

    def fetch_page(self, request: DataRequest, cursor: str | None = None) -> ProviderPage:
        if cursor is None:
            offset = 0
        elif cursor.isdecimal():
            offset = int(cursor)
        else:
            raise ProviderError("fixture cursor must be a nonnegative integer")
        total_seconds = int((request.end - request.start).total_seconds())
        interval_seconds = int(request.interval.duration.total_seconds())
        total_bars, remainder = divmod(total_seconds, interval_seconds)
        if remainder:
            raise ProviderError("request window must contain whole intervals")
        if offset > total_bars:
            raise ProviderError("fixture cursor exceeds request range")
        stop = min(offset + request.page_size, total_bars)
        downloaded_at = request.end + request.interval.duration
        bars: list[RawBar] = []
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        for index in range(offset, stop):
            opened_at = request.start + index * request.interval.duration
            closed_at = opened_at + request.interval.duration
            tick = int((opened_at - epoch).total_seconds() // interval_seconds)
            opened = self._price(request.symbol, tick)
            closed = self._price(request.symbol, tick + 1)
            base_volume = 100.0 + (tick % 211)
            bars.append(
                RawBar(
                    symbol=request.symbol,
                    interval=request.interval,
                    timestamp_open=opened_at,
                    timestamp_close=closed_at,
                    open=opened,
                    high=max(opened, closed) * 1.001,
                    low=min(opened, closed) * 0.999,
                    close=closed,
                    source=self.name,
                    downloaded_at=downloaded_at,
                    base_volume=base_volume,
                    quote_volume=base_volume * (opened + closed) / 2.0,
                    trade_count=50 + tick % 100,
                    taker_buy_volume=base_volume * (0.45 + (tick % 10) / 100.0),
                    open_interest=(
                        base_volume * 100.0
                        if request.symbol.venue.instrument_type is InstrumentType.PERPETUAL
                        else None
                    ),
                    funding_rate=(
                        ((tick % 17) - 8) / 1_000_000
                        if request.symbol.venue.instrument_type is InstrumentType.PERPETUAL
                        else None
                    ),
                )
            )
        next_cursor = str(stop) if stop < total_bars else None
        identity_payload = (
            f"{request.request_id}|{cursor or 'START'}|{next_cursor or 'END'}|"
            f"{','.join(bar.timestamp_open.isoformat() for bar in bars)}"
        )
        return ProviderPage(
            request_id=request.request_id,
            cursor=cursor,
            bars=tuple(bars),
            next_cursor=next_cursor,
            response_id=hashlib.sha256(identity_payload.encode()).hexdigest(),
            fetched_at=downloaded_at,
        )


class UnavailableVenueProvider:
    """Explicit placeholder; a production venue adapter is not silently selected."""

    def __init__(self, provider_name: str, minimum_request_interval_seconds: float) -> None:
        self._name = provider_name
        self._minimum_interval = minimum_request_interval_seconds

    @property
    def name(self) -> str:
        return self._name

    @property
    def minimum_request_interval_seconds(self) -> float:
        return self._minimum_interval

    def fetch_page(self, request: DataRequest, cursor: str | None = None) -> ProviderPage:
        del request, cursor
        raise VenueProviderUnavailable(
            "real venue collection is unavailable until Phase 0 decisions are confirmed "
            "and a reviewed adapter is implemented"
        )


def raw_bar_to_dict(bar: RawBar) -> dict[str, Any]:
    return {
        "venue": bar.symbol.venue.venue,
        "instrument_type": bar.symbol.venue.instrument_type.value,
        "canonical_asset": bar.symbol.canonical_asset,
        "quote_asset": bar.symbol.quote_asset,
        "venue_symbol": bar.symbol.venue_symbol,
        "interval": bar.interval.value,
        "timestamp_open": bar.timestamp_open.isoformat(),
        "timestamp_close": bar.timestamp_close.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "source": bar.source,
        "downloaded_at": bar.downloaded_at.isoformat(),
        "base_volume": bar.base_volume,
        "quote_volume": bar.quote_volume,
        "trade_count": bar.trade_count,
        "taker_buy_volume": bar.taker_buy_volume,
        "open_interest": bar.open_interest,
        "funding_rate": bar.funding_rate,
    }


def raw_bar_from_dict(value: Mapping[str, Any]) -> RawBar:
    required = {
        "venue",
        "instrument_type",
        "canonical_asset",
        "quote_asset",
        "venue_symbol",
        "interval",
        "timestamp_open",
        "timestamp_close",
        "open",
        "high",
        "low",
        "close",
        "source",
        "downloaded_at",
        "base_volume",
        "quote_volume",
        "trade_count",
        "taker_buy_volume",
        "open_interest",
        "funding_rate",
    }
    if set(value) != required:
        raise ProviderError("cached bar schema does not match the required raw-bar schema")
    try:
        venue = VenueIdentity(value["venue"], InstrumentType(value["instrument_type"]))
        symbol = SymbolIdentity(
            venue,
            value["canonical_asset"],
            value["quote_asset"],
            value["venue_symbol"],
        )
        return RawBar(
            symbol=symbol,
            interval=CandleInterval(value["interval"]),
            timestamp_open=datetime.fromisoformat(value["timestamp_open"]),
            timestamp_close=datetime.fromisoformat(value["timestamp_close"]),
            open=value["open"],
            high=value["high"],
            low=value["low"],
            close=value["close"],
            source=value["source"],
            downloaded_at=datetime.fromisoformat(value["downloaded_at"]),
            base_volume=value["base_volume"],
            quote_volume=value["quote_volume"],
            trade_count=value["trade_count"],
            taker_buy_volume=value["taker_buy_volume"],
            open_interest=value["open_interest"],
            funding_rate=value["funding_rate"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("cached raw bar is invalid") from exc
