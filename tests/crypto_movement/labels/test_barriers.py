from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from crypto_movement.contracts import (
    HORIZONS,
    LOWER_BARRIER_LOG,
    UPPER_BARRIER_LOG,
    AmbiguityState,
    CandleInterval,
    CompletedAnchor,
    FirstBarrierOutcome,
    InstrumentType,
    LabelHorizon,
    RawBar,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.labels.barriers import (
    AUXILIARY_ARITHMETIC_BARRIERS,
    PRIMARY_BARRIER,
    BarrierKind,
    BarrierSpec,
    IncompleteLabelWindowError,
    generate_barrier_label,
    generate_required_horizon_labels,
)
from crypto_movement.time import UTC


@pytest.fixture
def symbol() -> SymbolIdentity:
    return SymbolIdentity(VenueIdentity("fixture", InstrumentType.SPOT), "BTC", "USD", "BTC-USD")


@pytest.fixture
def anchor(symbol: SymbolIdentity) -> CompletedAnchor:
    timestamp = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return CompletedAnchor(symbol, CandleInterval.FIFTEEN_MINUTES, timestamp, timestamp)


def make_bars(
    anchor: CompletedAnchor,
    count: int = 48,
    *,
    overrides: dict[int, tuple[float, float, float, float]] | None = None,
) -> tuple[RawBar, ...]:
    overrides = overrides or {}
    bars = []
    previous_close = 100.0
    for index in range(count):
        opened, high, low, closed = overrides.get(
            index, (previous_close, max(previous_close, 101.0), min(previous_close, 99.0), 100.0)
        )
        timestamp_open = anchor.anchor_timestamp + anchor.interval.duration * index
        timestamp_close = timestamp_open + anchor.interval.duration
        bars.append(
            RawBar(
                symbol=anchor.symbol,
                interval=anchor.interval,
                timestamp_open=timestamp_open,
                timestamp_close=timestamp_close,
                open=opened,
                high=high,
                low=low,
                close=closed,
                source="hand-worked-fixture",
                downloaded_at=timestamp_close,
            )
        )
        previous_close = closed
    return tuple(bars)


def test_primary_and_auxiliary_arithmetic_barriers_are_exact() -> None:
    assert PRIMARY_BARRIER.upper_log_return == UPPER_BARRIER_LOG == math.log(1.04)
    assert PRIMARY_BARRIER.lower_log_return == LOWER_BARRIER_LOG == math.log(0.96)
    assert PRIMARY_BARRIER.upper_price(100.0) == pytest.approx(104.0)
    assert PRIMARY_BARRIER.lower_price(100.0) == pytest.approx(96.0)
    assert [item.fraction_or_scale for item in AUXILIARY_ARITHMETIC_BARRIERS] == [0.01, 0.02]
    assert not math.isclose(abs(PRIMARY_BARRIER.lower_log_return), PRIMARY_BARRIER.upper_log_return)


def test_volatility_normalized_barrier_is_separate_from_primary() -> None:
    auxiliary = BarrierSpec.volatility_normalized(0.02, multiplier=1.5)
    assert auxiliary.kind is BarrierKind.VOLATILITY_NORMALIZED
    assert auxiliary.upper_log_return == pytest.approx(0.03)
    assert auxiliary.lower_log_return == pytest.approx(-0.03)
    assert PRIMARY_BARRIER.kind is BarrierKind.ARITHMETIC


def test_up_first_exact_touch_and_regression_targets(anchor: CompletedAnchor) -> None:
    bars = make_bars(
        anchor,
        overrides={
            0: (100.0, 104.0, 99.0, 103.0),
            1: (103.0, 105.0, 95.0, 102.0),
            3: (100.0, 102.0, 98.0, 101.0),
        },
    )
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=bars,
        horizon=LabelHorizon.ONE_HOUR,
    )
    assert label.outcome is FirstBarrierOutcome.UP_FIRST
    assert label.ambiguity is AmbiguityState.NOT_AMBIGUOUS
    assert label.upper_reached and label.lower_reached
    assert label.time_to_event == timedelta(minutes=15)
    assert label.terminal_log_return == pytest.approx(math.log(1.01))
    assert label.mfe_log_return == pytest.approx(math.log(1.05))
    assert label.mae_log_return == pytest.approx(math.log(0.95))


def test_down_first_exact_touch(anchor: CompletedAnchor) -> None:
    bars = make_bars(
        anchor,
        overrides={
            0: (100.0, 101.0, 96.0, 97.0),
            1: (97.0, 104.0, 97.0, 103.0),
        },
    )
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=bars,
        horizon=LabelHorizon.ONE_HOUR,
    )
    assert label.outcome is FirstBarrierOutcome.DOWN_FIRST
    assert label.upper_reached and label.lower_reached
    assert label.time_to_event == timedelta(minutes=15)


def test_neither_is_distinct_from_ambiguity(anchor: CompletedAnchor) -> None:
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=make_bars(anchor),
        horizon=LabelHorizon.ONE_HOUR,
    )
    assert label.outcome is FirstBarrierOutcome.NEITHER
    assert label.ambiguity is AmbiguityState.NOT_AMBIGUOUS
    assert not label.upper_reached and not label.lower_reached
    assert label.first_event_timestamp is None
    assert label.time_to_event is None


def test_required_horizons_are_computed_independently(anchor: CompletedAnchor) -> None:
    bars = make_bars(
        anchor,
        overrides={
            7: (100.0, 101.0, 96.0, 97.0),
            30: (100.0, 104.0, 99.0, 103.0),
            47: (100.0, 101.0, 99.0, 101.0),
        },
    )
    labels = generate_required_horizon_labels(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=bars,
    )
    assert tuple(label.horizon for label in labels) == HORIZONS
    assert [label.outcome for label in labels] == [
        FirstBarrierOutcome.NEITHER,
        FirstBarrierOutcome.DOWN_FIRST,
        FirstBarrierOutcome.DOWN_FIRST,
        FirstBarrierOutcome.DOWN_FIRST,
    ]
    assert [label.label_timestamp - anchor.anchor_timestamp for label in labels] == [
        timedelta(hours=1),
        timedelta(hours=3),
        timedelta(hours=6),
        timedelta(hours=12),
    ]
    assert labels[0].terminal_log_return == pytest.approx(0.0)
    assert labels[-1].terminal_log_return == pytest.approx(math.log(1.01))


def test_missing_or_gapped_window_is_rejected_without_forward_fill(anchor: CompletedAnchor) -> None:
    bars = make_bars(anchor, count=4)
    with pytest.raises(IncompleteLabelWindowError, match="requires 12"):
        generate_barrier_label(
            anchor=anchor,
            anchor_close=100.0,
            future_bars=bars[:3],
            horizon=LabelHorizon.THREE_HOURS,
        )

    gapped = bars[:1] + bars[2:4]
    shifted = make_bars(anchor, count=1)[0]
    gapped = gapped + (shifted,)
    with pytest.raises(IncompleteLabelWindowError, match="gap or duplicate"):
        generate_barrier_label(
            anchor=anchor,
            anchor_close=100.0,
            future_bars=gapped,
            horizon=LabelHorizon.ONE_HOUR,
        )


def test_thirty_minute_input_uses_two_steps_per_hour(symbol: SymbolIdentity) -> None:
    timestamp = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    anchor = CompletedAnchor(symbol, CandleInterval.THIRTY_MINUTES, timestamp, timestamp)
    bars = make_bars(anchor, count=2, overrides={1: (100.0, 104.0, 99.0, 103.0)})
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=bars,
        horizon=LabelHorizon.ONE_HOUR,
    )
    assert label.outcome is FirstBarrierOutcome.UP_FIRST
    assert label.time_to_event == timedelta(hours=1)
