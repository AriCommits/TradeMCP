"""Versioned option strategy input and result specifications."""

from .specifications import (
    AccountHolding,
    AccountSnapshot,
    CandidatePosition,
    MarginType,
    SimulationSummary,
    StrategySpecification,
)

from .base import (
    CapitalPolicy,
    DataRequirement,
    EntryPolicy,
    ExitPolicy,
    ForecastRequirement,
    OptionStrategy,
    PolicyAction,
    PolicyDecision,
    RollPolicy,
    SizingDecision,
    SizingPolicy,
    StrategyContext,
    StrategyRequirements,
)
from .registry import StrategyRegistry, validate_plugin
from .validation import ParameterField, ParameterKind, ParameterSchema

__all__ = [
    "AccountHolding",
    "AccountSnapshot",
    "CandidatePosition",
    "MarginType",
    "SimulationSummary",
    "StrategySpecification",
    "CapitalPolicy",
    "DataRequirement",
    "EntryPolicy",
    "ExitPolicy",
    "ForecastRequirement",
    "OptionStrategy",
    "ParameterField",
    "ParameterKind",
    "ParameterSchema",
    "PolicyAction",
    "PolicyDecision",
    "RollPolicy",
    "SizingDecision",
    "SizingPolicy",
    "StrategyContext",
    "StrategyRegistry",
    "StrategyRequirements",
    "validate_plugin",
]
