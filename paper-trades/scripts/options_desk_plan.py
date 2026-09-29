#!/usr/bin/env python3
"""Options Desk plan CLI: screen | compare | stress | plan (paper only).

Agnostic handoff contract:
  * ``--out-dir`` is REQUIRED on every subcommand; all writes go there only.
  * ``--paper-trades-root`` (or env ``PAPER_TRADES_ROOT``) locates read inputs
    only. No live brokers; no Slack; TradeMCP logic is soft-imported or inline.

O2 implements ``screen`` and registers all four subparsers; ``compare`` /
``stress`` / ``plan`` handlers are attached by later sprints (O3/O4/O5).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from options_desk import config  # noqa: E402


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--out-dir", required=True, metavar="PATH",
        help="REQUIRED. Directory for all outputs (created if missing).",
    )
    p.add_argument(
        "--paper-trades-root", default=os.environ.get(config.ENV_ROOT),
        metavar="PATH", help="Optional root for read inputs (inputs only).",
    )
    p.add_argument("--underlying", default="SPY", help="Underlying symbol.")
    p.add_argument("--spot", type=float, default=450.0, help="Reference spot (paper).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="options_desk_plan.py",
        description="Paper-only options screen/compare/stress/plan.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_screen = sub.add_parser("screen", help="Screen liquid candidates.")
    _add_common(p_screen)
    p_screen.add_argument("--structure", default="csp", help="csp|pcs|debit|...")
    p_screen.add_argument("--dte", default="7-14", help="DTE range, e.g. 7-14.")
    p_screen.set_defaults(func=_cmd_screen)

    p_compare = sub.add_parser("compare", help="Compare/rank structures.")
    _add_common(p_compare)
    p_compare.add_argument(
        "--structures", default="csp,pcs",
        help="Comma-separated structures to compare.",
    )
    p_compare.set_defaults(func=_cmd_compare)

    p_stress = sub.add_parser("stress", help="Stress a candidate.")
    _add_common(p_stress)
    p_stress.add_argument("--structure", default="csp")
    p_stress.add_argument("--dte", default="7-14")
    p_stress.set_defaults(func=_cmd_stress)

    p_plan = sub.add_parser("plan", help="Build a trade plan (json+md).")
    _add_common(p_plan)
    p_plan.add_argument("--structure", default="csp")
    p_plan.add_argument("--dte", default="7-14")
    p_plan.set_defaults(func=_cmd_plan)

    return parser


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def _cmd_screen(args: argparse.Namespace) -> int:
    from options_desk import screen

    config.ensure_out_dir(args.out_dir)
    rows = screen.run_screen(
        args.underlying, args.structure, args.dte, spot=args.spot
    )
    if not rows:
        print("no candidates", file=sys.stderr)
        return 1
    print(json.dumps(rows, indent=2))
    top = rows[0]
    print(
        f"screened {len(rows)} candidate(s); top {top['occ_symbols'][0]} "
        f"mid={top['mid']} note='{top['liquidity_note']}'",
        file=sys.stderr,
    )
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    from options_desk import compare

    config.ensure_out_dir(args.out_dir)
    return compare.run_compare(args)


def _cmd_stress(args: argparse.Namespace) -> int:
    from options_desk import stress

    config.ensure_out_dir(args.out_dir)
    return stress.run_stress(args)


def _cmd_plan(args: argparse.Namespace) -> int:
    from options_desk import plan

    config.ensure_out_dir(args.out_dir)
    return plan.run_plan(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
