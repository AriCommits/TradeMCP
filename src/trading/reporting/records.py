"""Typed schema for auditable option trade-plan reports.

The records intentionally describe a plan, not an order.  No field represents
broker authorization or submission state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading.options.contracts import VersionedRecord, require_utc


class EvidenceKind(str, Enum):
    """Provenance category for every claim shown to a user."""

    OBSERVATION = "observation"
    ESTIMATE = "estimate"
    SIMULATION = "simulation"
    BROKER_STATE = "broker_state"


class AlternativeDisposition(str, Enum):
    SELECTED = "selected"
    REJECTED = "rejected"


@dataclass(frozen=True)
class QuoteSummary(VersionedRecord):
    contract_id: str
    observed_at_utc: datetime
    bid: Decimal
    ask: Decimal
    bid_size: int | None
    ask_size: int | None

    def __post_init__(self) -> None:
        require_utc(self.observed_at_utc, "observed_at_utc")
        if not self.contract_id:
            raise ValueError("contract_id is required")
        if self.bid < 0 or self.ask < self.bid:
            raise ValueError("quote must be non-negative and not crossed")
        if self.bid_size is not None and self.bid_size < 0:
            raise ValueError("bid_size cannot be negative")
        if self.ask_size is not None and self.ask_size < 0:
            raise ValueError("ask_size cannot be negative")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class CapitalPayoffSummary(VersionedRecord):
    currency: str
    capital_required: Decimal
    premium: Decimal
    maximum_profit: Decimal | None
    maximum_loss: Decimal | None
    break_even_underlying: Decimal | None
    assignment_obligation: str

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")
        if self.capital_required < 0 or self.premium < 0:
            raise ValueError("capital and premium cannot be negative")
        if self.maximum_profit is not None and self.maximum_profit < 0:
            raise ValueError("maximum_profit cannot be negative")
        if self.maximum_loss is not None and self.maximum_loss < 0:
            raise ValueError("maximum_loss cannot be negative")
        if not self.assignment_obligation:
            raise ValueError("assignment_obligation is required")


@dataclass(frozen=True)
class ForecastSummary(VersionedRecord):
    forecast_id: str
    target: str
    horizon: str
    point_estimate: Decimal
    unit: str
    training_cutoff_utc: datetime
    calibration_metrics: dict[str, Decimal]

    def __post_init__(self) -> None:
        require_utc(self.training_cutoff_utc, "training_cutoff_utc")
        if not self.forecast_id or not self.target or not self.horizon or not self.unit:
            raise ValueError("forecast identity, target, horizon, and unit are required")
        if any(not key for key in self.calibration_metrics):
            raise ValueError("calibration metric names cannot be empty")


@dataclass(frozen=True)
class StressSummary(VersionedRecord):
    stress_result_id: str
    scenario_count: int
    worst_scenario_id: str
    worst_pnl: Decimal
    best_scenario_id: str
    best_pnl: Decimal
    axes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.scenario_count <= 0:
            raise ValueError("scenario_count must be positive")
        if not all((self.stress_result_id, self.worst_scenario_id, self.best_scenario_id)):
            raise ValueError("stress result and scenario identities are required")
        if self.worst_pnl > self.best_pnl:
            raise ValueError("worst_pnl cannot exceed best_pnl")
        if not self.axes or len(set(self.axes)) != len(self.axes):
            raise ValueError("stress axes must be non-empty and unique")


@dataclass(frozen=True)
class EvidenceRecord(VersionedRecord):
    evidence_id: str
    kind: EvidenceKind
    label: str
    value: str
    source_id: str
    as_of_utc: datetime

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        if not all((self.evidence_id, self.label, self.value, self.source_id)):
            raise ValueError("evidence id, label, value, and source are required")


@dataclass(frozen=True)
class BrokerStateEvidence(VersionedRecord):
    """Read-only broker/account facts; never an instruction to submit an order."""

    adapter_id: str
    account_id_redacted: str
    observed_at_utc: datetime
    option_buying_power: Decimal
    option_approval_level: int
    capabilities_version: str

    def __post_init__(self) -> None:
        require_utc(self.observed_at_utc, "observed_at_utc")
        if not all((self.adapter_id, self.account_id_redacted, self.capabilities_version)):
            raise ValueError("broker adapter, redacted account, and capabilities are required")
        if self.option_buying_power < 0 or self.option_approval_level < 0:
            raise ValueError("broker buying power and approval level cannot be negative")


@dataclass(frozen=True)
class PlanAlternative(VersionedRecord):
    candidate_id: str
    label: str
    disposition: AlternativeDisposition
    rationale: tuple[str, ...]
    quote: QuoteSummary
    capital_payoff: CapitalPayoffSummary
    objective_score: Decimal | None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.label or not self.rationale:
            raise ValueError("candidate id, label, and rationale are required")


@dataclass(frozen=True)
class DataQualityIssue(VersionedRecord):
    code: str
    severity: str
    source_id: str
    message: str

    def __post_init__(self) -> None:
        if not all((self.code, self.severity, self.source_id, self.message)):
            raise ValueError("quality issue fields are required")


@dataclass(frozen=True)
class DataQualitySummary(VersionedRecord):
    checked_at_utc: datetime
    source_count: int
    accepted_record_count: int
    rejected_record_count: int
    issues: tuple[DataQualityIssue, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.checked_at_utc, "checked_at_utc")
        if min(self.source_count, self.accepted_record_count, self.rejected_record_count) < 0:
            raise ValueError("data-quality counts cannot be negative")


@dataclass(frozen=True)
class FeatureManifestEntry(VersionedRecord):
    name: str
    version: str
    source_id: str
    available_at_utc: datetime

    def __post_init__(self) -> None:
        require_utc(self.available_at_utc, "available_at_utc")
        if not all((self.name, self.version, self.source_id)):
            raise ValueError("feature name, version, and source are required")


@dataclass(frozen=True)
class FeatureManifest(VersionedRecord):
    manifest_id: str
    features: tuple[FeatureManifestEntry, ...]

    def __post_init__(self) -> None:
        if not self.manifest_id or not self.features:
            raise ValueError("manifest id and features are required")
        names = [item.name for item in self.features]
        if len(set(names)) != len(names):
            raise ValueError("feature names must be unique")


@dataclass(frozen=True)
class ReportError(VersionedRecord):
    code: str
    component: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not self.code or not self.component or not self.message:
            raise ValueError("error code, component, and message are required")


@dataclass(frozen=True)
class RunMetadata(VersionedRecord):
    run_id: str
    correlation_id: str
    generated_at_utc: datetime
    code_version: str
    config_version: str
    data_version: str
    input_identities: tuple[str, ...]
    errors: tuple[ReportError, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.generated_at_utc, "generated_at_utc")
        if not all(
            (
                self.run_id,
                self.correlation_id,
                self.code_version,
                self.config_version,
                self.data_version,
            )
        ):
            raise ValueError("run, correlation, and version metadata are required")
        if not self.input_identities or any(not value for value in self.input_identities):
            raise ValueError("at least one non-empty input identity is required")


@dataclass(frozen=True)
class TradePlanReport(VersionedRecord):
    """Canonical input to both JSON and Markdown report projections."""

    title: str
    decision_at_utc: datetime
    strategy_id: str
    strategy_version: str
    selected: PlanAlternative
    rejected: tuple[PlanAlternative, ...]
    forecasts: tuple[ForecastSummary, ...]
    stresses: tuple[StressSummary, ...]
    evidence: tuple[EvidenceRecord, ...]
    broker_state: BrokerStateEvidence | None
    data_quality: DataQualitySummary
    feature_manifest: FeatureManifest
    run: RunMetadata
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        if not self.title or not self.strategy_id or not self.strategy_version:
            raise ValueError("title and strategy identity/version are required")
        if self.selected.disposition is not AlternativeDisposition.SELECTED:
            raise ValueError("selected alternative must have selected disposition")
        if any(item.disposition is not AlternativeDisposition.REJECTED for item in self.rejected):
            raise ValueError("rejected alternatives must have rejected disposition")
        candidate_ids = [self.selected.candidate_id, *(item.candidate_id for item in self.rejected)]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate alternatives must be unique")
        if not self.limitations:
            raise ValueError("reports must state at least one limitation")
        if self.run.generated_at_utc < self.decision_at_utc:
            raise ValueError("report cannot be generated before its decision timestamp")
        alternatives = (self.selected, *self.rejected)
        if any(item.quote.observed_at_utc > self.decision_at_utc for item in alternatives):
            raise ValueError("candidate quote cannot come from after the decision timestamp")
        if self.data_quality.checked_at_utc > self.decision_at_utc:
            raise ValueError("data-quality checks cannot come from after the decision timestamp")
        if any(item.as_of_utc > self.decision_at_utc for item in self.evidence):
            raise ValueError("evidence cannot come from after the decision timestamp")
        if any(item.training_cutoff_utc > self.decision_at_utc for item in self.forecasts):
            raise ValueError("forecast training cutoff cannot follow the decision timestamp")
        if any(
            item.available_at_utc > self.decision_at_utc for item in self.feature_manifest.features
        ):
            raise ValueError("feature cannot be available after the decision timestamp")
        if (
            self.broker_state is not None
            and self.broker_state.observed_at_utc > self.decision_at_utc
        ):
            raise ValueError("broker state cannot come from after the decision timestamp")
