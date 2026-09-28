"""Ring summary assembly for Scout wake-context.

Stdlib only. Distills the ring (from ring.json or a snapshot's ring block) into
a compact, deterministic summary for the embed. Tolerant of missing/partial
ring data (renders an explicit "no ring data" state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .loaders import RingData


@dataclass
class RingSummary:
    count: int = 0
    members: list[dict[str, Any]] = field(default_factory=list)
    top_by_abs_z: dict[str, Any] | None = None
    present: bool = False
    quality_flags: list[str] = field(default_factory=list)


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def summarize(ring: RingData) -> RingSummary:
    summary = RingSummary()
    if not ring.present or not ring.entries:
        summary.quality_flags.append("no_ring_data")
        summary.quality_flags.extend(ring.quality_flags)
        return summary

    members: list[dict[str, Any]] = []
    for entry in ring.entries:
        sym = entry.get("symbol") or entry.get("sym") or entry.get("name")
        if not sym:
            summary.quality_flags.append("entry_without_symbol")
            continue
        z = _as_float(entry.get("z"))
        residual = _as_float(entry.get("residual"))
        members.append(
            {
                "symbol": str(sym).upper(),
                "z": z,
                "residual": residual,
            }
        )

    # deterministic ordering: by |z| desc, then symbol asc
    members.sort(key=lambda m: (-(abs(m["z"]) if m["z"] is not None else 0.0), m["symbol"]))
    summary.members = members
    summary.count = len(members)
    summary.present = summary.count > 0
    if summary.present:
        summary.top_by_abs_z = members[0]
    else:
        summary.quality_flags.append("no_valid_members")
    return summary
