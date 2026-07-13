from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import pytest

from trading.forecasts.targets import ForecastTarget
from trading.options.contracts import TimeHorizonKind
from trading.strategies.base import (
    DataRequirement,
    ForecastRequirement,
    StrategyRequirements,
)
from trading.strategies.registry import StrategyRegistry
from trading.strategies.specifications import MarginType, StrategySpecification
from trading.strategies.validation import ParameterField, ParameterKind, ParameterSchema


class _PolicySet:
    def evaluate(self, context: object) -> object:
        return context

    def size(self, context: object, *, capital_limit: object) -> object:
        return context, capital_limit

    def requirement(self, context: object) -> object:
        return context


@dataclass
class _Plugin:
    specification: StrategySpecification
    parameter_schema: ParameterSchema
    requirements: StrategyRequirements
    entry_policy: Any = _PolicySet()
    exit_policy: Any = _PolicySet()
    roll_policy: Any = _PolicySet()
    sizing_policy: Any = _PolicySet()
    capital_policy: Any = _PolicySet()


def _plugin(strategy_id: str = "weekend_short_put") -> _Plugin:
    requirements = StrategyRequirements(
        data=(DataRequirement.OPTION_CHAIN, DataRequirement.ACCOUNT_SNAPSHOT),
        forecasts=(
            ForecastRequirement(ForecastTarget.GAP_RETURN, TimeHorizonKind.OVERNIGHT_INTERVALS),
        ),
    )
    return _Plugin(
        specification=StrategySpecification(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            family="short_premium",
            parameters={},
            required_forecasts=(ForecastTarget.GAP_RETURN.value,),
            required_features=("option_chain", "account_snapshot"),
            allowed_objectives=("tail_adjusted_return",),
            supported_margin_types=(MarginType.CASH,),
        ),
        parameter_schema=ParameterSchema(
            schema_version="1.0.0",
            fields={
                "delta": ParameterField(ParameterKind.NUMBER, minimum=0.05, maximum=0.5),
                "max_contracts": ParameterField(
                    ParameterKind.INTEGER, required=False, default=1, minimum=1
                ),
            },
        ),
        requirements=requirements,
    )


def test_registry_discovers_plugins_in_deterministic_identity_order() -> None:
    registry = StrategyRegistry()
    keys = registry.discover((_plugin("weekend_short_put"), _plugin("cash_secured_put")))

    assert keys == (("cash_secured_put", "1.0.0"), ("weekend_short_put", "1.0.0"))
    assert registry.resolve("weekend_short_put", "1.0.0").specification.family == "short_premium"


def test_registry_rejects_duplicate_identity() -> None:
    registry = StrategyRegistry()
    registry.register(_plugin())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_plugin())


def test_parameter_schema_normalizes_defaults_and_rejects_invalid_values() -> None:
    registry = StrategyRegistry()
    registry.register(_plugin())

    normalized = registry.validated_parameters("weekend_short_put", "1.0.0", {"delta": 0.2})
    assert normalized == {"delta": 0.2, "max_contracts": 1}

    with pytest.raises(ValueError, match="unknown strategy parameters"):
        registry.validated_parameters(
            "weekend_short_put", "1.0.0", {"delta": 0.2, "surprise": True}
        )
    with pytest.raises(ValueError, match="delta must be <= 0.5"):
        registry.validated_parameters("weekend_short_put", "1.0.0", {"delta": 0.9})


def test_plugin_validation_detects_contract_drift() -> None:
    plugin = _plugin()
    mismatched = replace(
        plugin,
        specification=replace(
            plugin.specification,
            required_forecasts=(ForecastTarget.REALIZED_VOLATILITY.value,),
        ),
    )

    with pytest.raises(ValueError, match="forecast requirements disagree"):
        StrategyRegistry().register(mismatched)


def test_plugin_validation_requires_versioned_parameter_schema() -> None:
    plugin = _plugin()
    mismatched = replace(
        plugin,
        parameter_schema=replace(plugin.parameter_schema, schema_version="2.0.0"),
    )

    with pytest.raises(ValueError, match="schema version must match"):
        StrategyRegistry().register(mismatched)
