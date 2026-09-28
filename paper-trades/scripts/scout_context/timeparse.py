"""Central-Time timestamp parsing for Scout wake-context.

Stdlib only, and deliberately tolerant of a missing IANA tz database (common on
minimal / uv-managed Windows Pythons). Parses ``"YYYY-MM-DD HH:MM:SS CDT|CT"``
into a normalized ``YYYY-MM-DD-HHMM`` key plus a UTC anchor ``datetime``.

Offset handling:
  * ``CDT`` -> fixed UTC-5   (explicit daylight)
  * ``CST`` -> fixed UTC-6   (explicit standard)
  * ``CT``  -> resolved via America/Chicago when the tz database is available,
               otherwise assumed daylight (UTC-5) which matches the trading
               calendar for most active sessions. The resolution never raises.

Using the explicit abbreviation directly avoids a hard ``tzdata`` dependency so
the CLI runs on a bare box with no installs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_UTC = timezone.utc

# Fixed offsets for explicit Central abbreviations.
_CDT = timezone(timedelta(hours=-5))  # Central Daylight Time
_CST = timezone(timedelta(hours=-6))  # Central Standard Time

# "2026-09-28 15:00:00 CDT" / "... CST" / "... CT"
_TS_RE = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+"
    r"(CDT|CST|CT)\s*$"
)


class TimeParseError(ValueError):
    """Raised when a --ts-ct string cannot be parsed."""


def _central_tz_for_bare_ct(naive: datetime) -> timezone:
    """Best-effort tz for a bare ``CT`` suffix.

    Prefers the IANA zone when available; degrades to CDT if the tz database is
    missing. Never raises.
    """
    try:
        from zoneinfo import ZoneInfo  # local import: optional dependency path

        zone = ZoneInfo("America/Chicago")
        # Ask the zone for the actual offset at this wall-clock time.
        aware = naive.replace(tzinfo=zone)
        off = aware.utcoffset()
        if off is not None:
            return timezone(off)
    except Exception:  # noqa: BLE001 - any failure means "no tz db"; degrade.
        pass
    return _CDT


def parse_ts_ct(text: str) -> tuple[str, datetime]:
    """Parse a Central-Time timestamp string.

    Returns ``(key, utc_dt)`` where ``key`` is ``"YYYY-MM-DD-HHMM"`` and
    ``utc_dt`` is timezone-aware UTC. Raises :class:`TimeParseError` on
    malformed input.
    """
    if not isinstance(text, str):
        raise TimeParseError(f"expected str, got {type(text).__name__}")

    m = _TS_RE.match(text)
    if not m:
        raise TimeParseError(
            f"unrecognized --ts-ct value: {text!r} "
            '(expected "YYYY-MM-DD HH:MM:SS CDT|CST|CT")'
        )

    year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
    abbr = m.group(7)

    naive = datetime(year, month, day, hour, minute, second)
    if abbr == "CDT":
        tz = _CDT
    elif abbr == "CST":
        tz = _CST
    else:  # bare "CT"
        tz = _central_tz_for_bare_ct(naive)

    utc_dt = naive.replace(tzinfo=tz).astimezone(_UTC)
    key = f"{year:04d}-{month:02d}-{day:02d}-{hour:02d}{minute:02d}"
    return key, utc_dt


def key_from_utc(utc_dt: datetime, *, assume_daylight: bool = True) -> str:
    """Derive a ``YYYY-MM-DD-HHMM`` key from a UTC datetime, in Central time.

    Degrades gracefully when the tz database is absent by assuming CDT (or CST
    when ``assume_daylight`` is False).
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=_UTC)
    try:
        from zoneinfo import ZoneInfo

        central = utc_dt.astimezone(ZoneInfo("America/Chicago"))
    except Exception:  # noqa: BLE001
        central = utc_dt.astimezone(_CDT if assume_daylight else _CST)
    return f"{central:%Y-%m-%d-%H%M}"
