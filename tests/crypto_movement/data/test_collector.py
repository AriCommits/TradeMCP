from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.collector import MarketDataCollector, PageCache
from crypto_movement.data.providers import (
    DataRequest,
    DeterministicFixtureProvider,
    ProviderError,
)


def _request(page_size: int = 2) -> DataRequest:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.PERPETUAL),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    return DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + 5 * timedelta(minutes=15),
        page_size,
    )


class InterruptingProvider:
    def __init__(self, delegate: DeterministicFixtureProvider) -> None:
        self.delegate = delegate
        self.calls = 0

    @property
    def name(self) -> str:
        return self.delegate.name

    @property
    def minimum_request_interval_seconds(self) -> float:
        return self.delegate.minimum_request_interval_seconds

    def fetch_page(self, request, cursor=None):
        self.calls += 1
        if self.calls == 2:
            raise ProviderError("simulated interruption")
        return self.delegate.fetch_page(request, cursor)


class CountingProvider:
    def __init__(self, delegate: DeterministicFixtureProvider) -> None:
        self.delegate = delegate
        self.calls = 0

    @property
    def name(self) -> str:
        return self.delegate.name

    @property
    def minimum_request_interval_seconds(self) -> float:
        return self.delegate.minimum_request_interval_seconds

    def fetch_page(self, request, cursor=None):
        self.calls += 1
        return self.delegate.fetch_page(request, cursor)


def test_interrupted_collection_resumes_from_cached_pages_without_duplicates(tmp_path) -> None:
    request = _request()
    cache = PageCache(tmp_path / "cache")
    interrupted = InterruptingProvider(DeterministicFixtureProvider())
    with pytest.raises(ProviderError, match="interruption"):
        MarketDataCollector(interrupted, cache).collect(request)

    resumed_provider = CountingProvider(DeterministicFixtureProvider())
    resumed = MarketDataCollector(resumed_provider, cache).collect(request)
    assert len(resumed.bars) == 5
    assert len({bar.timestamp_open for bar in resumed.bars}) == 5
    assert resumed.cache_hits == 1
    assert resumed.provider_fetches == 2
    assert resumed_provider.calls == 2

    replay_provider = CountingProvider(DeterministicFixtureProvider())
    replay = MarketDataCollector(replay_provider, cache).collect(request)
    assert replay.bars == resumed.bars
    assert replay.cache_hits == 3
    assert replay.provider_fetches == 0
    assert replay_provider.calls == 0


def test_collector_waits_between_uncached_provider_pages(tmp_path) -> None:
    clock = [0.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    provider = DeterministicFixtureProvider(minimum_request_interval_seconds=2.0)
    result = MarketDataCollector(
        provider,
        PageCache(tmp_path / "cache"),
        monotonic=monotonic,
        sleeper=sleeper,
    ).collect(_request(page_size=1))
    assert result.provider_fetches == 5
    assert sleeps == [2.0, 2.0, 2.0, 2.0]
