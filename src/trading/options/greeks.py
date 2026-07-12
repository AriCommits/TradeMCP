"""Black-Scholes-Merton Greeks with explicit units and boundary behavior."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import OptionType
from .pricing import _normal_cdf, _validate_inputs


@dataclass(frozen=True)
class OptionGreeks:
    """Greeks per option share before applying a contract multiplier.

    ``delta`` is price change per 1 currency-unit spot move; ``gamma`` is delta
    change per 1-unit spot move; ``vega`` is price change per one volatility
    percentage point; ``theta`` is price change per one calendar day using an
    Actual/365 convention; and ``rho`` is price change per one rate percentage
    point. All values are per option share before the contract multiplier.
    """

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def black_scholes_merton_greeks(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    volatility: float,
    dividend_yield: float,
    option_type: OptionType,
) -> OptionGreeks:
    """Calculate analytic Greeks; reject boundaries where derivatives are ambiguous."""
    _validate_inputs(spot, strike, time_to_expiry_years, rate, volatility, dividend_yield)
    if time_to_expiry_years == 0.0:
        raise ValueError("Greeks are undefined at expiry; use intrinsic value for price")

    discounted_spot = spot * math.exp(-dividend_yield * time_to_expiry_years)
    discounted_strike = strike * math.exp(-rate * time_to_expiry_years)
    if volatility == 0.0:
        difference = discounted_spot - discounted_strike
        if math.isclose(difference, 0.0, rel_tol=0.0, abs_tol=1e-14):
            raise ValueError("Greeks are undefined at the zero-volatility payoff boundary")
        call_itm = difference > 0.0
        if option_type is OptionType.CALL:
            if not call_itm:
                return OptionGreeks(0.0, 0.0, 0.0, 0.0, 0.0)
            return OptionGreeks(
                math.exp(-dividend_yield * time_to_expiry_years),
                0.0,
                0.0,
                (dividend_yield * discounted_spot - rate * discounted_strike) / 365.0,
                time_to_expiry_years * discounted_strike / 100.0,
            )
        if call_itm:
            return OptionGreeks(0.0, 0.0, 0.0, 0.0, 0.0)
        return OptionGreeks(
            -math.exp(-dividend_yield * time_to_expiry_years),
            0.0,
            0.0,
            (rate * discounted_strike - dividend_yield * discounted_spot) / 365.0,
            -time_to_expiry_years * discounted_strike / 100.0,
        )

    sqrt_time = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike)
        + (rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry_years
    ) / (volatility * sqrt_time)
    d2 = d1 - volatility * sqrt_time
    density = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
    gamma = (
        math.exp(-dividend_yield * time_to_expiry_years) * density / (spot * volatility * sqrt_time)
    )
    vega = discounted_spot * density * sqrt_time / 100.0
    annual_theta = -(discounted_spot * volatility * density) / (2.0 * sqrt_time)
    if option_type is OptionType.CALL:
        return OptionGreeks(
            math.exp(-dividend_yield * time_to_expiry_years) * _normal_cdf(d1),
            gamma,
            vega,
            (
                annual_theta
                - rate * discounted_strike * _normal_cdf(d2)
                + dividend_yield * discounted_spot * _normal_cdf(d1)
            )
            / 365.0,
            time_to_expiry_years * discounted_strike * _normal_cdf(d2) / 100.0,
        )
    return OptionGreeks(
        math.exp(-dividend_yield * time_to_expiry_years) * (_normal_cdf(d1) - 1.0),
        gamma,
        vega,
        (
            annual_theta
            + rate * discounted_strike * _normal_cdf(-d2)
            - dividend_yield * discounted_spot * _normal_cdf(-d1)
        )
        / 365.0,
        -time_to_expiry_years * discounted_strike * _normal_cdf(-d2) / 100.0,
    )
