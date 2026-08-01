"""Competing first-barrier labels built from complete causal candle windows."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from itertools import groupby
from typing import TypeAlias

from crypto_movement.contracts import (
    HORIZONS,
    LOWER_BARRIER_LOG,
    UPPER_BARRIER_LOG,
    AmbiguityState,
    CandleInterval,
    CompletedAnchor,
    FirstBarrierLabel,
    FirstBarrierOutcome,
    LabelHorizon,
    RawBar,
    ResampledBar,
    SymbolIdentity,
)
from crypto_movement.time import as_utc


class LabelConstructionError(ValueError):
    """Base error for invalid or incomplete label inputs."""


class IncompleteLabelWindowError(LabelConstructionError):
    """Raised instead of filling or truncating a future label window."""


class InvalidFineEvidenceError(LabelConstructionError):
    """Raised when evidence marked complete violates its resolution contract."""


class BarrierKind(str, Enum):
    ARITHMETIC = "arithmetic"
    VOLATILITY_NORMALIZED = "volatility_normalized"


class EvidenceKind(str, Enum):
    COARSE_BAR = "coarse_bar"
    ONE_MINUTE_BAR = "one_minute_bar"
    TRADE = "trade"
    NONE = "none"


Candle: TypeAlias = RawBar | ResampledBar


@dataclass(frozen=True, slots=True)
class BarrierSpec:
    """Asymmetric log barriers derived from a declared economic threshold."""

    threshold_id: str
    kind: BarrierKind
    upper_log_return: float
    lower_log_return: float
    fraction_or_scale: float

    def __post_init__(self) -> None:
        if not self.threshold_id.strip():
            raise ValueError("threshold_id cannot be blank")
        values = (self.upper_log_return, self.lower_log_return, self.fraction_or_scale)
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in values):
            raise ValueError("barrier values must be finite real numbers")
        if self.upper_log_return <= 0 or self.lower_log_return >= 0:
            raise ValueError("barriers must straddle zero")
        if self.fraction_or_scale <= 0:
            raise ValueError("fraction_or_scale must be positive")

    @classmethod
    def arithmetic(cls, fraction: float, *, threshold_id: str | None = None) -> BarrierSpec:
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
            raise TypeError("fraction must be a real number")
        fraction = float(fraction)
        if not math.isfinite(fraction) or not 0 < fraction < 1:
            raise ValueError("arithmetic fraction must be between zero and one")
        identifier = threshold_id or f"arithmetic_{fraction:.12g}"
        return cls(
            identifier,
            BarrierKind.ARITHMETIC,
            math.log1p(fraction),
            math.log1p(-fraction),
            fraction,
        )

    @classmethod
    def volatility_normalized(
        cls,
        log_return_scale: float,
        *,
        multiplier: float = 1.0,
        threshold_id: str | None = None,
    ) -> BarrierSpec:
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in (log_return_scale, multiplier)
        ):
            raise TypeError("volatility scale and multiplier must be real numbers")
        scale = float(log_return_scale)
        multiple = float(multiplier)
        if not math.isfinite(scale) or not math.isfinite(multiple) or scale <= 0 or multiple <= 0:
            raise ValueError("volatility scale and multiplier must be finite and positive")
        barrier = scale * multiple
        identifier = threshold_id or f"volatility_{multiple:.12g}x_{scale:.12g}"
        return cls(identifier, BarrierKind.VOLATILITY_NORMALIZED, barrier, -barrier, barrier)

    def upper_price(self, anchor_close: float) -> float:
        return anchor_close * math.exp(self.upper_log_return)

    def lower_price(self, anchor_close: float) -> float:
        return anchor_close * math.exp(self.lower_log_return)


PRIMARY_BARRIER = BarrierSpec(
    "arithmetic_4pct",
    BarrierKind.ARITHMETIC,
    UPPER_BARRIER_LOG,
    LOWER_BARRIER_LOG,
    0.04,
)
AUXILIARY_ARITHMETIC_BARRIERS = (
    BarrierSpec.arithmetic(0.01, threshold_id="arithmetic_1pct"),
    BarrierSpec.arithmetic(0.02, threshold_id="arithmetic_2pct"),
)


@dataclass(frozen=True, slots=True)
class TradeTick:
    symbol: SymbolIdentity
    timestamp: datetime
    price: float

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("trade symbol must be a SymbolIdentity")
        object.__setattr__(self, "timestamp", as_utc(self.timestamp, field_name="trade timestamp"))
        if isinstance(self.price, bool) or not isinstance(self.price, (int, float)):
            raise TypeError("trade price must be a real number")
        if not math.isfinite(float(self.price)) or self.price <= 0:
            raise ValueError("trade price must be finite and positive")
        object.__setattr__(self, "price", float(self.price))


@dataclass(frozen=True, slots=True)
class FineBarEvidence:
    """One-minute bars claiming complete coverage of one ambiguous coarse bar."""

    bars: tuple[RawBar, ...]
    complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        if any(bar.interval is not CandleInterval.ONE_MINUTE for bar in self.bars):
            raise InvalidFineEvidenceError("fine bar evidence must contain only one-minute bars")


@dataclass(frozen=True, slots=True)
class TradeEvidence:
    """A complete ordered trade stream over one ambiguous coarse bar."""

    symbol: SymbolIdentity
    coverage_start: datetime
    coverage_end: datetime
    trades: tuple[TradeTick, ...]
    complete: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("trade evidence symbol must be a SymbolIdentity")
        start = as_utc(self.coverage_start, field_name="coverage_start")
        end = as_utc(self.coverage_end, field_name="coverage_end")
        if end <= start:
            raise InvalidFineEvidenceError("trade evidence coverage must be non-empty")
        trades = tuple(self.trades)
        if any(trade.symbol != self.symbol for trade in trades):
            raise InvalidFineEvidenceError("trade evidence contains a different symbol")
        if any(left.timestamp > right.timestamp for left, right in zip(trades, trades[1:])):
            raise InvalidFineEvidenceError("trade evidence must be chronological")
        if any(not start <= trade.timestamp <= end for trade in trades):
            raise InvalidFineEvidenceError("trade timestamp lies outside declared coverage")
        object.__setattr__(self, "coverage_start", start)
        object.__setattr__(self, "coverage_end", end)
        object.__setattr__(self, "trades", trades)


FineEvidence: TypeAlias = FineBarEvidence | TradeEvidence


@dataclass(frozen=True, slots=True)
class BarrierLabel:
    """Full L0 result schema, including reach flags and ambiguity state."""

    anchor: CompletedAnchor
    horizon: LabelHorizon
    barrier: BarrierSpec
    label_timestamp: datetime
    terminal_log_return: float
    mfe_log_return: float
    mae_log_return: float
    upper_reached: bool
    lower_reached: bool
    outcome: FirstBarrierOutcome | None
    ambiguity: AmbiguityState
    first_event_timestamp: datetime | None
    time_to_event: timedelta | None
    resolution_evidence: EvidenceKind

    @property
    def core_contract(self) -> FirstBarrierLabel:
        return FirstBarrierLabel(
            anchor=self.anchor,
            horizon=self.horizon,
            label_timestamp=self.label_timestamp,
            outcome=self.outcome,
            ambiguity=self.ambiguity,
            terminal_log_return=self.terminal_log_return,
            mfe_log_return=self.mfe_log_return,
            mae_log_return=self.mae_log_return,
            time_to_event=self.time_to_event,
        )


@dataclass(frozen=True, slots=True)
class _Resolution:
    outcome: FirstBarrierOutcome
    timestamp: datetime
    evidence_kind: EvidenceKind


def _positive_price(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise ValueError(f"{field_name} must be finite and positive")
    return converted


def _validate_label_window(
    anchor: CompletedAnchor,
    horizon: LabelHorizon,
    future_bars: Sequence[Candle],
) -> tuple[Candle, ...]:
    expected_count = horizon.steps(anchor.interval)
    window_end = anchor.anchor_timestamp + horizon.duration
    eligible = tuple(
        bar
        for bar in future_bars
        if bar.timestamp_open >= anchor.anchor_timestamp and bar.timestamp_close <= window_end
    )
    if len(eligible) != expected_count:
        raise IncompleteLabelWindowError(
            f"{horizon.value} window requires {expected_count} complete bars; found {len(eligible)}"
        )
    expected_open = anchor.anchor_timestamp
    for index, bar in enumerate(eligible):
        if bar.symbol != anchor.symbol:
            raise LabelConstructionError(f"future bar {index} has a different symbol")
        if bar.interval is not anchor.interval:
            raise LabelConstructionError(f"future bar {index} has a different interval")
        if bar.timestamp_open != expected_open:
            raise IncompleteLabelWindowError(
                f"gap or duplicate at future bar {index}: expected {expected_open.isoformat()}"
            )
        expected_close = expected_open + anchor.interval.duration
        if bar.timestamp_close != expected_close:
            raise IncompleteLabelWindowError(f"future bar {index} has invalid candle bounds")
        expected_open = expected_close
    if expected_open != window_end:
        raise IncompleteLabelWindowError("future label window does not end at its horizon")
    return eligible


def _resolve_fine_bars(
    evidence: FineBarEvidence,
    coarse_bar: Candle,
    upper_price: float,
    lower_price: float,
) -> _Resolution | None:
    if not evidence.complete:
        return None
    bars = evidence.bars
    expected_count = int(coarse_bar.interval.duration / CandleInterval.ONE_MINUTE.duration)
    if len(bars) != expected_count:
        raise InvalidFineEvidenceError("complete fine bars do not cover the coarse candle")
    expected_open = coarse_bar.timestamp_open
    first: _Resolution | None = None
    upper_seen = False
    lower_seen = False
    for index, bar in enumerate(bars):
        if bar.symbol != coarse_bar.symbol:
            raise InvalidFineEvidenceError(f"fine bar {index} has a different symbol")
        if bar.timestamp_open != expected_open:
            raise InvalidFineEvidenceError(f"gap or duplicate at fine bar {index}")
        expected_open = bar.timestamp_close
        up_hit = bar.high >= upper_price
        down_hit = bar.low <= lower_price
        upper_seen = upper_seen or up_hit
        lower_seen = lower_seen or down_hit
        if first is None:
            if up_hit and down_hit:
                return None
            if up_hit:
                first = _Resolution(
                    FirstBarrierOutcome.UP_FIRST, bar.timestamp_close, EvidenceKind.ONE_MINUTE_BAR
                )
            elif down_hit:
                first = _Resolution(
                    FirstBarrierOutcome.DOWN_FIRST, bar.timestamp_close, EvidenceKind.ONE_MINUTE_BAR
                )
    if expected_open != coarse_bar.timestamp_close:
        raise InvalidFineEvidenceError("fine bars do not end at the coarse close")
    if not upper_seen or not lower_seen:
        raise InvalidFineEvidenceError("fine bars do not corroborate both coarse-bar reaches")
    return first


def _resolve_trades(
    evidence: TradeEvidence,
    coarse_bar: Candle,
    upper_price: float,
    lower_price: float,
) -> _Resolution | None:
    if not evidence.complete:
        return None
    if evidence.symbol != coarse_bar.symbol:
        raise InvalidFineEvidenceError("trade evidence has a different symbol")
    if (
        evidence.coverage_start != coarse_bar.timestamp_open
        or evidence.coverage_end != coarse_bar.timestamp_close
    ):
        raise InvalidFineEvidenceError("trade evidence does not cover the full coarse candle")
    first: _Resolution | None = None
    upper_seen = False
    lower_seen = False
    for timestamp, timestamp_trades in groupby(evidence.trades, key=lambda trade: trade.timestamp):
        prices = tuple(trade.price for trade in timestamp_trades)
        up_hit = any(price >= upper_price for price in prices)
        down_hit = any(price <= lower_price for price in prices)
        upper_seen = upper_seen or up_hit
        lower_seen = lower_seen or down_hit
        if first is None:
            if up_hit and down_hit:
                return None
            if up_hit:
                first = _Resolution(FirstBarrierOutcome.UP_FIRST, timestamp, EvidenceKind.TRADE)
            elif down_hit:
                first = _Resolution(FirstBarrierOutcome.DOWN_FIRST, timestamp, EvidenceKind.TRADE)
    if not upper_seen or not lower_seen:
        raise InvalidFineEvidenceError("trades do not corroborate both coarse-bar reaches")
    return first


def resolve_ambiguous_bar(
    evidence: FineEvidence,
    coarse_bar: Candle,
    upper_price: float,
    lower_price: float,
) -> _Resolution | None:
    """Resolve a both-hit candle only from complete finer chronological evidence."""

    if isinstance(evidence, FineBarEvidence):
        return _resolve_fine_bars(evidence, coarse_bar, upper_price, lower_price)
    if isinstance(evidence, TradeEvidence):
        return _resolve_trades(evidence, coarse_bar, upper_price, lower_price)
    raise TypeError("unsupported fine evidence type")


def generate_barrier_label(
    *,
    anchor: CompletedAnchor,
    anchor_close: float,
    future_bars: Sequence[RawBar | ResampledBar],
    horizon: LabelHorizon,
    barrier: BarrierSpec = PRIMARY_BARRIER,
    fine_evidence_by_coarse_open: Mapping[datetime, FineEvidence] | None = None,
) -> BarrierLabel:
    """Generate one horizon independently, rejecting incomplete future windows."""

    anchor_price = _positive_price(anchor_close, "anchor_close")
    bars = _validate_label_window(anchor, horizon, future_bars)
    upper_price = barrier.upper_price(anchor_price)
    lower_price = barrier.lower_price(anchor_price)
    terminal = math.log(bars[-1].close / anchor_price)
    mfe = max(math.log(bar.high / anchor_price) for bar in bars)
    mae = min(math.log(bar.low / anchor_price) for bar in bars)
    upper_reached = any(bar.high >= upper_price for bar in bars)
    lower_reached = any(bar.low <= lower_price for bar in bars)

    outcome: FirstBarrierOutcome | None = FirstBarrierOutcome.NEITHER
    ambiguity = AmbiguityState.NOT_AMBIGUOUS
    first_timestamp: datetime | None = None
    evidence_kind = EvidenceKind.NONE

    for bar in bars:
        up_hit = bar.high >= upper_price
        down_hit = bar.low <= lower_price
        if not up_hit and not down_hit:
            continue
        if up_hit and down_hit:
            evidence = (
                fine_evidence_by_coarse_open.get(bar.timestamp_open)
                if fine_evidence_by_coarse_open is not None
                else None
            )
            resolution = (
                resolve_ambiguous_bar(evidence, bar, upper_price, lower_price)
                if evidence is not None
                else None
            )
            if resolution is None:
                outcome = None
                ambiguity = AmbiguityState.UNRESOLVED
                evidence_kind = EvidenceKind.NONE
            else:
                outcome = resolution.outcome
                ambiguity = AmbiguityState.RESOLVED_WITH_FINE_DATA
                first_timestamp = resolution.timestamp
                evidence_kind = resolution.evidence_kind
            break
        outcome = FirstBarrierOutcome.UP_FIRST if up_hit else FirstBarrierOutcome.DOWN_FIRST
        first_timestamp = bar.timestamp_close
        evidence_kind = EvidenceKind.COARSE_BAR
        break

    time_to_event = (
        first_timestamp - anchor.anchor_timestamp if first_timestamp is not None else None
    )
    result = BarrierLabel(
        anchor=anchor,
        horizon=horizon,
        barrier=barrier,
        label_timestamp=anchor.anchor_timestamp + horizon.duration,
        terminal_log_return=terminal,
        mfe_log_return=mfe,
        mae_log_return=mae,
        upper_reached=upper_reached,
        lower_reached=lower_reached,
        outcome=outcome,
        ambiguity=ambiguity,
        first_event_timestamp=first_timestamp,
        time_to_event=time_to_event,
        resolution_evidence=evidence_kind,
    )
    result.core_contract
    return result


def generate_required_horizon_labels(
    *,
    anchor: CompletedAnchor,
    anchor_close: float,
    future_bars: Sequence[RawBar | ResampledBar],
    barrier: BarrierSpec = PRIMARY_BARRIER,
    fine_evidence_by_coarse_open: Mapping[datetime, FineEvidence] | None = None,
) -> tuple[BarrierLabel, ...]:
    """Generate all required horizons through separate calls from the same anchor."""

    return tuple(
        generate_barrier_label(
            anchor=anchor,
            anchor_close=anchor_close,
            future_bars=future_bars,
            horizon=horizon,
            barrier=barrier,
            fine_evidence_by_coarse_open=fine_evidence_by_coarse_open,
        )
        for horizon in HORIZONS
    )
