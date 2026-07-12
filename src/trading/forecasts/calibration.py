"""Small deterministic calibration reports for statistical forecast baselines."""

from __future__ import annotations

import numpy as np


def distribution_metrics(samples: np.ndarray) -> dict[str, float]:
    """Compare an expanding-window median forecast with a last-value naive forecast."""

    clean = samples[np.isfinite(samples)].astype(float)
    if clean.size < 3:
        return {
            "backtest_count": 0.0,
            "model_mae": 0.0,
            "naive_mae": 0.0,
            "mae_skill": 0.0,
            "quantile_90_coverage": 0.0,
        }
    model_errors: list[float] = []
    naive_errors: list[float] = []
    covered: list[float] = []
    start = max(2, min(20, clean.size // 3))
    for index in range(start, clean.size):
        train = clean[:index]
        actual = clean[index]
        model_errors.append(abs(float(np.median(train)) - actual))
        naive_errors.append(abs(float(train[-1]) - actual))
        low, high = np.quantile(train, [0.05, 0.95])
        covered.append(float(low <= actual <= high))
    model_mae = float(np.mean(model_errors))
    naive_mae = float(np.mean(naive_errors))
    skill = 0.0 if naive_mae == 0.0 else 1.0 - model_mae / naive_mae
    return {
        "backtest_count": float(len(model_errors)),
        "model_mae": model_mae,
        "naive_mae": naive_mae,
        "mae_skill": float(skill),
        "quantile_90_coverage": float(np.mean(covered)),
    }


def probability_metrics(outcomes: np.ndarray) -> dict[str, float]:
    """Expanding-frequency Brier score versus a constant 50% naive probability."""

    clean = outcomes[np.isfinite(outcomes)].astype(float)
    if clean.size < 3:
        return {"backtest_count": 0.0, "brier_score": 0.0, "naive_brier": 0.0, "brier_skill": 0.0}
    start = max(2, min(20, clean.size // 3))
    squared: list[float] = []
    naive: list[float] = []
    for index in range(start, clean.size):
        probability = float(np.mean(clean[:index]))
        squared.append((probability - clean[index]) ** 2)
        naive.append((0.5 - clean[index]) ** 2)
    score = float(np.mean(squared))
    naive_score = float(np.mean(naive))
    skill = 0.0 if naive_score == 0.0 else 1.0 - score / naive_score
    return {
        "backtest_count": float(len(squared)),
        "brier_score": score,
        "naive_brier": naive_score,
        "brier_skill": float(skill),
    }
