"""Globally synchronized rolling walk-forward cutoff calendars."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from crypto_movement.contracts import MINIMUM_PURGE, FoldIdentity, SymbolIdentity
from crypto_movement.time import as_utc


class LockboxAccessError(PermissionError):
    """Raised when untouched lockbox timestamps are requested without authorization."""


class Partition(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    PURGED = "purged"
    OUTSIDE = "outside"
    LOCKBOX = "lockbox"


@dataclass(frozen=True, slots=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = as_utc(self.start, field_name="range start")
        end = as_utc(self.end, field_name="range end")
        if end <= start:
            raise ValueError("time range must be non-empty")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, timestamp: datetime) -> bool:
        value = as_utc(timestamp)
        return self.start <= value < self.end


@dataclass(frozen=True, slots=True)
class InnerFoldIdentity:
    """The sole chronological tuning holdout nested inside an outer history."""

    inner_fold_id: str
    parent_fold_id: str
    train: TimeRange
    validation: TimeRange
    purge: timedelta
    embargo: timedelta

    def __post_init__(self) -> None:
        if not self.inner_fold_id.strip() or not self.parent_fold_id.strip():
            raise ValueError("inner and parent fold IDs cannot be blank")
        if self.validation.start - self.train.end < self.purge + self.embargo:
            raise ValueError("inner fold violates purge plus embargo")


@dataclass(frozen=True, slots=True)
class GlobalCutoff:
    """One FoldIdentity shared by every symbol for one rolling history."""

    fold: FoldIdentity
    history_years: int
    symbol_ids: tuple[str, ...]
    outer_index: int

    def __post_init__(self) -> None:
        if self.history_years not in (1, 3, 5):
            raise ValueError("history_years must be one of 1, 3, or 5")
        if isinstance(self.outer_index, bool) or self.outer_index < 0:
            raise ValueError("outer_index must be nonnegative")
        symbols = tuple(sorted(set(self.symbol_ids)))
        if not symbols or symbols != self.symbol_ids:
            raise ValueError("symbol_ids must be non-empty, unique, and sorted")

    @property
    def inner_fold(self) -> InnerFoldIdentity:
        return InnerFoldIdentity(
            inner_fold_id=f"{self.fold.fold_id}:inner-000",
            parent_fold_id=self.fold.fold_id,
            train=TimeRange(self.fold.train_start, self.fold.train_end),
            validation=TimeRange(self.fold.validation_start, self.fold.validation_end),
            purge=self.fold.purge,
            embargo=self.fold.embargo,
        )

    def includes_symbol(self, symbol: SymbolIdentity | str) -> bool:
        identifier = symbol.canonical_id if isinstance(symbol, SymbolIdentity) else symbol
        return identifier in self.symbol_ids

    def partition_at(self, symbol: SymbolIdentity | str, timestamp: datetime) -> Partition:
        if not self.includes_symbol(symbol):
            raise KeyError("symbol is not part of this global cutoff")
        value = as_utc(timestamp)
        fold = self.fold
        if fold.train_start <= value < fold.train_end:
            return Partition.TRAIN
        if fold.validation_start <= value < fold.validation_end:
            return Partition.VALIDATION
        if fold.test_start <= value < fold.test_end:
            return Partition.TEST
        if fold.train_end <= value < fold.validation_start:
            return Partition.PURGED
        if fold.validation_end <= value < fold.test_start:
            return Partition.PURGED
        return Partition.OUTSIDE


@dataclass(frozen=True, slots=True)
class GlobalFoldCalendar:
    cutoffs: tuple[GlobalCutoff, ...]
    symbol_ids: tuple[str, ...]
    lockbox: TimeRange

    def __post_init__(self) -> None:
        symbol_ids = tuple(sorted(set(self.symbol_ids)))
        if not symbol_ids or symbol_ids != self.symbol_ids:
            raise ValueError("calendar symbol_ids must be non-empty, unique, and sorted")
        if not self.cutoffs:
            raise ValueError("calendar must contain at least one cutoff")
        if any(cutoff.symbol_ids != symbol_ids for cutoff in self.cutoffs):
            raise ValueError("every cutoff must use the same cross-asset symbol set")
        identities = [cutoff.fold.fold_id for cutoff in self.cutoffs]
        if len(identities) != len(set(identities)):
            raise ValueError("fold identities must be unique")
        if any(cutoff.fold.test_end > self.lockbox.start for cutoff in self.cutoffs):
            raise ValueError("development folds cannot overlap the lockbox")

    def require_development_timestamp(
        self,
        timestamp: datetime,
        *,
        allow_lockbox: bool = False,
    ) -> datetime:
        value = as_utc(timestamp)
        if self.lockbox.contains(value) and not allow_lockbox:
            raise LockboxAccessError("lockbox access is denied by default")
        return value

    def cutoffs_for_history(self, years: int) -> tuple[GlobalCutoff, ...]:
        return tuple(cutoff for cutoff in self.cutoffs if cutoff.history_years == years)


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    symbols: tuple[SymbolIdentity, ...]
    outer_tests: tuple[TimeRange, ...]
    validation_duration: timedelta
    lockbox: TimeRange
    history_years: tuple[int, ...] = (1, 3, 5)
    purge: timedelta = MINIMUM_PURGE
    embargo: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        symbols = tuple(sorted(self.symbols, key=lambda item: item.canonical_id))
        if not symbols or len({symbol.canonical_id for symbol in symbols}) != len(symbols):
            raise ValueError("symbols must be non-empty and unique")
        if self.history_years != tuple(sorted(set(self.history_years))):
            raise ValueError("history_years must be unique and sorted")
        if any(year not in (1, 3, 5) for year in self.history_years):
            raise ValueError("history_years may contain only 1, 3, and 5")
        if self.validation_duration <= timedelta(0):
            raise ValueError("validation_duration must be positive")
        if self.purge < MINIMUM_PURGE:
            raise ValueError("purge must be at least 12 hours")
        if self.embargo < timedelta(0):
            raise ValueError("embargo must be nonnegative")
        tests = tuple(self.outer_tests)
        if not tests:
            raise ValueError("outer_tests must be non-empty")
        if any(left.end > right.start for left, right in zip(tests, tests[1:])):
            raise ValueError("outer tests must be chronological and non-overlapping")
        if any(test.end > self.lockbox.start for test in tests):
            raise ValueError("outer tests cannot enter the lockbox")
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "outer_tests", tests)


def _subtract_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def build_global_fold_calendar(spec: WalkForwardSpec) -> GlobalFoldCalendar:
    """Build immutable common cutoffs for every history and outer test."""

    symbol_ids = tuple(symbol.canonical_id for symbol in spec.symbols)
    cutoffs = []
    gap = spec.purge + spec.embargo
    for outer_index, test in enumerate(spec.outer_tests):
        validation_end = test.start - gap
        validation_start = validation_end - spec.validation_duration
        train_end = validation_start - gap
        for years in spec.history_years:
            fold = FoldIdentity(
                fold_id=f"outer-{outer_index:03d}-{test.start:%Y%m%dT%H%MZ}-{years}y",
                train_start=_subtract_years(train_end, years),
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test.start,
                test_end=test.end,
                purge=spec.purge,
                embargo=spec.embargo,
            )
            cutoffs.append(GlobalCutoff(fold, years, symbol_ids, outer_index))
    return GlobalFoldCalendar(tuple(cutoffs), symbol_ids, spec.lockbox)


def common_partition_assignments(
    cutoff: GlobalCutoff,
    timestamps_by_symbol: dict[str, Iterable[datetime]],
) -> dict[tuple[str, datetime], Partition]:
    """Assign timestamps using only shared fold boundaries, never asset-local cutoffs."""

    if set(timestamps_by_symbol) != set(cutoff.symbol_ids):
        raise ValueError("timestamp panel must contain exactly the cutoff symbol set")
    assignments = {}
    for symbol_id in cutoff.symbol_ids:
        for timestamp in timestamps_by_symbol[symbol_id]:
            value = as_utc(timestamp)
            key = (symbol_id, value)
            if key in assignments:
                raise ValueError(f"duplicate timestamp for {symbol_id}: {value.isoformat()}")
            assignments[key] = cutoff.partition_at(symbol_id, value)
    return assignments
