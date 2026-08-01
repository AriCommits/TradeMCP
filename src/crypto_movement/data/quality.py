"""Pre-contract tabular quality scanning with deterministic issue identities."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    RawBar,
    SymbolIdentity,
    VenueIdentity,
)


class QualitySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            QualitySeverity.INFO: 0,
            QualitySeverity.WARNING: 1,
            QualitySeverity.ERROR: 2,
            QualitySeverity.CRITICAL: 3,
        }[self]


class QualityIssueCode(str, Enum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_FIELD_TYPE = "invalid_field_type"
    INVALID_TIMESTAMP = "invalid_timestamp"
    IDENTITY_MISMATCH = "identity_mismatch"
    INTERVAL_MISMATCH = "interval_mismatch"
    INCONSISTENT_INTERVAL_BOUNDARY = "inconsistent_interval_boundary"
    NONPOSITIVE_PRICE = "nonpositive_price"
    HIGH_BELOW_LOW = "high_below_low"
    LOW_ABOVE_BODY = "low_above_body"
    HIGH_BELOW_BODY = "high_below_body"
    INVALID_VOLUME = "invalid_volume"
    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    NON_MONOTONIC_TIMESTAMP = "non_monotonic_timestamp"
    GAP = "gap"
    STALE_CLOSE_RUN = "stale_close_run"
    DISCONTINUITY = "discontinuity"
    EXTREME_PRINT = "extreme_print"
    CONTRACT_REJECTION = "contract_rejection"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Immutable pre-model source identity carried into every issue and report."""

    venue: str
    instrument_type: str
    canonical_asset: str
    quote_asset: str
    venue_symbol: str
    interval: str
    partition_path: str
    partition_checksum_sha256: str
    manifest_id: str
    request_id: str
    universe_snapshot_id: str

    def __post_init__(self) -> None:
        for name in (
            "venue",
            "instrument_type",
            "canonical_asset",
            "quote_asset",
            "venue_symbol",
            "interval",
            "partition_path",
            "partition_checksum_sha256",
            "manifest_id",
            "request_id",
            "universe_snapshot_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be blank")
        checksum = self.partition_checksum_sha256.lower()
        if len(checksum) != 64 or any(
            character not in "0123456789abcdef" for character in checksum
        ):
            raise ValueError("partition checksum must be a SHA-256 hex digest")
        object.__setattr__(self, "partition_checksum_sha256", checksum)

    @property
    def symbol_id(self) -> str:
        return (
            f"{self.venue}:{self.instrument_type}:"
            f"{self.canonical_asset}/{self.quote_asset}:{self.venue_symbol}"
        )

    def identity_dict(self) -> dict[str, str]:
        return {
            "venue": self.venue,
            "instrument_type": self.instrument_type,
            "canonical_asset": self.canonical_asset,
            "quote_asset": self.quote_asset,
            "venue_symbol": self.venue_symbol,
            "interval": self.interval,
            "partition_path": self.partition_path,
            "partition_checksum_sha256": self.partition_checksum_sha256,
            "manifest_id": self.manifest_id,
            "request_id": self.request_id,
            "universe_snapshot_id": self.universe_snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityIssueCode
    severity: QualitySeverity
    start: datetime | None
    end: datetime | None
    message: str
    provenance: SourceProvenance
    row_indices: tuple[int, ...]
    issue_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("quality issue message cannot be blank")
        if not self.row_indices:
            raise ValueError("quality issue must identify at least one source row")
        if self.start is not None:
            _require_utc(self.start, "issue start")
        if self.end is not None:
            _require_utc(self.end, "issue end")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("quality issue end must follow start")
        payload = {
            "schema_version": 1,
            "code": self.code.value,
            "severity": self.severity.value,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "message": self.message,
            "provenance": self.provenance.identity_dict(),
            "row_indices": list(self.row_indices),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "issue_id", hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True, slots=True)
class QualityAcknowledgment:
    """Explicit acknowledgment bound to exactly one issue identity and code."""

    issue_id: str
    issue_code: QualityIssueCode
    acknowledged_by: str
    acknowledged_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        if len(self.issue_id) != 64:
            raise ValueError("acknowledgment issue_id must be a SHA-256 digest")
        if not self.acknowledged_by.strip() or not self.rationale.strip():
            raise ValueError("acknowledgment actor and rationale cannot be blank")
        _require_utc(self.acknowledged_at, "acknowledged_at")


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    expected_interval: CandleInterval = CandleInterval.FIFTEEN_MINUTES
    stale_run_length: int = 4
    discontinuity_fraction: float = 0.50
    extreme_print_fraction: float = 0.20
    corroboration_tolerance_fraction: float = 0.03

    def __post_init__(self) -> None:
        if self.stale_run_length < 2:
            raise ValueError("stale_run_length must be at least two")
        for name in (
            "discontinuity_fraction",
            "extreme_print_fraction",
            "corroboration_tolerance_fraction",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True, slots=True)
class QualityScan:
    provenance: SourceProvenance
    policy: QualityPolicy
    scanned_row_count: int
    bars: tuple[RawBar, ...]
    issues: tuple[QualityIssue, ...]

    @property
    def issue_counts(self) -> Mapping[QualityIssueCode, int]:
        return Counter(issue.code for issue in self.issues)

    @property
    def critical_issues(self) -> tuple[QualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is QualitySeverity.CRITICAL)


class QualityGateError(RuntimeError):
    """Raised when critical issues lack matching, issue-specific acknowledgments."""


_REQUIRED_FIELDS = {
    "venue",
    "instrument_type",
    "canonical_asset",
    "quote_asset",
    "venue_symbol",
    "interval",
    "timestamp_open",
    "timestamp_close",
    "open",
    "high",
    "low",
    "close",
    "source",
    "downloaded_at",
}
_OPTIONAL_FIELDS = {
    "base_volume",
    "quote_volume",
    "trade_count",
    "taker_buy_volume",
    "open_interest",
    "funding_rate",
}


def _require_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(timezone.utc)


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return _require_utc(value, "timestamp")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp is not ISO-8601") from exc
        return _require_utc(parsed, "timestamp")
    raise TypeError("timestamp must be a datetime or ISO-8601 string")


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _issue(
    code: QualityIssueCode,
    severity: QualitySeverity,
    start: datetime | None,
    end: datetime | None,
    message: str,
    provenance: SourceProvenance,
    *indices: int,
) -> QualityIssue:
    diagnostic_end = end
    if start is not None and diagnostic_end is not None and diagnostic_end <= start:
        diagnostic_end = start + timedelta(microseconds=1)
    return QualityIssue(
        code, severity, start, diagnostic_end, message, provenance, tuple(sorted(set(indices)))
    )


def scan_rows(
    rows: Sequence[Mapping[str, Any]],
    provenance: SourceProvenance,
    *,
    policy: QualityPolicy | None = None,
    corroborating_closes: Mapping[datetime, float] | None = None,
) -> QualityScan:
    """Scan mappings before constructing RawBar so malformed records remain observable."""

    active_policy = policy or QualityPolicy()
    corroboration = corroborating_closes or {}
    issues: list[QualityIssue] = []
    accepted: list[tuple[int, RawBar]] = []
    observed_timestamps: list[tuple[int, datetime, datetime]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(
                _issue(
                    QualityIssueCode.INVALID_FIELD_TYPE,
                    QualitySeverity.CRITICAL,
                    None,
                    None,
                    "row must be a mapping",
                    provenance,
                    index,
                )
            )
            continue
        missing = sorted(_REQUIRED_FIELDS - set(row))
        if missing:
            issues.append(
                _issue(
                    QualityIssueCode.MISSING_REQUIRED_FIELD,
                    QualitySeverity.CRITICAL,
                    None,
                    None,
                    f"missing required fields: {','.join(missing)}",
                    provenance,
                    index,
                )
            )
            continue

        try:
            opened_at = _timestamp(row["timestamp_open"])
            closed_at = _timestamp(row["timestamp_close"])
            downloaded_at = _timestamp(row["downloaded_at"])
        except (TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    QualityIssueCode.INVALID_TIMESTAMP,
                    QualitySeverity.CRITICAL,
                    None,
                    None,
                    str(exc),
                    provenance,
                    index,
                )
            )
            continue
        observed_timestamps.append((index, opened_at, closed_at))

        row_issues: list[QualityIssue] = []
        expected_identity = {
            "venue": provenance.venue,
            "instrument_type": provenance.instrument_type,
            "canonical_asset": provenance.canonical_asset,
            "quote_asset": provenance.quote_asset,
            "venue_symbol": provenance.venue_symbol,
        }
        mismatches = [
            name for name, expected in expected_identity.items() if row.get(name) != expected
        ]
        if mismatches:
            row_issues.append(
                _issue(
                    QualityIssueCode.IDENTITY_MISMATCH,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    closed_at,
                    f"row identity differs from provenance: {','.join(mismatches)}",
                    provenance,
                    index,
                )
            )
        if row.get("interval") != active_policy.expected_interval.value:
            row_issues.append(
                _issue(
                    QualityIssueCode.INTERVAL_MISMATCH,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    closed_at,
                    f"expected interval {active_policy.expected_interval.value}",
                    provenance,
                    index,
                )
            )
        duration = active_policy.expected_interval.duration
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if (
            closed_at - opened_at != duration
            or (opened_at - epoch).total_seconds() % duration.total_seconds() != 0
        ):
            row_issues.append(
                _issue(
                    QualityIssueCode.INCONSISTENT_INTERVAL_BOUNDARY,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    max(closed_at, opened_at + timedelta(microseconds=1)),
                    "candle boundaries are not aligned to the declared interval",
                    provenance,
                    index,
                )
            )

        prices: dict[str, float] = {}
        try:
            prices = {name: _finite(row[name], name) for name in ("open", "high", "low", "close")}
        except (TypeError, ValueError) as exc:
            row_issues.append(
                _issue(
                    QualityIssueCode.INVALID_FIELD_TYPE,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    closed_at,
                    str(exc),
                    provenance,
                    index,
                )
            )
        if prices:
            if min(prices.values()) <= 0:
                row_issues.append(
                    _issue(
                        QualityIssueCode.NONPOSITIVE_PRICE,
                        QualitySeverity.CRITICAL,
                        opened_at,
                        closed_at,
                        "OHLC prices must all be positive",
                        provenance,
                        index,
                    )
                )
            if prices["high"] < prices["low"]:
                row_issues.append(
                    _issue(
                        QualityIssueCode.HIGH_BELOW_LOW,
                        QualitySeverity.CRITICAL,
                        opened_at,
                        closed_at,
                        "high is below low",
                        provenance,
                        index,
                    )
                )
            if prices["low"] > min(prices["open"], prices["close"]):
                row_issues.append(
                    _issue(
                        QualityIssueCode.LOW_ABOVE_BODY,
                        QualitySeverity.CRITICAL,
                        opened_at,
                        closed_at,
                        "low exceeds min(open,close)",
                        provenance,
                        index,
                    )
                )
            if prices["high"] < max(prices["open"], prices["close"]):
                row_issues.append(
                    _issue(
                        QualityIssueCode.HIGH_BELOW_BODY,
                        QualitySeverity.CRITICAL,
                        opened_at,
                        closed_at,
                        "high is below max(open,close)",
                        provenance,
                        index,
                    )
                )

        extras: dict[str, Any] = {name: row.get(name) for name in _OPTIONAL_FIELDS}
        try:
            for name in (
                "base_volume",
                "quote_volume",
                "taker_buy_volume",
                "open_interest",
                "funding_rate",
            ):
                if extras[name] is not None:
                    extras[name] = _finite(extras[name], name)
            trade_count = extras["trade_count"]
            if trade_count is not None and (
                isinstance(trade_count, bool) or not isinstance(trade_count, int)
            ):
                raise TypeError("trade_count must be an integer")
            nonnegative = (
                "base_volume",
                "quote_volume",
                "taker_buy_volume",
                "open_interest",
            )
            if any(extras[name] is not None and extras[name] < 0 for name in nonnegative):
                raise ValueError("volume, flow, and open interest must be nonnegative")
            if trade_count is not None and trade_count < 0:
                raise ValueError("trade_count must be nonnegative")
            if (
                extras["base_volume"] is not None
                and extras["taker_buy_volume"] is not None
                and extras["taker_buy_volume"] > extras["base_volume"]
            ):
                raise ValueError("taker_buy_volume cannot exceed base_volume")
        except (TypeError, ValueError) as exc:
            row_issues.append(
                _issue(
                    QualityIssueCode.INVALID_VOLUME,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    closed_at,
                    str(exc),
                    provenance,
                    index,
                )
            )

        issues.extend(row_issues)
        if any(item.severity is QualitySeverity.CRITICAL for item in row_issues):
            continue
        try:
            venue = VenueIdentity(
                provenance.venue,
                InstrumentType(provenance.instrument_type),
            )
            bar = RawBar(
                symbol=SymbolIdentity(
                    venue,
                    provenance.canonical_asset,
                    provenance.quote_asset,
                    provenance.venue_symbol,
                ),
                interval=active_policy.expected_interval,
                timestamp_open=opened_at,
                timestamp_close=closed_at,
                open=prices["open"],
                high=prices["high"],
                low=prices["low"],
                close=prices["close"],
                source=row["source"],
                downloaded_at=downloaded_at,
                base_volume=extras["base_volume"],
                quote_volume=extras["quote_volume"],
                trade_count=extras["trade_count"],
                taker_buy_volume=extras["taker_buy_volume"],
                open_interest=extras["open_interest"],
                funding_rate=extras["funding_rate"],
            )
        except (TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    QualityIssueCode.CONTRACT_REJECTION,
                    QualitySeverity.CRITICAL,
                    opened_at,
                    closed_at,
                    str(exc),
                    provenance,
                    index,
                )
            )
            continue
        accepted.append((index, bar))

    for previous, current in zip(observed_timestamps, observed_timestamps[1:], strict=False):
        previous_index, previous_open, _ = previous
        current_index, current_open, current_close = current
        if current_open == previous_open:
            issues.append(
                _issue(
                    QualityIssueCode.DUPLICATE_TIMESTAMP,
                    QualitySeverity.CRITICAL,
                    current_open,
                    current_close,
                    "duplicate candle open timestamp",
                    provenance,
                    previous_index,
                    current_index,
                )
            )
        elif current_open < previous_open:
            issues.append(
                _issue(
                    QualityIssueCode.NON_MONOTONIC_TIMESTAMP,
                    QualitySeverity.CRITICAL,
                    current_open,
                    current_close,
                    "source rows are not monotonic by timestamp_open",
                    provenance,
                    current_index,
                )
            )

    unique_by_open: dict[datetime, tuple[int, RawBar]] = {}
    for index, bar in accepted:
        unique_by_open.setdefault(bar.timestamp_open, (index, bar))
    ordered = tuple(unique_by_open[key] for key in sorted(unique_by_open))
    for (left_index, left), (right_index, right) in zip(ordered, ordered[1:], strict=False):
        if right.timestamp_open > left.timestamp_close:
            issues.append(
                _issue(
                    QualityIssueCode.GAP,
                    QualitySeverity.ERROR,
                    left.timestamp_close,
                    right.timestamp_open,
                    "missing candles; no forward fill is permitted",
                    provenance,
                    left_index,
                    right_index,
                )
            )
        change = abs(right.close / left.close - 1.0)
        if change >= active_policy.discontinuity_fraction:
            issues.append(
                _issue(
                    QualityIssueCode.DISCONTINUITY,
                    QualitySeverity.ERROR,
                    right.timestamp_open,
                    right.timestamp_close,
                    f"adjacent close change {change:.8f} exceeds discontinuity threshold",
                    provenance,
                    left_index,
                    right_index,
                )
            )
        if change >= active_policy.extreme_print_fraction:
            reference = corroboration.get(right.timestamp_close)
            corroborated = (
                reference is not None
                and reference > 0
                and abs(right.close / reference - 1.0)
                <= active_policy.corroboration_tolerance_fraction
            )
            issues.append(
                _issue(
                    QualityIssueCode.EXTREME_PRINT,
                    QualitySeverity.WARNING if corroborated else QualitySeverity.ERROR,
                    right.timestamp_open,
                    right.timestamp_close,
                    "extreme print corroborated by independent close"
                    if corroborated
                    else "extreme print lacks independent corroboration",
                    provenance,
                    right_index,
                )
            )

    if ordered:
        run_start = 0
        for position in range(1, len(ordered) + 1):
            ended = position == len(ordered)
            changed = not ended and ordered[position][1].close != ordered[run_start][1].close
            if ended or changed:
                run_length = position - run_start
                if run_length >= active_policy.stale_run_length:
                    indices = tuple(item[0] for item in ordered[run_start:position])
                    first = ordered[run_start][1]
                    last = ordered[position - 1][1]
                    issues.append(
                        _issue(
                            QualityIssueCode.STALE_CLOSE_RUN,
                            QualitySeverity.ERROR,
                            first.timestamp_open,
                            last.timestamp_close,
                            f"close remained unchanged for {run_length} candles",
                            provenance,
                            *indices,
                        )
                    )
                run_start = position

    ordered_issues = tuple(
        sorted(
            issues,
            key=lambda item: (
                item.start or datetime.min.replace(tzinfo=timezone.utc),
                item.code.value,
                item.issue_id,
            ),
        )
    )
    return QualityScan(
        provenance=provenance,
        policy=active_policy,
        scanned_row_count=len(rows),
        bars=tuple(bar for _, bar in ordered),
        issues=ordered_issues,
    )


def enforce_quality_gate(
    scan: QualityScan,
    acknowledgments: Sequence[QualityAcknowledgment] = (),
) -> None:
    """Fail unless each critical issue has a matching ID-and-code acknowledgment."""

    by_id: dict[str, QualityAcknowledgment] = {}
    for acknowledgment in acknowledgments:
        if acknowledgment.issue_id in by_id:
            raise QualityGateError(f"duplicate acknowledgment for issue {acknowledgment.issue_id}")
        by_id[acknowledgment.issue_id] = acknowledgment
    unresolved: list[QualityIssue] = []
    for issue in scan.critical_issues:
        matched_acknowledgment = by_id.get(issue.issue_id)
        if matched_acknowledgment is None or matched_acknowledgment.issue_code is not issue.code:
            unresolved.append(issue)
    if unresolved:
        raise QualityGateError(
            "unacknowledged critical quality issues: "
            + ", ".join(issue.issue_id for issue in unresolved)
        )
