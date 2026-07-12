from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd

from trading.accounts.records import BrokerCapabilities
from trading.forecasts import ForecastBundle, ForecastRequest, RealizedVolatilityForecaster
from trading.forecasts.targets import ForecastTarget
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
from trading.options.quotes import OptionQuote
from trading.portfolio import CapitalTreatment, calculate_capital_requirement
from trading.simulation import PessimisticFillPolicy, ShortPutSimulator, TransactionCostModel
from trading.strategies.specifications import AccountSnapshot, MarginType


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def _history() -> pd.DataFrame:
    timestamps = pd.bdate_range(end=DECISION - timedelta(days=1), periods=80, tz="UTC")
    close = 100 + np.linspace(0, 5, len(timestamps)) + np.sin(np.arange(len(timestamps)) / 5)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": "SPY",
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        }
    )


def test_forecast_capital_and_lifecycle_share_one_decision_context() -> None:
    forecast = RealizedVolatilityForecaster("ewma").forecast(
        _history(),
        ForecastRequest(
            decision_at_utc=DECISION,
            training_cutoff_utc=DECISION - timedelta(days=1),
            symbol="SPY",
            target=ForecastTarget.REALIZED_VOLATILITY,
            horizon=TimeHorizon(TimeHorizonKind.TRADING_DAYS, count=3),
        ),
    )
    bundle = ForecastBundle("bundle-sprint3", DECISION, "SPY", (forecast,))
    contract = OptionContract(
        contract_id="SPY-20260713-P-95",
        occ_symbol="SPY   260713P00095000",
        underlying="SPY",
        option_type=OptionType.PUT,
        strike=Decimal("95"),
        expiration_date=date(2026, 7, 13),
        expiration_at_utc=EXPIRATION,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )
    leg = OptionLeg(contract, LegSide.SHORT, 1)
    account = AccountSnapshot(
        account_id_hash="account",
        adapter="paper",
        as_of_utc=DECISION,
        currency="USD",
        cash=Decimal("25000"),
        net_liquidation=Decimal("25000"),
        buying_power=Decimal("25000"),
        option_buying_power=Decimal("25000"),
        margin_type=MarginType.PAPER,
        option_level="level_2",
    )
    capabilities = BrokerCapabilities(
        adapter="paper",
        as_of_utc=DECISION,
        published_at_utc=DECISION,
        supported_margin_types=(MarginType.PAPER,),
        option_levels=("level_2",),
        supports_equity_options=True,
        supports_multi_leg=True,
        supports_early_exercise_requests=False,
        source="fixture",
    )
    capital = calculate_capital_requirement(
        (leg,),
        account=account,
        capabilities=capabilities,
        option_prices={contract.contract_id: Decimal("1.20")},
        decision_at_utc=DECISION,
        annual_opportunity_rate=Decimal("0.04"),
    )
    quote = OptionQuote(
        contract_id=contract.contract_id,
        as_of_utc=DECISION,
        bid=Decimal("1.20"),
        ask=Decimal("1.30"),
        bid_size=20,
        ask_size=20,
        underlying_price=Decimal("100"),
        source="fixture",
        ingested_at_utc=DECISION,
    )
    simulation = ShortPutSimulator(
        PessimisticFillPolicy(),
        TransactionCostModel(commission_per_contract=Decimal("0.65")),
    ).simulate_expiration(
        simulation_id="simulation-sprint3",
        contract=contract,
        contracts=1,
        open_quote=quote,
        opened_at_utc=DECISION,
        settlement_underlying_price=Decimal("100"),
    )

    assert bundle.forecasts[0].training_cutoff_utc < DECISION
    assert capital.treatment is CapitalTreatment.CASH_SECURED
    assert capital.cash_required == Decimal("9500")
    assert capital.eligible
    assert simulation.final_share_delta == 0
    assert simulation.reconciled_cash == Decimal("119.35")
