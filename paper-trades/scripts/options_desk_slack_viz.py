#!/usr/bin/env python3
"""Options Desk viz CLI — writes a 3-panel PNG one-pager (file only).

Agnostic handoff contract:
  * ``--out-dir`` is REQUIRED; the PNG is written there only.
  * ``--paper-trades-root`` (or env) locates the read-only options DB.

Despite the historical name, this script performs **NO Slack / Composio /
posting / OAuth**. Posting is a separate on-box step. It reads the open book
(read-only, DB-fenced) and renders the figure to a PNG.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from options_desk import config, viz_data, viz_figure  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="options_desk_slack_viz.py",
        description="Write a 3-panel Options Desk PNG one-pager (no posting).",
    )
    parser.add_argument(
        "--out-dir", required=True, metavar="PATH",
        help="REQUIRED. Directory for the PNG (created if missing).",
    )
    parser.add_argument(
        "--paper-trades-root", default=os.environ.get(config.ENV_ROOT),
        metavar="PATH", help="Optional root for the read-only options DB.",
    )
    parser.add_argument(
        "--db", default=os.environ.get(config.ENV_DB), metavar="PATH",
        help="Optional explicit PAPERTRADE_DB path (must end options/papertrade.db).",
    )
    parser.add_argument("--title", default="Options Desk — Open Book")
    return parser


def run(args: argparse.Namespace) -> int:
    out_dir = config.ensure_out_dir(args.out_dir)
    book = viz_data.load_book(args.paper_trades_root, args.db)

    key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    png_path = config.out_path(out_dir, f"{key}.png")
    viz_figure.write_png(book, png_path, title=args.title)

    note = "" if book.present else f" (empty book: {','.join(book.quality_flags)})"
    print(f"wrote {png_path}{note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
