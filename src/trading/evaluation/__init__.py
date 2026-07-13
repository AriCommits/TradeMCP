"""Point-in-time, strategy-neutral options research evaluation."""

from .comparison import (
    RiskOutcomeSupplement,
    StrategyComparisonMetrics,
    StrategyComparisonReport,
    compare_strategy_evaluations,
)
from .engine import evaluate_walk_forward
from .folds import build_folds
from .records import (
    AggregateAttribution,
    ConfidenceInterval,
    EvidenceStatus,
    EvaluationScope,
    EvaluationVersions,
    FoldKind,
    OutcomeAttribution,
    SavedOutcomeObservation,
    WalkForwardConfig,
    WalkForwardEvaluation,
    WalkForwardFold,
)
from .statistics import effective_sample_size, mean_confidence_interval

__all__ = [
    "AggregateAttribution",
    "ConfidenceInterval",
    "EvidenceStatus",
    "EvaluationScope",
    "EvaluationVersions",
    "FoldKind",
    "OutcomeAttribution",
    "RiskOutcomeSupplement",
    "StrategyComparisonMetrics",
    "StrategyComparisonReport",
    "SavedOutcomeObservation",
    "WalkForwardConfig",
    "WalkForwardEvaluation",
    "WalkForwardFold",
    "build_folds",
    "compare_strategy_evaluations",
    "effective_sample_size",
    "evaluate_walk_forward",
    "mean_confidence_interval",
]
