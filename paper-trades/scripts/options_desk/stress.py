"""`stress` subcommand for the Options Desk MVP.

Applies deterministic spot shocks to the top screened candidate and emits
per-scenario P&L plus **Stop + Risk $** (consistent with R_REPORTING.md).
Paper research only.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import trademcp_bridge as bridge


def stress_top_candidate(
    underlying: str,
    structure: str = "csp",
    dte: str | None = None,
    *,
    spot: float = 450.0,
) -> dict[str, Any]:
    cands = bridge.screen_option_candidates(underlying, structure, dte, spot=spot, n=1)
    if not cands:
        return {}
    cand = cands[0]
    res = bridge.stress_option_candidate(cand)
    return {
        "underlying": cand.underlying,
        "structure": cand.structure,
        "occ_symbols": cand.occ_symbols,
        "strike": cand.strike,
        "expiry": cand.expiry,
        "stop": res.stop,
        "risk_usd": res.risk_usd,
        "scenarios": res.scenarios,
    }


def run_stress(args) -> int:
    out = stress_top_candidate(
        args.underlying, args.structure, args.dte, spot=args.spot
    )
    if not out:
        print("no candidate to stress", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    print(
        f"stress {out['occ_symbols'][0]}: stop={out['stop']} "
        f"risk=${out['risk_usd']} scenarios={list(out['scenarios'])}",
        file=sys.stderr,
    )
    return 0
