from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.options.contracts import (
    ExerciseStyle,
    OptionContract,
    OptionType,
    SettlementType,
)
from trading.options.quotes import OptionQuote, QuoteQualityFlag
from trading.simulation import (
    CoveredCallSimulator,
    FillError,
    LimitFillPolicy,
    MidpointFillPolicy,
    PessimisticFillPolicy,
    ShortPutSimulator,
    TransactionCostModel,
)
from trading.simulation.records import LifecycleEventKind


UTC = timezone.utc
OPENED = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def contract(option_type: OptionType = OptionType.PUT) -> OptionContract:
    suffix = "P" if option_type is OptionType.PUT else "C"
    return OptionContract(
        contract_id=f"XYZ-20260713-50-{suffix}",
        occ_symbol=f"XYZ260713{suffix}00050000",
        underlying="XYZ",
        option_type=option_type,
        strike=Decimal("50"),
        expiration_date=date(2026, 7, 13),
        expiration_at_utc=EXPIRATION,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )


def quote(
    bid: str,
    ask: str,
    *,
    at: datetime = OPENED,
    option_type: OptionType = OptionType.PUT,
    flags: tuple[QuoteQualityFlag, ...] = (),
) -> OptionQuote:
    return OptionQuote(
        contract_id=contract(option_type).contract_id,
        as_of_utc=at,
        bid=Decimal(bid),
        ask=Decimal(ask),
        bid_size=10,
        ask_size=12,
        underlying_price=Decimal("55"),
        source="fixture",
        ingested_at_utc=at,
        quality_flags=flags,
    )


def costs() -> TransactionCostModel:
    return TransactionCostModel(
        commission_per_contract=Decimal("0.65"),
        fee_per_contract=Decimal("0.03"),
    )


def test_short_put_pessimistic_close_reconciles_golden_cashflows() -> None:
    closed_at = OPENED + timedelta(days=1)
    result = ShortPutSimulator(PessimisticFillPolicy(), costs()).simulate_close(
        simulation_id="sim-close",
        contract=contract(),
        contracts=2,
        open_quote=quote("1.20", "1.30"),
        opened_at_utc=OPENED,
        close_quote=quote("0.45", "0.55", at=closed_at),
        closed_at_utc=closed_at,
    )

    assert [event.kind for event in result.events] == [
        LifecycleEventKind.OPENED,
        LifecycleEventKind.CLOSED,
    ]
    assert result.events[0].net_cashflow == Decimal("238.64")
    assert result.events[1].net_cashflow == Decimal("-111.36")
    assert result.reconciled_cash == Decimal("127.28")
    assert result.total_commissions == Decimal("2.60")
    assert result.total_fees == Decimal("0.12")
    assert result.total_slippage == Decimal("20.00")
    assert result.final_share_delta == 0


def test_midpoint_and_pessimistic_results_are_explicitly_distinct() -> None:
    pessimistic = ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
        simulation_id="sim-expiry",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.20", "1.40"),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("51"),
    )
    midpoint = ShortPutSimulator(MidpointFillPolicy()).simulate_expiration(
        simulation_id="sim-expiry",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.20", "1.40"),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("51"),
    )

    assert pessimistic.reconciled_cash == Decimal("120")
    assert midpoint.reconciled_cash == Decimal("130")
    assert pessimistic.total_slippage == Decimal("10")
    assert midpoint.total_slippage == 0
    assert pessimistic.events[-1].kind is LifecycleEventKind.EXPIRED_WORTHLESS


def test_short_put_physical_assignment_records_shares_and_strike_cash() -> None:
    result = ShortPutSimulator(PessimisticFillPolicy(), costs()).simulate_expiration(
        simulation_id="sim-assigned",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.00", "1.10"),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("42"),
    )

    assert result.events[-1].kind is LifecycleEventKind.ASSIGNED
    assert result.events[-1].net_cashflow == Decimal("-5000")
    assert result.final_share_delta == Decimal("100")
    assert result.reconciled_cash == Decimal("-4900.68")
    assert result.reconciled_cash == sum(event.net_cashflow for event in result.events)


def test_marketable_limit_fill_and_non_marketable_rejection() -> None:
    marketable = ShortPutSimulator(LimitFillPolicy(Decimal("1.15"))).simulate_expiration(
        simulation_id="sim-limit",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.20", "1.30"),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("55"),
    )
    assert marketable.reconciled_cash == Decimal("120")

    with pytest.raises(FillError, match="not marketable"):
        ShortPutSimulator(LimitFillPolicy(Decimal("1.25"))).simulate_expiration(
            simulation_id="sim-limit-no-fill",
            contract=contract(),
            contracts=1,
            open_quote=quote("1.20", "1.30"),
            opened_at_utc=OPENED,
            settlement_underlying_price=Decimal("55"),
        )


@pytest.mark.parametrize(
    "bad_quote, decision, message",
    [
        (quote("1.00", "1.10", at=OPENED - timedelta(minutes=5)), OPENED, "stale"),
        (
            quote("1.00", "1.10", flags=(QuoteQualityFlag.INDICATIVE,)),
            OPENED,
            "quality flags",
        ),
        (
            quote("0", "0.10", flags=(QuoteQualityFlag.ZERO_BID,)),
            OPENED,
            "zero bid",
        ),
    ],
)
def test_unsafe_quotes_fail_closed(
    bad_quote: OptionQuote, decision: datetime, message: str
) -> None:
    with pytest.raises(FillError, match=message):
        ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
            simulation_id="sim-bad",
            contract=contract(),
            contracts=1,
            open_quote=bad_quote,
            opened_at_utc=decision,
            settlement_underlying_price=Decimal("55"),
        )


def test_covered_call_assignment_requires_and_consumes_covered_shares() -> None:
    call = contract(OptionType.CALL)
    simulator = CoveredCallSimulator(PessimisticFillPolicy())
    with pytest.raises(ValueError, match="fully cover"):
        simulator.simulate_expiration(
            simulation_id="call-uncovered",
            contract=call,
            contracts=1,
            covered_shares=Decimal("99"),
            open_quote=quote("1.50", "1.60", option_type=OptionType.CALL),
            opened_at_utc=OPENED,
            settlement_underlying_price=Decimal("60"),
        )

    result = simulator.simulate_expiration(
        simulation_id="call-covered",
        contract=call,
        contracts=1,
        covered_shares=Decimal("100"),
        open_quote=quote("1.50", "1.60", option_type=OptionType.CALL),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("60"),
    )
    assert result.final_share_delta == Decimal("-100")
    assert result.reconciled_cash == Decimal("5150")
    assert result.events[-1].kind is LifecycleEventKind.ASSIGNED


class AlwaysAssign:
    def should_assign(
        self, option: OptionContract, at_utc: datetime, underlying_price: Decimal
    ) -> bool:
        return True


def test_early_assignment_is_explicitly_hook_gated() -> None:
    assignment_at = OPENED + timedelta(days=1)
    result = ShortPutSimulator(
        PessimisticFillPolicy(), early_assignment_hook=AlwaysAssign()
    ).simulate_early_assignment(
        simulation_id="sim-early",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.00", "1.10"),
        opened_at_utc=OPENED,
        assignment_at_utc=assignment_at,
        underlying_price=Decimal("45"),
    )
    assert result.events[-1].occurred_at_utc == assignment_at
    assert result.events[-1].kind is LifecycleEventKind.ASSIGNED
    assert "early_assignment=true" in result.events[-1].details


def test_unsupported_cash_settlement_fails_closed() -> None:
    cash_settled = replace(contract(), settlement_type=SettlementType.CASH)
    with pytest.raises(ValueError, match="cash-settled"):
        ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
            simulation_id="sim-unsupported",
            contract=cash_settled,
            contracts=1,
            open_quote=quote("1.00", "1.10"),
            opened_at_utc=OPENED,
            settlement_underlying_price=Decimal("45"),
        )


def test_result_records_are_immutable_and_serializable() -> None:
    result = ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
        simulation_id="sim-json",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.00", "1.10"),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("55"),
    )
    assert '"reconciled_cash":"100.00"' in result.to_json()
    with pytest.raises(AttributeError):
        result.reconciled_cash = Decimal("0")  # type: ignore[misc]


def test_locked_quote_is_executable_when_other_quality_checks_pass() -> None:
    result = ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
        simulation_id="sim-locked",
        contract=contract(),
        contracts=1,
        open_quote=quote("1.20", "1.20", flags=(QuoteQualityFlag.LOCKED,)),
        opened_at_utc=OPENED,
        settlement_underlying_price=Decimal("55"),
    )

    assert result.reconciled_cash == Decimal("120")


def test_open_at_expiration_and_assignment_before_open_fail_closed() -> None:
    with pytest.raises(ValueError, match="at or after expiration"):
        ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
            simulation_id="sim-expiration-open",
            contract=contract(),
            contracts=1,
            open_quote=quote("1.00", "1.10", at=EXPIRATION),
            opened_at_utc=EXPIRATION,
            settlement_underlying_price=Decimal("55"),
        )

    with pytest.raises(ValueError, match="follow the open"):
        ShortPutSimulator(
            PessimisticFillPolicy(), early_assignment_hook=AlwaysAssign()
        ).simulate_early_assignment(
            simulation_id="sim-bad-early",
            contract=contract(),
            contracts=1,
            open_quote=quote("1.00", "1.10"),
            opened_at_utc=OPENED,
            assignment_at_utc=OPENED - timedelta(seconds=1),
            underlying_price=Decimal("45"),
        )
