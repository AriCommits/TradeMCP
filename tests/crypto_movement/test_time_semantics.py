from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from crypto_movement.time import (
    UTC,
    as_utc,
    completed_anchor_from_open,
    is_interval_aligned,
    require_completed_candle,
    require_feature_available,
    require_interval_aligned,
    require_label_after_anchor,
    validate_candle_bounds,
)


def test_naive_and_non_utc_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        as_utc(datetime(2026, 1, 1))

    chicago = timezone(timedelta(hours=-6))
    with pytest.raises(ValueError, match="must be UTC"):
        as_utc(datetime(2026, 1, 1, tzinfo=chicago))


def test_zero_offset_aware_timestamp_is_normalized() -> None:
    zero_offset = timezone(timedelta(0), name="zero")
    result = as_utc(datetime(2026, 1, 1, tzinfo=zero_offset))
    assert result.tzinfo is UTC


def test_interval_alignment_and_candle_bounds_are_exact() -> None:
    interval = timedelta(minutes=15)
    opened = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    closed = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)

    assert is_interval_aligned(opened, interval)
    assert not is_interval_aligned(opened + timedelta(microseconds=1), interval)
    assert validate_candle_bounds(opened, closed, interval) == (opened, closed)

    with pytest.raises(ValueError, match="not aligned"):
        require_interval_aligned(opened + timedelta(minutes=1), interval)
    with pytest.raises(ValueError, match=r"open \+ interval"):
        validate_candle_bounds(opened, closed + interval, interval)


def test_completed_candle_uses_close_boundary_inclusively() -> None:
    closed = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    assert require_completed_candle(closed, closed) == (closed, closed)

    with pytest.raises(ValueError, match="incomplete candle"):
        require_completed_candle(closed, closed - timedelta(microseconds=1))


def test_anchor_is_the_close_of_the_completed_half_open_candle() -> None:
    opened = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert completed_anchor_from_open(opened, timedelta(minutes=15)) == datetime(
        2026, 1, 1, 12, 15, tzinfo=UTC
    )


def test_feature_and_label_timestamp_inequality_boundaries() -> None:
    anchor = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
    assert require_feature_available(anchor, anchor) == (anchor, anchor)
    assert require_label_after_anchor(anchor + timedelta(microseconds=1), anchor) == (
        anchor + timedelta(microseconds=1),
        anchor,
    )

    with pytest.raises(ValueError, match="at or before"):
        require_feature_available(anchor + timedelta(microseconds=1), anchor)
    with pytest.raises(ValueError, match="after anchor"):
        require_label_after_anchor(anchor, anchor)
