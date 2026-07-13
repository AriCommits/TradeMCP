"""Deterministic spot x IV x time x liquidity stress grids."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from itertools import product

from trading.options.contracts import VersionedRecord


@dataclass(frozen=True)
class StressGrid(VersionedRecord):
    spot_shocks: tuple[Decimal, ...]
    iv_shocks: tuple[Decimal, ...]
    time_fractions: tuple[Decimal, ...]
    liquidity_multipliers: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        axes = (self.spot_shocks, self.iv_shocks, self.time_fractions, self.liquidity_multipliers)
        if any(not axis for axis in axes):
            raise ValueError("every stress axis must be non-empty")
        if any(len(set(axis)) != len(axis) for axis in axes):
            raise ValueError("stress axis values must be unique")
        if any(value < 0 or value > 1 for value in self.time_fractions):
            raise ValueError("time fractions must be in [0, 1]")
        if any(value <= 0 for value in self.liquidity_multipliers):
            raise ValueError("liquidity multipliers must be positive")


@dataclass(frozen=True)
class StressPoint(VersionedRecord):
    scenario_id: str
    ordinal: int
    spot_shock: Decimal
    iv_shock: Decimal
    time_fraction: Decimal
    liquidity_multiplier: Decimal

    def __post_init__(self) -> None:
        if not self.scenario_id or self.ordinal < 0:
            raise ValueError("stress point requires an id and non-negative ordinal")


@dataclass(frozen=True)
class StressPointResult(VersionedRecord):
    point: StressPoint
    pnl: Decimal


@dataclass(frozen=True)
class StressGridResult(VersionedRecord):
    result_id: str
    input_identity: str
    evaluator_id: str
    evaluator_version: str
    grid: StressGrid
    results: tuple[StressPointResult, ...]
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        if not self.result_id or not self.input_identity:
            raise ValueError("stress result and input identities are required")
        if not self.evaluator_id or not self.evaluator_version or not self.results:
            raise ValueError("evaluator identity and stress results are required")


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


def build_stress_grid(grid: StressGrid) -> tuple[StressPoint, ...]:
    """Canonicalize axis order so equivalent grids produce identical scenarios."""

    combinations = product(
        sorted(grid.spot_shocks),
        sorted(grid.iv_shocks),
        sorted(grid.time_fractions),
        sorted(grid.liquidity_multipliers),
    )
    points: list[StressPoint] = []
    for ordinal, values in enumerate(combinations):
        payload = tuple(str(value) for value in values)
        points.append(StressPoint(f"stress-{_digest(payload)}", ordinal, *values))
    return tuple(points)


def _canonical_grid(grid: StressGrid) -> StressGrid:
    return StressGrid(
        spot_shocks=tuple(sorted(grid.spot_shocks)),
        iv_shocks=tuple(sorted(grid.iv_shocks)),
        time_fractions=tuple(sorted(grid.time_fractions)),
        liquidity_multipliers=tuple(sorted(grid.liquidity_multipliers)),
    )


def evaluate_stress_grid(
    *,
    grid: StressGrid,
    base_input_identity: str,
    evaluator_id: str,
    evaluator_version: str,
    evaluator: Callable[[StressPoint], Decimal],
) -> StressGridResult:
    if not base_input_identity or not evaluator_id or not evaluator_version:
        raise ValueError("base input and evaluator identity/version are required")
    canonical_grid = _canonical_grid(grid)
    points = build_stress_grid(canonical_grid)
    input_identity = _digest(
        {
            "base_input_identity": base_input_identity,
            "evaluator_id": evaluator_id,
            "evaluator_version": evaluator_version,
            "grid": canonical_grid.to_dict(),
        }
    )
    results = tuple(StressPointResult(point, evaluator(point)) for point in points)
    result_id = f"stress-result-{_digest([input_identity, [item.to_dict() for item in results]])}"
    return StressGridResult(
        result_id=result_id,
        input_identity=input_identity,
        evaluator_id=evaluator_id,
        evaluator_version=evaluator_version,
        grid=canonical_grid,
        results=results,
        metadata={
            "axis_order": "spot_shock,iv_shock,time_fraction,liquidity_multiplier",
            "scenario_count": str(len(results)),
            "base_input_identity": base_input_identity,
        },
    )
