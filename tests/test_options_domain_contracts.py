from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from trading.forecasts.targets import (
    ForecastBundle,
    ForecastDistribution,
    ForecastRecord,
    ForecastTarget,
)
from trading.mcp.schemas import (
    DataFreshness,
    ObjectiveScore,
    RiskSummary,
    StressResult,
    TradePlan,
    TradePlanStatus,
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
from trading.options.quotes import OptionChainSnapshot, OptionQuote
from trading.strategies.specifications import CandidatePosition, SimulationSummary


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 45, tzinfo=UTC)
EXPIRY = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


def make_contract() -> OptionContract:
    return OptionContract(
        contract_id="SPY-20260713-P-600",
        occ_symbol="SPY   260713P00600000",
        underlying="SPY",
        option_type=OptionType.PUT,
        strike=Decimal("600"),
        expiration_date=date(2026, 7, 13),
        expiration_at_utc=EXPIRY,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )


def make_candidate() -> CandidatePosition:
    leg = OptionLeg(make_contract(), LegSide.SHORT, 1, Decimal("1.25"))
    return CandidatePosition(
        candidate_id="candidate-1",
        decision_at_utc=DECISION,
        strategy_id="weekend_short_put",
        strategy_version="1.0",
        underlying="SPY",
        legs=(leg,),
        market_snapshot_id="chain-1",
        forecast_bundle_id="forecast-bundle-1",
        entry_rules={"fill": "bid"},
        exit_rules={"mode": "expiration"},
        capital_required=Decimal("60000"),
        eligible=True,
    )


def test_contract_and_chain_json_round_trip() -> None:
    contract = make_contract()
    quote = OptionQuote(
        contract_id=contract.contract_id,
        as_of_utc=DECISION,
        bid=Decimal("1.24"),
        ask=Decimal("1.27"),
        bid_size=100,
        ask_size=90,
        underlying_price=Decimal("610.25"),
        source="fixture",
        ingested_at_utc=DECISION,
    )
    chain = OptionChainSnapshot(
        chain_id="chain-1",
        underlying="SPY",
        session_date=date(2026, 7, 10),
        as_of_utc=DECISION,
        contracts=(contract,),
        quotes=(quote,),
        source="fixture",
        ingested_at_utc=DECISION,
    )

    assert json.loads(chain.to_json())["schema_version"] == "1.0"
    assert OptionChainSnapshot.from_json(chain.to_json()) == chain
    assert quote.midpoint == Decimal("1.255")


def test_forecast_bundle_round_trip_and_time_semantics() -> None:
    horizon = TimeHorizon(TimeHorizonKind.OVERNIGHT_INTERVALS, count=2)
    distribution = ForecastDistribution(
        point_estimate=0.01,
        quantiles={"0.05": -0.025, "0.95": 0.03},
        probabilities={"down_gap": 0.2},
        sample_count=500,
    )
    forecast = ForecastRecord(
        forecast_id="forecast-1",
        decision_at_utc=DECISION,
        symbol="SPY",
        target=ForecastTarget.GAP_RETURN,
        horizon=horizon,
        distribution=distribution,
        model_id="empirical_gap",
        model_version="1.0",
        training_cutoff_utc=DECISION - timedelta(microseconds=1),
        feature_version="1.0",
        calibration_metrics={"coverage_90": 0.89},
    )
    bundle = ForecastBundle("bundle-1", DECISION, "SPY", (forecast,))

    assert ForecastBundle.from_json(bundle.to_json()) == bundle
    with pytest.raises(ValueError, match="expiration_timestamp"):
        TimeHorizon(TimeHorizonKind.EXPIRATION_TIMESTAMP, count=1)


def test_trade_plan_round_trip() -> None:
    candidate = make_candidate()
    simulation = SimulationSummary(
        simulation_id="simulation-1",
        candidate_id=candidate.candidate_id,
        scenario_id="pessimistic",
        simulated_at_utc=DECISION,
        entry_fill=Decimal("1.24"),
        exit_fill=Decimal("0"),
        gross_pnl=Decimal("124"),
        net_pnl=Decimal("122.50"),
        capital_required=Decimal("60000"),
        return_on_capital=0.0020417,
        max_adverse_excursion=Decimal("80"),
        max_favorable_excursion=Decimal("124"),
        fees=Decimal("1.50"),
        slippage=Decimal("0"),
    )
    freshness = DataFreshness(DECISION, DECISION, DECISION)
    plan = TradePlan(
        trade_plan_id="plan-1",
        created_at_utc=DECISION,
        run_id="run-1",
        candidate=candidate,
        objective=ObjectiveScore("tail_adjusted_roc", 0.4, {"return": 0.5}, {}),
        simulations=(simulation,),
        risk=RiskSummary(
            max_profit=Decimal("124"),
            max_loss=Decimal("59876"),
            breakevens=(Decimal("598.76"),),
            expected_shortfall=Decimal("400"),
            probability_of_profit=0.8,
            probability_of_touch=0.3,
            probability_of_assignment=0.2,
        ),
        stress_results=(StressResult("spot_down_5", -0.05, 0.1, 1, Decimal("-800")),),
        data_freshness=freshness,
        status=TradePlanStatus.DRAFT,
        rank=1,
        rationale=("best tail-adjusted candidate",),
        assumptions=("cash secured",),
    )

    payload = plan.to_json()
    assert json.loads(payload)["candidate"]["legs"][0]["contract"]["strike"] == "600"
    assert TradePlan.from_json(payload) == plan


def test_validation_rejects_naive_timestamp_and_future_training_cutoff() -> None:
    with pytest.raises(ValueError, match="UTC"):
        TimeHorizon(
            TimeHorizonKind.EXPIRATION_TIMESTAMP,
            end_at_utc=datetime(2026, 7, 13, 20, 0),
        )

    with pytest.raises(ValueError, match="training_cutoff"):
        ForecastRecord(
            forecast_id="bad",
            decision_at_utc=DECISION,
            symbol="SPY",
            target=ForecastTarget.RETURN,
            horizon=TimeHorizon(TimeHorizonKind.TRADING_DAYS, count=1),
            distribution=ForecastDistribution(0.0, {}, {}),
            model_id="model",
            model_version="1",
            training_cutoff_utc=EXPIRY,
            feature_version="1",
            calibration_metrics={},
        )


def test_forecast_training_cutoff_must_strictly_precede_decision() -> None:
    with pytest.raises(ValueError, match="strictly precede"):
        ForecastRecord(
            forecast_id="equal-cutoff",
            decision_at_utc=DECISION,
            symbol="SPY",
            target=ForecastTarget.RETURN,
            horizon=TimeHorizon(TimeHorizonKind.TRADING_DAYS, count=1),
            distribution=ForecastDistribution(0.0, {}, {}),
            model_id="model",
            model_version="1",
            training_cutoff_utc=DECISION,
            feature_version="1",
            calibration_metrics={},
        )


def test_schema_version_is_required_and_checked() -> None:
    payload = make_contract().to_dict()
    payload["schema_version"] = "99.0"
    with pytest.raises(ValueError, match="schema_version"):
        OptionContract.from_dict(payload)
