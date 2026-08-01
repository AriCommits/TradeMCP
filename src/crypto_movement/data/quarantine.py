"""Explicit deterministic quarantine records; raw candles are never mutated."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from crypto_movement.contracts import RawBar
from crypto_movement.data.quality import (
    QualityIssue,
    QualityScan,
    QualitySeverity,
    SourceProvenance,
)


class QuarantineAction(str, Enum):
    EXCLUDE_INTERVAL = "exclude_interval"
    BLOCK_ONLY = "block_only"


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    issue_id: str
    issue_code: str
    severity: QualitySeverity
    action: QuarantineAction
    start: datetime | None
    end: datetime | None
    reason: str
    provenance: SourceProvenance
    quarantine_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("quarantine reason cannot be blank")
        if self.action is QuarantineAction.EXCLUDE_INTERVAL and (
            self.start is None or self.end is None
        ):
            raise ValueError("interval exclusion requires start and end")
        payload = {
            "schema_version": 1,
            "issue_id": self.issue_id,
            "issue_code": self.issue_code,
            "severity": self.severity.value,
            "action": self.action.value,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "reason": self.reason,
            "provenance": self.provenance.identity_dict(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "quarantine_id", hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True, slots=True)
class QuarantineResult:
    approved_bars: tuple[RawBar, ...]
    excluded_bars: tuple[RawBar, ...]
    records: tuple[QuarantineRecord, ...]

    def __post_init__(self) -> None:
        approved_ids = {
            (bar.symbol.canonical_id, bar.interval.value, bar.timestamp_open)
            for bar in self.approved_bars
        }
        excluded_ids = {
            (bar.symbol.canonical_id, bar.interval.value, bar.timestamp_open)
            for bar in self.excluded_bars
        }
        if approved_ids & excluded_ids:
            raise ValueError("a candle cannot be both approved and excluded")


def build_quarantine_records(
    issues: tuple[QualityIssue, ...],
    *,
    minimum_severity: QualitySeverity = QualitySeverity.ERROR,
) -> tuple[QuarantineRecord, ...]:
    """Create one traceable record per issue at or above the configured severity."""

    records: list[QuarantineRecord] = []
    for issue in issues:
        if issue.severity.rank < minimum_severity.rank:
            continue
        action = (
            QuarantineAction.EXCLUDE_INTERVAL
            if issue.start is not None and issue.end is not None
            else QuarantineAction.BLOCK_ONLY
        )
        records.append(
            QuarantineRecord(
                issue_id=issue.issue_id,
                issue_code=issue.code.value,
                severity=issue.severity,
                action=action,
                start=issue.start,
                end=issue.end,
                reason=issue.message,
                provenance=issue.provenance,
            )
        )
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.start or datetime.min.replace(tzinfo=__import__("datetime").timezone.utc),
                item.issue_code,
                item.quarantine_id,
            ),
        )
    )


def apply_quarantine(
    bars: tuple[RawBar, ...],
    records: tuple[QuarantineRecord, ...],
) -> QuarantineResult:
    """Exclude overlapping derived rows without repairing or forward-filling raw candles."""

    approved: list[RawBar] = []
    excluded: list[RawBar] = []
    for bar in bars:
        should_exclude = False
        for record in records:
            if record.action is not QuarantineAction.EXCLUDE_INTERVAL:
                continue
            start = record.start
            end = record.end
            if start is None or end is None:
                continue
            if bar.timestamp_open < end and bar.timestamp_close > start:
                should_exclude = True
                break
        (excluded if should_exclude else approved).append(bar)
    return QuarantineResult(
        approved_bars=tuple(approved),
        excluded_bars=tuple(excluded),
        records=records,
    )


def quarantine_scan(scan: QualityScan) -> QuarantineResult:
    records = build_quarantine_records(scan.issues)
    return apply_quarantine(scan.bars, records)
