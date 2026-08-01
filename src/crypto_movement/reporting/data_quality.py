"""Deterministic data-quality Parquet, exclusion, and Markdown reports."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_movement.data.quality import (
    QualityAcknowledgment,
    QualityIssue,
    QualityScan,
)
from crypto_movement.data.quarantine import QuarantineRecord, QuarantineResult
from crypto_movement.data.storage import sha256_file

QUALITY_REPORT_SCHEMA_VERSION = 1
EXCLUSION_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class DataQualityReportArtifacts:
    report_id: str
    quality_report_path: Path
    exclusion_log_path: Path
    markdown_summary_path: Path
    quality_report_checksum_sha256: str
    exclusion_log_checksum_sha256: str
    markdown_checksum_sha256: str


def _arrow_modules() -> tuple[Any, Any]:
    try:
        pa = importlib.import_module("pyarrow")
        pq = importlib.import_module("pyarrow.parquet")
    except ModuleNotFoundError as exc:
        raise RuntimeError("data-quality reporting requires pyarrow") from exc
    return pa, pq


def _quality_schema(pa: Any) -> Any:
    return pa.schema(
        [
            ("schema_version", pa.int16()),
            ("report_id", pa.string()),
            ("issue_id", pa.string()),
            ("issue_code", pa.string()),
            ("severity", pa.string()),
            ("affected_start", pa.timestamp("us", tz="UTC")),
            ("affected_end", pa.timestamp("us", tz="UTC")),
            ("message", pa.string()),
            ("row_indices_json", pa.string()),
            ("acknowledged", pa.bool_()),
            ("acknowledged_by", pa.string()),
            ("acknowledged_at", pa.timestamp("us", tz="UTC")),
            ("acknowledgment_rationale", pa.string()),
            ("venue", pa.string()),
            ("instrument_type", pa.string()),
            ("canonical_asset", pa.string()),
            ("quote_asset", pa.string()),
            ("venue_symbol", pa.string()),
            ("interval", pa.string()),
            ("partition_path", pa.string()),
            ("partition_checksum_sha256", pa.string()),
            ("manifest_id", pa.string()),
            ("request_id", pa.string()),
            ("universe_snapshot_id", pa.string()),
        ]
    )


def _exclusion_schema(pa: Any) -> Any:
    return pa.schema(
        [
            ("schema_version", pa.int16()),
            ("report_id", pa.string()),
            ("quarantine_id", pa.string()),
            ("issue_id", pa.string()),
            ("issue_code", pa.string()),
            ("severity", pa.string()),
            ("action", pa.string()),
            ("affected_start", pa.timestamp("us", tz="UTC")),
            ("affected_end", pa.timestamp("us", tz="UTC")),
            ("reason", pa.string()),
            ("venue", pa.string()),
            ("instrument_type", pa.string()),
            ("canonical_asset", pa.string()),
            ("quote_asset", pa.string()),
            ("venue_symbol", pa.string()),
            ("interval", pa.string()),
            ("partition_path", pa.string()),
            ("partition_checksum_sha256", pa.string()),
            ("manifest_id", pa.string()),
            ("request_id", pa.string()),
            ("universe_snapshot_id", pa.string()),
        ]
    )


def _acknowledgment_map(
    issues: Sequence[QualityIssue],
    acknowledgments: Sequence[QualityAcknowledgment],
) -> dict[str, QualityAcknowledgment]:
    issue_by_id = {issue.issue_id: issue for issue in issues}
    matched: dict[str, QualityAcknowledgment] = {}
    for acknowledgment in acknowledgments:
        issue = issue_by_id.get(acknowledgment.issue_id)
        if issue is None or acknowledgment.issue_code is not issue.code:
            continue
        if acknowledgment.issue_id in matched:
            raise ValueError("duplicate issue-specific acknowledgment")
        matched[acknowledgment.issue_id] = acknowledgment
    return matched


def _report_identity(
    scan: QualityScan,
    records: Sequence[QuarantineRecord],
    matched: dict[str, QualityAcknowledgment],
) -> str:
    payload = {
        "schema_version": QUALITY_REPORT_SCHEMA_VERSION,
        "provenance": scan.provenance.identity_dict(),
        "scanned_row_count": scan.scanned_row_count,
        "issues": [issue.issue_id for issue in scan.issues],
        "quarantines": [record.quarantine_id for record in records],
        "acknowledgments": [
            {
                "issue_id": key,
                "issue_code": value.issue_code.value,
                "acknowledged_by": value.acknowledged_by,
                "acknowledged_at": value.acknowledged_at.isoformat(),
                "rationale": value.rationale,
            }
            for key, value in sorted(matched.items())
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _provenance_columns(issue_or_record: QualityIssue | QuarantineRecord) -> dict[str, str]:
    return issue_or_record.provenance.identity_dict()


def _quality_rows(
    report_id: str,
    scan: QualityScan,
    matched: dict[str, QualityAcknowledgment],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue in scan.issues:
        acknowledgment = matched.get(issue.issue_id)
        rows.append(
            {
                "schema_version": QUALITY_REPORT_SCHEMA_VERSION,
                "report_id": report_id,
                "issue_id": issue.issue_id,
                "issue_code": issue.code.value,
                "severity": issue.severity.value,
                "affected_start": issue.start,
                "affected_end": issue.end,
                "message": issue.message,
                "row_indices_json": json.dumps(list(issue.row_indices), separators=(",", ":")),
                "acknowledged": acknowledgment is not None,
                "acknowledged_by": acknowledgment.acknowledged_by if acknowledgment else None,
                "acknowledged_at": acknowledgment.acknowledged_at if acknowledgment else None,
                "acknowledgment_rationale": acknowledgment.rationale if acknowledgment else None,
                **_provenance_columns(issue),
            }
        )
    return rows


def _exclusion_rows(
    report_id: str,
    records: Sequence[QuarantineRecord],
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": EXCLUSION_REPORT_SCHEMA_VERSION,
            "report_id": report_id,
            "quarantine_id": record.quarantine_id,
            "issue_id": record.issue_id,
            "issue_code": record.issue_code,
            "severity": record.severity.value,
            "action": record.action.value,
            "affected_start": record.start,
            "affected_end": record.end,
            "reason": record.reason,
            **_provenance_columns(record),
        }
        for record in records
    ]


def _atomic_parquet(path: Path, rows: list[dict[str, Any]], schema: Any) -> None:
    pa, pq = _arrow_modules()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(
            table,
            temporary,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _markdown(
    report_id: str,
    scan: QualityScan,
    quarantine: QuarantineResult,
    matched: dict[str, QualityAcknowledgment],
) -> str:
    counts = Counter((issue.code.value, issue.severity.value) for issue in scan.issues)
    unresolved = [issue for issue in scan.critical_issues if issue.issue_id not in matched]
    provenance = scan.provenance
    lines = [
        "# Data Quality Summary",
        "",
        f"- Schema version: {QUALITY_REPORT_SCHEMA_VERSION}",
        f"- Report ID: {report_id}",
        f"- Pilot gate: {'BLOCKED' if unresolved else 'READY'}",
        f"- Scanned rows: {scan.scanned_row_count}",
        f"- Contract-valid rows: {len(scan.bars)}",
        f"- Approved rows after quarantine: {len(quarantine.approved_bars)}",
        f"- Excluded rows: {len(quarantine.excluded_bars)}",
        f"- Critical issues: {len(scan.critical_issues)}",
        f"- Unacknowledged critical issues: {len(unresolved)}",
        "",
        "## Issue counts",
        "",
        "| Issue code | Severity | Count |",
        "|---|---|---:|",
    ]
    if counts:
        for (code, severity), count in sorted(counts.items()):
            lines.append(f"| {code} | {severity} | {count} |")
    else:
        lines.append("| none | none | 0 |")
    lines.extend(
        [
            "",
            "## Source provenance",
            "",
            f"- Venue/instrument: {provenance.venue}/{provenance.instrument_type}",
            (
                f"- Symbol mapping: {provenance.canonical_asset}/"
                f"{provenance.quote_asset} -> {provenance.venue_symbol}"
            ),
            f"- Interval: {provenance.interval}",
            f"- Partition: {provenance.partition_path}",
            f"- Partition SHA-256: {provenance.partition_checksum_sha256}",
            f"- Manifest ID: {provenance.manifest_id}",
            f"- Request ID: {provenance.request_id}",
            f"- Universe snapshot ID: {provenance.universe_snapshot_id}",
            "",
            (
                "Raw candles were not mutated or forward-filled. "
                "Exclusions apply only to derived data."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_data_quality_report(
    scan: QualityScan,
    quarantine: QuarantineResult,
    output_root: str | Path,
    *,
    acknowledgments: Sequence[QualityAcknowledgment] = (),
) -> DataQualityReportArtifacts:
    """Write fixed-name deterministic report artifacts under a configurable root."""

    matched = _acknowledgment_map(scan.issues, acknowledgments)
    report_id = _report_identity(scan, quarantine.records, matched)
    root = Path(output_root).resolve()
    quality_path = root / "data_quality_report.parquet"
    exclusion_path = root / "excluded_periods.parquet"
    markdown_path = root / "data_quality_summary.md"

    pa, _ = _arrow_modules()
    _atomic_parquet(
        quality_path,
        _quality_rows(report_id, scan, matched),
        _quality_schema(pa),
    )
    _atomic_parquet(
        exclusion_path,
        _exclusion_rows(report_id, quarantine.records),
        _exclusion_schema(pa),
    )
    markdown = _markdown(report_id, scan, quarantine, matched)
    temporary = markdown_path.with_name(f".{markdown_path.name}.{os.getpid()}.tmp")
    try:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(markdown, encoding="utf-8", newline="\n")
        os.replace(temporary, markdown_path)
    finally:
        temporary.unlink(missing_ok=True)

    return DataQualityReportArtifacts(
        report_id=report_id,
        quality_report_path=quality_path,
        exclusion_log_path=exclusion_path,
        markdown_summary_path=markdown_path,
        quality_report_checksum_sha256=sha256_file(quality_path),
        exclusion_log_checksum_sha256=sha256_file(exclusion_path),
        markdown_checksum_sha256=sha256_file(markdown_path),
    )


def _source_key(scan: QualityScan) -> str:
    return json.dumps(scan.provenance.identity_dict(), sort_keys=True, separators=(",", ":"))


def _validated_bundle_pairs(
    scans: Sequence[QualityScan],
    quarantines: Sequence[QuarantineResult],
) -> tuple[tuple[QualityScan, QuarantineResult], ...]:
    if not scans:
        raise ValueError("data-quality bundle requires at least one scan")
    if len(scans) != len(quarantines):
        raise ValueError("each scan requires exactly one quarantine result")

    pairs = list(zip(scans, quarantines, strict=True))
    source_keys: set[str] = set()
    for scan, quarantine in pairs:
        source_key = _source_key(scan)
        if source_key in source_keys:
            raise ValueError("duplicate source provenance in data-quality bundle")
        source_keys.add(source_key)
        if any(record.provenance != scan.provenance for record in quarantine.records):
            raise ValueError("quarantine provenance does not match its quality scan")
        scan_bar_ids = {
            (bar.symbol.canonical_id, bar.interval.value, bar.timestamp_open) for bar in scan.bars
        }
        result_bar_ids = {
            (bar.symbol.canonical_id, bar.interval.value, bar.timestamp_open)
            for bar in (*quarantine.approved_bars, *quarantine.excluded_bars)
        }
        if result_bar_ids != scan_bar_ids:
            raise ValueError("quarantine result must partition all contract-valid scan bars")
    return tuple(sorted(pairs, key=lambda pair: _source_key(pair[0])))


def _bundle_identity(
    pairs: Sequence[tuple[QualityScan, QuarantineResult]],
    matched: dict[str, QualityAcknowledgment],
) -> str:
    payload = {
        "schema_version": QUALITY_REPORT_SCHEMA_VERSION,
        "sources": [
            {
                "provenance": scan.provenance.identity_dict(),
                "scanned_row_count": scan.scanned_row_count,
                "issues": [issue.issue_id for issue in scan.issues],
                "quarantines": [record.quarantine_id for record in quarantine.records],
                "approved_bars": [
                    (
                        bar.symbol.canonical_id,
                        bar.interval.value,
                        bar.timestamp_open.isoformat(),
                    )
                    for bar in quarantine.approved_bars
                ],
                "excluded_bars": [
                    (
                        bar.symbol.canonical_id,
                        bar.interval.value,
                        bar.timestamp_open.isoformat(),
                    )
                    for bar in quarantine.excluded_bars
                ],
            }
            for scan, quarantine in pairs
        ],
        "acknowledgments": [
            {
                "issue_id": key,
                "issue_code": value.issue_code.value,
                "acknowledged_by": value.acknowledged_by,
                "acknowledged_at": value.acknowledged_at.isoformat(),
                "rationale": value.rationale,
            }
            for key, value in sorted(matched.items())
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _bundle_markdown(
    report_id: str,
    pairs: Sequence[tuple[QualityScan, QuarantineResult]],
    matched: dict[str, QualityAcknowledgment],
) -> str:
    issues = tuple(issue for scan, _ in pairs for issue in scan.issues)
    counts = Counter((issue.code.value, issue.severity.value) for issue in issues)
    critical = tuple(issue for issue in issues if issue.severity.value == "critical")
    unresolved = tuple(issue for issue in critical if issue.issue_id not in matched)
    lines = [
        "# Data Quality Summary",
        "",
        f"- Schema version: {QUALITY_REPORT_SCHEMA_VERSION}",
        f"- Report ID: {report_id}",
        f"- Pilot gate: {'BLOCKED' if unresolved else 'READY'}",
        f"- Source partitions: {len(pairs)}",
        f"- Scanned rows: {sum(scan.scanned_row_count for scan, _ in pairs)}",
        f"- Contract-valid rows: {sum(len(scan.bars) for scan, _ in pairs)}",
        (
            "- Approved rows after quarantine: "
            f"{sum(len(result.approved_bars) for _, result in pairs)}"
        ),
        f"- Excluded rows: {sum(len(result.excluded_bars) for _, result in pairs)}",
        f"- Critical issues: {len(critical)}",
        f"- Unacknowledged critical issues: {len(unresolved)}",
        "",
        "## Issue counts",
        "",
        "| Issue code | Severity | Count |",
        "|---|---|---:|",
    ]
    if counts:
        for (code, severity), count in sorted(counts.items()):
            lines.append(f"| {code} | {severity} | {count} |")
    else:
        lines.append("| none | none | 0 |")
    lines.extend(
        [
            "",
            "## Source provenance",
            "",
            (
                "| Asset | Venue/instrument | Venue symbol | Interval | "
                "Partition | Partition SHA-256 | Manifest | Request | Universe snapshot |"
            ),
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for scan, _ in pairs:
        provenance = scan.provenance
        lines.append(
            "| "
            f"{provenance.canonical_asset}/{provenance.quote_asset} | "
            f"{provenance.venue}/{provenance.instrument_type} | "
            f"{provenance.venue_symbol} | {provenance.interval} | "
            f"{provenance.partition_path} | "
            f"{provenance.partition_checksum_sha256} | "
            f"{provenance.manifest_id} | {provenance.request_id} | "
            f"{provenance.universe_snapshot_id} |"
        )
    lines.extend(
        [
            "",
            (
                "Raw candles were not mutated or forward-filled. "
                "Exclusions apply only to derived data."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_data_quality_bundle(
    scans: Sequence[QualityScan],
    quarantines: Sequence[QuarantineResult],
    output_root: str | Path,
    *,
    acknowledgments: Sequence[QualityAcknowledgment] = (),
) -> DataQualityReportArtifacts:
    """Write one deterministic report bundle across all source partitions."""

    pairs = _validated_bundle_pairs(scans, quarantines)
    issues = tuple(issue for scan, _ in pairs for issue in scan.issues)
    matched = _acknowledgment_map(issues, acknowledgments)
    report_id = _bundle_identity(pairs, matched)

    quality_rows = [row for scan, _ in pairs for row in _quality_rows(report_id, scan, matched)]
    quality_rows.sort(
        key=lambda row: (
            row["partition_path"],
            row["issue_code"],
            row["issue_id"],
        )
    )
    exclusion_rows = [
        row for _, quarantine in pairs for row in _exclusion_rows(report_id, quarantine.records)
    ]
    exclusion_rows.sort(
        key=lambda row: (
            row["partition_path"],
            row["issue_code"],
            row["quarantine_id"],
        )
    )

    root = Path(output_root).resolve()
    quality_path = root / "data_quality_report.parquet"
    exclusion_path = root / "excluded_periods.parquet"
    markdown_path = root / "data_quality_summary.md"
    pa, _ = _arrow_modules()
    _atomic_parquet(quality_path, quality_rows, _quality_schema(pa))
    _atomic_parquet(exclusion_path, exclusion_rows, _exclusion_schema(pa))

    markdown = _bundle_markdown(report_id, pairs, matched)
    temporary = markdown_path.with_name(f".{markdown_path.name}.{os.getpid()}.tmp")
    try:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(markdown, encoding="utf-8", newline="\n")
        os.replace(temporary, markdown_path)
    finally:
        temporary.unlink(missing_ok=True)

    return DataQualityReportArtifacts(
        report_id=report_id,
        quality_report_path=quality_path,
        exclusion_log_path=exclusion_path,
        markdown_summary_path=markdown_path,
        quality_report_checksum_sha256=sha256_file(quality_path),
        exclusion_log_checksum_sha256=sha256_file(exclusion_path),
        markdown_checksum_sha256=sha256_file(markdown_path),
    )
