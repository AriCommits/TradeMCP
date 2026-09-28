"""Path, output-key, and write-fence contracts for Scout wake-context.

Stdlib only. Defines the shared contracts every other module imports:

* input root resolution (``--paper-trades-root`` / env, reads only);
* output key derivation (``YYYY-MM-DD-HHMM``) from a snapshot filename or
  ``--ts-ct``, with snapshot taking precedence;
* output path construction under ``--out-dir`` only;
* a hard write fence that refuses anything outside ``--out-dir`` and any path
  under an ``options/`` or ``futures/`` subpath.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import timeparse

ENV_ROOT = "PAPER_TRADES_ROOT"

# wake-snapshot-2026-09-28-1500.json  ->  key "2026-09-28-1500"
_SNAPSHOT_KEY_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-\d{4})")

# Fenced subpath names that must never appear in a resolved write path.
_FORBIDDEN_PARTS = ("options", "futures")


class WriteFenceError(RuntimeError):
    """Raised when a write target violates the --out-dir fence."""


class KeyDerivationError(ValueError):
    """Raised when an output key cannot be derived from the given inputs."""


def input_root(args) -> Path | None:
    """Resolve the read-input root.

    Order: explicit ``--paper-trades-root`` arg, then env ``PAPER_TRADES_ROOT``.
    Returns ``None`` when neither is set (explicit input paths still work).
    """
    root = getattr(args, "paper_trades_root", None)
    if not root:
        root = os.environ.get(ENV_ROOT)
    return Path(root).expanduser() if root else None


def key_from_snapshot(snapshot_path) -> str:
    """Extract the ``YYYY-MM-DD-HHMM`` key from a snapshot filename."""
    name = Path(snapshot_path).name
    m = _SNAPSHOT_KEY_RE.search(name)
    if not m:
        raise KeyDerivationError(
            f"could not find a YYYY-MM-DD-HHMM key in snapshot name: {name!r}"
        )
    return m.group(1)


def derive_key(snapshot: str | None = None, ts_ct: str | None = None) -> str:
    """Derive the output key, preferring ``snapshot`` over ``ts_ct``."""
    if snapshot:
        return key_from_snapshot(snapshot)
    if ts_ct:
        key, _utc = timeparse.parse_ts_ct(ts_ct)
        return key
    raise KeyDerivationError("need either a snapshot path or a --ts-ct value")


def ensure_out_dir(out_dir) -> Path:
    """Create ``out_dir`` if missing and return it as a resolved ``Path``."""
    p = Path(out_dir).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def context_json_path(out_dir, key: str) -> Path:
    return Path(out_dir).expanduser().resolve() / f"wake-context-{key}.json"


def context_md_path(out_dir, key: str) -> Path:
    return Path(out_dir).expanduser().resolve() / f"wake-context-{key}.md"


def assert_write_allowed(out_dir, path) -> Path:
    """Hard fence for every write.

    Raises :class:`WriteFenceError` unless ``path`` resolves inside ``out_dir``
    and does not traverse an ``options/`` or ``futures/`` subpath.
    Returns the resolved path on success.
    """
    base = Path(out_dir).expanduser().resolve()
    target = Path(path).expanduser().resolve()

    try:
        rel = target.relative_to(base)
    except ValueError as exc:
        raise WriteFenceError(
            f"refusing to write outside --out-dir: {target} not under {base}"
        ) from exc

    lowered = {part.lower() for part in rel.parts}
    hit = lowered.intersection(_FORBIDDEN_PARTS)
    if hit:
        raise WriteFenceError(
            f"refusing to write under fenced subpath {sorted(hit)!r}: {target}"
        )
    return target
