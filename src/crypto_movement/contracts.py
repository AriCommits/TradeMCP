"""Immutable domain contracts for cryptocurrency movement research.

The types in this module are intentionally framework- and venue-independent.
They form the boundary between data acquisition, labels, features, folds, and
model artifacts without importing any exchange client or ML runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeAlias

from crypto_movement.time import (
    as_utc,
    require_completed_candle,
    require_feature_available,
    require_interval_aligned,
    require_label_after_anchor,
    validate_candle_bounds,
)

UPPER_BARRIER_ARITHMETIC = 0.04
LOWER_BARRIER_ARITHMETIC = -0.04
UPPER_BARRIER_LOG = math.log(1.04)
LOWER_BARRIER_LOG = math.log(0.96)
REQUIRED_HORIZON_HOURS = (1, 3, 6, 12)
MINIMUM_PURGE = timedelta(hours=max(REQUIRED_HORIZON_HOURS))

Number: TypeAlias = int | float


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned


def _finite_number(value: Number, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field_name} must be finite")
    return converted


def _optional_finite(value: Number | None, field_name: str) -> float | None:
    if value is None:
        return None
    return _finite_number(value, field_name)


class InstrumentType(str, Enum):
    """Venue instrument family represented by a symbol mapping."""

    SPOT = "spot"
    PERPETUAL = "perpetual"


class CandleInterval(str, Enum):
    """Supported source and predictor candle intervals."""

    ONE_MINUTE = "1m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"

    @property
    def duration(self) -> timedelta:
        minutes = {
            CandleInterval.ONE_MINUTE: 1,
            CandleInterval.FIFTEEN_MINUTES: 15,
            CandleInterval.THIRTY_MINUTES: 30,
        }[self]
        return timedelta(minutes=minutes)


class LabelHorizon(str, Enum):
    """Required forecast horizons; every output is trained separately."""

    ONE_HOUR = "1h"
    THREE_HOURS = "3h"
    SIX_HOURS = "6h"
    TWELVE_HOURS = "12h"

    @property
    def hours(self) -> int:
        return {
            LabelHorizon.ONE_HOUR: 1,
            LabelHorizon.THREE_HOURS: 3,
            LabelHorizon.SIX_HOURS: 6,
            LabelHorizon.TWELVE_HOURS: 12,
        }[self]

    @property
    def duration(self) -> timedelta:
        return timedelta(hours=self.hours)

    def steps(self, interval: CandleInterval) -> int:
        horizon_seconds = int(self.duration.total_seconds())
        interval_seconds = int(interval.duration.total_seconds())
        steps, remainder = divmod(horizon_seconds, interval_seconds)
        if remainder:
            raise ValueError(f"{self.value} is not divisible by {interval.value}")
        return steps


HORIZONS = tuple(LabelHorizon)


class FirstBarrierOutcome(str, Enum):
    UP_FIRST = "up_first"
    DOWN_FIRST = "down_first"
    NEITHER = "neither"


class AmbiguityState(str, Enum):
    NOT_AMBIGUOUS = "not_ambiguous"
    RESOLVED_WITH_FINE_DATA = "resolved_with_fine_data"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class VenueIdentity:
    """Canonical identity for a market-data venue and instrument family."""

    venue: str
    instrument_type: InstrumentType

    def __post_init__(self) -> None:
        object.__setattr__(self, "venue", _nonempty(self.venue, "venue").lower())
        if not isinstance(self.instrument_type, InstrumentType):
            raise TypeError("instrument_type must be an InstrumentType")

    @property
    def canonical_id(self) -> str:
        return f"{self.venue}:{self.instrument_type.value}"


@dataclass(frozen=True, slots=True)
class SymbolIdentity:
    """Mapping from a canonical asset/quote pair to its venue symbol."""

    venue: VenueIdentity
    canonical_asset: str
    quote_asset: str
    venue_symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.venue, VenueIdentity):
            raise TypeError("venue must be a VenueIdentity")
        object.__setattr__(
            self, "canonical_asset", _nonempty(self.canonical_asset, "canonical_asset").upper()
        )
        object.__setattr__(
            self, "quote_asset", _nonempty(self.quote_asset, "quote_asset").upper()
        )
        object.__setattr__(self, "venue_symbol", _nonempty(self.venue_symbol, "venue_symbol"))

    @property
    def canonical_pair(self) -> str:
        return f"{self.canonical_asset}/{self.quote_asset}"

    @property
    def canonical_id(self) -> str:
        return f"{self.venue.canonical_id}:{self.canonical_pair}:{self.venue_symbol}"


def _validated_ohlc(
    open_price: Number,
    high_price: Number,
    low_price: Number,
    close_price: Number,
) -> tuple[float, float, float, float]:
    opened = _finite_number(open_price, "open")
    high = _finite_number(high_price, "high")
    low = _finite_number(low_price, "low")
    closed = _finite_number(close_price, "close")
    if min(opened, high, low, closed) <= 0:
        raise ValueError("OHLC prices must be positive")
    if high < low:
        raise ValueError("high must be greater than or equal to low")
    if high < max(opened, closed):
        raise ValueError("high must be at least max(open, close)")
    if low > min(opened, closed):
        raise ValueError("low must be at most min(open, close)")
    return opened, high, low, closed


def _validate_market_extras(
    *,
    base_volume: Number | None,
    quote_volume: Number | None,
    trade_count: int | None,
    taker_buy_volume: Number | None,
    open_interest: Number | None,
    funding_rate: Number | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    base = _optional_finite(base_volume, "base_volume")
    quote = _optional_finite(quote_volume, "quote_volume")
    taker = _optional_finite(taker_buy_volume, "taker_buy_volume")
    interest = _optional_finite(open_interest, "open_interest")
    funding = _optional_finite(funding_rate, "funding_rate")
    for name, value in (
        ("base_volume", base),
        ("quote_volume", quote),
        ("taker_buy_volume", taker),
        ("open_interest", interest),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be nonnegative")
    if trade_count is not None:
        if isinstance(trade_count, bool) or not isinstance(trade_count, int):
            raise TypeError("trade_count must be an integer")
        if trade_count < 0:
            raise ValueError("trade_count must be nonnegative")
    if base is not None and taker is not None and taker > base:
        raise ValueError("taker_buy_volume cannot exceed base_volume")
    return base, quote, taker, interest, funding


@dataclass(frozen=True, slots=True)
class RawBar:
    """An immutable candle exactly as obtained from a provider."""

    symbol: SymbolIdentity
    interval: CandleInterval
    timestamp_open: datetime
    timestamp_close: datetime
    open: float
    high: float
    low: float
    close: float
    source: str
    downloaded_at: datetime
    base_volume: float | None = None
    quote_volume: float | None = None
    trade_count: int | None = None
    taker_buy_volume: float | None = None
    open_interest: float | None = None
    funding_rate: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("symbol must be a SymbolIdentity")
        if not isinstance(self.interval, CandleInterval):
            raise TypeError("interval must be a CandleInterval")
        opened_at, closed_at = validate_candle_bounds(
            self.timestamp_open, self.timestamp_close, self.interval.duration
        )
        closed_at, downloaded_at = require_completed_candle(closed_at, self.downloaded_at)
        prices = _validated_ohlc(self.open, self.high, self.low, self.close)
        extras = _validate_market_extras(
            base_volume=self.base_volume,
            quote_volume=self.quote_volume,
            trade_count=self.trade_count,
            taker_buy_volume=self.taker_buy_volume,
            open_interest=self.open_interest,
            funding_rate=self.funding_rate,
        )
        object.__setattr__(self, "timestamp_open", opened_at)
        object.__setattr__(self, "timestamp_close", closed_at)
        object.__setattr__(self, "downloaded_at", downloaded_at)
        object.__setattr__(self, "source", _nonempty(self.source, "source"))
        value: float | None
        for field_name, value in zip(("open", "high", "low", "close"), prices, strict=True):
            object.__setattr__(self, field_name, value)
        for field_name, value in zip(
            ("base_volume", "quote_volume", "taker_buy_volume", "open_interest", "funding_rate"),
            extras,
            strict=True,
        ):
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class ResampledBar:
    """A causal bar assembled from a complete set of source candles."""

    symbol: SymbolIdentity
    interval: CandleInterval
    source_interval: CandleInterval
    timestamp_open: datetime
    timestamp_close: datetime
    open: float
    high: float
    low: float
    close: float
    constituent_count: int
    generated_at: datetime
    base_volume: float | None = None
    quote_volume: float | None = None
    trade_count: int | None = None
    taker_buy_volume: float | None = None
    open_interest: float | None = None
    funding_rate: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("symbol must be a SymbolIdentity")
        if not isinstance(self.interval, CandleInterval) or not isinstance(
            self.source_interval, CandleInterval
        ):
            raise TypeError("intervals must be CandleInterval values")
        target_seconds = int(self.interval.duration.total_seconds())
        source_seconds = int(self.source_interval.duration.total_seconds())
        expected_count, remainder = divmod(target_seconds, source_seconds)
        if remainder or expected_count <= 1:
            raise ValueError("resampled interval must be a larger multiple of source_interval")
        if isinstance(self.constituent_count, bool) or not isinstance(self.constituent_count, int):
            raise TypeError("constituent_count must be an integer")
        if self.constituent_count != expected_count:
            raise ValueError("resampled bar must contain every constituent candle")
        opened_at, closed_at = validate_candle_bounds(
            self.timestamp_open, self.timestamp_close, self.interval.duration
        )
        closed_at, generated_at = require_completed_candle(closed_at, self.generated_at)
        prices = _validated_ohlc(self.open, self.high, self.low, self.close)
        extras = _validate_market_extras(
            base_volume=self.base_volume,
            quote_volume=self.quote_volume,
            trade_count=self.trade_count,
            taker_buy_volume=self.taker_buy_volume,
            open_interest=self.open_interest,
            funding_rate=self.funding_rate,
        )
        object.__setattr__(self, "timestamp_open", opened_at)
        object.__setattr__(self, "timestamp_close", closed_at)
        object.__setattr__(self, "generated_at", generated_at)
        value: float | None
        for field_name, value in zip(("open", "high", "low", "close"), prices, strict=True):
            object.__setattr__(self, field_name, value)
        for field_name, value in zip(
            ("base_volume", "quote_volume", "taker_buy_volume", "open_interest", "funding_rate"),
            extras,
            strict=True,
        ):
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class SequenceSpec:
    """Recent sequence shape with a fixed 24-hour information window."""

    interval: CandleInterval
    steps: int
    history: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        if self.interval not in (
            CandleInterval.FIFTEEN_MINUTES,
            CandleInterval.THIRTY_MINUTES,
        ):
            raise ValueError("predictor sequence interval must be 15m or 30m")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or self.steps <= 0:
            raise ValueError("steps must be a positive integer")
        if self.interval.duration * self.steps != self.history:
            raise ValueError("sequence interval and steps must cover exactly history")


PRIMARY_SEQUENCE = SequenceSpec(CandleInterval.FIFTEEN_MINUTES, 96)
ABLATION_SEQUENCE = SequenceSpec(CandleInterval.THIRTY_MINUTES, 48)


@dataclass(frozen=True, slots=True)
class CompletedAnchor:
    """A prediction anchor known to correspond to a completed candle."""

    symbol: SymbolIdentity
    interval: CandleInterval
    anchor_timestamp: datetime
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("symbol must be a SymbolIdentity")
        if not isinstance(self.interval, CandleInterval):
            raise TypeError("interval must be a CandleInterval")
        anchor = require_interval_aligned(
            self.anchor_timestamp, self.interval.duration, field_name="anchor_timestamp"
        )
        anchor, observed = require_completed_candle(anchor, self.observed_at)
        object.__setattr__(self, "anchor_timestamp", anchor)
        object.__setattr__(self, "observed_at", observed)


@dataclass(frozen=True, slots=True)
class FeatureAvailability:
    """Timestamp provenance for one predictor at one anchor."""

    feature_name: str
    feature_timestamp: datetime
    anchor_timestamp: datetime

    def __post_init__(self) -> None:
        feature, anchor = require_feature_available(
            self.feature_timestamp, self.anchor_timestamp
        )
        object.__setattr__(self, "feature_name", _nonempty(self.feature_name, "feature_name"))
        object.__setattr__(self, "feature_timestamp", feature)
        object.__setattr__(self, "anchor_timestamp", anchor)


@dataclass(frozen=True, slots=True)
class FirstBarrierLabel:
    """Competing first-barrier label and its regression targets."""

    anchor: CompletedAnchor
    horizon: LabelHorizon
    label_timestamp: datetime
    outcome: FirstBarrierOutcome | None
    ambiguity: AmbiguityState
    terminal_log_return: float | None = None
    mfe_log_return: float | None = None
    mae_log_return: float | None = None
    time_to_event: timedelta | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.anchor, CompletedAnchor):
            raise TypeError("anchor must be a CompletedAnchor")
        if not isinstance(self.horizon, LabelHorizon):
            raise TypeError("horizon must be a LabelHorizon")
        if not isinstance(self.ambiguity, AmbiguityState):
            raise TypeError("ambiguity must be an AmbiguityState")
        label, anchor_timestamp = require_label_after_anchor(
            self.label_timestamp, self.anchor.anchor_timestamp
        )
        if label != anchor_timestamp + self.horizon.duration:
            raise ValueError("label_timestamp must equal anchor + horizon")
        if self.ambiguity is AmbiguityState.UNRESOLVED:
            if self.outcome is not None:
                raise ValueError("an unresolved ambiguous label cannot have an outcome")
            if self.time_to_event is not None:
                raise ValueError("an unresolved ambiguous label cannot have time_to_event")
        elif not isinstance(self.outcome, FirstBarrierOutcome):
            raise ValueError("a non-ambiguous label must have a FirstBarrierOutcome")
        if self.outcome is FirstBarrierOutcome.NEITHER and self.time_to_event is not None:
            raise ValueError("a neither label cannot have time_to_event")
        if self.outcome in (FirstBarrierOutcome.UP_FIRST, FirstBarrierOutcome.DOWN_FIRST):
            if self.time_to_event is None:
                raise ValueError("a barrier event must have time_to_event")
        if self.time_to_event is not None:
            if not isinstance(self.time_to_event, timedelta):
                raise TypeError("time_to_event must be a timedelta")
            if not timedelta(0) < self.time_to_event <= self.horizon.duration:
                raise ValueError("time_to_event must fall inside the label horizon")
        object.__setattr__(self, "label_timestamp", label)
        for field_name in ("terminal_log_return", "mfe_log_return", "mae_log_return"):
            object.__setattr__(
                self,
                field_name,
                _optional_finite(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class FoldIdentity:
    """Globally synchronized chronological fold boundaries."""

    fold_id: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    purge: timedelta = MINIMUM_PURGE
    embargo: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _nonempty(self.fold_id, "fold_id"))
        names = (
            "train_start",
            "train_end",
            "validation_start",
            "validation_end",
            "test_start",
            "test_end",
        )
        values = tuple(as_utc(getattr(self, name), field_name=name) for name in names)
        for name, value in zip(names, values, strict=True):
            object.__setattr__(self, name, value)
        if self.purge < MINIMUM_PURGE:
            raise ValueError("purge must cover the maximum 12-hour label horizon")
        if self.embargo < timedelta(0):
            raise ValueError("embargo must be nonnegative")
        train_start, train_end, validation_start, validation_end, test_start, test_end = values
        if not train_start < train_end:
            raise ValueError("training interval must be non-empty")
        if not validation_start < validation_end:
            raise ValueError("validation interval must be non-empty")
        if not test_start < test_end:
            raise ValueError("test interval must be non-empty")
        required_gap = self.purge + self.embargo
        if validation_start - train_end < required_gap:
            raise ValueError("training and validation boundaries violate purge/embargo")
        if test_start - validation_end < required_gap:
            raise ValueError("validation and test boundaries violate purge/embargo")
