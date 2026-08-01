"""Framework-neutral MCP contracts and handlers for option trade decisions.

These tools stop at a broker-neutral order *intent*.  They deliberately expose no
broker adapter and contain no order-submission path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from trading.options.contracts import VersionedRecord, require_utc


class DecisionStatus(str, Enum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    NO_GO = "NO_GO"


class ReviewDecision(str, Enum):
    PENDING = "PENDING"
    GO = "GO"
    NO_GO = "NO_GO"
    NEEDS_INPUT = "NEEDS_INPUT"


@dataclass(frozen=True)
class UnitAssumptions(VersionedRecord):
    currency: str
    option_price_unit: str
    volatility_unit: str
    rate_unit: str
    contract_multiplier_unit: str

    def __post_init__(self) -> None:
        if self.currency != self.currency.upper() or len(self.currency) != 3:
            raise ValueError("currency must be a three-letter uppercase code")
        if any(
            not value
            for value in (
                self.option_price_unit,
                self.volatility_unit,
                self.rate_unit,
                self.contract_multiplier_unit,
            )
        ):
            raise ValueError("all unit assumptions are required")


@dataclass(frozen=True)
class ObjectiveAssumptions(VersionedRecord):
    objective_id: str
    objective_version: str
    score_unit: str
    parameters: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.objective_id or not self.objective_version or not self.score_unit:
            raise ValueError("objective identity, version, and score unit are required")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class AccountAssumptions(VersionedRecord):
    account_id: str
    account_type: str
    currency: str
    option_buying_power: Decimal
    as_of_utc: datetime
    broker_capability_version: str

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        if not self.account_id or not self.account_type or not self.broker_capability_version:
            raise ValueError("account and broker-capability assumptions are required")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("account currency must be a three-letter uppercase code")
        if self.option_buying_power < 0:
            raise ValueError("option_buying_power cannot be negative")


@dataclass(frozen=True)
class ReviewState(VersionedRecord):
    decision: ReviewDecision
    reviewed_at_utc: datetime | None = None
    reviewer_id: str | None = None
    review_id: str | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.reviewed_at_utc is not None:
            require_utc(self.reviewed_at_utc, "reviewed_at_utc")
        reviewed = self.decision is not ReviewDecision.PENDING
        if reviewed != bool(self.reviewed_at_utc and self.reviewer_id and self.review_id):
            raise ValueError("completed reviews require timestamp, reviewer_id, and review_id")


@dataclass(frozen=True, kw_only=True)
class DecisionToolRequest(VersionedRecord):
    correlation_id: str
    idempotency_key: str
    requested_at_utc: datetime
    market_as_of_utc: datetime
    units: UnitAssumptions
    objective: ObjectiveAssumptions
    account: AccountAssumptions
    inputs: Mapping[str, Any]
    dry_run: bool = True

    def __post_init__(self) -> None:
        require_utc(self.requested_at_utc, "requested_at_utc")
        require_utc(self.market_as_of_utc, "market_as_of_utc")
        if not self.correlation_id or not self.idempotency_key:
            raise ValueError("correlation_id and idempotency_key are required")
        if self.market_as_of_utc > self.requested_at_utc:
            raise ValueError("market data cannot be newer than the request")
        if self.account.as_of_utc > self.requested_at_utc:
            raise ValueError("account data cannot be newer than the request")
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


@dataclass(frozen=True, kw_only=True)
class ScreenOptionCandidatesRequest(DecisionToolRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class CompareOptionStrategiesRequest(DecisionToolRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class StressOptionCandidateRequest(DecisionToolRequest):
    pass


@dataclass(frozen=True, kw_only=True)
class BuildOptionTradePlanRequest(DecisionToolRequest):
    review_state: ReviewState = field(default_factory=lambda: ReviewState(ReviewDecision.PENDING))


@dataclass(frozen=True, kw_only=True)
class ReviewOptionTradePlanRequest(DecisionToolRequest):
    trade_plan_id: str
    requested_decision: ReviewDecision
    reviewer_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.trade_plan_id or not self.reviewer_id:
            raise ValueError("trade_plan_id and reviewer_id are required")
        if self.requested_decision is ReviewDecision.PENDING:
            raise ValueError("a review cannot request PENDING")


@dataclass(frozen=True, kw_only=True)
class CreateOptionOrderIntentRequest(DecisionToolRequest):
    trade_plan_id: str
    review_state: ReviewState

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.trade_plan_id:
            raise ValueError("trade_plan_id is required")


@dataclass(frozen=True)
class DecisionToolResult(VersionedRecord):
    tool_name: str
    result_id: str
    request_id: str
    correlation_id: str
    idempotency_key: str
    generated_at_utc: datetime
    status: DecisionStatus
    dry_run: bool
    payload: Mapping[str, Any]
    reasons: tuple[str, ...] = ()
    submitted: bool = False

    def __post_init__(self) -> None:
        require_utc(self.generated_at_utc, "generated_at_utc")
        if not all(
            (
                self.tool_name,
                self.result_id,
                self.request_id,
                self.correlation_id,
                self.idempotency_key,
            )
        ):
            raise ValueError("tool and identity fields are required")
        if self.submitted:
            raise ValueError("decision MCP tools never submit orders")
        if self.status is DecisionStatus.READY and self.reasons:
            raise ValueError("READY results cannot include failure reasons")
        if self.status is not DecisionStatus.READY and not self.reasons:
            raise ValueError("fail-closed results require reasons")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class CandidateScreeningService(Protocol):
    def screen_option_candidates(
        self, request: ScreenOptionCandidatesRequest
    ) -> Mapping[str, Any]: ...


class StrategyComparisonService(Protocol):
    def compare_option_strategies(
        self, request: CompareOptionStrategiesRequest
    ) -> Mapping[str, Any]: ...


class CandidateStressService(Protocol):
    def stress_option_candidate(
        self, request: StressOptionCandidateRequest
    ) -> Mapping[str, Any]: ...


class TradePlanService(Protocol):
    def build_option_trade_plan(
        self, request: BuildOptionTradePlanRequest
    ) -> Mapping[str, Any]: ...

    def review_option_trade_plan(
        self, request: ReviewOptionTradePlanRequest
    ) -> Mapping[str, Any]: ...


class OrderIntentService(Protocol):
    def create_option_order_intent(
        self, request: CreateOptionOrderIntentRequest
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class DecisionServices:
    candidates: CandidateScreeningService
    comparisons: StrategyComparisonService
    stress: CandidateStressService
    plans: TradePlanService
    order_intents: OrderIntentService


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(raw).hexdigest()


class DecisionToolHandlers:
    """Thin MCP handlers; domain work is supplied through injected services."""

    def __init__(self, services: DecisionServices) -> None:
        self._services = services

    def _invoke(
        self,
        tool_name: str,
        request: DecisionToolRequest,
        operation: Any,
        *,
        require_go_review: bool = False,
    ) -> DecisionToolResult:
        request_dict = request.to_dict()
        request_id = f"request-{_canonical_digest(request_dict)}"
        if require_go_review:
            review = getattr(request, "review_state", None)
            if review is None or review.decision is not ReviewDecision.GO:
                return self._result(
                    tool_name,
                    request,
                    request_id,
                    DecisionStatus.NO_GO,
                    {},
                    ("trade plan must have an explicit GO review",),
                )
        try:
            payload = dict(operation(request))
        except (KeyError, TypeError, ValueError) as exc:
            return self._result(
                tool_name, request, request_id, DecisionStatus.NEEDS_INPUT, {}, (str(exc),)
            )
        except Exception as exc:  # service boundaries fail closed
            return self._result(
                tool_name,
                request,
                request_id,
                DecisionStatus.NO_GO,
                {},
                (f"service failure: {type(exc).__name__}",),
            )
        status_text = str(payload.pop("status", DecisionStatus.READY.value)).upper()
        try:
            status = DecisionStatus(status_text)
        except ValueError:
            status = DecisionStatus.NO_GO
            payload = {}
            return self._result(
                tool_name,
                request,
                request_id,
                status,
                payload,
                ("service returned an unsupported decision status",),
            )
        reasons = tuple(str(item) for item in payload.pop("reasons", ()))
        if status is not DecisionStatus.READY and not reasons:
            reasons = ("service did not establish a safe decision",)
        return self._result(tool_name, request, request_id, status, payload, reasons)

    @staticmethod
    def _result(
        tool_name: str,
        request: DecisionToolRequest,
        request_id: str,
        status: DecisionStatus,
        payload: Mapping[str, Any],
        reasons: tuple[str, ...],
    ) -> DecisionToolResult:
        result_basis = {
            "tool_name": tool_name,
            "request_id": request_id,
            "status": status.value,
            "payload": payload,
            "reasons": reasons,
        }
        return DecisionToolResult(
            tool_name=tool_name,
            result_id=f"result-{_canonical_digest(result_basis)}",
            request_id=request_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            generated_at_utc=request.requested_at_utc,
            status=status,
            dry_run=request.dry_run,
            payload=payload,
            reasons=reasons,
            submitted=False,
        )

    def screen_option_candidates(
        self, request: ScreenOptionCandidatesRequest
    ) -> DecisionToolResult:
        return self._invoke(
            "screen_option_candidates", request, self._services.candidates.screen_option_candidates
        )

    def compare_option_strategies(
        self, request: CompareOptionStrategiesRequest
    ) -> DecisionToolResult:
        return self._invoke(
            "compare_option_strategies",
            request,
            self._services.comparisons.compare_option_strategies,
        )

    def stress_option_candidate(self, request: StressOptionCandidateRequest) -> DecisionToolResult:
        return self._invoke(
            "stress_option_candidate", request, self._services.stress.stress_option_candidate
        )

    def build_option_trade_plan(self, request: BuildOptionTradePlanRequest) -> DecisionToolResult:
        return self._invoke(
            "build_option_trade_plan", request, self._services.plans.build_option_trade_plan
        )

    def review_option_trade_plan(self, request: ReviewOptionTradePlanRequest) -> DecisionToolResult:
        return self._invoke(
            "review_option_trade_plan", request, self._services.plans.review_option_trade_plan
        )

    def create_option_order_intent(
        self, request: CreateOptionOrderIntentRequest
    ) -> DecisionToolResult:
        return self._invoke(
            "create_option_order_intent",
            request,
            self._services.order_intents.create_option_order_intent,
            require_go_review=True,
        )


def _tool_schema(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "required": [
                "correlation_id",
                "idempotency_key",
                "requested_at_utc",
                "market_as_of_utc",
                "units",
                "objective",
                "account",
                "inputs",
            ],
            "properties": {
                "correlation_id": {"type": "string", "minLength": 1},
                "idempotency_key": {"type": "string", "minLength": 1},
                "requested_at_utc": {"type": "string", "format": "date-time"},
                "market_as_of_utc": {"type": "string", "format": "date-time"},
                "units": {"type": "object"},
                "objective": {"type": "object"},
                "account": {"type": "object"},
                "inputs": {"type": "object"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "additionalProperties": True,
        },
    }


DECISION_TOOL_DEFINITIONS = (
    _tool_schema("screen_option_candidates", "Screen point-in-time option candidates."),
    _tool_schema("compare_option_strategies", "Compare strategy outcomes and objectives."),
    _tool_schema("stress_option_candidate", "Stress a candidate across configured axes."),
    _tool_schema("build_option_trade_plan", "Build a reviewable broker-neutral trade plan."),
    _tool_schema("review_option_trade_plan", "Record an explicit trade-plan review decision."),
    _tool_schema(
        "create_option_order_intent",
        "Create a broker-neutral order intent; this tool never submits an order.",
    ),
)
