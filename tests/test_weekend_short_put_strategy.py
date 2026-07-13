from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from trading.candidates import CandidateRejectionCode, ScreenedContract
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
from trading.options.events import MarketEventType
from trading.strategies import PolicyAction, StrategyContext, StrategyRegistry
from trading.strategies.specifications import AccountSnapshot, MarginType
from trading.strategies.weekend_short_put import build_weekend_short_put_strategy


UTC = timezone.utc
EDT_FRIDAY = datetime(2026, 7, 10, 19, 40, tzinfo=UTC)
EST_FRIDAY = datetime(2026, 1, 9, 20, 40, tzinfo=UTC)
MONDAY_EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def _contract(
    contract_id: str = "SPY-MON-590-P",
    *,
    expiration: datetime = MONDAY_EXPIRATION,
    strike: str = "590",
) -> OptionContract:
    return OptionContract(
        contract_id=contract_id,
        occ_symbol=f"SPY-{contract_id}",
        underlying="SPY",
        option_type=OptionType.PUT,
        strike=Decimal(strike),
        expiration_date=expiration.date(),
        expiration_at_utc=expiration,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )


def _account(decision: datetime, *, cash: str = "100000") -> AccountSnapshot:
    amount = Decimal(cash)
    return AccountSnapshot(
        account_id_hash="account",
        adapter="paper",
        as_of_utc=decision,
        currency="USD",
        cash=amount,
        net_liquidation=amount,
        buying_power=amount,
        option_buying_power=amount,
        margin_type=MarginType.CASH,
        option_level="cash_secured_put",
    )


def _record(
    target: ForecastTarget,
    decision: datetime,
    expiration: datetime,
) -> ForecastRecord:
    horizon = (
        TimeHorizon(TimeHorizonKind.OVERNIGHT_INTERVALS, count=1)
        if target is ForecastTarget.GAP_RETURN
        else TimeHorizon(TimeHorizonKind.EXPIRATION_TIMESTAMP, end_at_utc=expiration)
    )
    return ForecastRecord(
        forecast_id=f"forecast-{target.value}",
        decision_at_utc=decision,
        symbol="SPY",
        target=target,
        horizon=horizon,
        distribution=ForecastDistribution(0.1, {}, {}),
        model_id="fixture",
        model_version="1.0.0",
        training_cutoff_utc=decision - timedelta(seconds=1),
        feature_version="1.0.0",
        calibration_metrics={},
    )


def _bundle(
    decision: datetime,
    expiration: datetime,
    *,
    omit: ForecastTarget | None = None,
) -> ForecastBundle:
    targets = (
        ForecastTarget.GAP_RETURN,
        ForecastTarget.TOUCH_PROBABILITY,
        ForecastTarget.EXPIRATION_ITM_PROBABILITY,
        ForecastTarget.REALIZED_VOLATILITY,
        ForecastTarget.IV_CHANGE,
        ForecastTarget.BID_ASK_SPREAD,
    )
    return ForecastBundle(
        bundle_id="weekend-bundle",
        decision_at_utc=decision,
        symbol="SPY",
        forecasts=tuple(
            _record(target, decision, expiration) for target in targets if target is not omit
        ),
    )


def _context(
    decision: datetime = EDT_FRIDAY,
    *,
    forecasts: ForecastBundle | None = None,
    cash: str = "100000",
) -> StrategyContext:
    strategy = build_weekend_short_put_strategy()
    contract = _contract()
    return StrategyContext(
        decision_at_utc=decision,
        parameters=strategy.specification.parameters,
        legs=(OptionLeg(contract, LegSide.SHORT, 1, Decimal("1.00")),),
        account=_account(decision, cash=cash),
        forecasts=forecasts
        if forecasts is not None
        else _bundle(decision, contract.expiration_at_utc),
    )


def _screened(contract: OptionContract, decision: datetime = EDT_FRIDAY) -> ScreenedContract:
    return ScreenedContract(
        candidate_key=f"candidate-{contract.contract_id}",
        chain_id="chain",
        strategy_id="weekend_short_put",
        strategy_version="1.0.0",
        decision_at_utc=decision,
        contract=contract,
        quote=None,
        activity=None,
        eligible=True,
        rejection_reasons=(),
    )


def test_factory_is_registry_compatible_and_declares_no_synthetic_theta() -> None:
    strategy = build_weekend_short_put_strategy()
    registry = StrategyRegistry()
    registry.register(strategy)

    assert registry.resolve("weekend_short_put", "1.0.0") is strategy
    assert len(strategy.requirements.forecasts) == 6
    assert any("never added to P&L" in item for item in strategy.specification.known_limitations)


@pytest.mark.parametrize("decision", [EDT_FRIDAY, EST_FRIDAY])
def test_entry_window_is_dst_safe_for_new_york_fridays(decision: datetime) -> None:
    contract = _contract(expiration=decision + timedelta(days=3))
    strategy = build_weekend_short_put_strategy()
    context = StrategyContext(
        decision_at_utc=decision,
        parameters=strategy.specification.parameters,
        legs=(OptionLeg(contract, LegSide.SHORT, 1, Decimal("1")),),
        account=_account(decision),
        forecasts=_bundle(decision, contract.expiration_at_utc),
    )

    result = strategy.entry_policy.evaluate(context)

    assert result.action is PolicyAction.ENTER
    assert "premium_is_market_quote_no_synthetic_weekend_theta" in result.tags


def test_missing_forecast_fails_closed() -> None:
    strategy = build_weekend_short_put_strategy()
    result = strategy.entry_policy.evaluate(
        _context(forecasts=_bundle(EDT_FRIDAY, MONDAY_EXPIRATION, omit=ForecastTarget.IV_CHANGE))
    )

    assert result.action is PolicyAction.REJECT
    assert result.reasons == ("missing_forecast:iv_change",)


def test_nearest_expiration_is_selected_before_delta_filtering() -> None:
    strategy = build_weekend_short_put_strategy()
    monday = _screened(_contract("monday", strike="590"))
    tuesday_contract = _contract(
        "tuesday",
        expiration=MONDAY_EXPIRATION + timedelta(days=1),
        strike="585",
    )
    tuesday = _screened(tuesday_contract)

    selected = strategy.next_expiration_candidates(
        (tuesday, monday),
        absolute_delta_by_contract={"monday": 0.40, "tuesday": 0.20},
    )

    assert selected == ()


def test_nearest_expiration_requires_delta_and_sorts_selected_strikes() -> None:
    strategy = build_weekend_short_put_strategy()
    lower = _screened(_contract("lower", strike="585"))
    upper = _screened(_contract("upper", strike="595"))

    with pytest.raises(ValueError, match="missing point-in-time delta"):
        strategy.next_expiration_candidates((lower, upper), absolute_delta_by_contract={})

    selected = strategy.next_expiration_candidates(
        (upper, lower),
        absolute_delta_by_contract={"lower": 0.20, "upper": 0.25},
    )
    assert [item.contract.contract_id for item in selected] == ["lower", "upper"]


def test_screening_exit_sizing_and_capital_policies_match_reference_rules() -> None:
    strategy = build_weekend_short_put_strategy()
    context = _context(cash="2000000")
    policy = strategy.eligibility_policy()

    assert policy.minimum_open_interest == 100
    assert policy.maximum_relative_spread == Decimal("0.2")
    assert policy.require_capital_estimate is True
    assert MarketEventType.EARNINGS in policy.blocked_event_types
    assert strategy.exit_policy.evaluate(context).action is PolicyAction.HOLD
    assert strategy.roll_policy.evaluate(context).action is PolicyAction.REJECT
    assert strategy.sizing_policy.size(context, capital_limit=Decimal("100000")).contracts == 1
    requirement = strategy.capital_policy.requirement(context)
    assert requirement.cash_required == Decimal("59000")
    assert requirement.maximum_loss == Decimal("58900")
    assert requirement.eligible is True


def test_reference_yaml_makes_weekend_decay_accounting_explicit() -> None:
    path = (
        Path(__file__).parents[1] / "config" / "options" / "strategies" / "weekend_short_put.yaml"
    )
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert payload["strategy_id"] == "weekend_short_put"
    assert payload["strategy_version"] == "1.0.0"
    assert payload["entry"]["expiration_selection"] == "next_listed_after_entry"
    assert payload["accounting"]["weekend_theta"] == "embedded_in_friday_market_premium"
    assert payload["accounting"]["synthetic_weekend_theta_pnl"] is False


def test_screened_contract_invariant_rejects_reasons_on_eligible_candidate() -> None:
    contract = _contract()
    with pytest.raises(ValueError, match="inconsistent"):
        ScreenedContract(
            candidate_key="bad",
            chain_id="chain",
            strategy_id="weekend_short_put",
            strategy_version="1.0.0",
            decision_at_utc=EDT_FRIDAY,
            contract=contract,
            quote=None,
            activity=None,
            eligible=True,
            rejection_reasons=(CandidateRejectionCode.QUOTE_MISSING,),
        )
