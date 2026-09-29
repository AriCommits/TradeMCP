"""`screen` subcommand for the Options Desk MVP.

Returns >=1 liquid candidate (mid + width note) for an underlying / structure /
dte via the TradeMCP bridge. Paper research only.
"""

from __future__ import annotations

from typing import Any

from . import trademcp_bridge as bridge


def run_screen(
    underlying: str,
    structure: str = "csp",
    dte: str | None = None,
    *,
    spot: float = 450.0,
    n: int = 3,
) -> list[dict[str, Any]]:
    """Screen and return candidate dicts (mid + width note included)."""
    cands = bridge.screen_option_candidates(underlying, structure, dte, spot=spot, n=n)
    rows: list[dict[str, Any]] = []
    for c in cands:
        rows.append(
            {
                "underlying": c.underlying,
                "structure": c.structure,
                "occ_symbols": c.occ_symbols,
                "strike": c.strike,
                "expiry": c.expiry,
                "dte": c.dte,
                "mid": c.mid,
                "width": c.width,
                "credit": c.credit,
                "liquidity_note": c.liquidity_note,
            }
        )
    return rows
