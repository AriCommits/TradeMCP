"""Provider protocol and saved CSV/Parquet implementation."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd

from trading.options.contracts import (
    ExerciseStyle,
    OptionContract,
    OptionType,
    SettlementType,
    require_utc,
)

from .records import RawOptionQuoteRecord


class OptionsMarketDataProvider(Protocol):
    def contracts(self, underlying: str, as_of_utc: datetime) -> tuple[OptionContract, ...]: ...

    def quote_records(
        self, underlying: str, as_of_utc: datetime
    ) -> tuple[RawOptionQuoteRecord, ...]: ...


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"unsupported saved-data format: {path.suffix}")


def _utc(value: Any, name: str) -> datetime:
    parsed = cast(datetime, pd.Timestamp(value).to_pydatetime())
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a UTC offset")
    parsed = parsed.astimezone(timezone.utc)
    require_utc(parsed, name)
    return parsed


def _optional(value: Any, converter: Any) -> Any:
    return None if value is None or pd.isna(value) else converter(value)


def _mapping(value: Any) -> dict[str, Any]:
    if value is None or (not isinstance(value, dict) and pd.isna(value)):
        return {}
    if isinstance(value, dict):
        return value
    decoded = json.loads(str(value))
    if not isinstance(decoded, dict):
        raise ValueError("derived field namespaces must be JSON objects")
    return decoded


class SavedOptionsMarketDataProvider:
    """Load normalized contracts and lossless quotes from CSV or Parquet."""

    def __init__(self, contracts_path: str | Path, quotes_path: str | Path) -> None:
        self.contracts_path = Path(contracts_path)
        self.quotes_path = Path(quotes_path)

    def contracts(self, underlying: str, as_of_utc: datetime) -> tuple[OptionContract, ...]:
        require_utc(as_of_utc, "as_of_utc")
        frame = _read_table(self.contracts_path)
        selected = frame.loc[frame["underlying"].astype(str) == underlying]
        records: list[OptionContract] = []
        for row in selected.to_dict("records"):
            listed_at = _optional(row.get("listed_at_utc"), lambda x: _utc(x, "listed_at_utc"))
            if listed_at is not None and listed_at > as_of_utc:
                continue
            expiration_at = _utc(row["expiration_at_utc"], "expiration_at_utc")
            if expiration_at < as_of_utc:
                continue
            records.append(
                OptionContract(
                    contract_id=str(row["contract_id"]),
                    occ_symbol=str(row["occ_symbol"]),
                    underlying=str(row["underlying"]),
                    option_type=OptionType(str(row["option_type"]).lower()),
                    strike=Decimal(str(row["strike"])),
                    expiration_date=date.fromisoformat(str(row["expiration_date"])),
                    expiration_at_utc=expiration_at,
                    exercise_style=ExerciseStyle(str(row["exercise_style"]).lower()),
                    settlement_type=SettlementType(str(row["settlement_type"]).lower()),
                    multiplier=Decimal(str(row.get("multiplier", 100))),
                    currency=str(row.get("currency", "USD")),
                    listing_exchange=_optional(row.get("listing_exchange"), str),
                )
            )
        return tuple(sorted(records, key=lambda item: item.contract_id))

    def quote_records(
        self, underlying: str, as_of_utc: datetime
    ) -> tuple[RawOptionQuoteRecord, ...]:
        require_utc(as_of_utc, "as_of_utc")
        frame = _read_table(self.quotes_path)
        selected = frame.loc[frame["underlying"].astype(str) == underlying]
        records: list[RawOptionQuoteRecord] = []
        known = {
            "underlying",
            "contract_id",
            "as_of_utc",
            "bid",
            "ask",
            "bid_size",
            "ask_size",
            "underlying_price",
            "source",
            "ingested_at_utc",
            "last",
            "last_size",
            "source_record_id",
            "provider_fields",
            "internal_fields",
        }
        for row in selected.to_dict("records"):
            quote_at = _utc(row["as_of_utc"], "as_of_utc")
            if quote_at > as_of_utc:
                continue
            provider_fields = _mapping(row.get("provider_fields"))
            provider_fields.update({key: value for key, value in row.items() if key not in known})
            records.append(
                RawOptionQuoteRecord(
                    contract_id=str(row["contract_id"]),
                    as_of_utc=quote_at,
                    bid=_optional(row.get("bid"), lambda x: Decimal(str(x))),
                    ask=_optional(row.get("ask"), lambda x: Decimal(str(x))),
                    bid_size=_optional(row.get("bid_size"), int),
                    ask_size=_optional(row.get("ask_size"), int),
                    underlying_price=Decimal(str(row["underlying_price"])),
                    source=str(row["source"]),
                    ingested_at_utc=_utc(row["ingested_at_utc"], "ingested_at_utc"),
                    last=_optional(row.get("last"), lambda x: Decimal(str(x))),
                    last_size=_optional(row.get("last_size"), int),
                    source_record_id=_optional(row.get("source_record_id"), str),
                    provider_fields=provider_fields,
                    internal_fields=_mapping(row.get("internal_fields")),
                )
            )
        return tuple(sorted(records, key=lambda item: (item.as_of_utc, item.contract_id)))
