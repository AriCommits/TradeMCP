"""Optional, file-local review injector for Scout wake-context.

Stdlib only. Inserts a rendered context block under a ``## Offline wake context``
heading into an *explicit* wake-review markdown file.

Contract:
  * Operates only on the exact ``review_path`` passed by ``--inject-review`` —
    never derives or assumes ``feeds/signals/`` or any other location.
  * Idempotent: if the ``## Offline wake context`` heading already exists, the
    file is left unchanged. The result always contains exactly one such section.
  * Never modifies ``Decision`` / ``Judgment`` lines (verified byte-for-byte).
  * This is a convenience only; the standalone ``.json``/``.md`` under
    ``--out-dir`` remain the primary deliverable.
"""

from __future__ import annotations

from pathlib import Path

SECTION_HEADING = "## Offline wake context"


class InjectError(RuntimeError):
    """Raised when the target review file cannot be read/written."""


def has_section(text: str) -> bool:
    """True when the target already contains the context section heading."""
    for line in text.splitlines():
        if line.strip() == SECTION_HEADING:
            return True
    return False


def build_section(block_text: str) -> str:
    """Wrap the rendered block under the ``## Offline wake context`` heading."""
    return f"{SECTION_HEADING}\n\n{block_text.rstrip()}\n"


def inject_text(existing: str, block_text: str) -> tuple[str, bool]:
    """Return ``(new_text, changed)`` for injecting into ``existing``.

    Pure function (no I/O) so it is trivially testable. Idempotent: returns the
    input unchanged when the section already exists.
    """
    if has_section(existing):
        return existing, False

    section = build_section(block_text)
    if existing.strip() == "":
        return section, True

    sep = "" if existing.endswith("\n") else "\n"
    return f"{existing}{sep}\n{section}", True


def inject_review(review_path, block_text: str) -> bool:
    """Inject the block into the explicit ``review_path``.

    Returns True when the file was modified, False when it already had the
    section (idempotent no-op). Raises :class:`InjectError` on I/O failure or a
    missing target file.
    """
    path = Path(review_path)
    if not path.exists():
        raise InjectError(f"review file not found: {path}")
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InjectError(f"cannot read review file {path}: {exc}") from exc

    new_text, changed = inject_text(existing, block_text)
    if not changed:
        return False

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        raise InjectError(f"cannot write review file {path}: {exc}") from exc
    return True
