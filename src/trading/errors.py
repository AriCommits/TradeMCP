from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class TradingError(Exception):
    """Base exception for domain-specific failures."""


class ValidationError(TradingError):
    """Raised when an input or precondition check fails."""


class DataError(TradingError):
    """Raised for external or malformed data failures."""


class ComputeError(TradingError):
    """Raised for numerical/modeling failures."""


class ExecutionError(TradingError):
    """Raised for execution-layer failures."""


class BrokerError(TradingError):
    """Raised for broker adapter/API failures."""


@dataclass(frozen=True)
class ErrorPolicyConfig:
    verbosity: str
    retry_policy: str
    artifact_path: str
    retain_traceback: bool


def load_error_policy(path: str | Path) -> ErrorPolicyConfig:
    config_path = Path(path)
    if not config_path.exists():
        return ErrorPolicyConfig(
            verbosity="verbose",
            retry_policy="none",
            artifact_path="artifacts/errors",
            retain_traceback=True,
        )

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return ErrorPolicyConfig(
        verbosity=str(raw.get("verbosity", "verbose")),
        retry_policy=str(raw.get("retry_policy", "none")),
        artifact_path=str(raw.get("artifact_path", "artifacts/errors")),
        retain_traceback=bool(raw.get("retain_traceback", True)),
    )


@dataclass(frozen=True)
class ErrorReport:
    error_type: str
    message: str
    traceback: str
    command: str
    run_id: str
    timestamp_utc: str
    config_version: str
    device: str
    context: dict[str, Any]


def persist_error_report(
    exc: Exception,
    *,
    command: str,
    run_id: str,
    policy: ErrorPolicyConfig,
    config_version: str = "unknown",
    device: str = "cpu",
    context: dict[str, Any] | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    stack = traceback.format_exc()

    report = ErrorReport(
        error_type=type(exc).__name__,
        message=str(exc),
        traceback=stack if policy.retain_traceback else "",
        command=command,
        run_id=run_id,
        timestamp_utc=timestamp.isoformat(),
        config_version=config_version,
        device=device,
        context=context or {},
    )

    out_dir = Path(policy.artifact_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{run_id}.json"
    out_path = out_dir / filename
    out_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return out_path
