from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    timestamp_utc: str
    seed: int
    config_path: str
    config_hash: str
    git_commit: str
    python_version: str
    command: str
    user_meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_git_commit(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _hash_config(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_run_metadata(
    *,
    config: dict[str, Any],
    seed: int,
    config_path: str | Path | None = None,
    run_id: str | None = None,
    command: str | None = None,
    user_meta: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> RunMetadata:
    ts = datetime.now(timezone.utc)
    rid = run_id or ts.strftime("run_%Y%m%dT%H%M%SZ")
    root = repo_root or Path(__file__).resolve().parents[2]
    return RunMetadata(
        run_id=rid,
        timestamp_utc=ts.isoformat(),
        seed=int(seed),
        config_path=str(config_path) if config_path is not None else "unknown",
        config_hash=_hash_config(config),
        git_commit=_safe_git_commit(root),
        python_version=platform.python_version(),
        command=command or " ".join(sys.argv),
        user_meta=dict(user_meta or {}),
    )
