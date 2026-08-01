from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta

import pytest

from crypto_movement.contracts import (
    ABLATION_SEQUENCE,
    HORIZONS,
    LOWER_BARRIER_LOG,
    MINIMUM_PURGE,
    PRIMARY_SEQUENCE,
    UPPER_BARRIER_LOG,
    AmbiguityState,
    CandleInterval,
    CompletedAnchor,
    FeatureAvailability,
    FirstBarrierLabel,
    FirstBarrierOutcome,
    FoldIdentity,
    InstrumentType,
    LabelHorizon,
    RawBar,
    ResampledBar,
    SequenceSpec,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.time import UTC


@pytest.fixture
def symbol() -> SymbolIdentity:
    venue = VenueIdentity("Example Exchange", InstrumentType.PERPETUAL)
    return SymbolIdentity(venue, "btc", "usdt", "BTCUSDT")


@pytest.fixture
def completed_anchor(symbol: SymbolIdentity) -> CompletedAnchor:
    anchor = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    return CompletedAnchor(symbol, CandleInterval.FIFTEEN_MINUTES, anchor, anchor)


def _raw_bar(symbol: SymbolIdentity, **changes: object) -> RawBar:
    values: dict[str, object] = {
        "symbol": symbol,
        "interval": CandleInterval.FIFTEEN_MINUTES,
        "timestamp_open": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "timestamp_close": datetime(2026, 1, 1, 12, 15, tzinfo=UTC),
        "open": 100.0,
        "high": 104.0,
        "low": 96.0,
        "close": 102.0,
        "source": "fixture",
        "downloaded_at": datetime(2026, 1, 1, 12, 15, tzinfo=UTC),
        "base_volume": 10.0,
        "quote_volume": 1_010.0,
        "trade_count": 3,
        "taker_buy_volume": 4.0,
    }
    values.update(changes)
    return RawBar(**values)  # type: ignore[arg-type]


def test_venue_and_symbol_are_canonical_and_immutable(symbol: SymbolIdentity) -> None:
    assert symbol.venue.canonical_id == "example exchange:perpetual"
    assert symbol.canonical_pair == "BTC/USDT"
    assert symbol.canonical_id.endswith(":BTC/USDT:BTCUSDT")

    with pytest.raises(FrozenInstanceError):
        symbol.canonical_asset = "ETH"  # type: ignore[misc]


def test_barrier_constants_are_arithmetic_to_log_conversions() -> None:
    assert UPPER_BARRIER_LOG == math.log(1.04)
    assert LOWER_BARRIER_LOG == math.log(0.96)
    assert not math.isclose(abs(LOWER_BARRIER_LOG), UPPER_BARRIER_LOG)


def test_sequence_contracts_and_horizon_steps() -> None:
    assert PRIMARY_SEQUENCE.interval is CandleInterval.FIFTEEN_MINUTES
    assert PRIMARY_SEQUENCE.steps == 96
    assert ABLATION_SEQUENCE.interval is CandleInterval.THIRTY_MINUTES
    assert ABLATION_SEQUENCE.steps == 48
    assert PRIMARY_SEQUENCE.history == ABLATION_SEQUENCE.history == timedelta(hours=24)
    assert HORIZONS == (
        LabelHorizon.ONE_HOUR,
        LabelHorizon.THREE_HOURS,
        LabelHorizon.SIX_HOURS,
        LabelHorizon.TWELVE_HOURS,
    )
    assert [horizon.steps(CandleInterval.FIFTEEN_MINUTES) for horizon in HORIZONS] == [
        4,
        12,
        24,
        48,
    ]
    assert [horizon.steps(CandleInterval.THIRTY_MINUTES) for horizon in HORIZONS] == [
        2,
        6,
        12,
        24,
    ]

    with pytest.raises(ValueError, match="exactly history"):
        SequenceSpec(CandleInterval.FIFTEEN_MINUTES, 95)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"open": 0.0}, "positive"),
        ({"high": 95.0}, "greater than or equal to low"),
        ({"high": 101.0}, r"max\(open, close\)"),
        ({"low": 101.0}, r"min\(open, close\)"),
        ({"base_volume": -1.0}, "nonnegative"),
        ({"taker_buy_volume": 11.0}, "cannot exceed"),
        ({"close": math.inf}, "finite"),
    ],
)
def test_raw_bar_rejects_invalid_prices_and_market_values(
    symbol: SymbolIdentity,
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _raw_bar(symbol, **changes)


def test_raw_bar_requires_aligned_complete_utc_candle(symbol: SymbolIdentity) -> None:
    bar = _raw_bar(symbol)
    assert bar.timestamp_close - bar.timestamp_open == timedelta(minutes=15)

    with pytest.raises(ValueError, match="not aligned"):
        _raw_bar(symbol, timestamp_open=datetime(2026, 1, 1, 12, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="incomplete candle"):
        _raw_bar(symbol, downloaded_at=datetime(2026, 1, 1, 12, 14, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _raw_bar(symbol, timestamp_open=datetime(2026, 1, 1, 12, 0))


def test_resampled_bar_requires_every_constituent(symbol: SymbolIdentity) -> None:
    values = {
        "symbol": symbol,
        "interval": CandleInterval.THIRTY_MINUTES,
        "source_interval": CandleInterval.FIFTEEN_MINUTES,
        "timestamp_open": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        "timestamp_close": datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        "open": 100.0,
        "high": 104.0,
        "low": 96.0,
        "close": 102.0,
        "constituent_count": 2,
        "generated_at": datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
    }
    assert ResampledBar(**values).constituent_count == 2  # type: ignore[arg-type]
    values["constituent_count"] = 1
    with pytest.raises(ValueError, match="every constituent"):
        ResampledBar(**values)  # type: ignore[arg-type]


def test_completed_anchor_rejects_incomplete_candle(symbol: SymbolIdentity) -> None:
    anchor = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    assert CompletedAnchor(
        symbol, CandleInterval.FIFTEEN_MINUTES, anchor, anchor
    ).anchor_timestamp == anchor
    with pytest.raises(ValueError, match="incomplete candle"):
        CompletedAnchor(
            symbol,
            CandleInterval.FIFTEEN_MINUTES,
            anchor,
            anchor - timedelta(microseconds=1),
        )


def test_feature_availability_allows_anchor_but_rejects_future_predictor() -> None:
    anchor = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    assert FeatureAvailability("close", anchor, anchor).feature_timestamp == anchor
    with pytest.raises(ValueError, match="at or before"):
        FeatureAvailability("future close", anchor + timedelta(seconds=1), anchor)


def test_first_barrier_label_requires_exact_future_horizon(
    completed_anchor: CompletedAnchor,
) -> None:
    label_time = completed_anchor.anchor_timestamp + timedelta(hours=1)
    label = FirstBarrierLabel(
        anchor=completed_anchor,
        horizon=LabelHorizon.ONE_HOUR,
        label_timestamp=label_time,
        outcome=FirstBarrierOutcome.UP_FIRST,
        ambiguity=AmbiguityState.NOT_AMBIGUOUS,
        terminal_log_return=0.02,
        mfe_log_return=UPPER_BARRIER_LOG,
        mae_log_return=-0.01,
        time_to_event=timedelta(hours=1),
    )
    assert label.label_timestamp > completed_anchor.anchor_timestamp

    with pytest.raises(ValueError, match=r"anchor \+ horizon"):
        replace(label, label_timestamp=label_time - timedelta(microseconds=1))
    with pytest.raises(ValueError, match="must have time_to_event"):
        replace(label, time_to_event=None)


def test_unresolved_ambiguity_never_guesses_an_outcome(
    completed_anchor: CompletedAnchor,
) -> None:
    label_time = completed_anchor.anchor_timestamp + timedelta(hours=3)
    ambiguous = FirstBarrierLabel(
        anchor=completed_anchor,
        horizon=LabelHorizon.THREE_HOURS,
        label_timestamp=label_time,
        outcome=None,
        ambiguity=AmbiguityState.UNRESOLVED,
    )
    assert ambiguous.outcome is None
    with pytest.raises(ValueError, match="cannot have an outcome"):
        replace(ambiguous, outcome=FirstBarrierOutcome.UP_FIRST)


def test_fold_identity_enforces_chronology_and_twelve_hour_purge() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    fold = FoldIdentity(
        fold_id="outer-001",
        train_start=start,
        train_end=start + timedelta(days=365),
        validation_start=start + timedelta(days=365, hours=12),
        validation_end=start + timedelta(days=395),
        test_start=start + timedelta(days=395, hours=12),
        test_end=start + timedelta(days=425),
    )
    assert fold.purge == MINIMUM_PURGE

    with pytest.raises(ValueError, match="maximum 12-hour"):
        replace(fold, purge=timedelta(hours=11, minutes=59))
    with pytest.raises(ValueError, match="violate purge"):
        replace(fold, validation_start=fold.train_end + timedelta(hours=11))
