from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.accounts.records import BrokerCapabilities
from trading.options.contracts import (
    ExerciseStyle,
    LegSide,
    OptionContract,
    OptionLeg,
    OptionType,
    SettlementType,
)
from trading.options.greeks import OptionGreeks
from trading.portfolio import (
    CapitalAllocation,
    CapitalTreatment,
    ConcentrationLimits,
    aggregate_option_greeks,
    calculate_capital_requirement,
    check_concentration,
)
from trading.strategies.specifications import AccountHolding, AccountSnapshot, MarginType


UTC = timezone.utc
NOW = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRY = NOW + timedelta(days=30)


def contract(
    option_type: OptionType,
    strike: str,
    *,
    suffix: str,
) -> OptionContract:
    return OptionContract(
        contract_id=f"SPY-{suffix}",
        occ_symbol=f"SPY-{suffix}",
        underlying="SPY",
        option_type=option_type,
        strike=Decimal(strike),
        expiration_date=EXPIRY.date(),
        expiration_at_utc=EXPIRY,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )


def account(
    *,
    cash: str = "100000",
    option_buying_power: str = "100000",
    option_level: str = "level_2",
    shares: str = "0",
) -> AccountSnapshot:
    holdings: tuple[AccountHolding, ...] = ()
    if Decimal(shares):
        holdings = (AccountHolding("SPY", "equity", Decimal(shares), Decimal("610")),)
    return AccountSnapshot(
        account_id_hash="account-hash",
        adapter="fixture",
        as_of_utc=NOW,
        currency="USD",
        cash=Decimal(cash),
        net_liquidation=Decimal("100000"),
        buying_power=Decimal("100000"),
        option_buying_power=Decimal(option_buying_power),
        margin_type=MarginType.CASH,
        option_level=option_level,
        holdings=holdings,
    )


def capabilities(*, multi_leg: bool = True) -> BrokerCapabilities:
    return BrokerCapabilities(
        adapter="fixture",
        as_of_utc=NOW,
        published_at_utc=NOW,
        supported_margin_types=(MarginType.CASH,),
        option_levels=("level_2",),
        supports_equity_options=True,
        supports_multi_leg=multi_leg,
        supports_early_exercise_requests=False,
        source="test fixture",
    )


def test_cash_secured_put_collateral_and_opportunity_cost() -> None:
    put = OptionLeg(contract(OptionType.PUT, "600", suffix="P600"), LegSide.SHORT, 1)
    result = calculate_capital_requirement(
        (put,),
        account=account(),
        capabilities=capabilities(),
        option_prices={put.contract.contract_id: Decimal("2")},
        decision_at_utc=NOW,
        annual_opportunity_rate=Decimal("0.05"),
    )

    assert result.treatment is CapitalTreatment.CASH_SECURED
    assert result.cash_required == Decimal("60000")
    assert result.maximum_loss == Decimal("59800")
    assert result.estimated_buying_power_reduction == Decimal("60000")
    assert result.opportunity_cost == Decimal("60000") * Decimal("0.05") * 30 / 365
    assert result.buying_power_is_estimate
    assert result.eligible


def test_capital_fails_closed_on_missing_price_or_capability() -> None:
    put = OptionLeg(contract(OptionType.PUT, "600", suffix="P600"), LegSide.SHORT, 1)
    with pytest.raises(ValueError, match="missing option price"):
        calculate_capital_requirement(
            (put,),
            account=account(),
            capabilities=capabilities(),
            option_prices={},
            decision_at_utc=NOW,
        )

    result = calculate_capital_requirement(
        (put,),
        account=account(option_level="level_1"),
        capabilities=capabilities(),
        option_prices={put.contract.contract_id: Decimal("2")},
        decision_at_utc=NOW,
    )
    assert not result.eligible
    assert result.rejection_reasons == ("account option level or margin type is not supported",)


def test_cash_and_buying_power_are_both_gated() -> None:
    put = OptionLeg(contract(OptionType.PUT, "600", suffix="P600"), LegSide.SHORT, 1)
    result = calculate_capital_requirement(
        (put,),
        account=account(cash="50000", option_buying_power="55000"),
        capabilities=capabilities(),
        option_prices={put.contract.contract_id: Decimal("2")},
        decision_at_utc=NOW,
    )
    assert not result.eligible
    assert result.rejection_reasons == (
        "insufficient cash",
        "insufficient option buying power",
    )


def test_covered_call_requires_deliverable_shares() -> None:
    call = OptionLeg(contract(OptionType.CALL, "620", suffix="C620"), LegSide.SHORT, 2)
    rejected = calculate_capital_requirement(
        (call,),
        account=account(shares="100"),
        capabilities=capabilities(),
        option_prices={call.contract.contract_id: Decimal("1.5")},
        decision_at_utc=NOW,
    )
    accepted = calculate_capital_requirement(
        (call,),
        account=account(shares="200"),
        capabilities=capabilities(),
        option_prices={call.contract.contract_id: Decimal("1.5")},
        decision_at_utc=NOW,
    )
    assert rejected.covered_shares_required == Decimal("200")
    assert not rejected.eligible
    assert accepted.eligible
    assert accepted.maximum_loss == Decimal("121700.0")


def test_defined_risk_credit_spread_uses_width_less_credit() -> None:
    short = OptionLeg(contract(OptionType.PUT, "600", suffix="P600"), LegSide.SHORT, 1)
    long = OptionLeg(contract(OptionType.PUT, "590", suffix="P590"), LegSide.LONG, 1)
    result = calculate_capital_requirement(
        (short, long),
        account=account(),
        capabilities=capabilities(),
        option_prices={
            short.contract.contract_id: Decimal("3"),
            long.contract.contract_id: Decimal("1"),
        },
        decision_at_utc=NOW,
    )
    assert result.treatment is CapitalTreatment.DEFINED_RISK
    assert result.maximum_loss == Decimal("800")
    assert result.estimated_buying_power_reduction == Decimal("800")


def test_concentration_gates_all_dimensions_after_candidate() -> None:
    existing = (
        CapitalAllocation("SPY", "ETF", "short_put", EXPIRY.date(), Decimal("10000")),
        CapitalAllocation("QQQ", "ETF", "short_put", EXPIRY.date(), Decimal("10000")),
    )
    candidate = CapitalAllocation("SPY", "ETF", "short_put", EXPIRY.date(), Decimal("15000"))
    result = check_concentration(
        candidate,
        existing,
        account=account(),
        limits=ConcentrationLimits(
            symbol=Decimal("0.20"),
            sector=Decimal("0.30"),
            strategy=Decimal("0.30"),
            expiration=Decimal("0.30"),
        ),
    )
    assert result.symbol_fraction == Decimal("0.25")
    assert result.sector_fraction == Decimal("0.35")
    assert result.rejection_reasons == (
        "symbol concentration limit exceeded",
        "sector concentration limit exceeded",
        "strategy concentration limit exceeded",
        "expiration concentration limit exceeded",
    )


def test_greek_aggregation_applies_side_quantity_and_multiplier() -> None:
    call = contract(OptionType.CALL, "620", suffix="C620")
    long = OptionLeg(call, LegSide.LONG, 2)
    short = OptionLeg(call, LegSide.SHORT, 1)
    greeks = OptionGreeks(delta=0.5, gamma=0.02, vega=0.1, theta=-0.03, rho=0.04)
    exposure = aggregate_option_greeks(((long, greeks), (short, greeks)))
    assert exposure.delta == Decimal("50.0")
    assert exposure.gamma == Decimal("2.00")
    assert exposure.vega == Decimal("10.0")
    assert exposure.theta == Decimal("-3.00")


def test_account_and_broker_capability_freshness_fail_closed() -> None:
    put = OptionLeg(contract(OptionType.PUT, "600", suffix="P600"), LegSide.SHORT, 1)
    prices = {put.contract.contract_id: Decimal("2")}

    with pytest.raises(ValueError, match="account snapshot is stale"):
        calculate_capital_requirement(
            (put,),
            account=replace(account(), as_of_utc=NOW - timedelta(minutes=2)),
            capabilities=capabilities(),
            option_prices=prices,
            decision_at_utc=NOW,
            max_account_age=timedelta(minutes=1),
        )

    stale_capabilities = replace(
        capabilities(),
        as_of_utc=NOW - timedelta(days=2),
        published_at_utc=NOW - timedelta(days=2),
    )
    with pytest.raises(ValueError, match="broker capabilities are stale"):
        calculate_capital_requirement(
            (put,),
            account=account(),
            capabilities=stale_capabilities,
            option_prices=prices,
            decision_at_utc=NOW,
            max_capability_age=timedelta(days=1),
        )
