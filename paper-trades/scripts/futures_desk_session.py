#!/usr/bin/env python3
"""Futures Desk evening session helper (paper only).

Weekday ~6:20 CT helper: freeze a marks + Risk$/R stub board when a paper book
is available, and always write a HOLD/TRIM/EXIT session markdown skeleton with
commodity kill-line reminders (Hormuz reopen / weekly Brent under $85).

Agnostic handoff contract (Plan 4 — matches Plan 2/3):
  * ``--out-dir`` is REQUIRED; all writes go there only. Refuses without it;
    creates the directory if missing. No hardcoded /workspace write targets.
  * ``--paper-trades-root`` (or env ``PAPER_TRADES_ROOT``) is OPTIONAL and
    inputs-only (last-check.json / running-book CSV).
  * ``--as-of`` is OPTIONAL session stamp (default: now America/Chicago).

Never calls brokers. Never posts Slack. Never submits orders. Futures fence:
does not touch scout/tape/options books. Exit 0 on success (skeleton-only is OK).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Central Time, resolved tolerantly. Prefer the IANA zone (America/Chicago) when
# the tz database is installed; otherwise degrade to a fixed Central Daylight
# offset (UTC-5). This mirrors ``scout_context/timeparse.py`` and avoids a hard
# ``tzdata`` dependency so the CLI runs on a bare box (e.g. minimal Windows /
# uv-managed Pythons) with no installs. Resolution never raises at import time.
_CDT = timezone(timedelta(hours=-5))  # Central Daylight Time fallback


def _central_tz() -> Any:
    """Best-effort Central tzinfo; falls back to fixed CDT when no tz db."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Chicago")
    except Exception:  # noqa: BLE001 - missing tz db → degrade, never raise.
        return _CDT


CT = _central_tz()
ENV_ROOT = "PAPER_TRADES_ROOT"

KILL_LINES = (
    "Hormuz reopen (confirmed reopen / free transit — not a rejected proposal alone)",
    "Weekly Brent cash close under $85",
)

STOP_BANDS = (
    "Equity / crypto perps: default mechanical stop ~3–6% from entry",
    "Commodities (oil, metals, …): ~12–20% catastrophe floor + evening HOLD/TRIM/EXIT re-judge",
    "Bands are defaults — journal a one-line reason if wider/tighter",
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="futures_desk_session.py",
        description=(
            "Paper-only Futures Desk evening session helper. "
            "Writes marks freeze (if available) + HOLD/TRIM/EXIT skeleton under --out-dir. "
            "No brokers, no Slack."
        ),
    )
    p.add_argument(
        "--out-dir",
        required=True,
        metavar="PATH",
        help="REQUIRED. Directory for all outputs (created if missing). "
        "Nothing is written outside this directory.",
    )
    p.add_argument(
        "--paper-trades-root",
        default=os.environ.get(ENV_ROOT),
        metavar="PATH",
        help="Optional root for read inputs (last-check.json, running-book CSV). "
        "Defaults to env PAPER_TRADES_ROOT. Inputs only; never a write target.",
    )
    p.add_argument(
        "--as-of",
        metavar='"YYYY-MM-DD HH:MM CT"',
        help="Optional session stamp label (America/Chicago). Default: now CT.",
    )
    return p


def ensure_out_dir(path: str | Path) -> Path:
    out = Path(path).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def assert_under_out(out_dir: Path, target: Path) -> Path:
    resolved = target.expanduser().resolve()
    try:
        resolved.relative_to(out_dir)
    except ValueError as exc:
        raise SystemExit(f"refusing write outside --out-dir: {resolved}") from exc
    return resolved


def parse_as_of(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(CT)
    text = raw.strip()
    for suffix in (" CT", " CDT", " CST", " America/Chicago"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)  # noqa: DTZ007 - tz applied next line
            return dt.replace(tzinfo=CT)
        except ValueError:
            continue
    raise SystemExit(
        f"could not parse --as-of {raw!r}; expected 'YYYY-MM-DD HH:MM CT'"
    )


def stamp_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d-%H%M")


def load_marks_from_last_check(root: Path) -> dict[str, Any] | None:
    path = root / "last-check.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fp = data.get("futures_paper")
    if not isinstance(fp, dict):
        return None
    positions = fp.get("positions") or {}
    if not isinstance(positions, dict) or not positions:
        return None
    rows = []
    for sym, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        rows.append(
            {
                "symbol": sym,
                "side": pos.get("side"),
                "size": pos.get("size"),
                "entry": pos.get("entry"),
                "mark": pos.get("mark"),
                "u_pnl": pos.get("u_pnl"),
                "stop": pos.get("stop"),
                "risk_usd": pos.get("risk$") if "risk$" in pos else pos.get("risk_usd"),
                "R": pos.get("R"),
                "status": pos.get("status", "open"),
                "funding": pos.get("funding"),
            }
        )
    if not rows:
        return None
    return {
        "source": str(path),
        "source_kind": "last-check.json",
        "checked_at_chicago": data.get("checked_at_chicago"),
        "equity": fp.get("equity"),
        "pnl_pct": fp.get("pnl_pct"),
        "collateral": fp.get("collateral"),
        "starting": fp.get("starting"),
        "total_fills": fp.get("total_fills"),
        "rows": rows,
    }


def load_marks_from_running_book(root: Path) -> dict[str, Any] | None:
    path = root / "slack" / "paper-running-book.csv"
    if not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for rec in reader:
                desk = (rec.get("Desk") or "").strip()
                status = (rec.get("Status") or "").strip().lower()
                if desk != "Futures" or status != "open":
                    continue
                rows.append(
                    {
                        "symbol": rec.get("Symbol"),
                        "side": (rec.get("Side") or "").lower() or None,
                        "size": _num(rec.get("Qty")),
                        "entry": _num(rec.get("Entry")),
                        "mark": None,
                        "u_pnl": _num(rec.get("PnL_$")),
                        "stop": _num(rec.get("Stop")),
                        "risk_usd": _num(rec.get("Risk_$")),
                        "R": _num(rec.get("R")),
                        "status": "open",
                        "theme": rec.get("Theme"),
                    }
                )
    except OSError:
        return None
    if not rows:
        return None
    return {
        "source": str(path),
        "source_kind": "paper-running-book.csv",
        "checked_at_chicago": None,
        "equity": None,
        "pnl_pct": None,
        "collateral": None,
        "starting": None,
        "total_fills": None,
        "rows": rows,
    }


def _num(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def load_marks(root: Path | None) -> dict[str, Any] | None:
    if root is None:
        return None
    if not root.is_dir():
        return None
    return load_marks_from_last_check(root) or load_marks_from_running_book(root)


def fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def marks_table_md(bundle: dict[str, Any]) -> str:
    lines = [
        "| Symbol | Side | Size | Entry | Mark | uPnL | Stop | Risk $ | R | Re-judge |",
        "|--------|------|------|-------|------|------|------|--------|---|----------|",
    ]
    for row in bundle["rows"]:
        lines.append(
            "| {symbol} | {side} | {size} | {entry} | {mark} | {u_pnl} | {stop} | {risk} | {R} |  |".format(
                symbol=fmt(row.get("symbol"), 0),
                side=fmt(row.get("side"), 0),
                size=fmt(row.get("size")),
                entry=fmt(row.get("entry")),
                mark=fmt(row.get("mark")),
                u_pnl=fmt(row.get("u_pnl")),
                stop=fmt(row.get("stop")),
                risk=fmt(row.get("risk_usd")),
                R=fmt(row.get("R")),
            )
        )
    return "\n".join(lines)


def write_marks(out_dir: Path, key: str, bundle: dict[str, Any]) -> tuple[Path, Path]:
    md_path = assert_under_out(out_dir, out_dir / f"{key}-marks.md")
    json_path = assert_under_out(out_dir, out_dir / f"{key}-marks.json")
    header = [
        f"# Futures marks freeze — {key}",
        "",
        f"- **Source:** `{bundle['source_kind']}` (`{bundle['source']}`)",
        f"- **Checked at (CT):** {bundle.get('checked_at_chicago') or '—'}",
        (
            f"- **Equity:** {fmt(bundle.get('equity'))} · "
            f"**PnL %:** {fmt(bundle.get('pnl_pct'))} · "
            f"**Collateral:** {fmt(bundle.get('collateral'))}"
        ),
        "",
        marks_table_md(bundle),
        "",
        "_Paper only. Stub Risk$/R from freeze file — re-confirm before any decision._",
        "",
    ]
    md_path.write_text("\n".join(header), encoding="utf-8")
    payload = {
        "as_of_key": key,
        "source_kind": bundle["source_kind"],
        "source": bundle["source"],
        "checked_at_chicago": bundle.get("checked_at_chicago"),
        "equity": bundle.get("equity"),
        "pnl_pct": bundle.get("pnl_pct"),
        "collateral": bundle.get("collateral"),
        "starting": bundle.get("starting"),
        "total_fills": bundle.get("total_fills"),
        "rows": bundle["rows"],
        "paper_only": True,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return md_path, json_path


def write_session(
    out_dir: Path,
    key: str,
    as_of: datetime,
    bundle: dict[str, Any] | None,
    marks_md_name: str | None,
) -> Path:
    path = assert_under_out(out_dir, out_dir / f"{key}-session.md")
    as_of_label = as_of.strftime("%Y-%m-%d %H:%M CT")
    if bundle:
        marks_block = [
            f"Frozen from `{bundle['source_kind']}`"
            + (f" (see `{marks_md_name}`)" if marks_md_name else "")
            + ".",
            "",
            marks_table_md(bundle),
        ]
        if bundle.get("equity") is not None:
            marks_block.append("")
            marks_block.append(
                f"Account stub: equity ~{fmt(bundle.get('equity'))} · "
                f"pnl % ~{fmt(bundle.get('pnl_pct'))} · "
                f"collateral ~{fmt(bundle.get('collateral'))} · "
                f"opens {len(bundle['rows'])}/8"
            )
    else:
        marks_block = [
            (
                "_No paper book / marks found under `--paper-trades-root` "
                "(looked for `last-check.json` futures_paper.positions, then "
                "`slack/paper-running-book.csv` Desk=Futures Status=open). "
                "Fill marks by hand or re-run with a root that has a freeze._"
            ),
        ]

    kill_bullets = "\n".join(f"- {line}" for line in KILL_LINES)
    stop_bullets = "\n".join(f"- {line}" for line in STOP_BANDS)

    body = f"""# Futures Desk session — {as_of_label}

_Plan 4 helper output. **Paper only.** No brokers / no Slack from this CLI.
Human fills diet + HOLD/TRIM/EXIT judgments. Fence: Kraken futures paper only
— no scout/tape/invariants, no TradingCLI options._

## Marks (freeze)

{chr(10).join(marks_block)}

## Geo / oil / rates skim (placeholder)

- **Oil / Hormuz:** _TODO — wire skim (do not invent)._
- **Rates / FOMC path:** _TODO._
- **Equities / soft-equity short thesis:** _TODO._
- **Gold / metals:** _TODO._
- **Crypto perps:** _TODO — skip chase unless thesis + stop ready._
- Futures X skim path (box): `/workspace/paper-trades/feeds/x-skim-futures-YYYY-MM-DD.md` (optional read; not scraped here).

## HOLD

| Symbol | One-liner | Stop intact? |
|--------|-----------|--------------|
|  |  |  |

## TRIM

| Symbol | Trim to | Why |
|--------|---------|-----|
|  |  |  |

## EXIT

| Symbol | Why (thesis kill / stop / R) |
|--------|------------------------------|
|  |  |

## Commodity kill lines (reminders)

{kill_bullets}

Recommend EXIT on a commodity **only** if a kill line actually prints — not on
headline noise alone. Evening re-judge still applies under STOP_POLICY commodity
bands.

## STOP_POLICY bands (reminder)

{stop_bullets}

Canon: `docs/desk-ops/STOP_POLICY.md` (box: `/workspace/paper-trades/STOP_POLICY.md`).
R = P&L $ ÷ Risk $ — see `docs/desk-ops/R_REPORTING.md`.

## Fence

- Kraken **futures paper** only.
- No scout / tape / invariants spot books.
- No TradingCLI options.
- **No orders** from this CLI. **No Slack** from this CLI.
- Tags: `futures` · `paper`

## Slack (human / on-box — not this CLI)

- `#desk-futures` — evening HOLD/TRIM/EXIT + commodity one-liners (after review).
- `#ops-paper-metrics` — equity/marks digest (optional).
"""
    path.write_text(body, encoding="utf-8")
    return path


def run(args: argparse.Namespace) -> int:
    out_dir = ensure_out_dir(args.out_dir)
    as_of = parse_as_of(args.as_of)
    key = stamp_key(as_of)

    root: Path | None = None
    if args.paper_trades_root:
        root = Path(args.paper_trades_root).expanduser().resolve()

    bundle = load_marks(root)
    marks_md_name = None
    if bundle:
        md_path, json_path = write_marks(out_dir, key, bundle)
        marks_md_name = md_path.name
        print(f"wrote marks: {md_path}", file=sys.stderr)
        print(f"wrote marks json: {json_path}", file=sys.stderr)
    else:
        print(
            "no marks/book found; writing session skeleton only",
            file=sys.stderr,
        )

    session_path = write_session(out_dir, key, as_of, bundle, marks_md_name)
    print(f"wrote session: {session_path}", file=sys.stderr)
    print(f"out-dir: {out_dir}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
