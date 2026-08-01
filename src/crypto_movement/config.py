"""Strict, fail-closed configuration for the crypto movement study."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn

import yaml


class ConfigError(ValueError):
    """Raised when a research configuration is invalid or ambiguous."""


class FullDownloadBlockedError(RuntimeError):
    """Raised when unresolved research decisions block a full download."""


class DecisionStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PROXY_ASSUMPTION = "PROXY_ASSUMPTION"
    BLOCKING_FULL_DOWNLOAD = "BLOCKING_FULL_DOWNLOAD"


class PilotSource(str, Enum):
    FIXTURE = "fixture"
    VENUE_API = "venue_api"

REQUIRED_FULL_DOWNLOAD_DECISIONS = frozenset(
    {
        "production_venue",
        "venue_api",
        "instrument_type",
        "venue_pair",
        "quote_currency",
        "candle_boundary_convention",
        "maker_fee",
        "taker_fee",
        "spread_model",
        "slippage_model",
        "funding_history_and_timing",
        "prop_trailing_drawdown",
        "prop_intraday_drawdown",
        "prop_end_of_day_drawdown",
        "venue_rate_limits",
        "verified_data_coverage",
        "fine_resolution_label_data",
        "gap_and_relisting_policy",
        "point_in_time_universe",
        "final_lockbox_dates",
        "gen1_bundle_location",
    }
)


def _fail(message: str) -> NoReturn:
    raise ConfigError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        _fail(f"{label} keys must be strings")
    return value


def _strict_keys(
    value: Mapping[str, Any], required: set[str], label: str, optional: set[str] | None = None
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        _fail(f"{label} is missing keys: {', '.join(sorted(missing))}")
    if unknown:
        _fail(f"{label} has unknown keys: {', '.join(sorted(unknown))}")


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be numeric")
    return float(value)


def _utc_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{label} must be an ISO-8601 string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ConfigError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(f"{label} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _project_root(start: Path) -> Path:
    resolved = start.resolve()
    current = resolved if resolved.is_dir() else resolved.parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() or (candidate / ".git").exists():
            return candidate
    _fail(f"cannot locate project root from {resolved}")


def _resolved_research_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty path")
    candidate = Path(value)
    resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigError(f"{label} must remain inside the project root") from exc
    if not relative.parts or relative.parts[0].lower() not in {"data", "models", "outputs"}:
        _fail(f"{label} must be under data/, models/, or outputs/")
    return resolved


@dataclass(frozen=True)
class Decision:
    status: DecisionStatus
    value: object
    source: str
    as_of: str
    notes: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ConfigError("decision source cannot be blank")
        try:
            date.fromisoformat(self.as_of)
        except ValueError as exc:
            raise ConfigError("decision as_of must be an ISO date") from exc
        if self.status is DecisionStatus.CONFIRMED:
            if not isinstance(self.value, (str, int, float, bool)):
                raise ConfigError("a confirmed decision requires a concrete scalar value")
            if isinstance(self.value, str) and not self.value.strip():
                raise ConfigError("a confirmed decision value cannot be blank")


@dataclass(frozen=True)
class StudyDesign:
    name: str
    timezone: str
    primary_interval_minutes: int
    ablation_interval_minutes: int
    sequence_hours: int
    horizons_hours: tuple[int, ...]
    primary_decision_horizon_hours: int
    anchor_stride_minutes: int
    barrier_fraction: float

    def __post_init__(self) -> None:
        expected = ("UTC", 15, 30, 24, (1, 3, 6, 12), 6, 60, 0.04)
        actual = (
            self.timezone,
            self.primary_interval_minutes,
            self.ablation_interval_minutes,
            self.sequence_hours,
            self.horizons_hours,
            self.primary_decision_horizon_hours,
            self.anchor_stride_minutes,
            self.barrier_fraction,
        )
        if actual != expected:
            raise ConfigError("study design differs from the frozen Plan 1 specification")
        if not self.name.strip():
            raise ConfigError("study.name cannot be blank")


@dataclass(frozen=True)
class ProjectPaths:
    raw: Path
    interim: Path
    processed: Path
    api_cache: Path
    models: Path
    outputs: Path


@dataclass(frozen=True)
class FullDownloadGate:
    allowed: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class ProjectConfig:
    schema_version: int
    study: StudyDesign
    paths: ProjectPaths
    decisions: Mapping[str, Decision]

    def __post_init__(self) -> None:
        missing = REQUIRED_FULL_DOWNLOAD_DECISIONS - set(self.decisions)
        if missing:
            raise ConfigError(
                "project decisions are missing required full-download keys: "
                + ", ".join(sorted(missing))
            )
        object.__setattr__(self, "decisions", MappingProxyType(dict(self.decisions)))

    @property
    def full_download_gate(self) -> FullDownloadGate:
        blockers = tuple(
            sorted(
                name
                for name, decision in self.decisions.items()
                if decision.status is not DecisionStatus.CONFIRMED
            )
        )
        return FullDownloadGate(not blockers, blockers)

    def require_full_download_ready(self) -> None:
        gate = self.full_download_gate
        if not gate.allowed:
            raise FullDownloadBlockedError(
                "full download is blocked by unresolved decisions: " + ", ".join(gate.blockers)
            )

    def canonical_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "study": asdict(self.study),
            "paths": {key: str(value) for key, value in asdict(self.paths).items()},
            "decisions": {
                name: {
                    "status": decision.status.value,
                    "value": decision.value,
                    "source": decision.source,
                    "as_of": decision.as_of,
                    "notes": decision.notes,
                }
                for name, decision in sorted(self.decisions.items())
            },
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        )


@dataclass(frozen=True)
class FoldWindow:
    fold_id: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    purge_hours: int
    embargo_hours: int

    def __post_init__(self) -> None:
        if not self.fold_id.strip():
            raise ConfigError("fold id cannot be blank")
        ordered = (
            self.train_start,
            self.train_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        if any(
            item.tzinfo is None or item.utcoffset() != timezone.utc.utcoffset(item)
            for item in ordered
        ):
            raise ConfigError("fold timestamps must be timezone-aware UTC")
        if not all(left < right for left, right in pairwise(ordered)):
            raise ConfigError("fold timestamps must be strictly chronological")
        if self.purge_hours < 12:
            raise ConfigError("fold purge must be at least 12 hours")
        if self.embargo_hours < 0:
            raise ConfigError("fold embargo cannot be negative")
        validation_gap = (self.validation_start - self.train_end).total_seconds() / 3600
        test_gap = (self.test_start - self.validation_end).total_seconds() / 3600
        required_gap = self.purge_hours + self.embargo_hours
        if validation_gap < required_gap or test_gap < required_gap:
            raise ConfigError("fold boundaries do not satisfy the declared purge and embargo")


@dataclass(frozen=True)
class PilotConfig:
    schema_version: int
    source: PilotSource
    assets: tuple[str, ...]
    interval_minutes: int
    start: datetime
    end_exclusive: datetime
    folds: tuple[FoldWindow, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ConfigError("pilot schema_version must be 1")
        if self.interval_minutes not in (15, 30):
            raise ConfigError("pilot interval_minutes must be 15 or 30")
        if not self.start < self.end_exclusive:
            raise ConfigError("pilot start must precede end_exclusive")
        if not self.assets or len(set(self.assets)) != len(self.assets):
            raise ConfigError("pilot assets must be non-empty and unique")
        if any(not item or item != item.upper() for item in self.assets):
            raise ConfigError("pilot assets must be uppercase canonical identifiers")
        if any(
            fold.train_start < self.start or fold.test_end > self.end_exclusive
            for fold in self.folds
        ):
            raise ConfigError("pilot fold falls outside the configured pilot interval")


def _read_yaml(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise ConfigError(f"configuration file does not exist: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path.name}") from exc
    return _mapping(loaded, path.name)


def load_project_config(path: Path | str, *, root: Path | str | None = None) -> ProjectConfig:
    config_path = Path(path).resolve()
    project_root = Path(root).resolve() if root is not None else _project_root(config_path)
    raw = _read_yaml(config_path)
    _strict_keys(raw, {"schema_version", "study", "paths", "decisions"}, "project config")
    if _integer(raw["schema_version"], "schema_version") != 1:
        _fail("project schema_version must be 1")

    study_raw = _mapping(raw["study"], "study")
    study_keys = {
        "name",
        "timezone",
        "primary_interval_minutes",
        "ablation_interval_minutes",
        "sequence_hours",
        "horizons_hours",
        "primary_decision_horizon_hours",
        "anchor_stride_minutes",
        "barrier_fraction",
    }
    _strict_keys(study_raw, study_keys, "study")
    horizons = study_raw["horizons_hours"]
    if not isinstance(horizons, list):
        _fail("study.horizons_hours must be a list")
    study = StudyDesign(
        name=str(study_raw["name"]),
        timezone=str(study_raw["timezone"]),
        primary_interval_minutes=_integer(
            study_raw["primary_interval_minutes"], "primary interval"
        ),
        ablation_interval_minutes=_integer(
            study_raw["ablation_interval_minutes"], "ablation interval"
        ),
        sequence_hours=_integer(study_raw["sequence_hours"], "sequence hours"),
        horizons_hours=tuple(_integer(item, "horizon") for item in horizons),
        primary_decision_horizon_hours=_integer(
            study_raw["primary_decision_horizon_hours"], "primary horizon"
        ),
        anchor_stride_minutes=_integer(
            study_raw["anchor_stride_minutes"], "anchor stride"
        ),
        barrier_fraction=_number(study_raw["barrier_fraction"], "barrier fraction"),
    )

    paths_raw = _mapping(raw["paths"], "paths")
    path_keys = {"raw", "interim", "processed", "api_cache", "models", "outputs"}
    _strict_keys(paths_raw, path_keys, "paths")
    path_values = {
        name: _resolved_research_path(project_root, paths_raw[name], f"paths.{name}")
        for name in path_keys
    }
    paths = ProjectPaths(
        raw=path_values["raw"],
        interim=path_values["interim"],
        processed=path_values["processed"],
        api_cache=path_values["api_cache"],
        models=path_values["models"],
        outputs=path_values["outputs"],
    )

    decisions_raw = _mapping(raw["decisions"], "decisions")
    decisions: dict[str, Decision] = {}
    for name, item in decisions_raw.items():
        decision_raw = _mapping(item, f"decisions.{name}")
        _strict_keys(
            decision_raw,
            {"status", "value", "source", "as_of", "notes"},
            f"decisions.{name}",
        )
        try:
            status = DecisionStatus(str(decision_raw["status"]))
        except ValueError as exc:
            raise ConfigError(f"decisions.{name}.status is invalid") from exc
        source = decision_raw["source"]
        as_of = decision_raw["as_of"]
        notes = decision_raw["notes"]
        if not all(isinstance(value, str) for value in (source, as_of, notes)):
            _fail(f"decisions.{name} metadata must be strings")
        decisions[name] = Decision(
            status, decision_raw["value"], source, as_of, notes
        )
    if not decisions:
        _fail("decisions cannot be empty")
    return ProjectConfig(1, study, paths, decisions)


def load_pilot_config(path: Path | str, *, root: Path | str | None = None) -> PilotConfig:
    config_path = Path(path).resolve()
    if root is not None:
        Path(root).resolve()  # Validate the caller's explicit root without using CWD.
    raw = _read_yaml(config_path)
    required = {
        "schema_version",
        "source",
        "assets",
        "interval_minutes",
        "start",
        "end_exclusive",
        "folds",
    }
    _strict_keys(raw, required, "pilot config")
    try:
        source = PilotSource(str(raw["source"]))
    except ValueError as exc:
        raise ConfigError("pilot source is invalid") from exc
    assets = raw["assets"]
    folds_raw = raw["folds"]
    if not isinstance(assets, list) or not isinstance(folds_raw, list):
        _fail("pilot assets and folds must be lists")
    fold_keys = {
        "id",
        "train_start",
        "train_end",
        "validation_start",
        "validation_end",
        "test_start",
        "test_end",
        "purge_hours",
        "embargo_hours",
    }
    folds: list[FoldWindow] = []
    for index, item in enumerate(folds_raw):
        fold_raw = _mapping(item, f"folds[{index}]")
        _strict_keys(fold_raw, fold_keys, f"folds[{index}]")
        folds.append(
            FoldWindow(
                fold_id=str(fold_raw["id"]),
                train_start=_utc_datetime(fold_raw["train_start"], "train_start"),
                train_end=_utc_datetime(fold_raw["train_end"], "train_end"),
                validation_start=_utc_datetime(
                    fold_raw["validation_start"], "validation_start"
                ),
                validation_end=_utc_datetime(
                    fold_raw["validation_end"], "validation_end"
                ),
                test_start=_utc_datetime(fold_raw["test_start"], "test_start"),
                test_end=_utc_datetime(fold_raw["test_end"], "test_end"),
                purge_hours=_integer(fold_raw["purge_hours"], "purge_hours"),
                embargo_hours=_integer(fold_raw["embargo_hours"], "embargo_hours"),
            )
        )
    if len({fold.fold_id for fold in folds}) != len(folds):
        _fail("pilot fold ids must be unique")
    return PilotConfig(
        schema_version=_integer(raw["schema_version"], "schema_version"),
        source=source,
        assets=tuple(str(item) for item in assets),
        interval_minutes=_integer(raw["interval_minutes"], "interval_minutes"),
        start=_utc_datetime(raw["start"], "start"),
        end_exclusive=_utc_datetime(raw["end_exclusive"], "end_exclusive"),
        folds=tuple(folds),
    )
