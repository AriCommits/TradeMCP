"""Strategy plug-in and policy contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from trading.forecasts.targets import ForecastBundle, ForecastTarget
from trading.options.contracts import OptionLeg, TimeHorizonKind, require_utc
from trading.portfolio.records import CapitalRequirement
from trading.strategies.specifications import AccountSnapshot, StrategySpecification
from trading.strategies.validation import ParameterSchema


class DataRequirement(str, Enum):
    OPTION_CHAIN = "option_chain"
    UNDERLYING_MARK = "underlying_mark"
    ACCOUNT_SNAPSHOT = "account_snapshot"
    CORPORATE_EVENTS = "corporate_events"
    DIVIDENDS = "dividends"
    RATES = "rates"
    EXCHANGE_CALENDAR = "exchange_calendar"


@dataclass(frozen=True, order=True)
class ForecastRequirement:
    target: ForecastTarget
    horizon_kind: TimeHorizonKind
    minimum_model_version: str | None = None


@dataclass(frozen=True)
class StrategyRequirements:
    data: tuple[DataRequirement, ...]
    forecasts: tuple[ForecastRequirement, ...]

    def __post_init__(self) -> None:
        if len(set(self.data)) != len(self.data):
            raise ValueError("data requirements must be unique")
        pairs = {(item.target, item.horizon_kind) for item in self.forecasts}
        if len(pairs) != len(self.forecasts):
            raise ValueError("forecast target and horizon requirements must be unique")


@dataclass(frozen=True)
class StrategyContext:
    """Point-in-time inputs shared by strategy policies."""

    decision_at_utc: datetime
    parameters: Mapping[str, Any]
    legs: tuple[OptionLeg, ...]
    account: AccountSnapshot
    forecasts: ForecastBundle | None = None

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if self.account.as_of_utc > self.decision_at_utc:
            raise ValueError("account snapshot cannot be from after the decision timestamp")
        if self.forecasts is not None and self.forecasts.decision_at_utc != self.decision_at_utc:
            raise ValueError("forecast bundle must match the decision timestamp")


class PolicyAction(str, Enum):
    ENTER = "enter"
    HOLD = "hold"
    EXIT = "exit"
    ROLL = "roll"
    REJECT = "reject"


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reasons: tuple[str, ...]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reasons:
            raise ValueError("policy decisions require at least one reason")


@dataclass(frozen=True)
class SizingDecision:
    contracts: int
    reason: str

    def __post_init__(self) -> None:
        if self.contracts < 0 or not self.reason:
            raise ValueError("sizing requires a non-negative contract count and reason")


@runtime_checkable
class EntryPolicy(Protocol):
    def evaluate(self, context: StrategyContext) -> PolicyDecision: ...


@runtime_checkable
class ExitPolicy(Protocol):
    def evaluate(self, context: StrategyContext) -> PolicyDecision: ...


@runtime_checkable
class RollPolicy(Protocol):
    def evaluate(self, context: StrategyContext) -> PolicyDecision: ...


@runtime_checkable
class SizingPolicy(Protocol):
    def size(self, context: StrategyContext, *, capital_limit: Decimal) -> SizingDecision: ...


@runtime_checkable
class CapitalPolicy(Protocol):
    def requirement(self, context: StrategyContext) -> CapitalRequirement: ...


@runtime_checkable
class OptionStrategy(Protocol):
    """Complete read-only strategy plug-in contract consumed by the registry."""

    @property
    def specification(self) -> StrategySpecification: ...

    @property
    def parameter_schema(self) -> ParameterSchema: ...

    @property
    def requirements(self) -> StrategyRequirements: ...

    @property
    def entry_policy(self) -> EntryPolicy: ...

    @property
    def exit_policy(self) -> ExitPolicy: ...

    @property
    def roll_policy(self) -> RollPolicy: ...

    @property
    def sizing_policy(self) -> SizingPolicy: ...

    @property
    def capital_policy(self) -> CapitalPolicy: ...
