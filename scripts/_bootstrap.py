from __future__ import annotations

from pathlib import Path
import sys


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_src_path(root: Path | None = None) -> Path:
    repo_root = root or project_root()
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return repo_root
