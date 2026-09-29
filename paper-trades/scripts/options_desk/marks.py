"""Mark resolution for the Options Desk MVP (fail-closed, never invents).

Stdlib only. Resolution chain (first hit wins):
  1. TradingCLI / Yahoo mark file if supplied (paper research export);
  2. ``options/greeks-latest.json`` under the input root;
  3. CBOE delayed export if supplied.

If no source yields a mark, returns an explicit :class:`Mark` with
``present=False`` and a reason — the caller must treat that as "no mark", never
substitute a synthetic value. Synthetic ``greeks_viz`` demo marks are **never**
accepted as trading input.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Mark:
    """A resolved mark for an option (or an explicit absence)."""

    occ_symbol: str
    mid: float | None = None
    bid: float | None = None
    ask: float | None = None
    source: str | None = None
    present: bool = False
    quality_flags: list[str] = field(default_factory=list)

    @property
    def width(self) -> float | None:
        if self.bid is not None and self.ask is not None:
            return round(self.ask - self.bid, 6)
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _mark_from_row(occ: str, row: dict[str, Any], source: str) -> Mark | None:
    bid = row.get("bid")
    ask = row.get("ask")
    mid = row.get("mid")
    try:
        bid = float(bid) if bid is not None else None
        ask = float(ask) if ask is not None else None
        mid = float(mid) if mid is not None else None
    except (TypeError, ValueError):
        return None
    if mid is None and bid is not None and ask is not None:
        mid = round((bid + ask) / 2.0, 6)
    if mid is None:
        return None
    # reject synthetic/demo marks explicitly
    if str(row.get("source", "")).lower() in ("greeks_viz", "demo", "synthetic"):
        return None
    return Mark(
        occ_symbol=occ, mid=mid, bid=bid, ask=ask, source=source, present=True
    )


def resolve_mark(
    occ_symbol: str,
    *,
    root: Path | None = None,
    tradingcli_file: str | Path | None = None,
    cboe_file: str | Path | None = None,
) -> Mark:
    """Resolve a single option's mark via the documented chain. Fail closed."""
    sources: list[tuple[str, Path | None]] = [
        ("tradingcli", Path(tradingcli_file) if tradingcli_file else None),
        (
            "greeks-latest",
            (root / "options" / "greeks-latest.json") if root else None,
        ),
        ("cboe-delayed", Path(cboe_file) if cboe_file else None),
    ]
    tried: list[str] = []
    for source, path in sources:
        if path is None:
            continue
        tried.append(source)
        data = _read_json(path)
        if not data:
            continue
        quotes = data.get("quotes") or data.get("marks") or data
        row = quotes.get(occ_symbol) if isinstance(quotes, dict) else None
        if isinstance(row, dict):
            mark = _mark_from_row(occ_symbol, row, source)
            if mark is not None:
                return mark
    return Mark(
        occ_symbol=occ_symbol,
        present=False,
        quality_flags=[f"no_mark:tried={','.join(tried) or 'none'}"],
    )
