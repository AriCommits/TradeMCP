"""Immutable partitioned Parquet storage for raw provider candles."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    RawBar,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.providers import raw_bar_to_dict


class ImmutablePartitionError(RuntimeError):
    """Raised when an existing raw partition conflicts with requested content."""


@dataclass(frozen=True, slots=True)
class PartitionWrite:
    path: Path
    checksum_sha256: str
    semantic_id: str
    row_count: int
    first_open: datetime
    last_close: datetime
    created: bool


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _arrow_modules() -> tuple[Any, Any]:
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("Parquet storage requires the project dependency 'pyarrow'") from exc
    return pa, pq


def _component(value: str) -> str:
    cleaned = value.strip().replace("/", "-")
    if not cleaned or not re.fullmatch(r"[A-Za-z0-9._-]+", cleaned):
        raise ValueError(f"unsafe partition component: {value!r}")
    return cleaned


def _semantic_digest(bars: Sequence[RawBar]) -> str:
    rows = [raw_bar_to_dict(bar) for bar in sorted(bars, key=lambda item: item.timestamp_open)]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _schema(pa: Any) -> Any:
    return pa.schema(
        [
            ("venue", pa.string()),
            ("instrument_type", pa.string()),
            ("canonical_asset", pa.string()),
            ("quote_asset", pa.string()),
            ("venue_symbol", pa.string()),
            ("interval", pa.string()),
            ("timestamp_open", pa.timestamp("us", tz="UTC")),
            ("timestamp_close", pa.timestamp("us", tz="UTC")),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("base_volume", pa.float64()),
            ("quote_volume", pa.float64()),
            ("trade_count", pa.int64()),
            ("taker_buy_volume", pa.float64()),
            ("open_interest", pa.float64()),
            ("funding_rate", pa.float64()),
            ("source", pa.string()),
            ("downloaded_at", pa.timestamp("us", tz="UTC")),
        ]
    )


def _parquet_row(bar: RawBar) -> dict[str, Any]:
    return {
        "venue": bar.symbol.venue.venue,
        "instrument_type": bar.symbol.venue.instrument_type.value,
        "canonical_asset": bar.symbol.canonical_asset,
        "quote_asset": bar.symbol.quote_asset,
        "venue_symbol": bar.symbol.venue_symbol,
        "interval": bar.interval.value,
        "timestamp_open": bar.timestamp_open,
        "timestamp_close": bar.timestamp_close,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "base_volume": bar.base_volume,
        "quote_volume": bar.quote_volume,
        "trade_count": bar.trade_count,
        "taker_buy_volume": bar.taker_buy_volume,
        "open_interest": bar.open_interest,
        "funding_rate": bar.funding_rate,
        "source": bar.source,
        "downloaded_at": bar.downloaded_at,
    }


def _bar_from_row(row: dict[str, Any]) -> RawBar:
    venue = VenueIdentity(row["venue"], InstrumentType(row["instrument_type"]))
    symbol = SymbolIdentity(
        venue,
        row["canonical_asset"],
        row["quote_asset"],
        row["venue_symbol"],
    )
    return RawBar(
        symbol=symbol,
        interval=CandleInterval(row["interval"]),
        timestamp_open=row["timestamp_open"],
        timestamp_close=row["timestamp_close"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        source=row["source"],
        downloaded_at=row["downloaded_at"],
        base_volume=row["base_volume"],
        quote_volume=row["quote_volume"],
        trade_count=row["trade_count"],
        taker_buy_volume=row["taker_buy_volume"],
        open_interest=row["open_interest"],
        funding_rate=row["funding_rate"],
    )


class ParquetBarStore:
    """Write content-addressed monthly partitions without changing completed files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def write_bars(self, bars: Iterable[RawBar]) -> tuple[PartitionWrite, ...]:
        materialized = tuple(bars)
        if not materialized:
            return ()
        grouped: dict[tuple[str, ...], list[RawBar]] = defaultdict(list)
        seen: dict[tuple[str, str, datetime], RawBar] = {}
        for bar in materialized:
            if not isinstance(bar, RawBar):
                raise TypeError("ParquetBarStore accepts RawBar values only")
            duplicate_key = (
                bar.symbol.canonical_id,
                bar.interval.value,
                bar.timestamp_open,
            )
            existing = seen.get(duplicate_key)
            if existing is not None:
                if existing != bar:
                    raise ImmutablePartitionError("conflicting duplicate raw candle")
                continue
            seen[duplicate_key] = bar
            pair = f"{bar.symbol.canonical_asset}-{bar.symbol.quote_asset}"
            key = (
                bar.symbol.venue.venue,
                bar.symbol.venue.instrument_type.value,
                bar.interval.value,
                pair,
                f"{bar.timestamp_open.year:04d}",
                f"{bar.timestamp_open.month:02d}",
            )
            grouped[key].append(bar)
        return tuple(
            self._write_partition(key, tuple(grouped[key])) for key in sorted(grouped)
        )

    def _write_partition(
        self, key: tuple[str, ...], bars: tuple[RawBar, ...]
    ) -> PartitionWrite:
        venue, instrument, interval, symbol, year, month = key
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp_open))
        identity = _semantic_digest(ordered)
        directory = (
            self.root
            / f"venue={_component(venue)}"
            / f"instrument={_component(instrument)}"
            / f"interval={_component(interval)}"
            / f"symbol={_component(symbol)}"
            / f"year={year}"
            / f"month={month}"
        )
        target = directory / f"part-{identity[:24]}.parquet"
        if target.exists():
            existing = self.read_bars(target)
            if _semantic_digest(existing) != identity:
                raise ImmutablePartitionError(f"existing partition content is corrupt: {target}")
            return self._record(target, identity, existing, created=False)

        pa, pq = _arrow_modules()
        directory.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            table = pa.Table.from_pylist([_parquet_row(bar) for bar in ordered], schema=_schema(pa))
            pq.write_table(
                table,
                temporary,
                compression="zstd",
                use_dictionary=True,
                write_statistics=True,
            )
            if target.exists():
                existing = self.read_bars(target)
                if _semantic_digest(existing) != identity:
                    raise ImmutablePartitionError(
                        f"concurrent partition conflicts with requested content: {target}"
                    )
                return self._record(target, identity, existing, created=False)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return self._record(target, identity, ordered, created=True)

    @staticmethod
    def _record(
        path: Path,
        semantic_id: str,
        bars: Sequence[RawBar],
        *,
        created: bool,
    ) -> PartitionWrite:
        return PartitionWrite(
            path=path,
            checksum_sha256=sha256_file(path),
            semantic_id=semantic_id,
            row_count=len(bars),
            first_open=bars[0].timestamp_open,
            last_close=bars[-1].timestamp_close,
            created=created,
        )

    @staticmethod
    def read_bars(path: str | Path) -> tuple[RawBar, ...]:
        _, pq = _arrow_modules()
        table = pq.read_table(Path(path))
        bars = tuple(_bar_from_row(row) for row in table.to_pylist())
        timestamps = [bar.timestamp_open for bar in bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ImmutablePartitionError("stored partition is not unique and chronological")
        return bars
