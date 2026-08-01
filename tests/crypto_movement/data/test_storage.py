from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pyarrow")

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.providers import DataRequest, DeterministicFixtureProvider
from crypto_movement.data.storage import ParquetBarStore


def _bars():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.PERPETUAL),
        "BTC",
        "USDT",
        "XBTUSDT-PERP",
    )
    request = DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + 3 * timedelta(minutes=15),
        10,
    )
    return DeterministicFixtureProvider().fetch_page(request).bars


def test_partition_path_schema_and_optional_fields_round_trip(tmp_path) -> None:
    store = ParquetBarStore(tmp_path / "raw")
    write = store.write_bars(_bars())[0]
    path = write.path.as_posix()
    assert "venue=fixture" in path
    assert "instrument=perpetual" in path
    assert "interval=15m" in path
    assert "symbol=BTC-USDT" in path
    assert "year=2024/month=01" in path
    restored = store.read_bars(write.path)
    assert restored == _bars()
    assert restored[0].base_volume is not None
    assert restored[0].quote_volume is not None
    assert restored[0].trade_count is not None
    assert restored[0].taker_buy_volume is not None
    assert restored[0].open_interest is not None
    assert restored[0].funding_rate is not None


def test_replay_does_not_mutate_completed_partition(tmp_path) -> None:
    store = ParquetBarStore(tmp_path / "raw")
    first = store.write_bars(_bars())[0]
    before = (first.path.stat().st_mtime_ns, first.checksum_sha256)
    second = store.write_bars(_bars())[0]
    after = (second.path.stat().st_mtime_ns, second.checksum_sha256)
    assert first.path == second.path
    assert first.created
    assert not second.created
    assert before == after
