"""Config, path resolution, and hard fences for the Options Desk MVP.

Stdlib only. Central place for:
  * ``--out-dir`` resolution + creation (all writes go here only);
  * ``--paper-trades-root`` / env resolution for read inputs only;
  * a write fence that refuses any path outside ``--out-dir``;
  * the DB fence: ``PAPERTRADE_DB`` must end with ``options/papertrade.db``;
  * a Kraken fence guard (this package must never touch Kraken tools).
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ROOT = "PAPER_TRADES_ROOT"
ENV_DB = "PAPERTRADE_DB"
ACCOUNT = "options"
DB_SUFFIX = os.path.join("options", "papertrade.db")


class WriteFenceError(RuntimeError):
    """Raised when a write target resolves outside --out-dir."""


class DBFenceError(RuntimeError):
    """Raised when PAPERTRADE_DB is not under the options path."""


class KrakenFenceError(RuntimeError):
    """Raised if a Kraken code path is ever reached (must never happen)."""


def input_root(paper_trades_root: str | None = None) -> Path | None:
    """Resolve the read-input root: explicit arg, then env. May be ``None``."""
    root = paper_trades_root or os.environ.get(ENV_ROOT)
    return Path(root).expanduser() if root else None


def ensure_out_dir(out_dir) -> Path:
    """Create ``out_dir`` if missing; return it resolved."""
    if not out_dir:
        raise WriteFenceError("--out-dir is required")
    p = Path(out_dir).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def out_path(out_dir, name: str) -> Path:
    """Construct an output path under ``out_dir`` (validated by the fence)."""
    target = Path(out_dir).expanduser().resolve() / name
    assert_write_allowed(out_dir, target)
    return target


def assert_write_allowed(out_dir, path) -> Path:
    """Raise :class:`WriteFenceError` unless ``path`` is inside ``out_dir``."""
    base = Path(out_dir).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise WriteFenceError(
            f"refusing to write outside --out-dir: {target} not under {base}"
        ) from exc
    return target


def resolve_db_path(
    paper_trades_root: str | None = None, db_path: str | None = None
) -> Path:
    """Resolve the PAPERTRADE_DB path: explicit arg, env, then root default."""
    raw = db_path or os.environ.get(ENV_DB)
    if raw:
        return Path(raw).expanduser()
    root = input_root(paper_trades_root)
    if root is None:
        # Nothing to anchor to; return the bare suffix so the fence can judge it.
        return Path(DB_SUFFIX)
    return root / DB_SUFFIX


def assert_db_fenced(db_path) -> Path:
    """Raise :class:`DBFenceError` unless the path ends with options/papertrade.db."""
    p = Path(db_path)
    # normalize separators for a suffix comparison
    normalized = p.as_posix().lower()
    if not normalized.endswith("options/papertrade.db"):
        raise DBFenceError(
            f"refusing DB outside options path (must end with "
            f"'options/papertrade.db'): {p}"
        )
    return p


def assert_no_kraken(name: str = "") -> None:
    """Tripwire: called from code that must never reach a Kraken path."""
    raise KrakenFenceError(f"Kraken access is forbidden in options_desk: {name}")
