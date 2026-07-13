"""Small deterministic statistical summaries for walk-forward evidence."""

from __future__ import annotations

import math
from decimal import Decimal
from statistics import NormalDist

from .records import ConfidenceInterval


def mean_confidence_interval(
    values: tuple[Decimal, ...], confidence_level: Decimal
) -> ConfidenceInterval | None:
    if not values:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    if len(values) == 1:
        return ConfidenceInterval(
            mean=mean, lower=mean, upper=mean, confidence_level=confidence_level
        )
    floats = [float(item) for item in values]
    variance = sum((item - float(mean)) ** 2 for item in floats) / (len(floats) - 1)
    z_value = NormalDist().inv_cdf((1 + float(confidence_level)) / 2)
    margin = Decimal(str(z_value * math.sqrt(variance / len(floats))))
    return ConfidenceInterval(
        mean=mean,
        lower=mean - margin,
        upper=mean + margin,
        confidence_level=confidence_level,
    )


def effective_sample_size(values: tuple[Decimal, ...]) -> Decimal:
    """Autocorrelation-adjusted ESS using the initial positive sequence."""

    size = len(values)
    if size < 2:
        return Decimal(size)
    floats = [float(item) for item in values]
    mean = sum(floats) / size
    denominator = sum((item - mean) ** 2 for item in floats)
    if denominator == 0:
        return Decimal(size)
    correlation_sum = 0.0
    for lag in range(1, size):
        numerator = sum(
            (floats[index] - mean) * (floats[index + lag] - mean) for index in range(size - lag)
        )
        correlation = numerator / denominator
        if correlation <= 0:
            break
        correlation_sum += correlation
    ess = size / (1 + 2 * correlation_sum)
    return Decimal(str(max(1.0, min(float(size), ess))))
