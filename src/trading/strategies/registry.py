"""Deterministic in-process discovery for validated option strategy plug-ins."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from trading.forecasts.targets import ForecastTarget
from trading.strategies.base import (
    CapitalPolicy,
    EntryPolicy,
    ExitPolicy,
    OptionStrategy,
    RollPolicy,
    SizingPolicy,
)
from trading.strategies.specifications import StrategySpecification
from trading.strategies.validation import validate_strategy_id, validate_version


class StrategyRegistry:
    """Explicit registry; discovery never depends on filesystem/import ordering."""

    def __init__(self) -> None:
        self._plugins: dict[tuple[str, str], OptionStrategy] = {}

    def register(self, plugin: OptionStrategy) -> None:
        if not isinstance(plugin, OptionStrategy):
            raise TypeError("strategy plug-in does not implement OptionStrategy")
        validate_plugin(plugin)
        spec = plugin.specification
        key = (spec.strategy_id, spec.strategy_version)
        if key in self._plugins:
            raise ValueError(f"strategy plug-in already registered: {key!r}")
        self._plugins[key] = plugin

    def discover(self, plugins: Iterable[OptionStrategy]) -> tuple[tuple[str, str], ...]:
        """Register an explicit collection in stable identity order."""

        ordered = sorted(
            plugins,
            key=lambda item: (item.specification.strategy_id, item.specification.strategy_version),
        )
        for plugin in ordered:
            self.register(plugin)
        return self.keys()

    def resolve(self, strategy_id: str, strategy_version: str) -> OptionStrategy:
        key = (strategy_id, strategy_version)
        try:
            return self._plugins[key]
        except KeyError as exc:
            raise KeyError(f"strategy plug-in not found: {key!r}") from exc

    def keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._plugins))

    def specifications(self) -> tuple[StrategySpecification, ...]:
        return tuple(self._plugins[key].specification for key in self.keys())

    def validated_parameters(
        self,
        strategy_id: str,
        strategy_version: str,
        parameters: Mapping[str, object],
    ) -> dict[str, object]:
        plugin = self.resolve(strategy_id, strategy_version)
        return plugin.parameter_schema.validate(parameters)

    def configured(
        self,
        strategy_id: str,
        strategy_version: str,
        parameters: Mapping[str, object],
    ) -> StrategySpecification:
        plugin = self.resolve(strategy_id, strategy_version)
        normalized = plugin.parameter_schema.validate(parameters)
        return replace(plugin.specification, parameters=normalized)


def validate_plugin(plugin: OptionStrategy) -> None:
    spec = plugin.specification
    validate_strategy_id(spec.strategy_id)
    validate_version(spec.strategy_version, field_name="strategy_version")
    if plugin.parameter_schema.schema_version != spec.strategy_version:
        raise ValueError("parameter schema version must match strategy_version")

    policies = (
        ("entry_policy", plugin.entry_policy, EntryPolicy),
        ("exit_policy", plugin.exit_policy, ExitPolicy),
        ("roll_policy", plugin.roll_policy, RollPolicy),
        ("sizing_policy", plugin.sizing_policy, SizingPolicy),
        ("capital_policy", plugin.capital_policy, CapitalPolicy),
    )
    invalid_policies = [
        name for name, policy, contract in policies if not isinstance(policy, contract)
    ]
    if invalid_policies:
        raise TypeError(f"strategy policies do not implement their contracts: {invalid_policies!r}")

    declared_forecasts = tuple(sorted(spec.required_forecasts))
    required_forecasts = tuple(
        sorted({item.target.value for item in plugin.requirements.forecasts})
    )
    unknown = [name for name in declared_forecasts if name not in ForecastTarget._value2member_map_]
    if unknown:
        raise ValueError(f"unknown forecast targets in specification: {unknown!r}")
    if declared_forecasts != required_forecasts:
        raise ValueError("specification and plug-in forecast requirements disagree")

    required_data = {item.value for item in plugin.requirements.data}
    missing_features = sorted(set(spec.required_features).difference(required_data))
    if missing_features:
        raise ValueError(
            "specification required_features must be declared data requirements: "
            f"{missing_features!r}"
        )
