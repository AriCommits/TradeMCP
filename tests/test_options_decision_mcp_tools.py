from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

import pytest

from trading.mcp.decision_tools import (
    DECISION_TOOL_DEFINITIONS,
    AccountAssumptions,
    BuildOptionTradePlanRequest,
    CompareOptionStrategiesRequest,
    CreateOptionOrderIntentRequest,
    DecisionServices,
    DecisionStatus,
    DecisionToolHandlers,
    ObjectiveAssumptions,
    ReviewDecision,
    ReviewOptionTradePlanRequest,
    ReviewState,
    ScreenOptionCandidatesRequest,
    StressOptionCandidateRequest,
    UnitAssumptions,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 10, 20, tzinfo=UTC)


class StubServices:
    def screen_option_candidates(self, request: ScreenOptionCandidatesRequest) -> Mapping[str, Any]:
        return {"candidate_ids": ["candidate-1"]}

    def compare_option_strategies(
        self, request: CompareOptionStrategiesRequest
    ) -> Mapping[str, Any]:
        return {"comparison_id": "comparison-1"}

    def stress_option_candidate(self, request: StressOptionCandidateRequest) -> Mapping[str, Any]:
        return {"stress_result_id": "stress-1"}

    def build_option_trade_plan(self, request: BuildOptionTradePlanRequest) -> Mapping[str, Any]:
        return {"trade_plan_id": "plan-1"}

    def review_option_trade_plan(self, request: ReviewOptionTradePlanRequest) -> Mapping[str, Any]:
        return {"review_id": "review-1", "decision": request.requested_decision.value}

    def create_option_order_intent(
        self, request: CreateOptionOrderIntentRequest
    ) -> Mapping[str, Any]:
        return {"order_intent_id": "intent-1", "broker": None}


def _common() -> dict[str, Any]:
    return {
        "correlation_id": "correlation-1",
        "idempotency_key": "idempotency-1",
        "requested_at_utc": NOW,
        "market_as_of_utc": NOW,
        "units": UnitAssumptions(
            currency="USD",
            option_price_unit="currency_per_share",
            volatility_unit="annualized_decimal",
            rate_unit="annualized_decimal",
            contract_multiplier_unit="shares_per_contract",
        ),
        "objective": ObjectiveAssumptions("tail_roc", "1", "dimensionless"),
        "account": AccountAssumptions(
            "account-1", "cash", "USD", Decimal("10000"), NOW, "capabilities-1"
        ),
        "inputs": {"candidate_id": "candidate-1"},
    }


def _handlers(services: Any | None = None) -> DecisionToolHandlers:
    service = services or StubServices()
    return DecisionToolHandlers(DecisionServices(service, service, service, service, service))


@pytest.mark.parametrize(
    ("method", "tool_request"),
    [
        ("screen_option_candidates", ScreenOptionCandidatesRequest(**_common())),
        ("compare_option_strategies", CompareOptionStrategiesRequest(**_common())),
        ("stress_option_candidate", StressOptionCandidateRequest(**_common())),
        ("build_option_trade_plan", BuildOptionTradePlanRequest(**_common())),
        (
            "review_option_trade_plan",
            ReviewOptionTradePlanRequest(
                **_common(),
                trade_plan_id="plan-1",
                requested_decision=ReviewDecision.GO,
                reviewer_id="reviewer-1",
                reasons=("within limits",),
            ),
        ),
    ],
)
def test_handlers_return_typed_deterministic_dry_run_results(
    method: str, tool_request: Any
) -> None:
    handler = getattr(_handlers(), method)
    first = handler(tool_request)
    second = handler(tool_request)

    assert first.status is DecisionStatus.READY
    assert first.dry_run is True
    assert first.submitted is False
    assert first.request_id == second.request_id
    assert first.result_id == second.result_id
    assert first.correlation_id == "correlation-1"


def test_order_intent_requires_explicit_go_review_and_never_submits() -> None:
    pending = CreateOptionOrderIntentRequest(
        **_common(), trade_plan_id="plan-1", review_state=ReviewState(ReviewDecision.PENDING)
    )
    blocked = _handlers().create_option_order_intent(pending)
    assert blocked.status is DecisionStatus.NO_GO
    assert blocked.submitted is False

    approved = CreateOptionOrderIntentRequest(
        **_common(),
        dry_run=False,
        trade_plan_id="plan-1",
        review_state=ReviewState(
            ReviewDecision.GO, NOW, "reviewer-1", "review-1", ("within limits",)
        ),
    )
    result = _handlers().create_option_order_intent(approved)
    assert result.status is DecisionStatus.READY
    assert result.dry_run is False
    assert result.submitted is False
    assert result.payload["broker"] is None


def test_validation_and_service_errors_fail_closed() -> None:
    class MissingInput(StubServices):
        def screen_option_candidates(
            self, request: ScreenOptionCandidatesRequest
        ) -> Mapping[str, Any]:
            raise ValueError("chain snapshot is required")

    class UnsafeFailure(StubServices):
        def screen_option_candidates(
            self, request: ScreenOptionCandidatesRequest
        ) -> Mapping[str, Any]:
            raise RuntimeError("unexpected")

    request = ScreenOptionCandidatesRequest(**_common())
    needs_input = _handlers(MissingInput()).screen_option_candidates(request)
    no_go = _handlers(UnsafeFailure()).screen_option_candidates(request)
    assert needs_input.status is DecisionStatus.NEEDS_INPUT
    assert needs_input.reasons == ("chain snapshot is required",)
    assert no_go.status is DecisionStatus.NO_GO
    assert no_go.reasons == ("service failure: RuntimeError",)


def test_timestamps_must_be_explicit_utc() -> None:
    values = _common()
    values["requested_at_utc"] = datetime(2026, 7, 10, 20)
    with pytest.raises(ValueError, match="UTC"):
        ScreenOptionCandidatesRequest(**values)


def test_tool_catalog_has_all_six_tools_and_dry_run_defaults() -> None:
    names = {definition["name"] for definition in DECISION_TOOL_DEFINITIONS}
    assert names == {
        "screen_option_candidates",
        "compare_option_strategies",
        "stress_option_candidate",
        "build_option_trade_plan",
        "review_option_trade_plan",
        "create_option_order_intent",
    }
    assert all(
        definition["inputSchema"]["properties"]["dry_run"]["default"] is True
        for definition in DECISION_TOOL_DEFINITIONS
    )
