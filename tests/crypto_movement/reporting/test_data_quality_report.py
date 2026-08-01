from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from crypto_movement.data.quality import QualityAcknowledgment, scan_rows
from crypto_movement.data.quarantine import quarantine_scan
from crypto_movement.reporting.data_quality import (
    write_data_quality_bundle,
    write_data_quality_report,
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


def _rows(count, asset="BTC"):
    from datetime import timedelta

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        opened = start + index * timedelta(minutes=15)
        closed = opened + timedelta(minutes=15)
        rows.append(
            {
                "venue": "fixture",
                "instrument_type": "spot",
                "canonical_asset": asset,
                "quote_asset": "USDT",
                "venue_symbol": f"{asset}USDT",
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


pq = pytest.importorskip("pyarrow.parquet")


def test_reports_are_deterministic_and_contain_full_provenance(tmp_path) -> None:
    rows = _rows(2)
    scan = scan_rows([rows[0], dict(rows[0]), rows[1]], _provenance())
    issue = scan.critical_issues[0]
    acknowledgment = QualityAcknowledgment(
        issue_id=issue.issue_id,
        issue_code=issue.code,
        acknowledged_by="reviewer",
        acknowledged_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        rationale="duplicate source candle quarantined",
    )
    quarantine = quarantine_scan(scan)
    first = write_data_quality_report(
        scan,
        quarantine,
        tmp_path,
        acknowledgments=[acknowledgment],
    )
    first_bytes = (
        first.quality_report_path.read_bytes(),
        first.exclusion_log_path.read_bytes(),
        first.markdown_summary_path.read_bytes(),
    )
    second = write_data_quality_report(
        scan,
        quarantine,
        tmp_path,
        acknowledgments=[acknowledgment],
    )
    second_bytes = (
        second.quality_report_path.read_bytes(),
        second.exclusion_log_path.read_bytes(),
        second.markdown_summary_path.read_bytes(),
    )
    assert first.report_id == second.report_id
    assert first_bytes == second_bytes
    assert first.quality_report_checksum_sha256 == second.quality_report_checksum_sha256

    issue_rows = pq.read_table(first.quality_report_path).to_pylist()
    exclusion_rows = pq.read_table(first.exclusion_log_path).to_pylist()
    assert issue_rows[0]["schema_version"] == 1
    assert issue_rows[0]["acknowledged"]
    assert issue_rows[0]["partition_checksum_sha256"] == "a" * 64
    assert issue_rows[0]["manifest_id"] == "manifest-1"
    assert issue_rows[0]["request_id"] == "request-1"
    assert exclusion_rows[0]["quarantine_id"] == quarantine.records[0].quarantine_id
    summary = first.markdown_summary_path.read_text(encoding="utf-8")
    assert "Pilot gate: READY" in summary
    assert "Raw candles were not mutated or forward-filled" in summary


def test_empty_report_retains_stable_parquet_schemas(tmp_path) -> None:
    scan = scan_rows(_rows(2), _provenance())
    quarantine = quarantine_scan(scan)
    artifacts = write_data_quality_report(scan, quarantine, tmp_path)
    quality = pq.read_table(artifacts.quality_report_path)
    exclusions = pq.read_table(artifacts.exclusion_log_path)
    assert quality.num_rows == 0
    assert exclusions.num_rows == 0
    assert "partition_checksum_sha256" in quality.schema.names
    assert "quarantine_id" in exclusions.schema.names


def test_bundle_aggregates_five_assets_deterministically_without_collisions(tmp_path) -> None:
    assets = (
        ("BTC", "a"),
        ("ETH", "b"),
        ("SOL", "c"),
        ("BNB", "d"),
        ("XRP", "e"),
    )
    scans = []
    for asset, checksum_character in assets:
        provenance = replace(
            _provenance(),
            canonical_asset=asset,
            venue_symbol=f"{asset}USDT",
            partition_path=f"venue=fixture/asset={asset}/part.parquet",
            partition_checksum_sha256=checksum_character * 64,
            manifest_id=f"manifest-{asset.lower()}",
            request_id=f"request-{asset.lower()}",
        )
        rows = _rows(2, asset)
        scans.append(
            scan_rows(
                [rows[0], dict(rows[0]), rows[1]],
                provenance,
            )
        )
    quarantines = [quarantine_scan(scan) for scan in scans]

    first = write_data_quality_bundle(scans, quarantines, tmp_path / "first")
    second = write_data_quality_bundle(
        list(reversed(scans)),
        list(reversed(quarantines)),
        tmp_path / "second",
    )

    assert first.report_id == second.report_id
    assert first.quality_report_path.read_bytes() == second.quality_report_path.read_bytes()
    assert first.exclusion_log_path.read_bytes() == second.exclusion_log_path.read_bytes()
    assert first.markdown_summary_path.read_bytes() == second.markdown_summary_path.read_bytes()

    issue_rows = pq.read_table(first.quality_report_path).to_pylist()
    exclusion_rows = pq.read_table(first.exclusion_log_path).to_pylist()
    expected_assets = {asset for asset, _ in assets}
    expected_checksums = {character * 64 for _, character in assets}
    assert {row["canonical_asset"] for row in issue_rows} == expected_assets
    assert {row["partition_checksum_sha256"] for row in issue_rows} == expected_checksums
    assert {row["canonical_asset"] for row in exclusion_rows} == expected_assets
    summary = first.markdown_summary_path.read_text(encoding="utf-8")
    assert "Source partitions: 5" in summary
    assert all(f"asset={asset}/part.parquet" in summary for asset in expected_assets)
