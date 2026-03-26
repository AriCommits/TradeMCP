from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .strategy_registry import StrategyRegistry


@dataclass(frozen=True)
class StrategySuggestion:
    strategy_id: str
    market: str
    score: float
    confidence: float
    expected_edge_bps: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ResearchOrchestrator:
    def __init__(self, registry: StrategyRegistry | None = None) -> None:
        self.registry = registry or StrategyRegistry()

    def rank_strategies(
        self,
        *,
        market: str,
        predictions: pd.DataFrame,
        vol_forecasts: pd.DataFrame,
        vi_scores: pd.DataFrame,
        max_shortfall_bps: float,
    ) -> list[StrategySuggestion]:
        specs = self.registry.for_market(market)
        if not specs:
            return []

        edge_bps = float(np.nan_to_num(predictions.get("target", pd.Series(dtype=float)).abs().median() * 10000.0))
        vol_level = float(np.nan_to_num(vol_forecasts.get("vol_forecast", pd.Series(dtype=float)).median(), nan=0.01))
        vi_mean = float(np.nan_to_num(vi_scores.get("vi", pd.Series(dtype=float)).mean(), nan=1.0))

        stability = 1.0 / (1.0 + max(vi_mean, 0.0))
        regime_support = 0.0
        if "regime" in predictions.columns and not predictions.empty:
            regime_support = float((predictions["regime"] >= 0).mean())

        vol_pressure = min(vol_level * 5000.0 / max(max_shortfall_bps, 1e-6), 1.0)
        execution_feasibility = float(max(0.0, 1.0 - vol_pressure))
        edge_component = float(min(edge_bps / max(max_shortfall_bps, 1e-6), 1.0))

        risk_multiplier = {
            "conservative": 0.85,
            "balanced": 1.0,
            "aggressive": 1.15,
        }

        ranked: list[StrategySuggestion] = []
        for spec in specs:
            mult = risk_multiplier.get(spec.risk_profile, 1.0)
            score = (
                edge_component * 0.4
                + stability * 0.2
                + execution_feasibility * 0.3
                + regime_support * 0.1
            ) * mult
            confidence = max(0.0, min(score, 1.0))
            expected_edge = edge_bps * mult * execution_feasibility

            reasons = (
                f"edge_bps={edge_bps:.2f}",
                f"stability={stability:.3f}",
                f"execution_feasibility={execution_feasibility:.3f}",
                f"risk_profile={spec.risk_profile}",
            )
            ranked.append(
                StrategySuggestion(
                    strategy_id=spec.strategy_id,
                    market=spec.market,
                    score=float(score),
                    confidence=float(confidence),
                    expected_edge_bps=float(expected_edge),
                    reasons=reasons,
                )
            )

        ranked.sort(key=lambda item: (item.score, item.expected_edge_bps), reverse=True)
        return ranked
