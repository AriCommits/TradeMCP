from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crypto_movement.contracts import (
    AmbiguityState,
    CandleInterval,
    CompletedAnchor,
    FirstBarrierOutcome,
    InstrumentType,
    LabelHorizon,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.labels.barriers import (
    PRIMARY_BARRIER,
    BarrierLabel,
    BarrierSpec,
    EvidenceKind,
)
from crypto_movement.labels.event_catalog import (
    AmbiguityPolicy,
    build_event_catalog,
    catalog_records,
)
from crypto_movement.time import UTC


def make_label(
    outcome: FirstBarrierOutcome | None,
    *,
    ambiguity: AmbiguityState = AmbiguityState.NOT_AMBIGUOUS,
    barrier: BarrierSpec = PRIMARY_BARRIER,
    asset: str = "BTC",
    year: int = 2026,
) -> BarrierLabel:
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.SPOT), asset, "USD", f"{asset}-USD"
    )
    timestamp = datetime(year, 1, 1, tzinfo=UTC)
    anchor = CompletedAnchor(symbol, CandleInterval.FIFTEEN_MINUTES, timestamp, timestamp)
    event = outcome in (FirstBarrierOutcome.UP_FIRST, FirstBarrierOutcome.DOWN_FIRST)
    return BarrierLabel(
        anchor=anchor,
        horizon=LabelHorizon.ONE_HOUR,
        barrier=barrier,
        label_timestamp=timestamp + timedelta(hours=1),
        terminal_log_return=0.0,
        mfe_log_return=0.05 if outcome is FirstBarrierOutcome.UP_FIRST or outcome is None else 0.01,
        mae_log_return=-0.05
        if outcome is FirstBarrierOutcome.DOWN_FIRST or outcome is None
        else -0.01,
        upper_reached=outcome is FirstBarrierOutcome.UP_FIRST or outcome is None,
        lower_reached=outcome is FirstBarrierOutcome.DOWN_FIRST or outcome is None,
        outcome=outcome,
        ambiguity=ambiguity,
        first_event_timestamp=timestamp + timedelta(minutes=15) if event else None,
        time_to_event=timedelta(minutes=15) if event else None,
        resolution_evidence=EvidenceKind.COARSE_BAR if event else EvidenceKind.NONE,
    )


def row_map(rows):
    return {
        (row.ambiguity_policy, row.outcome_class): (
            row.count,
            row.total,
            row.eligible_anchor_count,
            row.rate,
            row.eligible_anchor_rate,
        )
        for row in rows
    }


def test_catalog_counts_classes_and_keeps_ambiguity_distinct() -> None:
    labels = (
        make_label(FirstBarrierOutcome.UP_FIRST),
        make_label(FirstBarrierOutcome.UP_FIRST),
        make_label(FirstBarrierOutcome.DOWN_FIRST),
        make_label(FirstBarrierOutcome.NEITHER),
        make_label(None, ambiguity=AmbiguityState.UNRESOLVED),
    )
    rows = build_event_catalog(labels)
    counts = row_map(rows)
    assert counts[(AmbiguityPolicy.RETAIN.value, "up_first")] == (2, 5, 5, 0.4, 0.4)
    assert counts[(AmbiguityPolicy.RETAIN.value, "ambiguous")] == (1, 5, 5, 0.2, 0.2)
    assert counts[(AmbiguityPolicy.EXCLUDE.value, "up_first")] == (2, 4, 5, 0.5, 0.4)
    assert counts[(AmbiguityPolicy.EXCLUDE.value, "ambiguous")] == (0, 4, 5, 0.0, 0.0)
    assert all(row.symbol.endswith(":BTC/USD:BTC-USD") for row in rows)


def test_conservative_sensitivity_policies_are_explicit() -> None:
    labels = (
        make_label(FirstBarrierOutcome.DOWN_FIRST),
        make_label(None, ambiguity=AmbiguityState.UNRESOLVED),
    )
    rows = build_event_catalog(
        labels,
        ambiguity_policies=(
            AmbiguityPolicy.ASSUME_DOWN_FIRST,
            AmbiguityPolicy.ASSUME_NEITHER,
        ),
    )
    counts = row_map(rows)
    assert counts[(AmbiguityPolicy.ASSUME_DOWN_FIRST.value, "down_first")][:3] == (2, 2, 2)
    assert counts[(AmbiguityPolicy.ASSUME_NEITHER.value, "down_first")][:3] == (1, 2, 2)
    assert counts[(AmbiguityPolicy.ASSUME_NEITHER.value, "neither")][:3] == (1, 2, 2)


def test_catalog_groups_year_symbol_horizon_and_threshold() -> None:
    one_percent = BarrierSpec.arithmetic(0.01, threshold_id="arithmetic_1pct")
    volatility = BarrierSpec.volatility_normalized(0.02, multiplier=2.0)
    labels = (
        make_label(FirstBarrierOutcome.UP_FIRST, year=2025),
        make_label(FirstBarrierOutcome.UP_FIRST, year=2026, asset="ETH"),
        make_label(FirstBarrierOutcome.NEITHER, barrier=one_percent),
        make_label(FirstBarrierOutcome.DOWN_FIRST, barrier=volatility),
    )
    rows = build_event_catalog(labels, ambiguity_policies=(AmbiguityPolicy.RETAIN,))
    assert len(rows) == 16
    assert {row.anchor_year for row in rows} == {2025, 2026}
    assert {row.threshold_id for row in rows} == {
        "arithmetic_4pct",
        "arithmetic_1pct",
        volatility.threshold_id,
    }
    assert {record["ambiguity_policy"] for record in catalog_records(rows)} == {
        AmbiguityPolicy.RETAIN.value
    }


def test_catalog_rejects_duplicate_or_empty_policy_sets() -> None:
    label = make_label(FirstBarrierOutcome.NEITHER)
    with pytest.raises(ValueError, match="non-empty and unique"):
        build_event_catalog((label,), ambiguity_policies=())
    with pytest.raises(ValueError, match="non-empty and unique"):
        build_event_catalog(
            (label,),
            ambiguity_policies=(AmbiguityPolicy.RETAIN, AmbiguityPolicy.RETAIN),
        )


def test_required_hand_worked_parquet_fixture_inventory() -> None:
    parquet = pytest.importorskip("pyarrow.parquet")
    fixture_path = Path("tests/fixtures/crypto_movement/label_cases.parquet")
    table = parquet.read_table(fixture_path)
    cases = set(table.column("case_id").to_pylist())
    assert cases == {
        "up_first",
        "down_first",
        "neither",
        "exact_upper_touch",
        "exact_lower_touch",
        "both_hit_unresolved",
        "both_hit_fine_resolved",
        "missing_future_gap",
    }
    assert table.schema.metadata[b"fixture_schema_version"] == b"1"
