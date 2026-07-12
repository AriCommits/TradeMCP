from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from trading.options import (
    ExerciseStyle,
    OptionType,
    binomial_price,
    black_scholes_merton_greeks,
    black_scholes_merton_price,
    european_arbitrage_bounds,
    solve_implied_volatility,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "options_pricing"


def _fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_bsm_matches_positive_time_language_neutral_fixture() -> None:
    fixture = _fixture("black_scholes_v1.json")
    tolerance = fixture["absolute_tolerance"]
    for case in fixture["cases"]:
        values = case["input"]
        compatibility = fixture["implementation_compatibility"]
        if (
            values["time_to_expiry_years"] < compatibility["minimum_time_to_expiry_years"]
            or values["volatility"] < compatibility["minimum_volatility"]
        ):
            continue
        option_type = OptionType(values["option_type"])
        price = black_scholes_merton_price(
            values["spot"],
            values["strike"],
            values["time_to_expiry_years"],
            values["rate"],
            values["volatility"],
            values["dividend_yield"],
            option_type,
        )
        greeks = black_scholes_merton_greeks(
            values["spot"],
            values["strike"],
            values["time_to_expiry_years"],
            values["rate"],
            values["volatility"],
            values["dividend_yield"],
            option_type,
        )
        actual = {"price": price, **greeks.__dict__}
        for field, expected in case["expected"].items():
            if not field.startswith("effective_"):
                canonical_expected = expected
                if field == "theta":
                    canonical_expected /= 365.0
                elif field in {"vega", "rho"}:
                    canonical_expected /= 100.0
                assert actual[field] == pytest.approx(canonical_expected, abs=tolerance)


def test_expiry_and_zero_volatility_are_limits_not_clamps() -> None:
    assert black_scholes_merton_price(110, 100, 0, 0.05, 0.3, 0, OptionType.CALL) == 10
    assert black_scholes_merton_price(90, 100, 0, 0.05, 0.3, 0, OptionType.PUT) == 10
    expected = max(100 * math.exp(-0.01) - 95 * math.exp(-0.03), 0.0)
    assert black_scholes_merton_price(100, 95, 1, 0.03, 0, 0.01, OptionType.CALL) == expected
    with pytest.raises(ValueError, match="undefined at expiry"):
        black_scholes_merton_greeks(100, 100, 0, 0.03, 0.2, 0, OptionType.CALL)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_bsm_rejects_non_finite_values(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        black_scholes_merton_price(bad, 100, 1, 0.03, 0.2, 0, OptionType.CALL)


def test_put_call_parity_and_arbitrage_bounds() -> None:
    arguments = (103.0, 100.0, 0.75, 0.04, 0.27, 0.015)
    call = black_scholes_merton_price(*arguments, OptionType.CALL)
    put = black_scholes_merton_price(*arguments, OptionType.PUT)
    parity = arguments[0] * math.exp(-arguments[5] * arguments[2])
    parity -= arguments[1] * math.exp(-arguments[3] * arguments[2])
    assert call - put == pytest.approx(parity, abs=1e-12)
    for option_type, price in ((OptionType.CALL, call), (OptionType.PUT, put)):
        lower, upper = european_arbitrage_bounds(
            arguments[0], arguments[1], arguments[2], arguments[3], arguments[5], option_type
        )
        assert lower <= price <= upper


@pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
def test_implied_volatility_round_trip(option_type: OptionType) -> None:
    target_volatility = 0.347
    price = black_scholes_merton_price(97, 105, 0.42, 0.035, target_volatility, 0.012, option_type)
    result = solve_implied_volatility(price, 97, 105, 0.42, 0.035, 0.012, option_type)
    assert result.converged
    assert result.volatility == pytest.approx(target_volatility, abs=1e-8)
    assert abs(result.residual) <= 1e-8
    assert result.iterations > 0


def test_iv_solver_reports_nonconvergence_and_rejects_unpriced_inputs() -> None:
    price = black_scholes_merton_price(100, 100, 1, 0.02, 0.4, 0, OptionType.CALL)
    result = solve_implied_volatility(
        price, 100, 100, 1, 0.02, 0, OptionType.CALL, max_iterations=1
    )
    assert not result.converged
    assert result.reason == "max_iterations"
    with pytest.raises(ValueError, match="arbitrage bounds"):
        solve_implied_volatility(101, 100, 100, 1, 0.02, 0, OptionType.CALL)
    with pytest.raises(ValueError, match="not bracketed"):
        solve_implied_volatility(
            price, 100, 100, 1, 0.02, 0, OptionType.CALL, maximum_volatility=0.1
        )


def test_binomial_matches_fixture_and_american_put_dominates_european() -> None:
    fixture = _fixture("binomial_v1.json")
    prices: dict[str, float] = {}
    for case in fixture["cases"]:
        values = case["input"]
        result = binomial_price(
            values["spot"],
            values["strike"],
            values["time_to_expiry_years"],
            values["rate"],
            values["volatility"],
            values["dividend_yield"],
            OptionType(values["option_type"]),
            ExerciseStyle(values["exercise_style"]),
            steps=values["steps"],
        )
        prices[case["id"]] = result.price
        assert result.price == pytest.approx(
            case["expected"]["price"], abs=fixture["absolute_tolerance"]
        )
        assert result.diagnostics.risk_neutral_probability is not None
        assert 0 <= result.diagnostics.risk_neutral_probability <= 1
    assert prices["american_atm_put_200_steps"] >= prices["european_atm_put_200_steps"]


def test_binomial_validates_steps_probability_and_boundary_limits() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        binomial_price(100, 100, 1, 0.02, 0.2, 0, OptionType.CALL, ExerciseStyle.EUROPEAN, steps=0)
    with pytest.raises(ValueError, match="no-arbitrage"):
        binomial_price(100, 100, 1, 5, 0.01, 0, OptionType.CALL, ExerciseStyle.EUROPEAN, steps=1)
    expiry = binomial_price(105, 100, 0, 0.02, 0.2, 0, OptionType.CALL, ExerciseStyle.AMERICAN)
    assert expiry.price == 5
    assert expiry.diagnostics.expiry_limit
    deterministic = binomial_price(100, 100, 1, 0.02, 0, 0, OptionType.PUT, ExerciseStyle.AMERICAN)
    assert deterministic.diagnostics.deterministic_limit
