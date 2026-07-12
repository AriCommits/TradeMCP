"""Validated baseline option-pricing functions.

All prices are per option share, rates and dividend yields are continuously
compounded annual decimal rates, volatility is an annual decimal standard
deviation, and time is measured in years.  No minimum time or volatility is
silently substituted: expiry and deterministic zero-volatility cases have
explicit limits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import ExerciseStyle, OptionType


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _require_finite(**values: float) -> None:
    for name, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")


def _validate_inputs(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float,
) -> None:
    _require_finite(
        spot=spot,
        strike=strike,
        time_to_expiry_years=time_to_expiry_years,
        rate=rate,
        volatility=volatility,
        dividend_yield=dividend_yield,
    )
    if spot <= 0.0:
        raise ValueError("spot must be positive")
    if strike <= 0.0:
        raise ValueError("strike must be positive")
    if time_to_expiry_years < 0.0:
        raise ValueError("time_to_expiry_years cannot be negative")
    if volatility < 0.0:
        raise ValueError("volatility cannot be negative")


def intrinsic_value(spot: float, strike: float, option_type: OptionType) -> float:
    """Return the immediate-exercise value per share."""
    _require_finite(spot=spot, strike=strike)
    if spot <= 0.0 or strike <= 0.0:
        raise ValueError("spot and strike must be positive")
    sign = 1.0 if option_type is OptionType.CALL else -1.0
    return max(sign * (spot - strike), 0.0)


def european_arbitrage_bounds(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    dividend_yield: float,
    option_type: OptionType,
) -> tuple[float, float]:
    """Return model-independent lower/upper bounds under continuous carry."""
    _validate_inputs(spot, strike, time_to_expiry_years, rate, 0.0, dividend_yield)
    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry_years)
    discounted_strike = strike * math.exp(-rate * time_to_expiry_years)
    if option_type is OptionType.CALL:
        return max(discounted_spot - discounted_strike, 0.0), discounted_spot
    return max(discounted_strike - discounted_spot, 0.0), discounted_strike


def black_scholes_merton_price(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float,
    option_type: OptionType,
) -> float:
    """Price a European option, including exact expiry and zero-volatility limits."""
    _validate_inputs(spot, strike, time_to_expiry_years, rate, volatility, dividend_yield)
    if time_to_expiry_years == 0.0:
        return intrinsic_value(spot, strike, option_type)

    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry_years)
    discounted_strike = strike * math.exp(-rate * time_to_expiry_years)
    if volatility == 0.0:
        if option_type is OptionType.CALL:
            return max(discounted_spot - discounted_strike, 0.0)
        return max(discounted_strike - discounted_spot, 0.0)

    sqrt_time = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry_years
    ) / (volatility * sqrt_time)
    d2 = d1 - volatility * sqrt_time
    if option_type is OptionType.CALL:
        return discounted_spot * _normal_cdf(d1) - discounted_strike * _normal_cdf(d2)
    return discounted_strike * _normal_cdf(-d2) - discounted_spot * _normal_cdf(-d1)


@dataclass(frozen=True)
class BinomialDiagnostics:
    """Numerical parameters used by a Cox-Ross-Rubinstein valuation."""

    steps: int
    up_factor: float | None
    down_factor: float | None
    risk_neutral_probability: float | None
    deterministic_limit: bool = False
    expiry_limit: bool = False


@dataclass(frozen=True)
class BinomialPriceResult:
    price: float
    diagnostics: BinomialDiagnostics


def _deterministic_american_price(
    spot: float,
    strike: float,
    time: float,
    rate: float,
    dividend_yield: float,
    option_type: OptionType,
    steps: int,
) -> float:
    best = intrinsic_value(spot, strike, option_type)
    for index in range(1, steps + 1):
        exercise_time = time * index / steps
        future_spot = spot * math.exp((rate - dividend_yield) * exercise_time)
        discounted = math.exp(-rate * exercise_time) * intrinsic_value(
            future_spot, strike, option_type
        )
        best = max(best, discounted)
    return best


def binomial_price(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float,
    option_type: OptionType,
    exercise_style: ExerciseStyle,
    *,
    steps: int = 200,
) -> BinomialPriceResult:
    """Price an American or European option using a validated CRR tree.

    A risk-neutral probability outside ``[0, 1]`` is rejected because that tree
    violates the one-step no-arbitrage condition; increasing ``steps`` is often
    the appropriate remedy.
    """
    _validate_inputs(spot, strike, time_to_expiry_years, rate, volatility, dividend_yield)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
        raise ValueError("steps must be a positive integer")
    if time_to_expiry_years == 0.0:
        return BinomialPriceResult(
            intrinsic_value(spot, strike, option_type),
            BinomialDiagnostics(steps, None, None, None, expiry_limit=True),
        )
    if volatility == 0.0:
        if exercise_style is ExerciseStyle.AMERICAN:
            price = _deterministic_american_price(
                spot,
                strike,
                time_to_expiry_years,
                rate,
                dividend_yield,
                option_type,
                steps,
            )
        else:
            price = black_scholes_merton_price(
                spot,
                strike,
                time_to_expiry_years,
                rate,
                0.0,
                dividend_yield,
                option_type,
            )
        return BinomialPriceResult(
            price,
            BinomialDiagnostics(steps, None, None, None, deterministic_limit=True),
        )

    dt = time_to_expiry_years / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    probability = (math.exp((rate - dividend_yield) * dt) - down) / (up - down)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError(
            "CRR risk-neutral probability is outside [0, 1]; tree violates "
            "the no-arbitrage condition (try more steps)"
        )
    discount = math.exp(-rate * dt)
    sign = 1.0 if option_type is OptionType.CALL else -1.0
    values = [
        max(sign * (spot * up**index * down ** (steps - index) - strike), 0.0)
        for index in range(steps + 1)
    ]
    for step in range(steps - 1, -1, -1):
        for index in range(step + 1):
            continuation = discount * (
                probability * values[index + 1] + (1.0 - probability) * values[index]
            )
            if exercise_style is ExerciseStyle.AMERICAN:
                node_spot = spot * up**index * down ** (step - index)
                continuation = max(continuation, max(sign * (node_spot - strike), 0.0))
            values[index] = continuation
    return BinomialPriceResult(values[0], BinomialDiagnostics(steps, up, down, probability))
