from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DirectoryLayout:
    src: str = "src"
    config: str = "config"
    docs: str = "docs"
    data: str = "data"
    scripts: str = "scripts"
    artifacts: str = "artifacts"
    downloads_misc: str = "downloads_misc"
    tests: str = "tests"
    backtests: str = "backtests"
    integrations: str = "config/integrations"
    adapters: str = "config/integrations/adapters"
    markets: str = "config/markets"
    architecture_docs: str = "docs/architecture"
    rust_backend: str = "backend/rust_exec_engine"


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    src: Path
    config: Path
    docs: Path
    data: Path
    scripts: Path
    artifacts: Path
    downloads_misc: Path
    tests: Path
    backtests: Path
    integrations: Path
    adapters: Path
    markets: Path
    architecture_docs: Path
    rust_backend: Path
    rust_backend_bin: Path


def _discover_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    return start.resolve()


def resolve_paths(repo_root: Path | None = None, layout: DirectoryLayout | None = None) -> ProjectPaths:
    config = layout or DirectoryLayout()
    root = _discover_repo_root(repo_root or Path(__file__).resolve().parents[2])
    rust_backend = root / config.rust_backend
    return ProjectPaths(
        repo_root=root,
        src=root / config.src,
        config=root / config.config,
        docs=root / config.docs,
        data=root / config.data,
        scripts=root / config.scripts,
        artifacts=root / config.artifacts,
        downloads_misc=root / config.downloads_misc,
        tests=root / config.tests,
        backtests=root / config.backtests,
        integrations=root / config.integrations,
        adapters=root / config.adapters,
        markets=root / config.markets,
        architecture_docs=root / config.architecture_docs,
        rust_backend=rust_backend,
        rust_backend_bin=rust_backend / "target/release/rust_exec_engine",
    )
