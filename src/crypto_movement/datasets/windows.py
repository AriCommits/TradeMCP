"""Lazy, quality-approved sequence windows ending at completed anchors."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeAlias, overload

from crypto_movement.artifacts import stable_digest
from crypto_movement.contracts import (
    PRIMARY_SEQUENCE,
    CandleInterval,
    CompletedAnchor,
    LabelHorizon,
    RawBar,
    ResampledBar,
    SequenceSpec,
    SymbolIdentity,
)
from crypto_movement.splits.walk_forward import TimeRange
from crypto_movement.time import is_interval_aligned

Bar: TypeAlias = RawBar | ResampledBar


class OverlapHandling(str, Enum):
    NONE = "none"
    CONCURRENCY_WEIGHTS = "concurrency_weights"
    PURGED_SAMPLING = "purged_sampling"


class WindowExclusionReason(str, Enum):
    STRIDE_MISALIGNED = "stride_misaligned"
    INSUFFICIENT_HISTORY = "insufficient_history"
    MISSING_SEQUENCE_BAR = "missing_sequence_bar"
    MISSING_ANCHOR_BAR = "missing_anchor_bar"
    MISSING_LABEL_BAR = "missing_label_bar"
    LOCKBOX_DENIED = "lockbox_denied"


@dataclass(frozen=True, slots=True)
class ApprovedBarPanel:
    """Bars admitted by an external quality gate, identified by its approval."""

    approval_id: str
    bars: tuple[Bar, ...]
    lineage_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.approval_id.strip():
            raise ValueError("approval_id cannot be blank")
        bars = tuple(self.bars)
        lineage_ids = tuple(sorted(set(self.lineage_ids)))
        if not lineage_ids or any(not item.strip() for item in lineage_ids):
            raise ValueError("lineage_ids must be non-empty and contain no blanks")
        if not bars:
            raise ValueError("approved panel must contain bars")
        seen = set()
        intervals = set()
        for bar in bars:
            if not isinstance(bar, (RawBar, ResampledBar)):
                raise TypeError("approved panel accepts raw or resampled bars")
            key = (bar.symbol.canonical_id, bar.interval, bar.timestamp_open)
            if key in seen:
                raise ValueError("approved panel contains duplicate bars")
            seen.add(key)
            intervals.add(bar.interval)
        if len(intervals) != 1:
            raise ValueError("approved panel must contain one candle interval")
        ordered = tuple(sorted(bars, key=lambda bar: (bar.symbol.canonical_id, bar.timestamp_open)))
        object.__setattr__(self, "bars", ordered)
        object.__setattr__(self, "lineage_ids", lineage_ids)

    @property
    def interval(self) -> CandleInterval:
        return self.bars[0].interval

    @property
    def identity(self) -> str:
        # Canonical dataclass serialization includes every OHLCV/provider field
        # and, for resampled bars, source interval/count/generation lineage.
        return stable_digest(
            {
                "approval_id": self.approval_id,
                "lineage_ids": self.lineage_ids,
                "bars": self.bars,
            }
        )


@dataclass(frozen=True, slots=True)
class WindowSpec:
    sequence: SequenceSpec = PRIMARY_SEQUENCE
    anchor_stride: timedelta = timedelta(hours=1)
    overlap_handling: OverlapHandling = OverlapHandling.NONE
    label_horizon: LabelHorizon = LabelHorizon.TWELVE_HOURS

    def __post_init__(self) -> None:
        if self.anchor_stride <= timedelta(0):
            raise ValueError("anchor_stride must be positive")
        quotient, remainder = divmod(
            int(self.anchor_stride.total_seconds()),
            int(self.sequence.interval.duration.total_seconds()),
        )
        if remainder or quotient < 1:
            raise ValueError("anchor_stride must be a whole multiple of the candle interval")
        if (
            self.anchor_stride < timedelta(hours=1)
            and self.overlap_handling is OverlapHandling.NONE
        ):
            raise ValueError("15/30-minute anchor studies require recorded overlap handling")


@dataclass(frozen=True, slots=True)
class WindowIndexEntry:
    window_id: str
    symbol: SymbolIdentity
    interval: CandleInterval
    anchor_timestamp: datetime
    sequence_start: datetime
    sequence_end: datetime
    label_end: datetime
    start_index: int
    stop_index: int

    @property
    def feature_end(self) -> datetime:
        return self.sequence_end


@dataclass(frozen=True, slots=True)
class WindowExclusion:
    symbol: SymbolIdentity
    anchor_timestamp: datetime
    reason: WindowExclusionReason


@dataclass(frozen=True, slots=True)
class BarWindow:
    entry: WindowIndexEntry
    anchor: CompletedAnchor
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if len(self.bars) != self.entry.stop_index - self.entry.start_index:
            raise ValueError("window bar count does not match its index")
        if self.bars[0].timestamp_open != self.entry.sequence_start:
            raise ValueError("window does not begin at sequence_start")
        if self.bars[-1].timestamp_close != self.entry.sequence_end:
            raise ValueError("window does not end at its completed anchor")
        if any(bar.timestamp_close > self.anchor.anchor_timestamp for bar in self.bars):
            raise ValueError("window contains a future predictor")


class LazyBarWindowDataset(Sequence[BarWindow]):
    """Index windows eagerly but materialize each bar tuple only on access."""

    def __init__(
        self,
        panel: ApprovedBarPanel,
        *,
        spec: WindowSpec = WindowSpec(),
        lockbox: TimeRange | None = None,
        allow_lockbox: bool = False,
    ) -> None:
        if panel.interval is not spec.sequence.interval:
            raise ValueError("panel interval does not match sequence specification")
        self.panel = panel
        self.spec = spec
        self.lockbox = lockbox
        self.allow_lockbox = allow_lockbox
        grouped: dict[str, list[Bar]] = defaultdict(list)
        symbols = {}
        for bar in panel.bars:
            grouped[bar.symbol.canonical_id].append(bar)
            symbols[bar.symbol.canonical_id] = bar.symbol
        self._bars_by_symbol = {
            symbol_id: tuple(sorted(bars, key=lambda bar: bar.timestamp_open))
            for symbol_id, bars in grouped.items()
        }
        entries = []
        exclusions = []
        for symbol_id in sorted(self._bars_by_symbol):
            symbol_entries, symbol_exclusions = self._index_symbol(
                symbols[symbol_id], self._bars_by_symbol[symbol_id]
            )
            entries.extend(symbol_entries)
            exclusions.extend(symbol_exclusions)
        self._entries = tuple(
            sorted(entries, key=lambda item: (item.anchor_timestamp, item.symbol.canonical_id))
        )
        self.exclusions = tuple(
            sorted(
                exclusions,
                key=lambda item: (
                    item.anchor_timestamp,
                    item.symbol.canonical_id,
                    item.reason.value,
                ),
            )
        )
        self._loaded_window_count = 0

    def _index_symbol(
        self,
        symbol: SymbolIdentity,
        bars: tuple[Bar, ...],
    ) -> tuple[list[WindowIndexEntry], list[WindowExclusion]]:
        entries = []
        exclusions = []
        sequence_steps = self.spec.sequence.steps
        future_steps = self.spec.label_horizon.steps(self.spec.sequence.interval)
        available_closes = {bar.timestamp_close for bar in bars}
        candidate_anchor = bars[0].timestamp_close
        while candidate_anchor <= bars[-1].timestamp_close and not is_interval_aligned(
            candidate_anchor, self.spec.anchor_stride
        ):
            candidate_anchor += self.spec.sequence.interval.duration
        while candidate_anchor <= bars[-1].timestamp_close:
            if candidate_anchor not in available_closes:
                exclusions.append(
                    WindowExclusion(
                        symbol, candidate_anchor, WindowExclusionReason.MISSING_ANCHOR_BAR
                    )
                )
            candidate_anchor += self.spec.anchor_stride

        for end_index, end_bar in enumerate(bars):
            anchor = end_bar.timestamp_close
            if not is_interval_aligned(anchor, self.spec.anchor_stride):
                exclusions.append(
                    WindowExclusion(symbol, anchor, WindowExclusionReason.STRIDE_MISALIGNED)
                )
                continue
            label_end = anchor + self.spec.label_horizon.duration
            if (
                self.lockbox is not None
                and not self.allow_lockbox
                and (anchor >= self.lockbox.start or label_end > self.lockbox.start)
            ):
                exclusions.append(
                    WindowExclusion(symbol, anchor, WindowExclusionReason.LOCKBOX_DENIED)
                )
                continue
            start_index = end_index - sequence_steps + 1
            if start_index < 0:
                exclusions.append(
                    WindowExclusion(symbol, anchor, WindowExclusionReason.INSUFFICIENT_HISTORY)
                )
                continue
            sequence = bars[start_index : end_index + 1]
            expected_open = anchor - self.spec.sequence.history
            valid_sequence = True
            for bar in sequence:
                if bar.timestamp_open != expected_open:
                    valid_sequence = False
                    break
                expected_open = bar.timestamp_close
            if not valid_sequence or expected_open != anchor:
                exclusions.append(
                    WindowExclusion(symbol, anchor, WindowExclusionReason.MISSING_SEQUENCE_BAR)
                )
                continue
            future = bars[end_index + 1 : end_index + 1 + future_steps]
            expected_open = anchor
            valid_future = len(future) == future_steps
            if valid_future:
                for bar in future:
                    if bar.timestamp_open != expected_open:
                        valid_future = False
                        break
                    expected_open = bar.timestamp_close
            if not valid_future or expected_open != label_end:
                exclusions.append(
                    WindowExclusion(symbol, anchor, WindowExclusionReason.MISSING_LABEL_BAR)
                )
                continue
            window_id = stable_digest(
                {
                    "panel_identity": self.panel.identity,
                    "symbol": symbol.canonical_id,
                    "interval": self.spec.sequence.interval,
                    "steps": sequence_steps,
                    "anchor": anchor,
                    "label_end": label_end,
                    "stride_seconds": int(self.spec.anchor_stride.total_seconds()),
                    "overlap_handling": self.spec.overlap_handling,
                }
            )
            entries.append(
                WindowIndexEntry(
                    window_id=window_id,
                    symbol=symbol,
                    interval=self.spec.sequence.interval,
                    anchor_timestamp=anchor,
                    sequence_start=anchor - self.spec.sequence.history,
                    sequence_end=anchor,
                    label_end=label_end,
                    start_index=start_index,
                    stop_index=end_index + 1,
                )
            )
        return entries, exclusions

    @property
    def entries(self) -> tuple[WindowIndexEntry, ...]:
        return self._entries

    @property
    def loaded_window_count(self) -> int:
        return self._loaded_window_count

    @property
    def identity(self) -> str:
        return stable_digest(
            {
                "panel_identity": self.panel.identity,
                "spec": self.spec,
                "entries": self._entries,
                "lockbox": self.lockbox,
                "allow_lockbox": self.allow_lockbox,
            }
        )

    def __len__(self) -> int:
        return len(self._entries)

    @overload
    def __getitem__(self, index: int) -> BarWindow: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[BarWindow]: ...

    def __getitem__(self, index: int | slice) -> BarWindow | Sequence[BarWindow]:
        if isinstance(index, slice):
            return tuple(self[item] for item in range(*index.indices(len(self))))
        entry = self._entries[index]
        bars = self._bars_by_symbol[entry.symbol.canonical_id][entry.start_index : entry.stop_index]
        self._loaded_window_count += 1
        return BarWindow(
            entry=entry,
            anchor=CompletedAnchor(
                entry.symbol,
                entry.interval,
                entry.anchor_timestamp,
                entry.anchor_timestamp,
            ),
            bars=bars,
        )
