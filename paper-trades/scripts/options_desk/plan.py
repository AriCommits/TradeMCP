"""`plan` subcommand for the Options Desk MVP.

Builds a trade plan from the top screened candidate via the TradeMCP bridge and
emits JSON + human Markdown under ``--out-dir``. Every plan carries Stop +
Risk $; CSP plans include collateral. Paper research only — never an order.
"""

from __future__ import annotations

import sys

from . import emit
from . import trademcp_bridge as bridge


def run_plan(args) -> int:
    cands = bridge.screen_option_candidates(
        args.underlying, args.structure, args.dte, spot=args.spot, n=1
    )
    if not cands:
        print("no candidate to plan", file=sys.stderr)
        return 1

    draft = bridge.build_option_trade_plan(cands[0])
    themes = [
        f"{args.structure.upper()} on {args.underlying}",
        f"DTE {args.dte}",
        "manage per STOP_POLICY",
    ]
    paths = emit.write_plan(args.out_dir, draft, themes=themes)
    print(f"wrote {paths['json']}")
    print(f"wrote {paths['md']}")
    print(
        f"plan {args.underlying} {args.structure}: stop={draft.stop} "
        f"risk=${draft.risk_usd}",
        file=sys.stderr,
    )
    return 0
