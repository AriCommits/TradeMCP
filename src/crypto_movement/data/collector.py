"""Restartable, cache-aware, rate-limited page collection."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_movement.contracts import RawBar
from crypto_movement.data.providers import (
    DataRequest,
    MarketDataProvider,
    ProviderError,
    ProviderPage,
    raw_bar_from_dict,
    raw_bar_to_dict,
)


class PageCache:
    """Content-validated JSON cache keyed by request identity and cursor."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    @staticmethod
    def _cursor_key(cursor: str | None) -> str:
        if cursor is None:
            return "START"
        return hashlib.sha256(cursor.encode()).hexdigest()[:24]

    def path_for(self, request: DataRequest, cursor: str | None) -> Path:
        return self.root / request.request_id / f"{self._cursor_key(cursor)}.json"

    def load(self, request: DataRequest, cursor: str | None) -> ProviderPage | None:
        path = self.path_for(request, cursor)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"cached provider page is unreadable: {path}") from exc
        expected = {
            "schema_version",
            "request_id",
            "cursor",
            "next_cursor",
            "response_id",
            "fetched_at",
            "bars",
        }
        if not isinstance(value, dict) or set(value) != expected or value["schema_version"] != 1:
            raise ProviderError(f"cached provider page schema is invalid: {path}")
        try:
            page = ProviderPage(
                request_id=value["request_id"],
                cursor=value["cursor"],
                bars=tuple(raw_bar_from_dict(item) for item in value["bars"]),
                next_cursor=value["next_cursor"],
                response_id=value["response_id"],
                fetched_at=__import__("datetime").datetime.fromisoformat(value["fetched_at"]),
            )
        except (TypeError, ValueError, ProviderError) as exc:
            raise ProviderError(f"cached provider page content is invalid: {path}") from exc
        self._validate_identity(request, cursor, page)
        return page

    def store(self, request: DataRequest, cursor: str | None, page: ProviderPage) -> Path:
        self._validate_identity(request, cursor, page)
        path = self.path_for(request, cursor)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "request_id": page.request_id,
            "cursor": page.cursor,
            "next_cursor": page.next_cursor,
            "response_id": page.response_id,
            "fetched_at": page.fetched_at.isoformat(),
            "bars": [raw_bar_to_dict(bar) for bar in page.bars],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ProviderError(f"refusing to mutate cached provider page: {path}")
            return path
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    @staticmethod
    def _validate_identity(
        request: DataRequest, cursor: str | None, page: ProviderPage
    ) -> None:
        if page.request_id != request.request_id or page.cursor != cursor:
            raise ProviderError("provider page does not match request identity and cursor")


@dataclass(frozen=True, slots=True)
class CollectionResult:
    request: DataRequest
    bars: tuple[RawBar, ...]
    page_response_ids: tuple[str, ...]
    cache_hits: int
    provider_fetches: int

    def __post_init__(self) -> None:
        timestamps = [bar.timestamp_open for bar in self.bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("collection result bars must be unique and chronological")

    @property
    def page_count(self) -> int:
        return len(self.page_response_ids)


class MarketDataCollector:
    """Collect all pages while persisting each successful response before advancing."""

    def __init__(
        self,
        provider: MarketDataProvider,
        cache: PageCache,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(provider, MarketDataProvider):
            raise TypeError("provider does not implement MarketDataProvider")
        self.provider = provider
        self.cache = cache
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._last_provider_request: float | None = None

    def _respect_rate_limit(self) -> None:
        minimum = self.provider.minimum_request_interval_seconds
        if minimum < 0:
            raise ProviderError("provider minimum request interval cannot be negative")
        if self._last_provider_request is not None:
            elapsed = self._monotonic() - self._last_provider_request
            remaining = minimum - elapsed
            if remaining > 0:
                self._sleeper(remaining)
        self._last_provider_request = self._monotonic()

    def collect(self, request: DataRequest) -> CollectionResult:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        bars_by_timestamp: dict[Any, RawBar] = {}
        response_ids: list[str] = []
        cache_hits = 0
        provider_fetches = 0

        while True:
            cursor_marker = cursor if cursor is not None else "<START>"
            if cursor_marker in seen_cursors:
                raise ProviderError("provider cursor cycle detected")
            seen_cursors.add(cursor_marker)

            page = self.cache.load(request, cursor)
            if page is None:
                self._respect_rate_limit()
                page = self.provider.fetch_page(request, cursor)
                PageCache._validate_identity(request, cursor, page)
                self._validate_page_bars(request, page)
                self.cache.store(request, cursor, page)
                provider_fetches += 1
            else:
                self._validate_page_bars(request, page)
                cache_hits += 1

            response_ids.append(page.response_id)
            for bar in page.bars:
                existing = bars_by_timestamp.get(bar.timestamp_open)
                if existing is not None and existing != bar:
                    raise ProviderError("conflicting duplicate candle returned by provider")
                bars_by_timestamp[bar.timestamp_open] = bar
            cursor = page.next_cursor
            if cursor is None:
                break

        bars = tuple(bars_by_timestamp[key] for key in sorted(bars_by_timestamp))
        return CollectionResult(
            request=request,
            bars=bars,
            page_response_ids=tuple(response_ids),
            cache_hits=cache_hits,
            provider_fetches=provider_fetches,
        )

    @staticmethod
    def _validate_page_bars(request: DataRequest, page: ProviderPage) -> None:
        for bar in page.bars:
            if bar.symbol != request.symbol or bar.interval is not request.interval:
                raise ProviderError("provider returned a candle for a different symbol or interval")
            if bar.timestamp_open < request.start or bar.timestamp_close > request.end:
                raise ProviderError("provider returned a candle outside the request window")
