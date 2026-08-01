from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_movement.config import FullDownloadBlockedError
from crypto_movement.contracts import CandleInterval
from crypto_movement.data.providers import (
    DataRequest,
    DeterministicFixtureProvider,
    UnavailableVenueProvider,
    VenueProviderUnavailable,
    load_data_config,
)

ROOT = Path(__file__).resolve().parents[3]
DATA_CONFIG = ROOT / "config/crypto_movement/data.yaml"


def _request(count: int = 5, page_size: int = 2) -> DataRequest:
    config = load_data_config(DATA_CONFIG, root=ROOT)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return DataRequest(
        config.symbol_identity("BTC"),
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + count * timedelta(minutes=15),
        page_size,
    )


def test_symbol_mapping_is_explicit_and_fixture_pages_are_deterministic() -> None:
    config = load_data_config(DATA_CONFIG, root=ROOT)
    assert config.symbol_identity("BTC").venue_symbol == "BTCUSDT"
    with pytest.raises(ValueError, match="no explicit venue symbol"):
        config.symbol_identity("DOGE")

    request = _request()
    provider = DeterministicFixtureProvider()
    first = provider.fetch_page(request)
    replay = provider.fetch_page(request)
    second = provider.fetch_page(request, first.next_cursor)
    assert first == replay
    assert first.next_cursor == "2"
    assert len(first.bars) == 2
    assert second.bars[0].timestamp_open == request.start + 2 * request.interval.duration
    assert first.bars[0].base_volume is not None
    assert first.bars[0].quote_volume is not None
    assert first.bars[0].trade_count is not None
    assert first.bars[0].taker_buy_volume is not None


def test_fixture_identity_changes_with_venue_symbol() -> None:
    config = load_data_config(DATA_CONFIG, root=ROOT)
    btc = config.symbol_identity("BTC")
    request = _request(count=1, page_size=1)
    assert request.symbol == btc
    assert request.request_id == _request(count=1, page_size=1).request_id


def test_real_provider_is_explicitly_unavailable() -> None:
    provider = UnavailableVenueProvider("blocked", 1.0)
    with pytest.raises(VenueProviderUnavailable, match="Phase 0"):
        provider.fetch_page(_request(count=1, page_size=1))


def test_cli_rejects_full_scope_before_any_collection() -> None:
    script = ROOT / "scripts/download_crypto_pilot.py"
    spec = importlib.util.spec_from_file_location("download_crypto_pilot", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(FullDownloadBlockedError):
        module.main(["--root", str(ROOT), "--scope", "full"])
