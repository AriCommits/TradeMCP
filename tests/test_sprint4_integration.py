from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from trading.candidates import CandidateEligibilityPolicy, screen_option_candidates
from trading.objectives import (
    ObjectiveWeights,
    RealizedObjectiveInput,
    ScoreKind,
    score_realized,
)
from trading.options.contracts import ExerciseStyle, OptionContract, OptionType, SettlementType
from trading.options.quotes import OptionChainSnapshot, OptionQuote
from trading.portfolio import CapitalRequirement, CapitalTreatment
from trading.simulation import PessimisticFillPolicy, ShortPutSimulator
from trading.strategies.base import DataRequirement, StrategyRequirements
from trading.strategies.registry import StrategyRegistry
from trading.strategies.specifications import MarginType, StrategySpecification
from trading.strategies.validation import ParameterSchema


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
EXPIRATION = datetime(2026, 7, 13, 20, 0, tzinfo=UTC)


class _Policies:
    def evaluate(self, context: object) -> object:
        return context

    def size(self, context: object, *, capital_limit: object) -> object:
        return context, capital_limit

    def requirement(self, context: object) -> object:
        return context


@dataclass
class _SyntheticStrategy:
    specification: StrategySpecification
    parameter_schema: ParameterSchema
    requirements: StrategyRequirements
    entry_policy: Any = _Policies()
    exit_policy: Any = _Policies()
    roll_policy: Any = _Policies()
    sizing_policy: Any = _Policies()
    capital_policy: Any = _Policies()


def _strategy() -> _SyntheticStrategy:
    return _SyntheticStrategy(
        specification=StrategySpecification(
            strategy_id="synthetic_short_put",
            strategy_version="1.0.0",
            family="short_premium",
            parameters={},
            required_forecasts=(),
            required_features=("option_chain",),
            allowed_objectives=("return_on_collateral",),
            supported_margin_types=(MarginType.CASH,),
        ),
        parameter_schema=ParameterSchema(schema_version="1.0.0", fields={}),
        requirements=StrategyRequirements(data=(DataRequirement.OPTION_CHAIN,), forecasts=()),
    )


def _market() -> tuple[OptionContract, OptionQuote, OptionChainSnapshot]:
    contract = OptionContract(
        contract_id="SPY-590-P",
        occ_symbol="SPY260713P00590000",
        underlying="SPY",
        option_type=OptionType.PUT,
        strike=Decimal("590"),
        expiration_date=date(2026, 7, 13),
        expiration_at_utc=EXPIRATION,
        exercise_style=ExerciseStyle.AMERICAN,
        settlement_type=SettlementType.PHYSICAL,
    )
    quote = OptionQuote(
        contract_id=contract.contract_id,
        as_of_utc=DECISION,
        bid=Decimal("1.00"),
        ask=Decimal("1.10"),
        bid_size=10,
        ask_size=10,
        underlying_price=Decimal("600"),
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
    return contract, quote, chain


def test_registered_strategy_screens_simulates_and_scores_without_core_branches() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy())
    configured = registry.configured("synthetic_short_put", "1.0.0", {})
    contract, quote, chain = _market()

    screened = screen_option_candidates(
        chain,
        decision_at_utc=DECISION,
        strategy_id=configured.strategy_id,
        strategy_version=configured.strategy_version,
        policy=CandidateEligibilityPolicy(
            require_event_calendar=False,
            require_account_and_capabilities=False,
        ),
    )
    assert len(screened) == 1
    assert screened[0].eligible is True

    simulation = ShortPutSimulator(PessimisticFillPolicy()).simulate_expiration(
        simulation_id="simulation-1",
        contract=contract,
        contracts=1,
        open_quote=quote,
        opened_at_utc=DECISION,
        settlement_underlying_price=Decimal("600"),
    )
    capital = CapitalRequirement(
        treatment=CapitalTreatment.CASH_SECURED,
        cash_required=Decimal("59000"),
        covered_shares_required=Decimal("0"),
        maximum_loss=Decimal("58900"),
        estimated_buying_power_reduction=Decimal("59000"),
        buying_power_is_estimate=True,
        estimate_basis="synthetic fixture",
        opportunity_cost=Decimal("0"),
        eligible=True,
    )
    score = score_realized(
        RealizedObjectiveInput(
            simulation=simulation,
            capital=capital,
            terminal_share_price=Decimal("600"),
            liquidity_cost=Decimal("0"),
            concentration_penalty=Decimal("0"),
        ),
        ObjectiveWeights(
            return_weight=Decimal("1"),
            tail_weight=Decimal("0"),
            capital_weight=Decimal("0"),
            liquidity_weight=Decimal("0"),
            concentration_weight=Decimal("0"),
        ),
    )

    assert score.kind is ScoreKind.REALIZED
    assert score.components.pnl == Decimal("100")
    assert score.total_score == Decimal("100") / Decimal("59000")


def test_candidate_keys_are_stable_for_equivalent_chain_ordering() -> None:
    contract, quote, chain = _market()
    duplicate_order = OptionChainSnapshot(
        chain_id=chain.chain_id,
        underlying=chain.underlying,
        session_date=chain.session_date,
        as_of_utc=chain.as_of_utc,
        contracts=(contract,),
        quotes=(quote,),
        source=chain.source,
        ingested_at_utc=chain.ingested_at_utc,
    )
    policy = CandidateEligibilityPolicy(
        max_snapshot_age=timedelta(minutes=5),
        require_event_calendar=False,
        require_account_and_capabilities=False,
    )

    first = screen_option_candidates(
        chain,
        decision_at_utc=DECISION,
        strategy_id="synthetic_short_put",
        strategy_version="1.0.0",
        policy=policy,
    )
    second = screen_option_candidates(
        duplicate_order,
        decision_at_utc=DECISION,
        strategy_id="synthetic_short_put",
        strategy_version="1.0.0",
        policy=policy,
    )

    assert first[0].candidate_key == second[0].candidate_key
