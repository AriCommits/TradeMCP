"""Framework-neutral, read-only MCP tools for options research.

The tools in this module deliberately accept point-in-time inputs and delegate all
storage/model work to injected services.  They do not read files, call networks, or
mutate accounts.  A host only needs to expose ``register_tool`` with the same keyword
arguments used by :func:`register_research_tools`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from trading.evaluation import WalkForwardEvaluation
from trading.forecasts import ForecastBundle
from trading.options.contracts import VersionedRecord, require_utc
from trading.options.quotes import OptionChainSnapshot
from trading.strategies.registry import StrategyRegistry


JsonObject = dict[str, Any]

UNIT_CONVENTIONS: JsonObject = {
    "timestamps": "ISO-8601 UTC instants ending in Z",
    "money_and_prices": "decimal currency units per underlying share unless named otherwise",
    "returns_rates_and_volatility": "decimal fractions; volatility and rates are annualized",
    "option_quantity": "contracts; contract multiplier is explicit",
}


class ResearchServices(Protocol):
    """Injected, side-effect-free research service boundary."""

    def get_options_chain(
        self, *, underlying: str, as_of_utc: datetime, data_version: str
    ) -> OptionChainSnapshot: ...

    def get_market_state(
        self,
        *,
        symbol: str,
        decision_at_utc: datetime,
        horizons: tuple[Mapping[str, Any], ...],
        provenance: Mapping[str, str],
    ) -> ForecastBundle: ...

    def validate_research_data(
        self,
        *,
        dataset_id: str,
        decision_at_utc: datetime,
        provenance: Mapping[str, str],
    ) -> Mapping[str, Any]: ...

    def run_options_walkforward(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        strategy_parameters: Mapping[str, Any],
        objective_id: str,
        objective_assumptions: Mapping[str, Any],
        account_assumptions: Mapping[str, Any],
        decision_at_utc: datetime,
        provenance: Mapping[str, str],
    ) -> WalkForwardEvaluation: ...

    def backtest_option_strategy(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        strategy_parameters: Mapping[str, Any],
        objective_id: str,
        objective_assumptions: Mapping[str, Any],
        account_assumptions: Mapping[str, Any],
        decision_at_utc: datetime,
        provenance: Mapping[str, str],
    ) -> Mapping[str, Any] | VersionedRecord: ...


class ToolServer(Protocol):
    def register_tool(
        self,
        *,
        name: str,
        description: str,
        handler: Callable[[Mapping[str, Any]], JsonObject],
        schema: Mapping[str, Any],
    ) -> Any: ...


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: Callable[[Mapping[str, Any]], JsonObject]
    schema: Mapping[str, Any]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _identity(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(_canonical(value).encode()).hexdigest()}"


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an explicit ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 UTC timestamp") from exc
    require_utc(parsed, field)
    return parsed


def _required_string(params: Mapping[str, Any], field: str) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value


def _required_mapping(params: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = params.get(field)
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field} must be a non-empty object")
    return value


def _provenance(params: Mapping[str, Any], *required: str) -> dict[str, str]:
    raw = _required_mapping(params, "provenance")
    result: dict[str, str] = {}
    missing: list[str] = []
    for name in required:
        value = raw.get(name)
        if not isinstance(value, str) or not value.strip():
            missing.append(name)
        else:
            result[name] = value
    if missing:
        raise ValueError(f"provenance requires non-empty versions: {sorted(missing)!r}")
    for name, value in raw.items():
        if not isinstance(name, str) or not isinstance(value, str) or not value.strip():
            raise ValueError("provenance keys and values must be non-empty strings")
        result[name] = value
    return dict(sorted(result.items()))


def _json_value(value: Any) -> Any:
    if isinstance(value, VersionedRecord):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _response(tool_name: str, params: Mapping[str, Any], result: Any) -> JsonObject:
    request = dict(params)
    correlation_id = _identity("correlation", {"tool": tool_name, "request": request})
    payload = _json_value(result)
    result_id = _identity(
        "result", {"tool": tool_name, "correlation_id": correlation_id, "result": payload}
    )
    return {
        "correlation_id": correlation_id,
        "result_id": result_id,
        "read_only": True,
        "unit_conventions": UNIT_CONVENTIONS,
        "result": payload,
    }


def _decision(params: Mapping[str, Any]) -> datetime:
    return _utc(params.get("decision_at_utc"), "decision_at_utc")


def _strategy_inputs(
    params: Mapping[str, Any], registry: StrategyRegistry
) -> tuple[str, str, Mapping[str, Any]]:
    strategy_id = _required_string(params, "strategy_id")
    strategy_version = _required_string(params, "strategy_version")
    raw = params.get("strategy_parameters", {})
    if not isinstance(raw, Mapping):
        raise ValueError("strategy_parameters must be an object")
    normalized = registry.validated_parameters(strategy_id, strategy_version, raw)
    return strategy_id, strategy_version, normalized


def _evaluation_inputs(
    params: Mapping[str, Any], registry: StrategyRegistry
) -> tuple[str, str, Mapping[str, Any], str, Mapping[str, Any], Mapping[str, Any]]:
    strategy_id, strategy_version, strategy_parameters = _strategy_inputs(params, registry)
    return (
        strategy_id,
        strategy_version,
        strategy_parameters,
        _required_string(params, "objective_id"),
        _required_mapping(params, "objective_assumptions"),
        _required_mapping(params, "account_assumptions"),
    )


def build_research_tools(
    services: ResearchServices, registry: StrategyRegistry
) -> tuple[ToolDefinition, ...]:
    """Build explicit tool definitions without binding to a particular MCP SDK."""

    def get_options_chain(params: Mapping[str, Any]) -> JsonObject:
        decision = _decision(params)
        provenance = _provenance(params, "data_version")
        chain = services.get_options_chain(
            underlying=_required_string(params, "underlying"),
            as_of_utc=decision,
            data_version=provenance["data_version"],
        )
        if chain.as_of_utc > decision or chain.ingested_at_utc > decision:
            raise ValueError("provider returned future-aware option-chain data")
        return _response("get_options_chain", params, chain)

    def get_market_state(params: Mapping[str, Any]) -> JsonObject:
        decision = _decision(params)
        provenance = _provenance(params, "data_version", "model_version", "feature_version")
        raw_horizons = params.get("horizons")
        if not isinstance(raw_horizons, Sequence) or isinstance(raw_horizons, (str, bytes)):
            raise ValueError("horizons must be a non-empty array")
        horizons = tuple(item for item in raw_horizons if isinstance(item, Mapping))
        if not horizons or len(horizons) != len(raw_horizons):
            raise ValueError("each horizon must be an object with explicit clock semantics")
        bundle = services.get_market_state(
            symbol=_required_string(params, "symbol"),
            decision_at_utc=decision,
            horizons=horizons,
            provenance=provenance,
        )
        if bundle.decision_at_utc != decision:
            raise ValueError("market-state bundle must match decision_at_utc")
        return _response("get_market_state", params, bundle)

    def validate_research_data(params: Mapping[str, Any]) -> JsonObject:
        result = services.validate_research_data(
            dataset_id=_required_string(params, "dataset_id"),
            decision_at_utc=_decision(params),
            provenance=_provenance(params, "data_version", "schema_version"),
        )
        return _response("validate_research_data", params, result)

    def list_option_strategies(params: Mapping[str, Any]) -> JsonObject:
        _decision(params)
        provenance = _provenance(params, "registry_version")
        result = {
            "provenance": provenance,
            "strategies": [item.to_dict() for item in registry.specifications()],
        }
        return _response("list_option_strategies", params, result)

    def validate_strategy_spec(params: Mapping[str, Any]) -> JsonObject:
        _decision(params)
        provenance = _provenance(params, "registry_version")
        strategy_id, strategy_version, normalized = _strategy_inputs(params, registry)
        result = {
            "valid": True,
            "strategy": registry.resolve(strategy_id, strategy_version).specification.to_dict(),
            "normalized_parameters": normalized,
            "provenance": provenance,
        }
        return _response("validate_strategy_spec", params, result)

    def run_options_walkforward(params: Mapping[str, Any]) -> JsonObject:
        decision = _decision(params)
        provenance = _provenance(
            params,
            "data_version",
            "model_version",
            "objective_version",
            "config_version",
            "code_version",
        )
        sid, version, strategy_params, oid, objective, account = _evaluation_inputs(
            params, registry
        )
        result = services.run_options_walkforward(
            strategy_id=sid,
            strategy_version=version,
            strategy_parameters=strategy_params,
            objective_id=oid,
            objective_assumptions=objective,
            account_assumptions=account,
            decision_at_utc=decision,
            provenance=provenance,
        )
        return _response("run_options_walkforward", params, result)

    def backtest_option_strategy(params: Mapping[str, Any]) -> JsonObject:
        decision = _decision(params)
        provenance = _provenance(
            params,
            "data_version",
            "model_version",
            "objective_version",
            "config_version",
            "code_version",
        )
        sid, version, strategy_params, oid, objective, account = _evaluation_inputs(
            params, registry
        )
        result = services.backtest_option_strategy(
            strategy_id=sid,
            strategy_version=version,
            strategy_parameters=strategy_params,
            objective_id=oid,
            objective_assumptions=objective,
            account_assumptions=account,
            decision_at_utc=decision,
            provenance=provenance,
        )
        return _response("backtest_option_strategy", params, result)

    common: JsonObject = {
        "type": "object",
        "required": ["decision_at_utc", "provenance"],
        "properties": {
            "decision_at_utc": {"type": "string", "format": "date-time", "pattern": "Z$"},
            "provenance": {"type": "object", "minProperties": 1},
        },
        "additionalProperties": False,
    }

    def schema(required: Sequence[str], properties: Mapping[str, Any]) -> JsonObject:
        return {
            **common,
            "required": [*common["required"], *required],
            "properties": {**common["properties"], **properties},
        }

    strategy_properties = {
        "strategy_id": {"type": "string"},
        "strategy_version": {"type": "string"},
        "strategy_parameters": {"type": "object"},
    }
    evaluation_properties = {
        **strategy_properties,
        "objective_id": {"type": "string"},
        "objective_assumptions": {"type": "object", "minProperties": 1},
        "account_assumptions": {"type": "object", "minProperties": 1},
    }
    evaluation_required = [
        "strategy_id",
        "strategy_version",
        "objective_id",
        "objective_assumptions",
        "account_assumptions",
    ]

    return (
        ToolDefinition(
            "get_options_chain",
            "Return a saved point-in-time option chain; never places or changes an order.",
            get_options_chain,
            schema(["underlying"], {"underlying": {"type": "string"}}),
        ),
        ToolDefinition(
            "get_market_state",
            "Return strategy-neutral point-in-time forecasts with explicit horizons.",
            get_market_state,
            schema(
                ["symbol", "horizons"],
                {"symbol": {"type": "string"}, "horizons": {"type": "array", "minItems": 1}},
            ),
        ),
        ToolDefinition(
            "validate_research_data",
            "Validate a saved research dataset and report point-in-time/provenance defects.",
            validate_research_data,
            schema(["dataset_id"], {"dataset_id": {"type": "string"}}),
        ),
        ToolDefinition(
            "list_option_strategies",
            "List registered, versioned option research strategies.",
            list_option_strategies,
            common,
        ),
        ToolDefinition(
            "validate_strategy_spec",
            "Validate and normalize a versioned option strategy specification.",
            validate_strategy_spec,
            schema(["strategy_id", "strategy_version"], strategy_properties),
        ),
        ToolDefinition(
            "run_options_walkforward",
            "Run a read-only, point-in-time walk-forward research evaluation.",
            run_options_walkforward,
            schema(evaluation_required, evaluation_properties),
        ),
        ToolDefinition(
            "backtest_option_strategy",
            "Backtest a versioned option strategy with explicit objective and account assumptions.",
            backtest_option_strategy,
            schema(evaluation_required, evaluation_properties),
        ),
    )


def register_research_tools(
    server: ToolServer, services: ResearchServices, registry: StrategyRegistry
) -> tuple[str, ...]:
    """Register all research tools and return names in deterministic order."""

    definitions = build_research_tools(services, registry)
    for item in definitions:
        server.register_tool(
            name=item.name,
            description=item.description,
            handler=item.handler,
            schema=item.schema,
        )
    return tuple(item.name for item in definitions)
