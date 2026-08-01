from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("pyarrow")

from crypto_movement.contracts import (
    CandleInterval,
    CompletedAnchor,
    FirstBarrierOutcome,
    FoldIdentity,
    InstrumentType,
    LabelHorizon,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.data.bars import (
    ConstituentProvenance,
    build_30_minute_bars,
    build_30_minute_panel,
)
from crypto_movement.data.collector import MarketDataCollector, PageCache
from crypto_movement.data.manifest import build_manifest, verify_manifest
from crypto_movement.data.providers import (
    DataRequest,
    DeterministicFixtureProvider,
    raw_bar_to_dict,
)
from crypto_movement.data.quality import (
    QualityGateError,
    QualityIssueCode,
    SourceProvenance,
    enforce_quality_gate,
    scan_rows,
)
from crypto_movement.data.quarantine import quarantine_scan
from crypto_movement.data.storage import ParquetBarStore, sha256_file
from crypto_movement.datasets.batching import SequentialBlockBatcher
from crypto_movement.datasets.windows import ApprovedBarPanel, LazyBarWindowDataset
from crypto_movement.labels.barriers import IncompleteLabelWindowError, generate_barrier_label
from crypto_movement.reporting.data_quality import (
    write_data_quality_bundle,
    write_data_quality_report,
)
from crypto_movement.splits.manifests import (
    ManifestProvenance,
    SplitEndpointInventory,
    build_fold_manifest,
    read_batch_manifest_parquet,
    read_fold_manifest_parquet,
    write_batch_manifest_parquet,
    write_fold_manifest_parquet,
)
from crypto_movement.splits.purging import AssignedExample, ExampleInterval, assign_example_to_fold
from crypto_movement.splits.walk_forward import (
    GlobalCutoff,
    GlobalFoldCalendar,
    Partition,
    TimeRange,
)
from crypto_movement.time import UTC


def test_d0_q0_l0_s0_fixture_pipeline_is_causal_and_reproducible(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
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
        start + timedelta(hours=40),
        37,
    )
    provider = DeterministicFixtureProvider()
    collection = MarketDataCollector(provider, PageCache(tmp_path / "cache")).collect(request)
    raw_root = tmp_path / "raw"
    store = ParquetBarStore(raw_root)
    partitions = store.write_bars(collection.bars)
    manifest = build_manifest(
        collection,
        provider_name=provider.name,
        universe_snapshot_id="fixture-five-asset-schema-v1",
        partition_root=raw_root,
        partitions=partitions,
    )
    verify_manifest(manifest, raw_root)
    original_checksum = sha256_file(partitions[0].path)
    restored = store.read_bars(partitions[0].path)

    source = SourceProvenance(
        venue=symbol.venue.venue,
        instrument_type=symbol.venue.instrument_type.value,
        canonical_asset=symbol.canonical_asset,
        quote_asset=symbol.quote_asset,
        venue_symbol=symbol.venue_symbol,
        interval=CandleInterval.FIFTEEN_MINUTES.value,
        partition_path=partitions[0].path.relative_to(raw_root).as_posix(),
        partition_checksum_sha256=partitions[0].checksum_sha256,
        manifest_id=manifest.manifest_id,
        request_id=request.request_id,
        universe_snapshot_id=manifest.universe_snapshot_id,
    )
    scan = scan_rows(tuple(raw_bar_to_dict(bar) for bar in restored), source)
    enforce_quality_gate(scan)
    quarantine = quarantine_scan(scan)
    assert quarantine.approved_bars == restored
    assert not quarantine.excluded_bars
    quality_artifacts = write_data_quality_report(
        scan,
        quarantine,
        tmp_path / "quality",
    )

    constituent_source = ConstituentProvenance(
        source.partition_path,
        source.partition_checksum_sha256,
        source.manifest_id,
    )
    provenance_by_bar = {
        (bar.symbol.canonical_id, bar.timestamp_open): constituent_source
        for bar in quarantine.approved_bars
    }
    thirty_minute = build_30_minute_bars(quarantine.approved_bars, provenance_by_bar)
    assert len(thirty_minute) == len(restored) // 2

    anchor_bar = restored[95]
    anchor = CompletedAnchor(
        symbol,
        CandleInterval.FIFTEEN_MINUTES,
        anchor_bar.timestamp_close,
        anchor_bar.timestamp_close,
    )
    label = generate_barrier_label(
        anchor=anchor,
        anchor_close=anchor_bar.close,
        future_bars=quarantine.approved_bars[96:144],
        horizon=LabelHorizon.TWELVE_HOURS,
    )
    assert label.outcome is FirstBarrierOutcome.NEITHER
    assert label.label_timestamp == anchor.anchor_timestamp + timedelta(hours=12)

    panel = ApprovedBarPanel(
        manifest.manifest_id,
        quarantine.approved_bars,
        (f"raw:{partitions[0].semantic_id}",),
    )
    dataset = LazyBarWindowDataset(panel)
    assert dataset.loaded_window_count == 0
    assert dataset.entries

    fold = FoldIdentity(
        fold_id="fixture-sprint3",
        train_start=start - timedelta(days=1),
        train_end=start + timedelta(days=2),
        validation_start=start + timedelta(days=2, hours=12),
        validation_end=start + timedelta(days=3),
        test_start=start + timedelta(days=3, hours=12),
        test_end=start + timedelta(days=4),
    )
    cutoff = GlobalCutoff(fold, 1, (symbol.canonical_id,), 0)
    partition_by_window = {}
    for entry in dataset.entries:
        assigned = assign_example_to_fold(
            cutoff,
            ExampleInterval(
                entry.symbol,
                entry.sequence_start,
                entry.feature_end,
                entry.anchor_timestamp,
                entry.label_end,
            ),
        )
        assert isinstance(assigned, AssignedExample)
        assert assigned.partition is Partition.TRAIN
        partition_by_window[entry.window_id] = assigned.partition

    batcher = SequentialBlockBatcher(
        dataset,
        partition_by_window=partition_by_window,
        partition=Partition.TRAIN,
        anchors_per_batch=2,
        fold_id=fold.fold_id,
        manifest_provenance=ManifestProvenance(
            panel_checksum=panel.identity,
            quarantine_checksum=quality_artifacts.exclusion_log_checksum_sha256,
            config_checksum="fixture-config-v1",
            universe_snapshot_id=manifest.universe_snapshot_id,
        ),
    )
    flattened = tuple(window for batch in batcher for window in batch.windows)
    assert tuple(window.entry.window_id for window in flattened) == tuple(
        entry.window_id for entry in dataset.entries
    )
    assert all(
        window.bars[-1].timestamp_close <= window.anchor.anchor_timestamp
        for window in flattened
    )
    assert all(window.entry.label_end > window.entry.anchor_timestamp for window in flattened)
    assert sha256_file(partitions[0].path) == original_checksum
    calendar = GlobalFoldCalendar(
        (cutoff,),
        cutoff.symbol_ids,
        TimeRange(start + timedelta(days=5), start + timedelta(days=6)),
    )
    inventory = {
        fold.fold_id: (
            SplitEndpointInventory(
                Partition.TRAIN,
                len(dataset),
                min(entry.sequence_start for entry in dataset.entries),
                max(entry.feature_end for entry in dataset.entries),
                max(entry.label_end for entry in dataset.entries),
            ),
            SplitEndpointInventory(Partition.VALIDATION, 0, None, None, None),
            SplitEndpointInventory(Partition.TEST, 0, None, None, None),
        )
    }
    fold_manifest = build_fold_manifest(
        calendar,
        provenance=batcher.manifest.provenance,
        inventory_by_fold=inventory,
    )
    fold_write = write_fold_manifest_parquet(
        tmp_path / "manifests/folds.parquet",
        fold_manifest,
    )
    batch_write = write_batch_manifest_parquet(
        tmp_path / "manifests/batches.parquet",
        batcher.manifest,
    )
    assert read_fold_manifest_parquet(
        fold_write.path,
        expected_checksum=fold_write.checksum_sha256,
    ) == fold_manifest
    assert read_batch_manifest_parquet(
        batch_write.path,
        expected_checksum=batch_write.checksum_sha256,
    ) == batcher.manifest


def test_five_asset_quality_gate_excludes_corrupt_label_and_window_sources(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    assets = ("BTC", "ETH", "ETC", "AVAX", "SOL")
    store = ParquetBarStore(tmp_path / "five-asset-raw")
    scans = []
    quarantines = []
    approved_by_asset = {}
    originals_by_asset = {}
    partition_checksums = {}
    lineage_ids = []
    source_by_asset = {}

    for asset in assets:
        symbol = SymbolIdentity(
            VenueIdentity("fixture", InstrumentType.SPOT),
            asset,
            "USDT",
            f"{asset}USDT",
        )
        request = DataRequest(
            symbol,
            CandleInterval.FIFTEEN_MINUTES,
            start,
            start + timedelta(hours=40),
            43,
        )
        provider = DeterministicFixtureProvider()
        collection = MarketDataCollector(
            provider,
            PageCache(tmp_path / "five-asset-cache"),
        ).collect(request)
        partition = store.write_bars(collection.bars)[0]
        manifest = build_manifest(
            collection,
            provider_name=provider.name,
            universe_snapshot_id="fixture-five-asset-schema-v1",
            partition_root=tmp_path / "five-asset-raw",
            partitions=(partition,),
        )
        verify_manifest(manifest, tmp_path / "five-asset-raw")
        partition_checksums[partition.path] = partition.checksum_sha256
        lineage_ids.append(f"raw:{partition.semantic_id}")
        originals_by_asset[asset] = collection.bars
        rows = [raw_bar_to_dict(bar) for bar in collection.bars]

        if asset == "ETC":
            rows.pop(120)
        elif asset == "ETH":
            rows.insert(121, dict(rows[120]))
        elif asset == "AVAX":
            rows[120]["high"] = float(rows[120]["low"]) * 0.9
        elif asset == "SOL":
            shifted = float(rows[120]["close"]) * 1.35
            rows[120].update(
                open=shifted,
                high=shifted * 1.001,
                low=shifted * 0.999,
                close=shifted,
            )

        source = SourceProvenance(
            venue=symbol.venue.venue,
            instrument_type=symbol.venue.instrument_type.value,
            canonical_asset=asset,
            quote_asset=symbol.quote_asset,
            venue_symbol=symbol.venue_symbol,
            interval=CandleInterval.FIFTEEN_MINUTES.value,
            partition_path=partition.path.relative_to(tmp_path / "five-asset-raw").as_posix(),
            partition_checksum_sha256=partition.checksum_sha256,
            manifest_id=manifest.manifest_id,
            request_id=request.request_id,
            universe_snapshot_id=manifest.universe_snapshot_id,
        )
        source_by_asset[asset] = source
        scan = scan_rows(tuple(rows), source)
        quarantine = quarantine_scan(scan)
        scans.append(scan)
        quarantines.append(quarantine)
        approved_by_asset[asset] = quarantine.approved_bars

    bundle = write_data_quality_bundle(
        tuple(scans),
        tuple(quarantines),
        tmp_path / "five-asset-quality",
    )
    issues_by_asset = {
        scan.provenance.canonical_asset: {issue.code for issue in scan.issues}
        for scan in scans
    }
    assert QualityIssueCode.DUPLICATE_TIMESTAMP in issues_by_asset["ETH"]
    assert QualityIssueCode.GAP in issues_by_asset["ETC"]
    assert QualityIssueCode.HIGH_BELOW_LOW in issues_by_asset["AVAX"]
    assert QualityIssueCode.EXTREME_PRINT in issues_by_asset["SOL"]
    scans_by_asset = {scan.provenance.canonical_asset: scan for scan in scans}
    for critical_asset in ("ETH", "AVAX"):
        with pytest.raises(QualityGateError):
            enforce_quality_gate(scans_by_asset[critical_asset])
    assert (
        "Pilot gate: BLOCKED"
        in bundle.markdown_summary_path.read_text(encoding="utf-8")
    )

    assert all(sha256_file(path) == checksum for path, checksum in partition_checksums.items())

    etc_source = source_by_asset["ETC"]
    etc_constituent = ConstituentProvenance(
        etc_source.partition_path,
        etc_source.partition_checksum_sha256,
        etc_source.manifest_id,
    )
    etc_provenance = {
        (bar.symbol.canonical_id, bar.timestamp_open): etc_constituent
        for bar in approved_by_asset["ETC"]
    }
    etc_30m = build_30_minute_panel(
        approved_by_asset["ETC"],
        etc_provenance,
    )
    assert len(etc_30m.bars) == 79
    assert len(etc_30m.exclusions) == 1
    assert any(
        item.bar.timestamp_open >= etc_30m.exclusions[0].target_close
        for item in etc_30m.bars
    )

    btc_anchor_bar = originals_by_asset["BTC"][95]
    btc_anchor = CompletedAnchor(
        btc_anchor_bar.symbol,
        CandleInterval.FIFTEEN_MINUTES,
        btc_anchor_bar.timestamp_close,
        btc_anchor_bar.timestamp_close,
    )
    btc_future = tuple(
        bar
        for bar in approved_by_asset["BTC"]
        if btc_anchor.anchor_timestamp <= bar.timestamp_open
        and bar.timestamp_close <= btc_anchor.anchor_timestamp + timedelta(hours=12)
    )
    clean_label = generate_barrier_label(
        anchor=btc_anchor,
        anchor_close=btc_anchor_bar.close,
        future_bars=btc_future,
        horizon=LabelHorizon.TWELVE_HOURS,
    )
    assert clean_label.label_timestamp == btc_anchor.anchor_timestamp + timedelta(hours=12)

    etc_anchor_bar = originals_by_asset["ETC"][95]
    etc_anchor = CompletedAnchor(
        etc_anchor_bar.symbol,
        CandleInterval.FIFTEEN_MINUTES,
        etc_anchor_bar.timestamp_close,
        etc_anchor_bar.timestamp_close,
    )
    etc_future = tuple(
        bar
        for bar in approved_by_asset["ETC"]
        if etc_anchor.anchor_timestamp <= bar.timestamp_open
        and bar.timestamp_close <= etc_anchor.anchor_timestamp + timedelta(hours=12)
    )
    with pytest.raises(IncompleteLabelWindowError):
        generate_barrier_label(
            anchor=etc_anchor,
            anchor_close=etc_anchor_bar.close,
            future_bars=etc_future,
            horizon=LabelHorizon.TWELVE_HOURS,
        )

    approved_panel = ApprovedBarPanel(
        bundle.report_id,
        tuple(
            bar
            for asset in assets
            for bar in approved_by_asset[asset]
        ),
        tuple(lineage_ids),
    )
    dataset = LazyBarWindowDataset(approved_panel)
    eligible_assets = {entry.symbol.canonical_asset for entry in dataset.entries}
    assert "BTC" in eligible_assets
    assert eligible_assets.isdisjoint({"ETH", "ETC", "AVAX", "SOL"})
    assert any(
        exclusion.reason.value == "missing_label_bar"
        for exclusion in dataset.exclusions
        if exclusion.symbol.canonical_asset != "BTC"
    )
