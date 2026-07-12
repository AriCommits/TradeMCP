"""Executable-side, midpoint, and limit fill policies with strict quote validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Protocol

from trading.options.contracts import require_utc
from trading.options.quotes import OptionQuote, QuoteQualityFlag


class FillError(ValueError):
    """Raised when a quote cannot safely support a simulated fill."""


class OrderAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Fill:
    price: Decimal
    reference_midpoint: Decimal
    adverse_slippage_per_share: Decimal
    policy: str


@dataclass(frozen=True)
class QuoteValidationPolicy:
    max_age: timedelta = timedelta(minutes=1)
    require_size: bool = True
    rejected_flags: frozenset[QuoteQualityFlag] = frozenset(
        {
            QuoteQualityFlag.STALE,
            QuoteQualityFlag.CROSSED,
            QuoteQualityFlag.INDICATIVE,
        }
    )

    def validate(self, quote: OptionQuote, decision_at_utc: datetime) -> None:
        require_utc(decision_at_utc, "decision_at_utc")
        if decision_at_utc < quote.as_of_utc:
            raise FillError("quote is from the future")
        if decision_at_utc - quote.as_of_utc > self.max_age:
            raise FillError("quote is stale for the configured fill policy")
        rejected = self.rejected_flags.intersection(quote.quality_flags)
        if rejected:
            raise FillError(
                f"unsupported quote quality flags: {sorted(flag.value for flag in rejected)}"
            )
        if self.require_size and (quote.bid_size is None or quote.ask_size is None):
            raise FillError("quote size is required")
        if quote.ask < quote.bid:
            raise FillError("crossed quote cannot be executed")


class FillPolicy(Protocol):
    def fill(self, quote: OptionQuote, action: OrderAction, decision_at_utc: datetime) -> Fill: ...


@dataclass(frozen=True)
class PessimisticFillPolicy:
    validation: QuoteValidationPolicy = QuoteValidationPolicy()

    def fill(self, quote: OptionQuote, action: OrderAction, decision_at_utc: datetime) -> Fill:
        self.validation.validate(quote, decision_at_utc)
        price = quote.ask if action is OrderAction.BUY else quote.bid
        if action is OrderAction.SELL and QuoteQualityFlag.ZERO_BID in quote.quality_flags:
            raise FillError("cannot open a short option at a zero bid")
        return Fill(price, quote.midpoint, abs(price - quote.midpoint), "pessimistic")


@dataclass(frozen=True)
class MidpointFillPolicy:
    validation: QuoteValidationPolicy = QuoteValidationPolicy()

    def fill(self, quote: OptionQuote, action: OrderAction, decision_at_utc: datetime) -> Fill:
        self.validation.validate(quote, decision_at_utc)
        if action is OrderAction.SELL and QuoteQualityFlag.ZERO_BID in quote.quality_flags:
            raise FillError("cannot assume midpoint execution on a zero-bid option")
        return Fill(quote.midpoint, quote.midpoint, Decimal("0"), "midpoint")


@dataclass(frozen=True)
class LimitFillPolicy:
    limit_price: Decimal
    validation: QuoteValidationPolicy = QuoteValidationPolicy()
    price_improvement: bool = True

    def __post_init__(self) -> None:
        if self.limit_price < 0:
            raise ValueError("limit_price cannot be negative")

    def fill(self, quote: OptionQuote, action: OrderAction, decision_at_utc: datetime) -> Fill:
        self.validation.validate(quote, decision_at_utc)
        executable = quote.ask if action is OrderAction.BUY else quote.bid
        marketable = (
            self.limit_price >= quote.ask
            if action is OrderAction.BUY
            else self.limit_price <= quote.bid
        )
        if not marketable:
            raise FillError("limit order is not marketable against the supplied quote")
        price = executable if self.price_improvement else self.limit_price
        adverse = (
            max(Decimal("0"), price - quote.midpoint)
            if action is OrderAction.BUY
            else max(Decimal("0"), quote.midpoint - price)
        )
        return Fill(price, quote.midpoint, adverse, "limit")
