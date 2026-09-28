#!/usr/bin/env python3
"""Scout wake-context CLI (offline regime + vol research block).

Context only, never an order. Deterministic and offline: reads read-only market
and signal inputs and writes a machine JSON + a human Markdown embed block.

Agnostic handoff contract:
  * ``--out-dir`` is REQUIRED; all writes go there only. The CLI refuses to run
    without it and creates it if missing.
  * ``--paper-trades-root`` (or env ``PAPER_TRADES_ROOT``) is OPTIONAL and
    locates read inputs only. Explicit input paths (``--snapshot``) override it.

Orchestration is wired in Sprint 7 (S9); this module currently establishes the
CLI surface and shared path/time contracts.
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running as a plain script: make the sibling ``scout_context`` package
# importable regardless of the caller's working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scout_context import paths  # noqa: E402  (after sys.path shim)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scout_wake_context.py",
        description=(
            "Build an offline regime + volatility context block for a Scout "
            "wake-review. Context only, never an order."
        ),
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        metavar="PATH",
        help="REQUIRED. Directory for all outputs (created if missing). "
        "Nothing is written outside this directory.",
    )
    parser.add_argument(
        "--paper-trades-root",
        default=os.environ.get(paths.ENV_ROOT),
        metavar="PATH",
        help="Optional root for read inputs (DB, snapshots, ring, squeeze). "
        "Defaults to env PAPER_TRADES_ROOT. Inputs only; never a write target.",
    )
    parser.add_argument(
        "--ts-ct",
        metavar='"YYYY-MM-DD HH:MM:SS CDT|CT"',
        help="Central-Time timestamp for the wake. Ignored when --snapshot is "
        "given (snapshot takes precedence).",
    )
    parser.add_argument(
        "--snapshot",
        metavar="PATH",
        help="Path to a frozen wake-snapshot-*.json. Overrides --ts-ct and any "
        "root-relative default input.",
    )
    parser.add_argument(
        "--inject-review",
        metavar="PATH",
        help="Optional explicit path to a wake-review markdown file to inject "
        "the context block into. Never assumes feeds/signals/.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute the pipeline. Filled in by Sprint 7 (S9)."""
    raise NotImplementedError("pipeline wiring lands in Sprint 7 (S9)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.snapshot and not args.ts_ct:
        parser.error("provide at least one of --snapshot or --ts-ct")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
