"""Point-in-time option quote and chain records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .contracts import OptionContract, VersionedRecord, require_utc


class QuoteQualityFlag(str, Enum):
    STALE = "stale"
    CROSSED = "crossed"
    LOCKED = "locked"
    ZERO_BID = "zero_bid"
    MISSING_SIZE = "missing_size"
    INDICATIVE = "indicative"


@dataclass(frozen=True)
class OptionQuote(VersionedRecord):
    contract_id: str
    as_of_utc: datetime
    bid: Decimal
    ask: Decimal
    bid_size: int | None
    ask_size: int | None
    underlying_price: Decimal
    source: str
    ingested_at_utc: datetime
    last: Decimal | None = None
    last_size: int | None = None
    quality_flags: tuple[QuoteQualityFlag, ...] = ()
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        require_utc(self.ingested_at_utc, "ingested_at_utc")
        if not self.contract_id or not self.source:
            raise ValueError("contract_id and source are required")
        if self.bid < 0 or self.ask < 0 or self.underlying_price <= 0:
            raise ValueError("bid/ask cannot be negative and underlying_price must be positive")
        if self.ask < self.bid and QuoteQualityFlag.CROSSED not in self.quality_flags:
            raise ValueError("crossed quotes must carry the crossed quality flag")
        if self.bid_size is not None and self.bid_size < 0:
            raise ValueError("bid_size cannot be negative")
        if self.ask_size is not None and self.ask_size < 0:
            raise ValueError("ask_size cannot be negative")
        if self.last is not None and self.last < 0:
            raise ValueError("last cannot be negative")

    @property
    def midpoint(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")


@dataclass(frozen=True)
class OptionChainSnapshot(VersionedRecord):
    chain_id: str
    underlying: str
    session_date: date
    as_of_utc: datetime
    contracts: tuple[OptionContract, ...]
    quotes: tuple[OptionQuote, ...]
    source: str
    ingested_at_utc: datetime
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        require_utc(self.ingested_at_utc, "ingested_at_utc")
        if not self.chain_id or not self.underlying or not self.source:
            raise ValueError("chain_id, underlying, and source are required")
        contract_ids = {contract.contract_id for contract in self.contracts}
        if len(contract_ids) != len(self.contracts):
            raise ValueError("chain contract_id values must be unique")
        if any(contract.underlying != self.underlying for contract in self.contracts):
            raise ValueError("all chain contracts must match the chain underlying")
        if any(quote.contract_id not in contract_ids for quote in self.quotes):
            raise ValueError("every quote must reference a contract in the snapshot")
        if any(quote.as_of_utc > self.as_of_utc for quote in self.quotes):
            raise ValueError("quote timestamps cannot be later than the chain snapshot")
