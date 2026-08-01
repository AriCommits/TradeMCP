"""UTC and interval primitives for the cryptocurrency research pipeline.

This module deliberately depends only on the Python standard library.  Keeping
time validation here prevents provider and model libraries from quietly
introducing different candle-boundary conventions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def as_utc(value: datetime, *, field_name: str = "timestamp") -> datetime:
    """Validate an aware, zero-offset timestamp and normalize it to ``UTC``.

    A zero-offset aware timestamp is accepted even when its ``tzinfo`` object is
    not ``datetime.timezone.utc``.  A naive timestamp is never assumed to be UTC.
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if offset != timedelta(0):
        raise ValueError(f"{field_name} must be UTC, got offset {offset}")
    return value.astimezone(UTC)


def require_positive_duration(value: timedelta, *, field_name: str = "duration") -> timedelta:
    """Return ``value`` after asserting that it is a positive duration."""

    if not isinstance(value, timedelta):
        raise TypeError(f"{field_name} must be a timedelta")
    if value <= timedelta(0):
        raise ValueError(f"{field_name} must be positive")
    return value


def _total_microseconds(value: timedelta) -> int:
    return ((value.days * 86_400) + value.seconds) * 1_000_000 + value.microseconds


def is_interval_aligned(timestamp: datetime, interval: timedelta) -> bool:
    """Return whether ``timestamp`` lies on an interval boundary since epoch."""

    normalized = as_utc(timestamp)
    duration = require_positive_duration(interval, field_name="interval")
    elapsed = _total_microseconds(normalized - UNIX_EPOCH)
    return elapsed % _total_microseconds(duration) == 0


def require_interval_aligned(
    timestamp: datetime,
    interval: timedelta,
    *,
    field_name: str = "timestamp",
) -> datetime:
    """Normalize an interval-aligned UTC timestamp or fail fast."""

    normalized = as_utc(timestamp, field_name=field_name)
    if not is_interval_aligned(normalized, interval):
        raise ValueError(f"{field_name} is not aligned to {interval}")
    return normalized


def validate_candle_bounds(
    timestamp_open: datetime,
    timestamp_close: datetime,
    interval: timedelta,
) -> tuple[datetime, datetime]:
    """Validate canonical half-open candle bounds ``[open, close)``."""

    duration = require_positive_duration(interval, field_name="interval")
    opened = require_interval_aligned(timestamp_open, duration, field_name="timestamp_open")
    closed = require_interval_aligned(timestamp_close, duration, field_name="timestamp_close")
    if closed - opened != duration:
        raise ValueError("timestamp_close must equal timestamp_open + interval")
    return opened, closed


def require_completed_candle(
    timestamp_close: datetime,
    observed_at: datetime,
) -> tuple[datetime, datetime]:
    """Validate that a candle was closed when it became observable.

    A candle is complete exactly at its close boundary, so equality is valid.
    """

    closed = as_utc(timestamp_close, field_name="timestamp_close")
    observed = as_utc(observed_at, field_name="observed_at")
    if observed < closed:
        raise ValueError("an incomplete candle cannot be used at observed_at")
    return closed, observed


def require_feature_available(
    feature_timestamp: datetime,
    anchor_timestamp: datetime,
) -> tuple[datetime, datetime]:
    """Enforce ``feature_timestamp <= anchor_timestamp``."""

    feature = as_utc(feature_timestamp, field_name="feature_timestamp")
    anchor = as_utc(anchor_timestamp, field_name="anchor_timestamp")
    if feature > anchor:
        raise ValueError("feature_timestamp must be at or before anchor_timestamp")
    return feature, anchor


def require_label_after_anchor(
    label_timestamp: datetime,
    anchor_timestamp: datetime,
) -> tuple[datetime, datetime]:
    """Enforce ``anchor_timestamp < label_timestamp``."""

    label = as_utc(label_timestamp, field_name="label_timestamp")
    anchor = as_utc(anchor_timestamp, field_name="anchor_timestamp")
    if label <= anchor:
        raise ValueError("label_timestamp must be after anchor_timestamp")
    return label, anchor


def completed_anchor_from_open(timestamp_open: datetime, interval: timedelta) -> datetime:
    """Return the close timestamp that may serve as an anchor for a candle."""

    opened = require_interval_aligned(timestamp_open, interval, field_name="timestamp_open")
    return opened + require_positive_duration(interval, field_name="interval")
