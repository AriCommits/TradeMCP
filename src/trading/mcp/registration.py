"""Unified registration for strategy-agnostic option research and planning tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from trading.options.contracts import VersionedRecord
from trading.strategies.registry import StrategyRegistry

from .decision_tools import (
    DECISION_TOOL_DEFINITIONS,
    BuildOptionTradePlanRequest,
    CompareOptionStrategiesRequest,
    CreateOptionOrderIntentRequest,
    DecisionServices,
    DecisionToolHandlers,
    DecisionToolRequest,
    ReviewOptionTradePlanRequest,
    ScreenOptionCandidatesRequest,
    StressOptionCandidateRequest,
)
from .research_tools import ResearchServices, build_research_tools


JsonObject = dict[str, Any]
RequestT = TypeVar("RequestT", bound=DecisionToolRequest)


class OptionToolServer(Protocol):
    def register_tool(
        self,
        *,
        name: str,
        description: str,
        handler: Callable[[Mapping[str, Any]], JsonObject],
        schema: Mapping[str, Any],
    ) -> Any: ...


class ArtifactAttachment(Protocol):
    def __call__(self, tool_name: str, response: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RegisteredOptionTool:
    name: str
    description: str
    handler: Callable[[Mapping[str, Any]], JsonObject]
    schema: Mapping[str, Any]


_DECISION_REQUEST_TYPES: dict[str, type[DecisionToolRequest]] = {
    "screen_option_candidates": ScreenOptionCandidatesRequest,
    "compare_option_strategies": CompareOptionStrategiesRequest,
    "stress_option_candidate": StressOptionCandidateRequest,
    "build_option_trade_plan": BuildOptionTradePlanRequest,
    "review_option_trade_plan": ReviewOptionTradePlanRequest,
    "create_option_order_intent": CreateOptionOrderIntentRequest,
}

_LONG_RUNNING_TOOLS = frozenset(
    {
        "run_options_walkforward",
        "backtest_option_strategy",
        "compare_option_strategies",
        "stress_option_candidate",
        "build_option_trade_plan",
    }
)


def _with_version(value: Any, record_type: type[VersionedRecord]) -> Any:
    if not isinstance(value, Mapping):
        return value
    return {"schema_version": record_type.schema_version, **dict(value)}


def _decision_request(request_type: type[RequestT], params: Mapping[str, Any]) -> RequestT:
    from .decision_tools import (
        AccountAssumptions,
        ObjectiveAssumptions,
        ReviewState,
        UnitAssumptions,
    )

    payload = dict(params)
    payload["units"] = _with_version(payload.get("units"), UnitAssumptions)
    payload["objective"] = _with_version(payload.get("objective"), ObjectiveAssumptions)
    payload["account"] = _with_version(payload.get("account"), AccountAssumptions)
    if "review_state" in payload:
        payload["review_state"] = _with_version(payload["review_state"], ReviewState)
    payload = {"schema_version": request_type.schema_version, **payload}
    return request_type.from_dict(payload)


def _attach_artifacts(
    definition: RegisteredOptionTool,
    artifact_attachment: ArtifactAttachment,
) -> RegisteredOptionTool:
    if definition.name not in _LONG_RUNNING_TOOLS:
        return definition

    def handler(params: Mapping[str, Any]) -> JsonObject:
        response = definition.handler(params)
        artifacts = dict(artifact_attachment(definition.name, response))
        return {**response, "artifacts": artifacts}

    return RegisteredOptionTool(
        definition.name,
        definition.description,
        handler,
        definition.schema,
    )


def build_option_tools(
    research_services: ResearchServices,
    registry: StrategyRegistry,
    decision_services: DecisionServices,
    artifact_attachment: ArtifactAttachment,
) -> tuple[RegisteredOptionTool, ...]:
    """Build all 13 Sprint 6 tools in deterministic registration order."""

    research = tuple(
        RegisteredOptionTool(item.name, item.description, item.handler, item.schema)
        for item in build_research_tools(research_services, registry)
    )
    handlers = DecisionToolHandlers(decision_services)
    decision: list[RegisteredOptionTool] = []
    for metadata in DECISION_TOOL_DEFINITIONS:
        name = str(metadata["name"])
        request_type = _DECISION_REQUEST_TYPES[name]
        operation = getattr(handlers, name)

        def handler(
            params: Mapping[str, Any],
            *,
            request_type: type[DecisionToolRequest] = request_type,
            operation: Callable[[DecisionToolRequest], VersionedRecord] = operation,
        ) -> JsonObject:
            request = _decision_request(request_type, params)
            return operation(request).to_dict()

        decision.append(
            RegisteredOptionTool(
                name=name,
                description=str(metadata["description"]),
                handler=handler,
                schema=dict(metadata["inputSchema"]),
            )
        )
    combined = (*research, *decision)
    if len({item.name for item in combined}) != len(combined):
        raise ValueError("option MCP tool names must be unique")
    return tuple(_attach_artifacts(item, artifact_attachment) for item in combined)


def register_option_tools(
    server: OptionToolServer,
    research_services: ResearchServices,
    registry: StrategyRegistry,
    decision_services: DecisionServices,
    artifact_attachment: ArtifactAttachment,
) -> tuple[str, ...]:
    definitions = build_option_tools(
        research_services,
        registry,
        decision_services,
        artifact_attachment,
    )
    for item in definitions:
        server.register_tool(
            name=item.name,
            description=item.description,
            handler=item.handler,
            schema=item.schema,
        )
    return tuple(item.name for item in definitions)
