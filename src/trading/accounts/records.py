"""Broker capability records used to gate strategies before order creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading.options.contracts import VersionedRecord, require_utc
from trading.strategies.specifications import MarginType


@dataclass(frozen=True)
class BrokerCapabilities(VersionedRecord):
    adapter: str
    as_of_utc: datetime
    published_at_utc: datetime
    supported_margin_types: tuple[MarginType, ...]
    option_levels: tuple[str, ...]
    supports_equity_options: bool
    supports_multi_leg: bool
    supports_early_exercise_requests: bool
    source: str

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        require_utc(self.published_at_utc, "published_at_utc")
        if not self.adapter or not self.source or not self.option_levels:
            raise ValueError("adapter, source, and at least one option level are required")
        if self.published_at_utc < self.as_of_utc:
            raise ValueError("published_at_utc cannot precede as_of_utc")

    def supports(self, margin_type: MarginType, option_level: str) -> bool:
        return (
            self.supports_equity_options
            and margin_type in self.supported_margin_types
            and option_level in self.option_levels
        )
