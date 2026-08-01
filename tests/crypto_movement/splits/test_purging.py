from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from crypto_movement.contracts import FoldIdentity, InstrumentType, SymbolIdentity, VenueIdentity
from crypto_movement.splits.purging import (
    AssignedExample,
    ExampleInterval,
    ExcludedExample,
    ExclusionReason,
    assert_no_partition_duplicates,
    assert_no_target_crossing,
    assign_example_to_fold,
    assign_examples,
)
from crypto_movement.splits.walk_forward import GlobalCutoff, Partition
from crypto_movement.time import UTC


def symbol() -> SymbolIdentity:
    venue = VenueIdentity("fixture", InstrumentType.SPOT)
    return SymbolIdentity(venue, "BTC", "USD", "BTC-USD")


def cutoff() -> GlobalCutoff:
    asset = symbol()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    fold = FoldIdentity(
        "outer-000-1y",
        start,
        start + timedelta(days=365),
        start + timedelta(days=365, hours=18),
        start + timedelta(days=395),
        start + timedelta(days=395, hours=18),
        start + timedelta(days=425),
        purge=timedelta(hours=12),
        embargo=timedelta(hours=6),
    )
    return GlobalCutoff(fold, 1, (asset.canonical_id,), 0)


def example(anchor, label_end) -> ExampleInterval:
    return ExampleInterval(
        symbol(),
        sequence_start=anchor - timedelta(hours=24),
        feature_end=anchor,
        anchor_timestamp=anchor,
        label_end=label_end,
    )


def test_safe_examples_assign_once_to_expected_partition() -> None:
    item = cutoff()
    fold = item.fold
    examples = (
        example(fold.train_end - timedelta(hours=1), fold.validation_start - timedelta(seconds=1)),
        example(
            fold.validation_end - timedelta(hours=1),
            fold.test_start - timedelta(seconds=1),
        ),
        example(fold.test_start + timedelta(hours=1), fold.test_start + timedelta(hours=13)),
    )
    assigned, excluded = assign_examples(item, examples)
    assert not excluded
    assert [result.partition for result in assigned] == [
        Partition.TRAIN,
        Partition.VALIDATION,
        Partition.TEST,
    ]
    assert_no_partition_duplicates(assigned)
    assert_no_target_crossing(fold, assigned)


def test_label_end_must_be_strictly_before_next_partition() -> None:
    item = cutoff()
    fold = item.fold
    train = assign_example_to_fold(
        item,
        example(fold.train_end - timedelta(hours=1), fold.validation_start),
    )
    validation = assign_example_to_fold(
        item,
        example(fold.validation_end - timedelta(hours=1), fold.test_start),
    )
    assert isinstance(train, ExcludedExample)
    assert isinstance(validation, ExcludedExample)
    assert train.reason is ExclusionReason.TARGET_CROSSES_BOUNDARY
    assert validation.reason is ExclusionReason.TARGET_CROSSES_BOUNDARY


def test_purge_and_embargo_anchors_are_excluded() -> None:
    item = cutoff()
    anchor = item.fold.train_end + timedelta(hours=1)
    result = assign_example_to_fold(item, example(anchor, anchor + timedelta(hours=12)))
    assert isinstance(result, ExcludedExample)
    assert result.reason is ExclusionReason.PURGE_OR_EMBARGO


def test_example_contract_rejects_future_feature_and_nonfuture_label() -> None:
    anchor = datetime(2025, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="at or before"):
        ExampleInterval(
            symbol(),
            anchor - timedelta(hours=24),
            anchor + timedelta(seconds=1),
            anchor,
            anchor + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="after anchor"):
        example(anchor, anchor)


def test_duplicate_example_membership_is_rejected() -> None:
    item = cutoff()
    anchor = item.fold.train_start + timedelta(days=1)
    duplicate = example(anchor, anchor + timedelta(hours=12))
    with pytest.raises(ValueError, match="duplicate example"):
        assign_examples(item, (duplicate, duplicate))

    assignment = AssignedExample(duplicate, Partition.TRAIN)
    with pytest.raises(AssertionError, match="both train and validation"):
        assert_no_partition_duplicates(
            (assignment, AssignedExample(duplicate, Partition.VALIDATION))
        )
