from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading.accounts import BrokerCapabilities, SavedAccountProvider
from trading.options.calendars import ExchangeSession, SavedExchangeCalendar
from trading.options.dividends import (
    CorporateCalendarSnapshot,
    DiscreteDividend,
    SavedCorporateCalendarProvider,
)
from trading.options.events import (
    EventCalendarSnapshot,
    MarketEvent,
    MarketEventType,
    SavedEventProvider,
)
from trading.options.market_inputs import MissingMarketInputError, StaleMarketInputError
from trading.options.rates import BorrowCarryRate, RiskFreeRate, SavedRateProvider
from trading.strategies.specifications import AccountSnapshot, MarginType


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
INGESTED = datetime(2026, 7, 10, 19, 59, tzinfo=UTC)
MONDAY_CLOSE = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def test_saved_rates_are_point_in_time_and_fail_closed() -> None:
    old = RiskFreeRate(
        "USD",
        3,
        Decimal("0.041"),
        DECISION - timedelta(days=2),
        DECISION - timedelta(days=2) + timedelta(minutes=1),
        "fixture",
        INGESTED,
    )
    future_revision = RiskFreeRate(
        "USD",
        3,
        Decimal("0.039"),
        DECISION - timedelta(hours=1),
        DECISION + timedelta(minutes=1),
        "fixture",
        INGESTED,
    )
    borrow = BorrowCarryRate(
        "SPY",
        Decimal("0.002"),
        DECISION - timedelta(hours=1),
        DECISION - timedelta(minutes=59),
        "fixture",
        INGESTED,
    )
    provider = SavedRateProvider((old, future_revision), (borrow,))

    assert provider.risk_free_rate("USD", 3, DECISION, timedelta(days=3)) == old
    assert provider.borrow_rate("SPY", DECISION, timedelta(hours=2)) == borrow
    with pytest.raises(StaleMarketInputError):
        provider.risk_free_rate("USD", 3, DECISION, timedelta(hours=1))
    with pytest.raises(MissingMarketInputError):
        provider.risk_free_rate("EUR", 3, DECISION, timedelta(days=3))


def test_dividend_calendar_excludes_future_knowledge_and_requires_coverage() -> None:
    dividend = DiscreteDividend(
        "div-1",
        "SPY",
        Decimal("1.75"),
        "USD",
        date(2026, 7, 13),
        date(2026, 7, 31),
        DECISION - timedelta(days=10),
        MONDAY_CLOSE,
        "fixture",
        INGESTED,
    )
    snapshot = CorporateCalendarSnapshot(
        "SPY", DECISION, MONDAY_CLOSE + timedelta(days=1), (dividend,), (), "fixture"
    )
    provider = SavedCorporateCalendarProvider((snapshot,))

    selected = provider.snapshot("SPY", DECISION, timedelta(minutes=1))
    assert selected.known_between(DECISION, MONDAY_CLOSE) == (dividend,)
    with pytest.raises(MissingMarketInputError, match="cover"):
        selected.known_between(DECISION, MONDAY_CLOSE + timedelta(days=2))

    future_news = DiscreteDividend(
        "div-2",
        "SPY",
        Decimal("2"),
        "USD",
        date(2026, 7, 13),
        None,
        DECISION + timedelta(seconds=1),
        MONDAY_CLOSE,
        "fixture",
        INGESTED,
    )
    with pytest.raises(ValueError, match="not announced"):
        CorporateCalendarSnapshot("SPY", DECISION, MONDAY_CLOSE, (future_news,), (), "fixture")


def test_event_calendar_distinguishes_announcement_from_effective_time() -> None:
    known_earnings = MarketEvent(
        "event-1",
        MarketEventType.EARNINGS,
        DECISION - timedelta(days=5),
        MONDAY_CLOSE,
        "fixture",
        INGESTED,
        symbol="SPY",
        confidence=Decimal("0.9"),
    )
    calendar = EventCalendarSnapshot(
        "events-1", DECISION, DECISION, MONDAY_CLOSE, (known_earnings,), "fixture"
    )
    provider = SavedEventProvider((calendar,))

    assert provider.snapshot(DECISION, timedelta(minutes=1)).events_between(
        DECISION, MONDAY_CLOSE, "SPY"
    ) == (known_earnings,)
    with pytest.raises(MissingMarketInputError, match="cover"):
        calendar.events_between(DECISION - timedelta(seconds=1), MONDAY_CLOSE)

    future_announcement = MarketEvent(
        "event-2",
        MarketEventType.REGULATORY,
        DECISION + timedelta(hours=1),
        MONDAY_CLOSE,
        "fixture",
        INGESTED,
        symbol="SPY",
    )
    with pytest.raises(ValueError, match="announced after"):
        EventCalendarSnapshot(
            "events-2", DECISION, DECISION, MONDAY_CLOSE, (future_announcement,), "fixture"
        )


def test_exchange_calendar_returns_exact_saved_expiration_or_fails() -> None:
    session = ExchangeSession(
        "XNYS",
        date(2026, 7, 13),
        datetime(2026, 7, 13, 13, 30, tzinfo=UTC),
        MONDAY_CLOSE,
        "fixture",
        DECISION - timedelta(days=30),
        MONDAY_CLOSE,
    )
    no_expiry = ExchangeSession(
        "XNYS",
        date(2026, 7, 14),
        datetime(2026, 7, 14, 13, 30, tzinfo=UTC),
        datetime(2026, 7, 14, 20, 0, tzinfo=UTC),
        "fixture",
        DECISION - timedelta(days=30),
    )
    calendar = SavedExchangeCalendar((session, no_expiry))

    assert calendar.expiration_at("XNYS", date(2026, 7, 13), DECISION) == MONDAY_CLOSE
    with pytest.raises(MissingMarketInputError, match="expiration"):
        calendar.expiration_at("XNYS", date(2026, 7, 14), DECISION)


def test_saved_account_provider_round_trip_and_staleness() -> None:
    snapshot = AccountSnapshot(
        "acct-hash",
        "paper",
        DECISION - timedelta(minutes=5),
        "USD",
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        MarginType.PAPER,
        "level_2",
    )
    capabilities = BrokerCapabilities(
        "paper",
        DECISION - timedelta(days=1),
        DECISION - timedelta(days=1),
        (MarginType.PAPER,),
        ("level_2",),
        True,
        True,
        False,
        "fixture",
    )
    provider = SavedAccountProvider.from_dict(
        {"snapshots": [snapshot.to_dict()], "capabilities": [capabilities.to_dict()]}
    )

    assert provider.account_snapshot("acct-hash", DECISION, timedelta(minutes=10)) == snapshot
    assert provider.broker_capabilities("paper", DECISION, timedelta(days=2)).supports(
        MarginType.PAPER, "level_2"
    )
    with pytest.raises(StaleMarketInputError):
        provider.account_snapshot("acct-hash", DECISION, timedelta(minutes=1))
    with pytest.raises(MissingMarketInputError):
        provider.account_snapshot("unknown", DECISION, timedelta(minutes=10))


def test_snapshots_reject_records_ingested_after_decision() -> None:
    delayed_dividend = DiscreteDividend(
        "div-delayed",
        "SPY",
        Decimal("1.25"),
        "USD",
        date(2026, 7, 13),
        None,
        DECISION - timedelta(days=1),
        MONDAY_CLOSE,
        "fixture",
        DECISION + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="ingested after"):
        CorporateCalendarSnapshot("SPY", DECISION, MONDAY_CLOSE, (delayed_dividend,), (), "fixture")

    delayed_event = MarketEvent(
        "event-delayed",
        MarketEventType.REGULATORY,
        DECISION - timedelta(days=1),
        MONDAY_CLOSE,
        "fixture",
        DECISION + timedelta(seconds=1),
        symbol="SPY",
    )
    with pytest.raises(ValueError, match="ingested after"):
        EventCalendarSnapshot(
            "events-delayed", DECISION, DECISION, MONDAY_CLOSE, (delayed_event,), "fixture"
        )
