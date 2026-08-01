"""Content-addressed report bundles and explicit persistence adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol

from trading.reporting.records import TradePlanReport
from trading.reporting.render import render_markdown


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("artifact path must be a safe, non-empty relative path")
    if ":" in path.parts[0]:
        raise ValueError("artifact path cannot contain a drive prefix")
    return path.as_posix()


class ArtifactStore(Protocol):
    """Minimal persistence port; callers must provide storage explicitly."""

    def write_text(self, relative_path: str, content: str) -> None: ...


@dataclass
class InMemoryArtifactStore:
    artifacts: dict[str, str]

    def __init__(self) -> None:
        self.artifacts = {}

    def write_text(self, relative_path: str, content: str) -> None:
        self.artifacts[_safe_relative_path(relative_path)] = content


@dataclass(frozen=True)
class RootedArtifactStore:
    root: Path

    def write_text(self, relative_path: str, content: str) -> None:
        safe = _safe_relative_path(relative_path)
        destination = self.root.joinpath(*PurePosixPath(safe).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class ReportBundle:
    """Canonical integration payload returned to MCP planning tools."""

    artifact_identity: str
    run_id: str
    correlation_id: str
    json_text: str
    markdown_text: str
    json_relative_path: str
    markdown_relative_path: str


def build_report_bundle(
    report: TradePlanReport,
    *,
    relative_directory: str = "trade-plans",
) -> ReportBundle:
    canonical_json = report.to_json()
    digest = sha256(canonical_json.encode("utf-8")).hexdigest()
    identity = f"trade-plan-sha256-{digest}"
    directory = _safe_relative_path(relative_directory)
    json_path = _safe_relative_path(f"{directory}/{identity}.json")
    markdown_path = _safe_relative_path(f"{directory}/{identity}.md")
    # Preserve canonical domain serialization while making identity independently verifiable.
    json_payload = json.dumps(
        {"artifact_identity": identity, "report": json.loads(canonical_json)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return ReportBundle(
        artifact_identity=identity,
        run_id=report.run.run_id,
        correlation_id=report.run.correlation_id,
        json_text=json_payload,
        markdown_text=render_markdown(report, identity),
        json_relative_path=json_path,
        markdown_relative_path=markdown_path,
    )


def persist_report_bundle(bundle: ReportBundle, store: ArtifactStore) -> None:
    store.write_text(bundle.json_relative_path, bundle.json_text)
    store.write_text(bundle.markdown_relative_path, bundle.markdown_text)
