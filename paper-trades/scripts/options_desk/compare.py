"""`compare` subcommand for the Options Desk MVP.

Ranks >=2 structures for an underlying by credit quality (credit / Risk $) via
the TradeMCP bridge. Prints a ranked JSON table. Paper research only.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import trademcp_bridge as bridge


def compare_structures(
    underlying: str, structures: list[str], *, spot: float = 450.0
) -> list[dict[str, Any]]:
    comps = bridge.compare_option_strategies(underlying, structures, spot=spot)
    rows: list[dict[str, Any]] = []
    for c in comps:
        rows.append(
            {
                "rank": c.rank,
                "structure": c.candidate.structure,
                "occ_symbols": c.candidate.occ_symbols,
                "strike": c.candidate.strike,
                "expiry": c.candidate.expiry,
                "credit": c.candidate.credit,
                "risk_usd": c.risk_usd,
                "credit_quality": c.credit_quality,
            }
        )
    return rows


def run_compare(args) -> int:
    structures = [s.strip() for s in str(args.structures).split(",") if s.strip()]
    if len(structures) < 2:
        print("compare needs >=2 structures", file=sys.stderr)
        return 1
    rows = compare_structures(args.underlying, structures, spot=args.spot)
    print(json.dumps(rows, indent=2))
    print(
        "compared "
        + ", ".join(f"#{r['rank']} {r['structure']}(q={r['credit_quality']})" for r in rows),
        file=sys.stderr,
    )
    return 0
