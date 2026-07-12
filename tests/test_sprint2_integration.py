from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.data import OptionChainReconstructor, QuoteQualityPolicy, RawOptionQuoteRecord
from trading.options import (
    ExerciseStyle,
    OptionContract,
    OptionType,
    SettlementType,
    black_scholes_merton_greeks,
    black_scholes_merton_price,
    solve_implied_volatility,
)
from trading.options.calendars import ExchangeSession, SavedExchangeCalendar
from trading.options.rates import RiskFreeRate, SavedRateProvider


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


class FixtureMarketDataProvider:
    def __init__(
        self,
        contract: OptionContract,
        quote: RawOptionQuoteRecord,
    ) -> None:
        self.contract = contract
        self.quote = quote

    def contracts(
        self,
        underlying: str,
        as_of_utc: datetime,
    ) -> tuple[OptionContract, ...]:
        if underlying == self.contract.underlying and as_of_utc < self.contract.expiration_at_utc:
            return (self.contract,)
        return ()

    def quote_records(
        self,
        underlying: str,
        as_of_utc: datetime,
    ) -> tuple[RawOptionQuoteRecord, ...]:
        if underlying == self.contract.underlying and self.quote.as_of_utc <= as_of_utc:
            return (self.quote,)
        return ()


def test_chain_rate_calendar_pricing_and_iv_share_canonical_units() -> None:
    contract = OptionContract(
        contract_id="SPY-20260713-C-100",
        occ_symbol="SPY   260713C00100000",
        underlying="SPY",
        option_type=OptionType.CALL,
        strike=Decimal("100"),
        expiration_date=date(2026, 7, 13),
        expiration_at_utc=EXPIRATION,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )
    rate_record = RiskFreeRate(
        currency="USD",
        tenor_days=3,
        annualized_rate=Decimal("0.04"),
        as_of_utc=DECISION - timedelta(hours=1),
        published_at_utc=DECISION - timedelta(minutes=59),
        source="fixture",
        ingested_at_utc=DECISION - timedelta(minutes=58),
    )
    rate = SavedRateProvider((rate_record,), ()).risk_free_rate(
        "USD", 3, DECISION, timedelta(hours=2)
    )
    calendar = SavedExchangeCalendar(
        (
            ExchangeSession(
                exchange="XNYS",
                session_date=date(2026, 7, 13),
                opens_at_utc=datetime(2026, 7, 13, 13, 30, tzinfo=UTC),
                closes_at_utc=EXPIRATION,
                source="fixture",
                published_at_utc=DECISION - timedelta(days=30),
                option_expiration_at_utc=EXPIRATION,
            ),
        )
    )
    exact_expiration = calendar.expiration_at("XNYS", date(2026, 7, 13), DECISION)
    years = (exact_expiration - DECISION).total_seconds() / (365.0 * 24.0 * 60.0 * 60.0)
    target_volatility = 0.25
    theoretical = black_scholes_merton_price(
        100.0,
        100.0,
        years,
        float(rate.annualized_rate),
        target_volatility,
        0.0,
        OptionType.CALL,
    )
    quote_record = RawOptionQuoteRecord(
        contract_id=contract.contract_id,
        as_of_utc=DECISION - timedelta(seconds=1),
        bid=Decimal(str(theoretical - 0.01)),
        ask=Decimal(str(theoretical + 0.01)),
        bid_size=50,
        ask_size=50,
        underlying_price=Decimal("100"),
        source="fixture",
        ingested_at_utc=DECISION,
    )
    reconstructed = OptionChainReconstructor(
        FixtureMarketDataProvider(contract, quote_record),
        QuoteQualityPolicy(max_age=timedelta(seconds=5)),
    ).reconstruct("SPY", date(2026, 7, 10), DECISION)
    quote = reconstructed.snapshot.quotes[0]

    solved = solve_implied_volatility(
        float(quote.midpoint),
        float(quote.underlying_price),
        float(contract.strike),
        years,
        float(rate.annualized_rate),
        0.0,
        contract.option_type,
    )
    greeks = black_scholes_merton_greeks(
        float(quote.underlying_price),
        float(contract.strike),
        years,
        float(rate.annualized_rate),
        solved.volatility,
        0.0,
        contract.option_type,
    )

    assert solved.converged
    assert solved.volatility == pytest.approx(target_volatility, abs=1e-8)
    assert greeks.theta < 0
    assert abs(greeks.theta) < 1  # currency per calendar day, not per year
    assert greeks.vega < 1  # currency per one volatility percentage point
