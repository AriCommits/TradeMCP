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

from scout_context import (  # noqa: E402  (after sys.path shim)
    bundle,
    inject,
    loaders,
    paths,
    regime,
    render_md,
    ring_summary,
    squeeze_overlay,
    vol_features,
)


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
    """Execute the end-to-end pipeline. Writes only under ``--out-dir``."""
    out_dir = paths.ensure_out_dir(args.out_dir)
    root = paths.input_root(args)

    # Output key + ring source, honoring snapshot-over-ts precedence.
    provenance: dict[str, object] = {}
    if args.snapshot:
        key = paths.derive_key(snapshot=args.snapshot)
        snap = loaders.load_snapshot(root, args.snapshot)
        ring_data = snap.ring
        provenance["snapshot"] = os.path.basename(str(args.snapshot))
        provenance["snapshot_quality"] = list(snap.quality_flags)
    else:
        key = paths.derive_key(ts_ct=args.ts_ct)
        ring_data = loaders.load_ring(root)
        latest = loaders.load_latest(root)
        provenance["ts_ct"] = args.ts_ct
        provenance["latest_alerts"] = latest.get("alerts", [])

    # Market + squeeze inputs (read-only, fail closed).
    series = loaders.load_ohlcv_5m(root)
    squeeze = loaders.load_squeeze(root)
    provenance["input_root"] = str(root) if root else None
    provenance["symbols"] = list(series.keys())

    # Analysis.
    regimes = regime.classify_all(series)
    vol = vol_features.compute_all(series)
    ring = ring_summary.summarize(ring_data)
    sq = squeeze_overlay.build(squeeze)

    # Assemble + serialize (both under --out-dir, fenced).
    ctx = bundle.build_bundle(key, regimes, vol, ring, sq, provenance=provenance)
    json_path = bundle.write_json(out_dir, ctx)
    md_path = render_md.write_md(out_dir, ctx)

    # Optional, file-local injection into an explicit review path.
    injected = None
    if args.inject_review:
        injected = inject.inject_review(
            args.inject_review, render_md.render_block(ctx)
        )

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    if args.inject_review:
        status = "injected" if injected else "already present (no-op)"
        print(f"inject-review: {status} -> {args.inject_review}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.snapshot and not args.ts_ct:
        parser.error("provide at least one of --snapshot or --ts-ct")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
