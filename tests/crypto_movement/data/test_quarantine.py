from __future__ import annotations

from crypto_movement.data.providers import raw_bar_to_dict
from crypto_movement.data.quality import QualityIssueCode, QualitySeverity, scan_rows
from crypto_movement.data.quarantine import (
    QuarantineAction,
    build_quarantine_records,
    quarantine_scan,
)


def _provenance():
    from crypto_movement.data.quality import SourceProvenance

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


def _rows(count):
    from datetime import datetime, timedelta, timezone

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        opened = start + index * timedelta(minutes=15)
        closed = opened + timedelta(minutes=15)
        rows.append(
            {
                "venue": "fixture",
                "instrument_type": "spot",
                "canonical_asset": "BTC",
                "quote_asset": "USDT",
                "venue_symbol": "BTCUSDT",
                "interval": "15m",
                "timestamp_open": opened.isoformat(),
                "timestamp_close": closed.isoformat(),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "source": "fixture",
                "downloaded_at": (closed + timedelta(hours=1)).isoformat(),
                "base_volume": 10.0,
                "quote_volume": 1000.0,
                "trade_count": 10,
                "taker_buy_volume": 5.0,
                "open_interest": None,
                "funding_rate": None,
            }
        )
    return rows


def test_duplicate_interval_is_quarantined_without_mutating_raw_rows() -> None:
    rows = _rows(2)
    rows = [rows[0], dict(rows[0]), rows[1]]
    snapshot = [dict(row) for row in rows]
    scan = scan_rows(rows, _provenance())
    result = quarantine_scan(scan)
    duplicate = next(
        record
        for record in result.records
        if record.issue_code == QualityIssueCode.DUPLICATE_TIMESTAMP.value
    )
    assert duplicate.action is QuarantineAction.EXCLUDE_INTERVAL
    assert duplicate.quarantine_id == build_quarantine_records(scan.issues)[0].quarantine_id
    assert scan.bars[0] in result.excluded_bars
    assert rows == snapshot
    assert raw_bar_to_dict(scan.bars[-1]) == rows[-1]


def test_malformed_row_creates_block_only_record() -> None:
    row = _rows(1)[0]
    del row["timestamp_open"]
    scan = scan_rows([row], _provenance())
    records = build_quarantine_records(scan.issues)
    assert len(records) == 1
    assert records[0].action is QuarantineAction.BLOCK_ONLY
    assert not quarantine_scan(scan).approved_bars


def test_stale_close_runs_fail_and_are_quarantined_by_default() -> None:
    rows = _rows(4)
    for row in rows:
        row.update(open=100.0, high=100.0, low=100.0, close=100.0)
    scan = scan_rows(rows, _provenance())
    result = quarantine_scan(scan)
    stale_issue = next(
        issue for issue in scan.issues if issue.code is QualityIssueCode.STALE_CLOSE_RUN
    )
    assert stale_issue.severity is QualitySeverity.ERROR
    assert not result.approved_bars
    assert result.excluded_bars == scan.bars
    assert [record.issue_id for record in result.records] == [stale_issue.issue_id]
