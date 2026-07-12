"""Bounded implied-volatility inversion with inspectable diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import OptionType
from .pricing import black_scholes_merton_price, european_arbitrage_bounds


@dataclass(frozen=True)
class ImpliedVolatilityResult:
    volatility: float
    converged: bool
    iterations: int
    residual: float
    lower_bound: float
    upper_bound: float
    reason: str


def solve_implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    dividend_yield: float,
    option_type: OptionType,
    *,
    minimum_volatility: float = 0.0,
    maximum_volatility: float = 5.0,
    price_tolerance: float = 1e-8,
    volatility_tolerance: float = 1e-10,
    max_iterations: int = 200,
) -> ImpliedVolatilityResult:
    """Invert BSM by bisection inside an explicit volatility bracket.

    Invalid or model-inconsistent prices raise ``ValueError``. Exhausting the
    iteration budget returns ``converged=False`` so callers cannot accidentally
    mistake the last iterate for a solved volatility.
    """
    numeric = {
        "market_price": market_price,
        "minimum_volatility": minimum_volatility,
        "maximum_volatility": maximum_volatility,
        "price_tolerance": price_tolerance,
        "volatility_tolerance": volatility_tolerance,
    }
    if any(not math.isfinite(value) for value in numeric.values()):
        raise ValueError("solver prices, bounds, and tolerances must be finite")
    if market_price < 0.0:
        raise ValueError("market_price cannot be negative")
    if time_to_expiry_years <= 0.0:
        raise ValueError("implied volatility is not identifiable at or after expiry")
    if minimum_volatility < 0.0 or maximum_volatility <= minimum_volatility:
        raise ValueError("volatility bounds must satisfy 0 <= minimum < maximum")
    if price_tolerance <= 0.0 or volatility_tolerance <= 0.0:
        raise ValueError("solver tolerances must be positive")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations <= 0
    ):
        raise ValueError("max_iterations must be a positive integer")

    lower_price_bound, upper_price_bound = european_arbitrage_bounds(
        spot, strike, time_to_expiry_years, rate, dividend_yield, option_type
    )
    if (
        market_price < lower_price_bound - price_tolerance
        or market_price > upper_price_bound + price_tolerance
    ):
        raise ValueError(
            f"market_price {market_price} violates European arbitrage bounds "
            f"[{lower_price_bound}, {upper_price_bound}]"
        )

    low = minimum_volatility
    high = maximum_volatility
    low_residual = (
        black_scholes_merton_price(
            spot, strike, time_to_expiry_years, rate, low, dividend_yield, option_type
        )
        - market_price
    )
    high_residual = (
        black_scholes_merton_price(
            spot, strike, time_to_expiry_years, rate, high, dividend_yield, option_type
        )
        - market_price
    )
    if abs(low_residual) <= price_tolerance:
        return ImpliedVolatilityResult(low, True, 0, low_residual, low, high, "lower_bound")
    if high_residual < -price_tolerance:
        raise ValueError("market_price is not bracketed by the configured volatility bounds")
    if abs(high_residual) <= price_tolerance:
        return ImpliedVolatilityResult(high, True, 0, high_residual, low, high, "upper_bound")

    midpoint = 0.5 * (low + high)
    residual = math.inf
    for iteration in range(1, max_iterations + 1):
        midpoint = 0.5 * (low + high)
        residual = (
            black_scholes_merton_price(
                spot,
                strike,
                time_to_expiry_years,
                rate,
                midpoint,
                dividend_yield,
                option_type,
            )
            - market_price
        )
        if abs(residual) <= price_tolerance:
            return ImpliedVolatilityResult(
                midpoint, True, iteration, residual, low, high, "price_tolerance"
            )
        if residual > 0.0:
            high = midpoint
        else:
            low = midpoint
        if high - low <= volatility_tolerance:
            return ImpliedVolatilityResult(
                midpoint, True, iteration, residual, low, high, "volatility_tolerance"
            )
    return ImpliedVolatilityResult(
        midpoint, False, max_iterations, residual, low, high, "max_iterations"
    )
