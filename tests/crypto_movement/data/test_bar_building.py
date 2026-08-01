from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.bars import (
    BarConstructionError,
    ConstituentProvenance,
    IncompleteBarPairError,
    build_30_minute_bars,
    build_30_minute_panel,
    constituent_key,
    raw_bar_identity,
)
from crypto_movement.data.providers import DataRequest, DeterministicFixtureProvider


def _bars(count: int = 4):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.PERPETUAL),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    request = DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + count * timedelta(minutes=15),
        100,
    )
    return DeterministicFixtureProvider().fetch_page(request).bars


def _lineage(bars):
    return {
        constituent_key(bar): ConstituentProvenance(
            partition_path="venue=fixture/part.parquet",
            partition_checksum_sha256="a" * 64,
            manifest_id="manifest-1",
        )
        for bar in bars
    }


def test_exact_pairs_preserve_ohlcv_and_constituent_lineage() -> None:
    source = _bars()
    source_snapshot = tuple(source)
    result = build_30_minute_bars(source, _lineage(source))
    assert len(result) == 2
    first = result[0]
    assert first.bar.open == source[0].open
    assert first.bar.close == source[1].close
    assert first.bar.high == max(source[0].high, source[1].high)
    assert first.bar.low == min(source[0].low, source[1].low)
    assert first.bar.base_volume == source[0].base_volume + source[1].base_volume
    assert first.bar.trade_count == source[0].trade_count + source[1].trade_count
    assert first.bar.open_interest == source[1].open_interest
    assert first.bar.funding_rate == source[1].funding_rate
    assert len(first.lineage.constituents) == 2
    assert first.lineage.schema_version == 1
    assert first.lineage.constituents[0].partition_checksum_sha256 == "a" * 64
    assert len(first.lineage.lineage_id) == 64
    assert tuple(source) == source_snapshot


def test_incomplete_or_misaligned_half_hour_is_rejected() -> None:
    source = _bars()
    with pytest.raises(IncompleteBarPairError):
        build_30_minute_bars((source[0], source[2], source[3]), _lineage(source))
    with pytest.raises(IncompleteBarPairError):
        build_30_minute_bars((source[1],), _lineage(source))


def test_mixed_source_semantics_and_missing_lineage_are_rejected() -> None:
    source = _bars(2)
    mixed = (source[0], replace(source[1], source="other-source"))
    with pytest.raises(BarConstructionError, match="source semantics"):
        build_30_minute_bars(mixed, _lineage(mixed))
    with pytest.raises(BarConstructionError, match="requires partition"):
        build_30_minute_bars(
            source, {constituent_key(source[0]): _lineage(source)[constituent_key(source[0])]}
        )


def test_panel_excludes_only_missing_pair_and_preserves_later_lineage() -> None:
    source = _bars(6)
    source_snapshot = tuple(source)
    with_one_missing = (source[0], source[1], source[3], source[4], source[5])
    provenance = _lineage(source)

    result = build_30_minute_panel(with_one_missing, provenance)
    reversed_result = build_30_minute_panel(tuple(reversed(with_one_missing)), provenance)

    assert result == reversed_result
    assert tuple(item.bar.timestamp_open for item in result.bars) == (
        source[0].timestamp_open,
        source[4].timestamp_open,
    )
    assert len(result.exclusions) == 1
    exclusion = result.exclusions[0]
    assert exclusion.target_open == source[2].timestamp_open
    assert exclusion.expected_constituent_opens == (
        source[2].timestamp_open,
        source[3].timestamp_open,
    )
    assert tuple(item.raw_bar_id for item in exclusion.observed_constituents) == (
        raw_bar_identity(source[3]),
    )
    later_lineage = result.bars[-1].lineage
    assert tuple(item.raw_bar_id for item in later_lineage.constituents) == (
        raw_bar_identity(source[4]),
        raw_bar_identity(source[5]),
    )
    assert all(item.partition_checksum_sha256 == "a" * 64 for item in later_lineage.constituents)
    assert tuple(source) == source_snapshot
