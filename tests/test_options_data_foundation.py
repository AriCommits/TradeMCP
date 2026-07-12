from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pandas as pd

from trading.data import (
    OptionChainReconstructor,
    OptionsParquetStore,
    OptionsQueryEngine,
    QuoteQualityIssue,
    QuoteQualityPolicy,
    SavedOptionsMarketDataProvider,
)
from trading.options.quotes import QuoteQualityFlag


AS_OF = datetime(2026, 7, 10, 20, 45, tzinfo=timezone.utc)


def _saved_provider(tmp_path):
    contracts = pd.DataFrame(
        [
            {
                "contract_id": f"SPY-{strike}",
                "occ_symbol": f"SPY 260713P{strike:08d}",
                "underlying": "SPY",
                "option_type": "put",
                "strike": strike,
                "expiration_date": "2026-07-13",
                "expiration_at_utc": "2026-07-13T20:00:00Z",
                "exercise_style": "american",
                "settlement_type": "physical",
                "multiplier": 100,
                "currency": "USD",
            }
            for strike in (590, 600, 610, 620, 630)
        ]
    )
    base = {"underlying": "SPY", "underlying_price": 610.0, "source": "fixture"}
    quotes = pd.DataFrame(
        [
            {
                **base,
                "contract_id": "SPY-590",
                "as_of_utc": "2026-07-10T20:30:00Z",
                "bid": 0.8,
                "ask": 0.9,
                "bid_size": 10,
                "ask_size": 11,
                "ingested_at_utc": "2026-07-10T20:31:00Z",
            },
            {
                **base,
                "contract_id": "SPY-590",
                "as_of_utc": "2026-07-10T20:44:00Z",
                "bid": 1.0,
                "ask": 1.1,
                "bid_size": 12,
                "ask_size": 13,
                "ingested_at_utc": "2026-07-10T20:44:01Z",
                "provider_fields": json.dumps({"provider_iv": 0.2}),
                "internal_fields": json.dumps({"research_tag": "x"}),
            },
            {
                **base,
                "contract_id": "SPY-600",
                "as_of_utc": "2026-07-10T20:44:00Z",
                "bid": 1.2,
                "ask": 1.1,
                "bid_size": 4,
                "ask_size": 5,
                "ingested_at_utc": "2026-07-10T20:44:01Z",
            },
            {
                **base,
                "contract_id": "SPY-610",
                "as_of_utc": "2026-07-10T20:44:00Z",
                "bid": 1.2,
                "ask": 1.2,
                "bid_size": 4,
                "ask_size": 5,
                "ingested_at_utc": "2026-07-10T20:44:01Z",
            },
            {
                **base,
                "contract_id": "SPY-620",
                "as_of_utc": "2026-07-10T20:44:00Z",
                "bid": 0.0,
                "ask": 0.1,
                "bid_size": None,
                "ask_size": 5,
                "ingested_at_utc": "2026-07-10T20:44:01Z",
            },
            {
                **base,
                "contract_id": "SPY-630",
                "as_of_utc": "2026-07-10T20:44:00Z",
                "bid": None,
                "ask": 2.0,
                "bid_size": None,
                "ask_size": 5,
                "ingested_at_utc": "2026-07-10T20:44:01Z",
            },
            {
                **base,
                "contract_id": "SPY-590",
                "as_of_utc": "2026-07-10T20:46:00Z",
                "bid": 9.0,
                "ask": 9.1,
                "bid_size": 1,
                "ask_size": 1,
                "ingested_at_utc": "2026-07-10T20:46:01Z",
            },
        ]
    )
    contracts_path, quotes_path = tmp_path / "contracts.parquet", tmp_path / "quotes.csv"
    contracts.to_parquet(contracts_path, index=False)
    quotes.to_csv(quotes_path, index=False)
    return SavedOptionsMarketDataProvider(contracts_path, quotes_path)


def test_reconstructs_as_of_and_classifies_quote_quality(tmp_path) -> None:
    result = OptionChainReconstructor(
        _saved_provider(tmp_path), QuoteQualityPolicy(max_age=timedelta(minutes=5))
    ).reconstruct("SPY", date(2026, 7, 10), AS_OF, chain_id="saved-spy")
    by_id = {quote.contract_id: quote for quote in result.snapshot.quotes}
    assert by_id["SPY-590"].bid == Decimal("1.0")
    assert "SPY-600" not in by_id
    assert QuoteQualityIssue.CROSSED in result.assessments["SPY-600"].issues
    assert result.rejected_records["SPY-600"].bid == Decimal("1.2")
    assert QuoteQualityFlag.LOCKED in by_id["SPY-610"].quality_flags
    assert QuoteQualityFlag.ZERO_BID in by_id["SPY-620"].quality_flags
    assert QuoteQualityFlag.MISSING_SIZE in by_id["SPY-620"].quality_flags
    assert "SPY-630" not in by_id
    assert QuoteQualityIssue.MISSING_BID in result.assessments["SPY-630"].issues
    assert result.rejected_records["SPY-630"].bid is None


def test_stale_quotes_are_flagged_not_silently_replaced(tmp_path) -> None:
    result = OptionChainReconstructor(
        _saved_provider(tmp_path),
        QuoteQualityPolicy(max_age=timedelta(seconds=30), reject_stale=False),
    ).reconstruct("SPY", date(2026, 7, 10), AS_OF)
    quote = next(item for item in result.snapshot.quotes if item.contract_id == "SPY-590")
    assert QuoteQualityFlag.STALE in quote.quality_flags

    strict = OptionChainReconstructor(
        _saved_provider(tmp_path), QuoteQualityPolicy(max_age=timedelta(seconds=30))
    ).reconstruct("SPY", date(2026, 7, 10), AS_OF)
    assert "SPY-590" in strict.rejected_records


def test_partitioned_parquet_and_duckdb_queries_preserve_namespaces(tmp_path) -> None:
    provider = _saved_provider(tmp_path)
    store = OptionsParquetStore(tmp_path / "lake")
    contract_paths = store.write_contracts(provider.contracts("SPY", AS_OF))
    quote_paths = store.write_quotes("SPY", provider.quote_records("SPY", AS_OF))
    assert "underlying=SPY" in str(contract_paths[0])
    assert "session_date=2026-07-10" in str(quote_paths[0])
    engine = OptionsQueryEngine(tmp_path / "lake")
    try:
        result = engine.query(
            "SELECT provider_fields, internal_fields FROM quotes "
            "WHERE contract_id = ? AND as_of_utc <= ? ORDER BY as_of_utc DESC LIMIT 1",
            ["SPY-590", AS_OF],
        )
    finally:
        engine.close()
    assert json.loads(result.iloc[0]["provider_fields"])["provider_iv"] == 0.2
    assert json.loads(result.iloc[0]["internal_fields"])["research_tag"] == "x"


def test_contracts_expired_before_snapshot_are_excluded(tmp_path) -> None:
    provider = _saved_provider(tmp_path)
    after_expiration = datetime(2026, 7, 14, 20, 0, tzinfo=timezone.utc)

    assert provider.contracts("SPY", after_expiration) == ()
