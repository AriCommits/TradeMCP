"""Squeeze overlay assembly for Scout wake-context (BTC/ETH/SOL only).

Stdlib only. Restricts to the BTC/ETH/SOL tag set and renders a documented
"no squeeze data" state when the input is absent — never fabricates status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .loaders import SQUEEZE_SYMBOLS, SqueezeData


@dataclass
class SqueezeOverlay:
    tags: dict[str, Any] = field(default_factory=dict)
    present: bool = False
    quality_flags: list[str] = field(default_factory=list)


def build(squeeze: SqueezeData) -> SqueezeOverlay:
    overlay = SqueezeOverlay()
    if not squeeze.present or not squeeze.tags:
        overlay.quality_flags.append("no_squeeze_data")
        overlay.quality_flags.extend(squeeze.quality_flags)
        return overlay

    # keep only the allowed symbols, deterministic ordering
    filtered = {
        sym: squeeze.tags[sym]
        for sym in SQUEEZE_SYMBOLS
        if sym in squeeze.tags
    }
    if not filtered:
        overlay.quality_flags.append("no_allowed_tags")
        return overlay

    overlay.tags = filtered
    overlay.present = True
    return overlay
