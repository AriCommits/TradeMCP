from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from trading.forecasts.targets import (
    ForecastBundle,
    ForecastDistribution,
    ForecastRecord,
    ForecastTarget,
)
from trading.options.contracts import (
    ExerciseStyle,
    LegSide,
    OptionContract,
    OptionLeg,
    OptionType,
    SettlementType,
    TimeHorizon,
    TimeHorizonKind,
)
from trading.portfolio.records import CapitalTreatment
from trading.strategies.base import PolicyAction, StrategyContext
from trading.strategies.cash_secured_put import build_cash_secured_put_strategy
from trading.strategies.registry import StrategyRegistry
from trading.strategies.specifications import AccountSnapshot, MarginType


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = DECISION + timedelta(days=35)


def _account(*, cash: str = "100000") -> AccountSnapshot:
    amount = Decimal(cash)
    return AccountSnapshot(
        account_id_hash="acct",
        adapter="paper",
        as_of_utc=DECISION,
        currency="USD",
        cash=amount,
        net_liquidation=amount,
        buying_power=amount,
        option_buying_power=amount,
        margin_type=MarginType.CASH,
        option_level="cash_secured_put",
    )


def _leg(*, expiration: datetime = EXPIRATION, limit_price: str = "2.00") -> OptionLeg:
    contract = OptionContract(
        contract_id="XYZ-50-P",
        occ_symbol="XYZ260814P00050000",
        underlying="XYZ",
        option_type=OptionType.PUT,
        strike=Decimal("50"),
        expiration_date=expiration.date(),
        expiration_at_utc=expiration,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )
    return OptionLeg(contract, LegSide.SHORT, 1, Decimal(limit_price))


def _forecast(target: ForecastTarget, value: float) -> ForecastRecord:
    return ForecastRecord(
        forecast_id=f"forecast-{target.value}",
        decision_at_utc=DECISION,
        symbol="XYZ",
        target=target,
        horizon=TimeHorizon(TimeHorizonKind.EXPIRATION_TIMESTAMP, end_at_utc=EXPIRATION),
        distribution=ForecastDistribution(value, {}, {}),
        model_id="fixture",
        model_version="1.0.0",
        training_cutoff_utc=DECISION - timedelta(seconds=1),
        feature_version="1.0.0",
        calibration_metrics={},
    )


def _bundle(*, omit: ForecastTarget | None = None) -> ForecastBundle:
    values = {
        ForecastTarget.REALIZED_VOLATILITY: 0.25,
        ForecastTarget.SKEW_CHANGE: 0.01,
        ForecastTarget.MAX_DOWN_MOVE: 0.10,
        ForecastTarget.TOUCH_PROBABILITY: 0.25,
        ForecastTarget.EXPIRATION_ITM_PROBABILITY: 0.15,
    }
    forecasts = tuple(
        _forecast(target, value) for target, value in values.items() if target is not omit
    )
    return ForecastBundle("bundle", DECISION, "XYZ", forecasts)


def _parameters(**overrides: object) -> dict[str, object]:
    strategy = build_cash_secured_put_strategy()
    runtime: dict[str, object] = {
        "option_delta": -0.20,
        "entry_implied_volatility": 0.35,
        "entry_put_skew": 0.05,
        "has_excluded_event": False,
        "entry_credit": 2.00,
        "current_option_price": 1.50,
    }
    runtime.update(overrides)
    return strategy.parameter_schema.validate(runtime)


def _context(
    *,
    parameters: dict[str, object] | None = None,
    forecasts: ForecastBundle | None = None,
    leg: OptionLeg | None = None,
    account: AccountSnapshot | None = None,
) -> StrategyContext:
    return StrategyContext(
        decision_at_utc=DECISION,
        parameters=parameters or _parameters(),
        legs=(leg or _leg(),),
        account=account or _account(),
        forecasts=forecasts or _bundle(),
    )


def test_factory_is_strictly_versioned_and_registry_compatible() -> None:
    strategy = build_cash_secured_put_strategy()
    registry = StrategyRegistry()
    registry.register(strategy)

    assert registry.resolve("cash_secured_put_30_45_dte", "1.0.0") is strategy
    assert strategy.parameter_schema.schema_version == "1.0.0"
    assert strategy.specification.parameters["profit_target_fraction"] == 0.50
    assert strategy.specification.parameters["timed_close_dte"] == 21
    configured = build_cash_secured_put_strategy({"profit_target_fraction": 0.40})
    assert configured.specification.parameters["profit_target_fraction"] == 0.40


def test_entry_accepts_complete_eligible_market_state() -> None:
    decision = build_cash_secured_put_strategy().entry_policy.evaluate(_context())

    assert decision.action is PolicyAction.ENTER
    assert "cash_secured" in decision.tags


@pytest.mark.parametrize(
    ("context", "message"),
    [
        (_context(leg=_leg(expiration=DECISION + timedelta(days=29))), "outside configured"),
        (_context(parameters=_parameters(option_delta=-0.40)), "delta is outside"),
        (_context(parameters=_parameters(has_excluded_event=True)), "excluded material event"),
        (
            _context(forecasts=_bundle(omit=ForecastTarget.TOUCH_PROBABILITY)),
            "missing unique expiration-matched touch_probability",
        ),
    ],
)
def test_entry_filters_and_missing_forecasts_fail_closed(
    context: StrategyContext, message: str
) -> None:
    decision = build_cash_secured_put_strategy().entry_policy.evaluate(context)

    assert decision.action is PolicyAction.REJECT
    assert any(message in reason for reason in decision.reasons)
    assert "fail_closed" in decision.tags


def test_entry_requires_runtime_iv_skew_delta_and_event_inputs() -> None:
    parameters = build_cash_secured_put_strategy().parameter_schema.validate({})
    decision = build_cash_secured_put_strategy().entry_policy.evaluate(
        _context(parameters=parameters)
    )

    assert decision.action is PolicyAction.REJECT
    assert len(decision.reasons) >= 4
    assert any("implied volatility" in reason for reason in decision.reasons)
    assert any("put skew" in reason for reason in decision.reasons)


def test_exit_uses_fifty_percent_profit_and_twenty_one_dte_defaults() -> None:
    strategy = build_cash_secured_put_strategy()
    at_profit = strategy.exit_policy.evaluate(
        _context(parameters=_parameters(current_option_price=1.00))
    )
    timed = strategy.exit_policy.evaluate(
        _context(leg=_leg(expiration=DECISION + timedelta(days=21)))
    )
    hold = strategy.exit_policy.evaluate(_context())

    assert at_profit.action is PolicyAction.EXIT
    assert timed.action is PolicyAction.EXIT
    assert hold.action is PolicyAction.HOLD


def test_cash_secured_capital_and_sizing_reserve_full_strike() -> None:
    strategy = build_cash_secured_put_strategy()
    context = _context(account=_account(cash="12000"))

    requirement = strategy.capital_policy.requirement(context)
    sizing = strategy.sizing_policy.size(context, capital_limit=Decimal("12000"))

    assert requirement.treatment is CapitalTreatment.CASH_SECURED
    assert requirement.cash_required == Decimal("5000")
    assert requirement.maximum_loss == Decimal("4800.00")
    assert requirement.eligible
    assert sizing.contracts == 1


def test_cash_secured_capital_fails_closed_without_credit_or_cash() -> None:
    strategy = build_cash_secured_put_strategy()
    no_credit = strategy.parameter_schema.validate(
        {
            "option_delta": -0.20,
            "entry_implied_volatility": 0.35,
            "entry_put_skew": 0.05,
            "has_excluded_event": False,
        }
    )

    assert not strategy.capital_policy.requirement(_context(parameters=no_credit)).eligible
    assert not strategy.capital_policy.requirement(_context(account=_account(cash="4000"))).eligible


def test_reference_config_matches_plugin_identity_and_safety_defaults() -> None:
    path = (
        Path(__file__).parents[1]
        / "config"
        / "options"
        / "strategies"
        / "cash_secured_put_30_45_dte.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert payload["strategy_id"] == "cash_secured_put_30_45_dte"
    assert payload["strategy_version"] == "1.0.0"
    assert payload["exit"] == {
        "profit_target_fraction": 0.5,
        "timed_close_dte": 21,
        "rolling_enabled": False,
    }
    assert payload["capital"]["reserve_full_strike_collateral"] is True
    assert payload["missing_input_policy"] == "reject"
