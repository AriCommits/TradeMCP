"""Deterministic option quote quality classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from trading.options.contracts import require_utc
from trading.options.quotes import QuoteQualityFlag

from .records import RawOptionQuoteRecord


class QuoteQualityIssue(str, Enum):
    STALE = "stale"
    CROSSED = "crossed"
    LOCKED = "locked"
    ZERO_BID = "zero_bid"
    MISSING_BID = "missing_bid"
    MISSING_ASK = "missing_ask"
    MISSING_SIZE = "missing_size"


@dataclass(frozen=True)
class QuoteQualityPolicy:
    max_age: timedelta = timedelta(minutes=5)
    reject_stale: bool = True
    reject_crossed: bool = True
    reject_locked: bool = False
    reject_zero_bid: bool = False

    def __post_init__(self) -> None:
        if self.max_age < timedelta(0):
            raise ValueError("max_age cannot be negative")


@dataclass(frozen=True)
class QuoteQualityAssessment:
    issues: tuple[QuoteQualityIssue, ...]
    canonical_flags: tuple[QuoteQualityFlag, ...]
    eligible_for_snapshot: bool


def assess_quote(
    record: RawOptionQuoteRecord,
    snapshot_at_utc: datetime,
    policy: QuoteQualityPolicy,
) -> QuoteQualityAssessment:
    require_utc(snapshot_at_utc, "snapshot_at_utc")
    if record.as_of_utc > snapshot_at_utc:
        raise ValueError("cannot assess a future quote for a point-in-time snapshot")
    issues: list[QuoteQualityIssue] = []
    flags: list[QuoteQualityFlag] = []
    if snapshot_at_utc - record.as_of_utc > policy.max_age:
        issues.append(QuoteQualityIssue.STALE)
        flags.append(QuoteQualityFlag.STALE)
    if record.bid is None:
        issues.append(QuoteQualityIssue.MISSING_BID)
    if record.ask is None:
        issues.append(QuoteQualityIssue.MISSING_ASK)
    if record.bid_size is None or record.ask_size is None:
        issues.append(QuoteQualityIssue.MISSING_SIZE)
        flags.append(QuoteQualityFlag.MISSING_SIZE)
    if record.bid is not None and record.ask is not None:
        if record.bid > record.ask:
            issues.append(QuoteQualityIssue.CROSSED)
            flags.append(QuoteQualityFlag.CROSSED)
        elif record.bid == record.ask:
            issues.append(QuoteQualityIssue.LOCKED)
            flags.append(QuoteQualityFlag.LOCKED)
        if record.bid == 0:
            issues.append(QuoteQualityIssue.ZERO_BID)
            flags.append(QuoteQualityFlag.ZERO_BID)
    structurally_complete = record.bid is not None and record.ask is not None
    policy_rejection = (
        (policy.reject_stale and QuoteQualityIssue.STALE in issues)
        or (policy.reject_crossed and QuoteQualityIssue.CROSSED in issues)
        or (policy.reject_locked and QuoteQualityIssue.LOCKED in issues)
        or (policy.reject_zero_bid and QuoteQualityIssue.ZERO_BID in issues)
    )
    return QuoteQualityAssessment(
        tuple(issues),
        tuple(flags),
        structurally_complete and not policy_rejection,
    )
