"""Strategy-neutral option objective scoring and deterministic stress grids."""

from .records import (
    EstimatedObjectiveInput,
    ObjectiveComponents,
    ObjectiveScore,
    ObjectiveWeights,
    PnlDistribution,
    PnlOutcome,
    RealizedObjectiveInput,
    ScoreKind,
)
from .scoring import score_estimate, score_realized
from .stress import (
    StressGrid,
    StressGridResult,
    StressPoint,
    StressPointResult,
    build_stress_grid,
    evaluate_stress_grid,
)

__all__ = [
    "EstimatedObjectiveInput",
    "ObjectiveComponents",
    "ObjectiveScore",
    "ObjectiveWeights",
    "PnlDistribution",
    "PnlOutcome",
    "RealizedObjectiveInput",
    "ScoreKind",
    "StressGrid",
    "StressGridResult",
    "StressPoint",
    "StressPointResult",
    "build_stress_grid",
    "evaluate_stress_grid",
    "score_estimate",
    "score_realized",
]
