from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from crypto_movement.contracts import (
    CandleInterval,
    InstrumentType,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.providers import (
    DataRequest,
    DeterministicFixtureProvider,
    raw_bar_to_dict,
)
from crypto_movement.data.quality import (
    QualityAcknowledgment,
    QualityGateError,
    QualityIssueCode,
    QualityPolicy,
    QualitySeverity,
    SourceProvenance,
    enforce_quality_gate,
    scan_rows,
)


def _provenance() -> SourceProvenance:
    return SourceProvenance(
        venue="fixture",
        instrument_type="spot",
        canonical_asset="BTC",
        quote_asset="USDT",
        venue_symbol="BTCUSDT",
        interval="15m",
        partition_path="venue=fixture/part.parquet",
        partition_checksum_sha256="a" * 64,
        manifest_id="manifest-1",
        request_id="request-1",
        universe_snapshot_id="universe-1",
    )


def _rows(count: int = 6):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    symbol = SymbolIdentity(
        VenueIdentity("fixture", InstrumentType.SPOT),
        "BTC",
        "USDT",
        "BTCUSDT",
    )
    request = DataRequest(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        start,
        start + count * timedelta(minutes=15),
        100,
    )
    return [raw_bar_to_dict(bar) for bar in DeterministicFixtureProvider().fetch_page(request).bars]


def _codes(scan):
    return {issue.code for issue in scan.issues}


def test_malformed_rows_become_issues_before_raw_bar_construction() -> None:
    cases = []

    missing = _rows(1)[0]
    del missing["open"]
    cases.append((missing, QualityIssueCode.MISSING_REQUIRED_FIELD))

    nonpositive = _rows(1)[0]
    nonpositive["low"] = 0.0
    cases.append((nonpositive, QualityIssueCode.NONPOSITIVE_PRICE))

    crossed = _rows(1)[0]
    crossed["high"] = crossed["low"] - 1.0
    cases.append((crossed, QualityIssueCode.HIGH_BELOW_LOW))

    negative_volume = _rows(1)[0]
    negative_volume["base_volume"] = -1.0
    cases.append((negative_volume, QualityIssueCode.INVALID_VOLUME))

    misaligned = _rows(1)[0]
    opened = datetime.fromisoformat(misaligned["timestamp_open"]) + timedelta(minutes=1)
    misaligned["timestamp_open"] = opened.isoformat()
    cases.append((misaligned, QualityIssueCode.INCONSISTENT_INTERVAL_BOUNDARY))

    for row, expected in cases:
        scan = scan_rows([row], _provenance())
        assert expected in _codes(scan)
        assert not scan.bars
        assert all(len(issue.issue_id) == 64 for issue in scan.issues)


def test_duplicates_and_nonmonotonic_rows_are_reported_then_normalized() -> None:
    rows = _rows(3)
    duplicate_scan = scan_rows([rows[0], dict(rows[0]), rows[2]], _provenance())
    assert QualityIssueCode.DUPLICATE_TIMESTAMP in _codes(duplicate_scan)
    assert [bar.timestamp_open for bar in duplicate_scan.bars] == sorted(
        {bar.timestamp_open for bar in duplicate_scan.bars}
    )

    reversed_scan = scan_rows([rows[1], rows[0]], _provenance())
    assert QualityIssueCode.NON_MONOTONIC_TIMESTAMP in _codes(reversed_scan)
    assert [bar.timestamp_open for bar in reversed_scan.bars] == sorted(
        bar.timestamp_open for bar in reversed_scan.bars
    )


def test_gap_stale_discontinuity_and_corroborated_extreme_are_explicit() -> None:
    rows = _rows(6)
    gap_scan = scan_rows([rows[0], rows[2]], _provenance())
    assert QualityIssueCode.GAP in _codes(gap_scan)

    stale_rows = _rows(4)
    for row in stale_rows:
        row.update(open=100.0, high=100.0, low=100.0, close=100.0)
    stale_scan = scan_rows(stale_rows, _provenance(), policy=QualityPolicy(stale_run_length=4))
    assert QualityIssueCode.STALE_CLOSE_RUN in _codes(stale_scan)

    extreme_rows = _rows(2)
    extreme_rows[0].update(open=100.0, high=100.0, low=100.0, close=100.0)
    extreme_rows[1].update(open=100.0, high=160.0, low=100.0, close=160.0)
    close_time = datetime.fromisoformat(extreme_rows[1]["timestamp_close"])
    extreme_scan = scan_rows(
        extreme_rows,
        _provenance(),
        corroborating_closes={close_time: 160.0},
    )
    extreme = next(
        issue for issue in extreme_scan.issues if issue.code is QualityIssueCode.EXTREME_PRINT
    )
    assert extreme.severity is QualitySeverity.WARNING
    assert QualityIssueCode.DISCONTINUITY in _codes(extreme_scan)


def test_critical_gate_requires_matching_issue_id_and_code() -> None:
    row = _rows(1)[0]
    row["base_volume"] = -1.0
    scan = scan_rows([row], _provenance())
    issue = scan.critical_issues[0]
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    wrong = QualityAcknowledgment(
        issue.issue_id,
        QualityIssueCode.NONPOSITIVE_PRICE,
        "reviewer",
        now,
        "wrong issue code on purpose",
    )
    with pytest.raises(QualityGateError):
        enforce_quality_gate(scan, [wrong])
    matching = QualityAcknowledgment(
        issue.issue_id,
        issue.code,
        "reviewer",
        now,
        "source record reviewed and excluded",
    )
    enforce_quality_gate(scan, [matching])


def test_invalid_duplicate_bounds_are_normalized_for_diagnostics() -> None:
    valid = _rows(1)[0]
    invalid = dict(valid)
    invalid["timestamp_close"] = invalid["timestamp_open"]

    scan = scan_rows([valid, invalid], _provenance())

    assert QualityIssueCode.INCONSISTENT_INTERVAL_BOUNDARY in _codes(scan)
    duplicate = next(
        issue for issue in scan.issues if issue.code is QualityIssueCode.DUPLICATE_TIMESTAMP
    )
    assert duplicate.start == datetime.fromisoformat(invalid["timestamp_open"])
    assert duplicate.end == duplicate.start + timedelta(microseconds=1)
    assert scan.bars == (scan.bars[0],)
