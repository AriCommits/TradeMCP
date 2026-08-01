from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from crypto_movement.contracts import (
    ABLATION_SEQUENCE,
    PRIMARY_SEQUENCE,
    CandleInterval,
    InstrumentType,
    RawBar,
    ResampledBar,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.datasets.cache import (
    CachedWindowDataset,
    WindowCacheIntegrityError,
    build_window_index_snapshot,
    read_window_index_cache,
    write_window_index_cache,
)
from crypto_movement.datasets.windows import (
    ApprovedBarPanel,
    LazyBarWindowDataset,
    OverlapHandling,
    WindowExclusionReason,
    WindowSpec,
)
from crypto_movement.splits.walk_forward import TimeRange
from crypto_movement.time import UTC


def make_panel(
    interval: CandleInterval,
    count: int,
    *,
    assets: tuple[str, ...] = ("BTC", "ETH"),
    omit: set[tuple[str, int]] | None = None,
) -> ApprovedBarPanel:
    omit = omit or set()
    venue = VenueIdentity("fixture", InstrumentType.SPOT)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for asset in assets:
        symbol = SymbolIdentity(venue, asset, "USD", f"{asset}-USD")
        for index in range(count):
            if (asset, index) in omit:
                continue
            timestamp_open = start + interval.duration * index
            timestamp_close = timestamp_open + interval.duration
            bars.append(
                RawBar(
                    symbol,
                    interval,
                    timestamp_open,
                    timestamp_close,
                    100.0,
                    101.0,
                    99.0,
                    100.0,
                    "approved-fixture",
                    timestamp_close,
                )
            )
    return ApprovedBarPanel("quality-report-v1", tuple(reversed(bars)), ("raw:fixture-v1",))


def test_lazy_15_minute_windows_are_exact_and_causal() -> None:
    dataset = LazyBarWindowDataset(make_panel(CandleInterval.FIFTEEN_MINUTES, 160))
    assert dataset.spec.sequence == PRIMARY_SEQUENCE
    assert dataset.loaded_window_count == 0
    assert len(dataset) == 10
    assert [entry.anchor_timestamp for entry in dataset.entries[:2]] == [
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
    ]
    assert [entry.symbol.canonical_asset for entry in dataset.entries[:2]] == ["BTC", "ETH"]

    window = dataset[0]
    assert dataset.loaded_window_count == 1
    assert len(window.bars) == 96
    assert window.entry.sequence_start == datetime(2026, 1, 1, tzinfo=UTC)
    assert window.entry.sequence_end == window.anchor.anchor_timestamp
    assert window.entry.label_end == window.anchor.anchor_timestamp + timedelta(hours=12)
    assert all(bar.timestamp_close <= window.anchor.anchor_timestamp for bar in window.bars)


def test_lazy_30_minute_ablation_uses_exactly_48_steps() -> None:
    spec = WindowSpec(sequence=ABLATION_SEQUENCE)
    dataset = LazyBarWindowDataset(
        make_panel(CandleInterval.THIRTY_MINUTES, 80, assets=("BTC",)),
        spec=spec,
    )
    assert len(dataset) == 5
    assert len(dataset[0].bars) == 48
    assert dataset[0].entry.label_end - dataset[0].entry.anchor_timestamp == timedelta(hours=12)


def test_gapped_history_and_incomplete_future_are_excluded_with_reasons() -> None:
    panel = make_panel(
        CandleInterval.FIFTEEN_MINUTES,
        160,
        assets=("BTC",),
        omit={("BTC", 40)},
    )
    dataset = LazyBarWindowDataset(panel)
    reasons = {exclusion.reason for exclusion in dataset.exclusions}
    assert WindowExclusionReason.MISSING_SEQUENCE_BAR in reasons
    assert WindowExclusionReason.MISSING_LABEL_BAR in reasons
    assert all(entry.label_end > entry.anchor_timestamp for entry in dataset.entries)


def test_missing_scheduled_anchor_bar_is_excluded_explicitly() -> None:
    dataset = LazyBarWindowDataset(
        make_panel(
            CandleInterval.FIFTEEN_MINUTES,
            160,
            assets=("BTC",),
            omit={("BTC", 95)},
        )
    )
    missing_anchor = datetime(2026, 1, 2, tzinfo=UTC)
    assert all(entry.anchor_timestamp != missing_anchor for entry in dataset.entries)
    assert any(
        exclusion.anchor_timestamp == missing_anchor
        and exclusion.reason is WindowExclusionReason.MISSING_ANCHOR_BAR
        for exclusion in dataset.exclusions
    )


def test_subhour_stride_requires_recorded_overlap_handling() -> None:
    with pytest.raises(ValueError, match="recorded overlap handling"):
        WindowSpec(anchor_stride=timedelta(minutes=15))
    spec = WindowSpec(
        anchor_stride=timedelta(minutes=15),
        overlap_handling=OverlapHandling.CONCURRENCY_WEIGHTS,
    )
    dataset = LazyBarWindowDataset(
        make_panel(CandleInterval.FIFTEEN_MINUTES, 146, assets=("BTC",)),
        spec=spec,
    )
    assert len(dataset) == 3
    assert all(
        right.anchor_timestamp - left.anchor_timestamp == timedelta(minutes=15)
        for left, right in zip(dataset.entries, dataset.entries[1:])
    )


def test_label_window_entering_lockbox_is_denied() -> None:
    lockbox = TimeRange(
        datetime(2026, 1, 2, 14, 0, tzinfo=UTC),
        datetime(2026, 1, 3, tzinfo=UTC),
    )
    dataset = LazyBarWindowDataset(
        make_panel(CandleInterval.FIFTEEN_MINUTES, 160, assets=("BTC",)),
        lockbox=lockbox,
    )
    assert dataset.entries
    assert any(
        exclusion.reason is WindowExclusionReason.LOCKBOX_DENIED for exclusion in dataset.exclusions
    )
    assert all(entry.label_end <= lockbox.start for entry in dataset.entries)


def test_cached_and_lazy_windows_are_equivalent_and_identity_verified() -> None:
    lazy = LazyBarWindowDataset(make_panel(CandleInterval.FIFTEEN_MINUTES, 160, assets=("BTC",)))
    snapshot = build_window_index_snapshot(lazy)
    path = Path("tests/crypto_movement/datasets/.s0-window-index-test.json")
    try:
        write_window_index_cache(path, snapshot)
        loaded = read_window_index_cache(path, lazy)
        cached = CachedWindowDataset(lazy, loaded)
        assert cached.cached_window_count == 0
        assert cached[0] == lazy[0]
        assert cached.cached_window_count == 1
        assert cached[0] is cached[0]
        assert cached.identity == snapshot.cache_id

        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["window_ids"][0] = "tampered"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(WindowCacheIntegrityError, match="identity"):
            read_window_index_cache(path, lazy)
    finally:
        path.unlink(missing_ok=True)


def test_panel_identity_covers_predictor_fields_and_explicit_lineage() -> None:
    panel = make_panel(CandleInterval.FIFTEEN_MINUTES, 160, assets=("BTC",))
    original = panel.bars[0]
    variants = (
        replace(original, base_volume=1.0),
        replace(original, quote_volume=100.0),
        replace(original, trade_count=1),
        replace(original, taker_buy_volume=1.0),
        replace(original, open_interest=10.0),
        replace(original, funding_rate=-0.0001),
        replace(original, source="changed-source"),
        replace(original, downloaded_at=original.downloaded_at + timedelta(seconds=1)),
    )
    for changed in variants:
        changed_bars = (changed, *panel.bars[1:])
        changed_panel = ApprovedBarPanel(panel.approval_id, changed_bars, panel.lineage_ids)
        assert changed_panel.identity != panel.identity

    opened = datetime(2026, 1, 1, tzinfo=UTC)
    resampled = ResampledBar(
        symbol=original.symbol,
        interval=CandleInterval.THIRTY_MINUTES,
        source_interval=CandleInterval.FIFTEEN_MINUTES,
        timestamp_open=opened,
        timestamp_close=opened + timedelta(minutes=30),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        constituent_count=2,
        generated_at=opened + timedelta(minutes=30),
    )
    lineage_a = ApprovedBarPanel("quality-v1", (resampled,), ("partition:a", "partition:b"))
    lineage_b = ApprovedBarPanel("quality-v1", (resampled,), ("partition:a", "partition:c"))
    assert lineage_a.identity != lineage_b.identity
    assert lineage_a.lineage_ids == ("partition:a", "partition:b")
