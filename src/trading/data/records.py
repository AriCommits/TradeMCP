"""Lossless provider records used before canonical quote validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from trading.options.contracts import require_utc


@dataclass(frozen=True)
class RawOptionQuoteRecord:
    """Provider quote whose sides may be incomplete before validation."""

    contract_id: str
    as_of_utc: datetime
    bid: Decimal | None
    ask: Decimal | None
    bid_size: int | None
    ask_size: int | None
    underlying_price: Decimal
    source: str
    ingested_at_utc: datetime
    last: Decimal | None = None
    last_size: int | None = None
    source_record_id: str | None = None
    provider_fields: Mapping[str, Any] = field(default_factory=dict)
    internal_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        require_utc(self.ingested_at_utc, "ingested_at_utc")
        if not self.contract_id or not self.source:
            raise ValueError("contract_id and source are required")
        if self.underlying_price <= 0:
            raise ValueError("underlying_price must be positive")
        if self.bid is not None and self.bid < 0:
            raise ValueError("bid cannot be negative")
        if self.ask is not None and self.ask < 0:
            raise ValueError("ask cannot be negative")
        if self.bid_size is not None and self.bid_size < 0:
            raise ValueError("bid_size cannot be negative")
        if self.ask_size is not None and self.ask_size < 0:
            raise ValueError("ask_size cannot be negative")
