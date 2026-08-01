from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from trading.mcp.decision_tools import DecisionServices
from trading.mcp.registration import register_option_tools
from trading.strategies import StrategyRegistry
from trading.strategies.cash_secured_put import build_cash_secured_put_strategy
from trading.strategies.weekend_short_put import build_weekend_short_put_strategy


UTC = timezone.utc
NOW = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)


class _Server:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.schemas: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        handler: Any,
        schema: Mapping[str, Any],
    ) -> None:
        assert description
        self.tools[name] = handler
        self.schemas[name] = dict(schema)


class _Research:
    def get_options_chain(self, **kwargs: Any) -> Any:
        raise AssertionError("not exercised in this acceptance flow")

    def get_market_state(self, **kwargs: Any) -> Any:
        raise AssertionError("not exercised in this acceptance flow")

    def validate_research_data(self, **kwargs: Any) -> dict[str, Any]:
        return {"valid": True, "dataset_id": kwargs["dataset_id"]}

    def run_options_walkforward(self, **kwargs: Any) -> Any:
        return {
            "evaluation_id": "walk-forward-1",
            "strategy_id": kwargs["strategy_id"],
            "status": "insufficient_evidence",
        }

    def backtest_option_strategy(self, **kwargs: Any) -> dict[str, Any]:
        return {"backtest_id": "backtest-1", "strategy_id": kwargs["strategy_id"]}


class _Decisions:
    def screen_option_candidates(self, request: Any) -> dict[str, Any]:
        return {"candidate_ids": ["candidate-1"], "dry_run": request.dry_run}

    def compare_option_strategies(self, request: Any) -> dict[str, Any]:
        return {"comparison_id": "comparison-1", "preferred_strategy_id": None}

    def stress_option_candidate(self, request: Any) -> dict[str, Any]:
        return {"stress_result_id": "stress-1", "scenario_count": 16}

    def build_option_trade_plan(self, request: Any) -> dict[str, Any]:
        return {"trade_plan_id": "plan-1", "review_state": "PENDING"}

    def review_option_trade_plan(self, request: Any) -> dict[str, Any]:
        return {
            "review_id": "review-1",
            "trade_plan_id": request.trade_plan_id,
            "decision": request.requested_decision.value,
        }

    def create_option_order_intent(self, request: Any) -> dict[str, Any]:
        return {
            "order_intent_id": "intent-1",
            "trade_plan_id": request.trade_plan_id,
            "broker_neutral": True,
        }


def _artifact(tool_name: str, response: Any) -> dict[str, str]:
    identity = f"artifact-{tool_name}"
    return {
        "artifact_identity": identity,
        "json_relative_path": f"mcp/{identity}.json",
        "markdown_relative_path": f"mcp/{identity}.md",
    }


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.discover((build_weekend_short_put_strategy(), build_cash_secured_put_strategy()))
    return registry


def _decision_request() -> dict[str, Any]:
    return {
        "correlation_id": "corr-1",
        "idempotency_key": "idempotency-1",
        "requested_at_utc": "2026-07-10T20:00:00Z",
        "market_as_of_utc": "2026-07-10T19:59:00Z",
        "units": {
            "currency": "USD",
            "option_price_unit": "currency_per_share",
            "volatility_unit": "annualized_decimal",
            "rate_unit": "annualized_decimal",
            "contract_multiplier_unit": "shares_per_contract",
        },
        "objective": {
            "objective_id": "tail_adjusted_return_on_collateral",
            "objective_version": "1.0.0",
            "score_unit": "decimal_return",
            "parameters": {"tail_weight": "1"},
        },
        "account": {
            "account_id": "paper-account",
            "account_type": "cash",
            "currency": "USD",
            "option_buying_power": str(Decimal("100000")),
            "as_of_utc": "2026-07-10T19:58:00Z",
            "broker_capability_version": "paper-v1",
        },
        "inputs": {"candidate_id": "candidate-1"},
    }


def test_complete_mcp_client_flow_is_typed_dry_run_and_reproducible() -> None:
    server = _Server()
    decisions = _Decisions()
    names = register_option_tools(
        server,
        _Research(),
        _registry(),
        DecisionServices(decisions, decisions, decisions, decisions, decisions),
        _artifact,
    )

    assert len(names) == 13
    assert len(set(names)) == 13
    assert names[:3] == ("get_options_chain", "get_market_state", "validate_research_data")
    assert names[-1] == "create_option_order_intent"

    listed = server.tools["list_option_strategies"](
        {
            "decision_at_utc": "2026-07-10T20:00:00Z",
            "provenance": {"registry_version": "registry-v1"},
        }
    )
    assert listed["read_only"] is True
    assert len(listed["result"]["strategies"]) == 2

    walkforward = server.tools["run_options_walkforward"](
        {
            "decision_at_utc": "2026-07-10T20:00:00Z",
            "strategy_id": "weekend_short_put",
            "strategy_version": "1.0.0",
            "strategy_parameters": {},
            "objective_id": "tail_adjusted_return_on_collateral",
            "objective_assumptions": {"tail_weight": 1},
            "account_assumptions": {"collateral": "cash_secured"},
            "provenance": {
                "data_version": "data-v1",
                "model_version": "model-v1",
                "objective_version": "objective-v1",
                "config_version": "config-v1",
                "code_version": "code-v1",
            },
        }
    )
    assert walkforward["read_only"] is True
    assert walkforward["artifacts"]["artifact_identity"] == "artifact-run_options_walkforward"

    common = _decision_request()
    screened = server.tools["screen_option_candidates"](common)
    assert screened["status"] == "READY"
    assert screened["dry_run"] is True
    assert screened["submitted"] is False

    planned = server.tools["build_option_trade_plan"](common)
    assert planned["payload"]["trade_plan_id"] == "plan-1"
    assert planned["artifacts"]["markdown_relative_path"].endswith(".md")

    reviewed = server.tools["review_option_trade_plan"](
        {
            **common,
            "trade_plan_id": "plan-1",
            "requested_decision": "GO",
            "reviewer_id": "human-reviewer",
            "reasons": ["within documented limits"],
        }
    )
    assert reviewed["payload"]["decision"] == "GO"

    intent = server.tools["create_option_order_intent"](
        {
            **common,
            "trade_plan_id": "plan-1",
            "review_state": {
                "decision": "GO",
                "reviewed_at_utc": "2026-07-10T20:00:00Z",
                "reviewer_id": "human-reviewer",
                "review_id": "review-1",
                "reasons": ["within documented limits"],
            },
        }
    )
    assert intent["status"] == "READY"
    assert intent["submitted"] is False
    assert intent["payload"]["broker_neutral"] is True

    repeated = server.tools["create_option_order_intent"](
        {
            **common,
            "trade_plan_id": "plan-1",
            "review_state": {
                "decision": "GO",
                "reviewed_at_utc": "2026-07-10T20:00:00Z",
                "reviewer_id": "human-reviewer",
                "review_id": "review-1",
                "reasons": ["within documented limits"],
            },
        }
    )
    assert repeated["request_id"] == intent["request_id"]
    assert repeated["result_id"] == intent["result_id"]


def test_transport_rejects_ambiguous_timestamps_before_service_execution() -> None:
    server = _Server()
    decisions = _Decisions()
    register_option_tools(
        server,
        _Research(),
        _registry(),
        DecisionServices(decisions, decisions, decisions, decisions, decisions),
        _artifact,
    )
    request = _decision_request()
    request["requested_at_utc"] = "2026-07-10T20:00:00"

    with pytest.raises(ValueError, match="timezone-aware"):
        server.tools["screen_option_candidates"](request)
