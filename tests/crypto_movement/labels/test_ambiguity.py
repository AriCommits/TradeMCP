from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from crypto_movement.contracts import (
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
    EvidenceKind,
    FineBarEvidence,
    InvalidFineEvidenceError,
    TradeEvidence,
    TradeTick,
    generate_barrier_label,
)
from crypto_movement.time import UTC


def make_anchor() -> CompletedAnchor:
    symbol = SymbolIdentity(VenueIdentity("fixture", InstrumentType.SPOT), "BTC", "USD", "BTC-USD")
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return CompletedAnchor(symbol, CandleInterval.FIFTEEN_MINUTES, timestamp, timestamp)


def make_coarse_bars(anchor: CompletedAnchor, *, both_hit: bool = True) -> tuple[RawBar, ...]:
    bars = []
    previous_close = 100.0
    for index in range(4):
        opened = previous_close
        high = 104.0 if index == 0 else max(opened, 101.0)
        low = 96.0 if index == 0 and both_hit else min(opened, 99.0)
        closed = 100.0
        timestamp_open = anchor.anchor_timestamp + timedelta(minutes=15 * index)
        timestamp_close = timestamp_open + timedelta(minutes=15)
        bars.append(
            RawBar(
                anchor.symbol,
                CandleInterval.FIFTEEN_MINUTES,
                timestamp_open,
                timestamp_close,
                opened,
                high,
                low,
                closed,
                "coarse-fixture",
                timestamp_close,
            )
        )
        previous_close = closed
    return tuple(bars)


def make_fine_bars(
    anchor: CompletedAnchor,
    *,
    first: FirstBarrierOutcome | None,
) -> tuple[RawBar, ...]:
    bars = []
    previous_close = 100.0
    for index in range(15):
        opened = previous_close
        high = max(opened, 101.0)
        low = min(opened, 99.0)
        closed = 100.0
        if index == 0 and first is FirstBarrierOutcome.UP_FIRST:
            high, low, closed = 104.0, 99.0, 103.0
        elif index == 1 and first is FirstBarrierOutcome.UP_FIRST:
            high, low, closed = 103.0, 96.0, 97.0
        elif index == 0 and first is FirstBarrierOutcome.DOWN_FIRST:
            high, low, closed = 101.0, 96.0, 97.0
        elif index == 1 and first is FirstBarrierOutcome.DOWN_FIRST:
            high, low, closed = 104.0, 97.0, 103.0
        elif index == 0 and first is None:
            high, low, closed = 104.0, 96.0, 100.0
        timestamp_open = anchor.anchor_timestamp + timedelta(minutes=index)
        timestamp_close = timestamp_open + timedelta(minutes=1)
        bars.append(
            RawBar(
                anchor.symbol,
                CandleInterval.ONE_MINUTE,
                timestamp_open,
                timestamp_close,
                opened,
                high,
                low,
                closed,
                "fine-fixture",
                timestamp_close,
            )
        )
        previous_close = closed
    return tuple(bars)


def label_with_evidence(anchor: CompletedAnchor, evidence: object | None = None):
    mapping = None if evidence is None else {anchor.anchor_timestamp: evidence}
    return generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=make_coarse_bars(anchor),
        horizon=LabelHorizon.ONE_HOUR,
        fine_evidence_by_coarse_open=mapping,  # type: ignore[arg-type]
    )


def test_both_hit_without_finer_evidence_is_unresolved_not_neither() -> None:
    label = label_with_evidence(make_anchor())
    assert label.upper_reached and label.lower_reached
    assert label.outcome is None
    assert label.ambiguity is AmbiguityState.UNRESOLVED
    assert label.resolution_evidence is EvidenceKind.NONE
    assert label.time_to_event is None


@pytest.mark.parametrize(
    "expected",
    [FirstBarrierOutcome.UP_FIRST, FirstBarrierOutcome.DOWN_FIRST],
)
def test_complete_one_minute_bars_resolve_order(expected: FirstBarrierOutcome) -> None:
    anchor = make_anchor()
    label = label_with_evidence(anchor, FineBarEvidence(make_fine_bars(anchor, first=expected)))
    assert label.outcome is expected
    assert label.ambiguity is AmbiguityState.RESOLVED_WITH_FINE_DATA
    assert label.resolution_evidence is EvidenceKind.ONE_MINUTE_BAR
    expected_minutes = 1 if expected is FirstBarrierOutcome.UP_FIRST else 1
    assert label.time_to_event == timedelta(minutes=expected_minutes)


def test_both_hit_inside_first_fine_bar_remains_unresolved() -> None:
    anchor = make_anchor()
    label = label_with_evidence(anchor, FineBarEvidence(make_fine_bars(anchor, first=None)))
    assert label.outcome is None
    assert label.ambiguity is AmbiguityState.UNRESOLVED


def test_incomplete_fine_evidence_is_not_eligible_for_resolution() -> None:
    anchor = make_anchor()
    evidence = FineBarEvidence(
        make_fine_bars(anchor, first=FirstBarrierOutcome.UP_FIRST)[:2], complete=False
    )
    label = label_with_evidence(anchor, evidence)
    assert label.outcome is None
    assert label.ambiguity is AmbiguityState.UNRESOLVED


def test_evidence_claiming_complete_coverage_rejects_gaps() -> None:
    anchor = make_anchor()
    incomplete = make_fine_bars(anchor, first=FirstBarrierOutcome.UP_FIRST)[:-1]
    with pytest.raises(InvalidFineEvidenceError, match="do not cover"):
        label_with_evidence(anchor, FineBarEvidence(incomplete))


def test_complete_trade_evidence_resolves_exact_order() -> None:
    anchor = make_anchor()
    evidence = TradeEvidence(
        symbol=anchor.symbol,
        coverage_start=anchor.anchor_timestamp,
        coverage_end=anchor.anchor_timestamp + timedelta(minutes=15),
        trades=(
            TradeTick(anchor.symbol, anchor.anchor_timestamp + timedelta(minutes=2), 96.0),
            TradeTick(anchor.symbol, anchor.anchor_timestamp + timedelta(minutes=3), 104.0),
        ),
    )
    label = label_with_evidence(anchor, evidence)
    assert label.outcome is FirstBarrierOutcome.DOWN_FIRST
    assert label.resolution_evidence is EvidenceKind.TRADE
    assert label.time_to_event == timedelta(minutes=2)


def test_fine_evidence_mapping_is_not_consumed_for_single_hit_bar() -> None:
    class ForbiddenMapping(dict[datetime, FineBarEvidence]):
        def get(self, key: datetime, default: object = None):  # type: ignore[override]
            raise AssertionError("fine evidence was consumed outside ambiguity resolution")

    anchor = make_anchor()
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=100.0,
        future_bars=make_coarse_bars(anchor, both_hit=False),
        horizon=LabelHorizon.ONE_HOUR,
        fine_evidence_by_coarse_open=ForbiddenMapping(),
    )
    assert label.outcome is FirstBarrierOutcome.UP_FIRST
    assert label.resolution_evidence is EvidenceKind.COARSE_BAR


def test_opposite_trade_hits_at_same_timestamp_remain_unresolved() -> None:
    anchor = make_anchor()
    timestamp = anchor.anchor_timestamp + timedelta(minutes=2)
    evidence = TradeEvidence(
        symbol=anchor.symbol,
        coverage_start=anchor.anchor_timestamp,
        coverage_end=anchor.anchor_timestamp + timedelta(minutes=15),
        trades=(
            TradeTick(anchor.symbol, timestamp, 96.0),
            TradeTick(anchor.symbol, timestamp, 104.0),
        ),
    )
    label = label_with_evidence(anchor, evidence)
    assert label.outcome is None
    assert label.ambiguity is AmbiguityState.UNRESOLVED
    assert label.time_to_event is None
