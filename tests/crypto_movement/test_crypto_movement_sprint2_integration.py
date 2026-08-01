from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("pyarrow")

from crypto_movement.contracts import (
    AmbiguityState,
    CandleInterval,
    CompletedAnchor,
    FirstBarrierOutcome,
    InstrumentType,
    LabelHorizon,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.collector import MarketDataCollector, PageCache
from crypto_movement.data.manifest import build_manifest, verify_manifest
from crypto_movement.data.providers import DataRequest, DeterministicFixtureProvider
from crypto_movement.data.storage import ParquetBarStore
from crypto_movement.labels.barriers import generate_barrier_label
from crypto_movement.time import UTC


def test_stored_fixture_reloads_to_identical_barrier_label(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.SPOT),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    request = DataRequest(
        symbol=symbol,
        interval=CandleInterval.FIFTEEN_MINUTES,
        start=start,
        end=start + timedelta(hours=1),
        page_size=2,
    )
    provider = DeterministicFixtureProvider()
    collection = MarketDataCollector(provider, PageCache(tmp_path / "cache")).collect(request)

    store = ParquetBarStore(tmp_path / "raw")
    partitions = store.write_bars(collection.bars)
    manifest = build_manifest(
        collection,
        provider_name=provider.name,
        universe_snapshot_id="fixture-snapshot",
        partition_root=tmp_path / "raw",
        partitions=partitions,
    )
    verify_manifest(manifest, tmp_path / "raw")
    restored = tuple(bar for partition in partitions for bar in store.read_bars(partition.path))

    anchor = CompletedAnchor(symbol, CandleInterval.FIFTEEN_MINUTES, start, start)
    direct = generate_barrier_label(
        anchor=anchor,
        anchor_close=collection.bars[0].open,
        future_bars=collection.bars,
        horizon=LabelHorizon.ONE_HOUR,
    )
    reloaded = generate_barrier_label(
        anchor=anchor,
        anchor_close=restored[0].open,
        future_bars=restored,
        horizon=LabelHorizon.ONE_HOUR,
    )

    assert reloaded == direct
    assert reloaded.outcome is FirstBarrierOutcome.NEITHER
    assert reloaded.ambiguity is AmbiguityState.NOT_AMBIGUOUS


def test_fixture_collection_resume_replays_cached_pages_without_provider_calls(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.SPOT),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    request = DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + timedelta(hours=1),
        2,
    )
    cache = PageCache(tmp_path / "cache")
    first = MarketDataCollector(DeterministicFixtureProvider(), cache).collect(request)

    class ForbiddenProvider(DeterministicFixtureProvider):
        def fetch_page(self, request, cursor=None):  # type: ignore[no-untyped-def]
            raise AssertionError("cached replay reached the provider")

    replay = MarketDataCollector(ForbiddenProvider(), cache).collect(request)
    assert replay.bars == first.bars
    assert replay.page_response_ids == first.page_response_ids
    assert replay.cache_hits == first.page_count
    assert replay.provider_fetches == 0
