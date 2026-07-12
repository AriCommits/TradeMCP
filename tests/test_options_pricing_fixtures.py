from __future__ import annotations

import json
import math
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "options_pricing"


def _load(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _black_scholes(case: dict, minimum_time: float, minimum_volatility: float) -> dict:
    values = case["input"]
    spot = values["spot"]
    strike = values["strike"]
    time = max(values["time_to_expiry_years"], minimum_time)
    rate = values["rate"]
    volatility = max(values["volatility"], minimum_volatility)
    dividend = values["dividend_yield"]
    sqrt_time = math.sqrt(time)
    d1 = (math.log(spot / strike) + (rate - dividend + volatility * volatility / 2.0) * time) / (
        volatility * sqrt_time
    )
    d2 = d1 - volatility * sqrt_time
    density_d1 = math.exp(-d1 * d1 / 2.0) / math.sqrt(2.0 * math.pi)
    dividend_discount = math.exp(-dividend * time)
    rate_discount = math.exp(-rate * time)

    if values["option_type"] == "call":
        price = spot * dividend_discount * _cdf(d1) - strike * rate_discount * _cdf(d2)
        delta = dividend_discount * _cdf(d1)
        theta = (
            -(spot * volatility * dividend_discount * density_d1) / (2.0 * sqrt_time)
            - rate * strike * rate_discount * _cdf(d2)
            + dividend * spot * dividend_discount * _cdf(d1)
        )
        rho = strike * time * rate_discount * _cdf(d2)
    else:
        price = strike * rate_discount * _cdf(-d2) - spot * dividend_discount * _cdf(-d1)
        delta = dividend_discount * (_cdf(d1) - 1.0)
        theta = (
            -(spot * volatility * dividend_discount * density_d1) / (2.0 * sqrt_time)
            + rate * strike * rate_discount * _cdf(-d2)
            - dividend * spot * dividend_discount * _cdf(-d1)
        )
        rho = -strike * time * rate_discount * _cdf(-d2)

    return {
        "price": price,
        "delta": delta,
        "gamma": dividend_discount * density_d1 / (spot * volatility * sqrt_time),
        "theta": theta,
        "vega": spot * dividend_discount * sqrt_time * density_d1,
        "rho": rho,
        "effective_time_to_expiry_years": time,
        "effective_volatility": volatility,
    }


def _binomial(case: dict, minimum_time: float, minimum_volatility: float) -> float:
    values = case["input"]
    spot = values["spot"]
    strike = values["strike"]
    time = max(values["time_to_expiry_years"], minimum_time)
    rate = values["rate"]
    volatility = max(values["volatility"], minimum_volatility)
    dividend = values["dividend_yield"]
    steps = values["steps"]
    dt = time / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    probability = (math.exp((rate - dividend) * dt) - down) / (up - down)
    discount = math.exp(-rate * dt)
    is_call = values["option_type"] == "call"
    is_american = values["exercise_style"] == "american"

    prices = []
    for index in range(steps + 1):
        terminal_spot = spot * up**index * down ** (steps - index)
        prices.append(
            max(terminal_spot - strike, 0.0) if is_call else max(strike - terminal_spot, 0.0)
        )

    for step in range(steps - 1, -1, -1):
        for index in range(step + 1):
            continuation = discount * (
                probability * prices[index + 1] + (1.0 - probability) * prices[index]
            )
            node_spot = spot * up**index * down ** (step - index)
            intrinsic = max(node_spot - strike, 0.0) if is_call else max(strike - node_spot, 0.0)
            prices[index] = max(continuation, intrinsic) if is_american else continuation
    return prices[0]


def test_black_scholes_fixture_values_and_legacy_clamps() -> None:
    fixture = _load("black_scholes_v1.json")
    compatibility = fixture["implementation_compatibility"]
    tolerance = fixture["absolute_tolerance"]

    for case in fixture["cases"]:
        actual = _black_scholes(
            case,
            compatibility["minimum_time_to_expiry_years"],
            compatibility["minimum_volatility"],
        )
        for field, expected in case["expected"].items():
            assert math.isclose(actual[field], expected, rel_tol=0.0, abs_tol=tolerance), (
                case["id"],
                field,
                actual[field],
                expected,
            )


def test_black_scholes_put_call_parity() -> None:
    fixture = _load("black_scholes_v1.json")
    cases = {case["id"]: case for case in fixture["cases"]}
    call = cases["atm_call_no_dividend"]
    put = cases["atm_put_no_dividend"]
    values = call["input"]
    parity = values["spot"] * math.exp(-values["dividend_yield"] * values["time_to_expiry_years"])
    parity -= values["strike"] * math.exp(-values["rate"] * values["time_to_expiry_years"])
    assert math.isclose(
        call["expected"]["price"] - put["expected"]["price"],
        parity,
        rel_tol=0.0,
        abs_tol=fixture["absolute_tolerance"],
    )


def test_binomial_fixture_values_and_american_put_bound() -> None:
    fixture = _load("binomial_v1.json")
    compatibility = fixture["implementation_compatibility"]
    tolerance = fixture["absolute_tolerance"]
    prices = {}

    for case in fixture["cases"]:
        actual = _binomial(
            case,
            compatibility["minimum_time_to_expiry_years"],
            compatibility["minimum_volatility"],
        )
        expected = case["expected"]["price"]
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance), (
            case["id"],
            actual,
            expected,
        )
        prices[case["id"]] = actual

    assert prices["american_atm_put_200_steps"] >= prices["european_atm_put_200_steps"]
