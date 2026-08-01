"""Target-window purging and duplicate-membership guards."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from crypto_movement.contracts import FoldIdentity, SymbolIdentity
from crypto_movement.splits.walk_forward import GlobalCutoff, Partition
from crypto_movement.time import as_utc


class ExclusionReason(str, Enum):
    OUTSIDE_FOLD = "outside_fold"
    PURGE_OR_EMBARGO = "purge_or_embargo"
    TARGET_CROSSES_BOUNDARY = "target_crosses_boundary"


@dataclass(frozen=True, slots=True)
class ExampleInterval:
    """Feature and target endpoints for one anchor before partitioning."""

    symbol: SymbolIdentity
    sequence_start: datetime
    feature_end: datetime
    anchor_timestamp: datetime
    label_end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, SymbolIdentity):
            raise TypeError("symbol must be a SymbolIdentity")
        names = ("sequence_start", "feature_end", "anchor_timestamp", "label_end")
        values = tuple(as_utc(getattr(self, name), field_name=name) for name in names)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value)
        sequence_start, feature_end, anchor, label_end = values
        if sequence_start > feature_end:
            raise ValueError("sequence_start must not exceed feature_end")
        if feature_end > anchor:
            raise ValueError("feature_end must be at or before anchor")
        if label_end <= anchor:
            raise ValueError("label_end must be after anchor")

    @property
    def identity_key(self) -> tuple[str, datetime, datetime]:
        return self.symbol.canonical_id, self.anchor_timestamp, self.label_end


@dataclass(frozen=True, slots=True)
class AssignedExample:
    example: ExampleInterval
    partition: Partition


@dataclass(frozen=True, slots=True)
class ExcludedExample:
    example: ExampleInterval
    reason: ExclusionReason


def assign_example_to_fold(
    cutoff: GlobalCutoff,
    example: ExampleInterval,
) -> AssignedExample | ExcludedExample:
    """Assign once and reject labels that cross the next visible partition."""

    if not cutoff.includes_symbol(example.symbol):
        raise KeyError("example symbol is not part of the global cutoff")
    partition = cutoff.partition_at(example.symbol, example.anchor_timestamp)
    fold = cutoff.fold
    if partition is Partition.TRAIN:
        if example.label_end >= fold.validation_start:
            return ExcludedExample(example, ExclusionReason.TARGET_CROSSES_BOUNDARY)
        return AssignedExample(example, partition)
    if partition is Partition.VALIDATION:
        if example.label_end >= fold.test_start:
            return ExcludedExample(example, ExclusionReason.TARGET_CROSSES_BOUNDARY)
        return AssignedExample(example, partition)
    if partition is Partition.TEST:
        if example.label_end > fold.test_end:
            return ExcludedExample(example, ExclusionReason.TARGET_CROSSES_BOUNDARY)
        return AssignedExample(example, partition)
    if partition is Partition.PURGED:
        return ExcludedExample(example, ExclusionReason.PURGE_OR_EMBARGO)
    return ExcludedExample(example, ExclusionReason.OUTSIDE_FOLD)


def assign_examples(
    cutoff: GlobalCutoff,
    examples: Iterable[ExampleInterval],
) -> tuple[tuple[AssignedExample, ...], tuple[ExcludedExample, ...]]:
    assigned = []
    excluded = []
    seen = set()
    for example in examples:
        if example.identity_key in seen:
            raise ValueError("duplicate example identity")
        seen.add(example.identity_key)
        result = assign_example_to_fold(cutoff, example)
        if isinstance(result, AssignedExample):
            assigned.append(result)
        else:
            excluded.append(result)
    assigned.sort(
        key=lambda item: (
            item.example.anchor_timestamp,
            item.example.symbol.canonical_id,
            item.example.label_end,
        )
    )
    excluded.sort(
        key=lambda item: (
            item.example.anchor_timestamp,
            item.example.symbol.canonical_id,
            item.example.label_end,
        )
    )
    return tuple(assigned), tuple(excluded)


def assert_no_partition_duplicates(assignments: Iterable[AssignedExample]) -> None:
    memberships: dict[tuple[str, datetime, datetime], Partition] = {}
    for assignment in assignments:
        key = assignment.example.identity_key
        previous = memberships.get(key)
        if previous is not None:
            raise AssertionError(
                f"example appears in both {previous.value} and {assignment.partition.value}"
            )
        memberships[key] = assignment.partition


def assert_no_target_crossing(
    fold: FoldIdentity,
    assignments: Iterable[AssignedExample],
) -> None:
    for assignment in assignments:
        label_end = assignment.example.label_end
        if assignment.partition is Partition.TRAIN and label_end >= fold.validation_start:
            raise AssertionError("training label crosses validation boundary")
        if assignment.partition is Partition.VALIDATION and label_end >= fold.test_start:
            raise AssertionError("validation label crosses test boundary")
        if assignment.partition is Partition.TEST and label_end > fold.test_end:
            raise AssertionError("test label crosses test end")
