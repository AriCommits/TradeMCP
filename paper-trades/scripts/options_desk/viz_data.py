"""Read-only book/marks/journal reader for the Options Desk PNG viz.

Stdlib only. Reads the open book from ``PAPERTRADE_DB`` (options account,
read-only) via sqlite3, resolves current marks, and optionally reads a journal
for the PnL panel. All access is fenced: the DB path must end with
``options/papertrade.db``. Degrades gracefully (empty book) when inputs are
absent — never fabricates positions or marks.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config


@dataclass
class Leg:
    occ_symbol: str
    qty: int
    entry: float
    stop: float | None
    mark: float | None
    delta: float | None = None
    theta: float | None = None


@dataclass
class BookView:
    legs: list[Leg] = field(default_factory=list)
    day_pnl_usd: float | None = None
    day_pnl_r: float | None = None
    quality_flags: list[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.legs)


def _open_ro(db_path: Path) -> sqlite3.Connection | None:
    """Open the sqlite DB strictly read-only. Returns ``None`` if unavailable."""
    if not db_path.exists():
        return None
    try:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def load_book(
    paper_trades_root: str | None = None,
    db_path: str | None = None,
) -> BookView:
    """Load open legs from the options papertrade DB (fenced, read-only)."""
    resolved = config.resolve_db_path(paper_trades_root, db_path)
    # Hard fence: refuse anything outside the options path.
    config.assert_db_fenced(resolved)

    view = BookView()
    conn = _open_ro(Path(resolved))
    if conn is None:
        view.quality_flags.append("db_absent_or_unreadable")
        return view
    try:
        if not _table_exists(conn, "positions"):
            view.quality_flags.append("no_positions_table")
            return view
        cur = conn.execute(
            "SELECT occ_symbol, qty, entry, stop, mark, delta, theta "
            "FROM positions WHERE COALESCE(status,'open')='open'"
        )
        for row in cur.fetchall():
            occ, qty, entry, stop, mark, delta, theta = row
            view.legs.append(
                Leg(
                    occ_symbol=str(occ),
                    qty=int(qty),
                    entry=float(entry),
                    stop=float(stop) if stop is not None else None,
                    mark=float(mark) if mark is not None else None,
                    delta=float(delta) if delta is not None else None,
                    theta=float(theta) if theta is not None else None,
                )
            )
    except sqlite3.Error as exc:
        view.quality_flags.append(f"db_error:{type(exc).__name__}")
    finally:
        conn.close()

    if not view.legs:
        view.quality_flags.append("no_open_legs")
    return view


def build_book_from_rows(rows: list[dict[str, Any]]) -> BookView:
    """Construct a BookView from in-memory rows (used by tests/fixtures)."""
    view = BookView()
    for r in rows:
        view.legs.append(
            Leg(
                occ_symbol=str(r["occ_symbol"]),
                qty=int(r["qty"]),
                entry=float(r["entry"]),
                stop=float(r["stop"]) if r.get("stop") is not None else None,
                mark=float(r["mark"]) if r.get("mark") is not None else None,
                delta=float(r["delta"]) if r.get("delta") is not None else None,
                theta=float(r["theta"]) if r.get("theta") is not None else None,
            )
        )
    if not view.legs:
        view.quality_flags.append("empty_rows")
    return view
