"""Strategy definitions, account state, candidates, and simulation summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from trading.options.contracts import OptionLeg, VersionedRecord, require_utc


class MarginType(str, Enum):
    CASH = "cash"
    REG_T = "reg_t"
    PORTFOLIO = "portfolio"
    PAPER = "paper"


@dataclass(frozen=True)
class AccountHolding(VersionedRecord):
    asset_id: str
    asset_kind: str
    quantity: Decimal
    mark_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.asset_id or not self.asset_kind:
            raise ValueError("holding asset_id and asset_kind are required")
        if self.mark_price is not None and self.mark_price < 0:
            raise ValueError("mark_price cannot be negative")


@dataclass(frozen=True)
class AccountSnapshot(VersionedRecord):
    account_id_hash: str
    adapter: str
    as_of_utc: datetime
    currency: str
    cash: Decimal
    net_liquidation: Decimal
    buying_power: Decimal
    option_buying_power: Decimal
    margin_type: MarginType
    option_level: str
    holdings: tuple[AccountHolding, ...] = ()
    open_order_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.as_of_utc, "as_of_utc")
        if not self.account_id_hash or not self.adapter or not self.option_level:
            raise ValueError("account identity, adapter, and option_level are required")
        if len(self.currency) != 3 or self.currency.upper() != self.currency:
            raise ValueError("currency must be an uppercase ISO-style code")
        if any(value < 0 for value in (self.buying_power, self.option_buying_power)):
            raise ValueError("buying power values cannot be negative")


@dataclass(frozen=True)
class StrategySpecification(VersionedRecord):
    strategy_id: str
    strategy_version: str
    family: str
    parameters: dict[str, Any]
    required_forecasts: tuple[str, ...]
    required_features: tuple[str, ...]
    allowed_objectives: tuple[str, ...]
    supported_margin_types: tuple[MarginType, ...]
    known_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_version or not self.family:
            raise ValueError("strategy identity, version, and family are required")


@dataclass(frozen=True)
class CandidatePosition(VersionedRecord):
    candidate_id: str
    decision_at_utc: datetime
    strategy_id: str
    strategy_version: str
    underlying: str
    legs: tuple[OptionLeg, ...]
    market_snapshot_id: str
    forecast_bundle_id: str
    entry_rules: dict[str, Any]
    exit_rules: dict[str, Any]
    capital_required: Decimal
    eligible: bool
    eligibility_flags: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.decision_at_utc, "decision_at_utc")
        required = (
            self.candidate_id,
            self.strategy_id,
            self.strategy_version,
            self.underlying,
            self.market_snapshot_id,
            self.forecast_bundle_id,
        )
        if not all(required) or not self.legs:
            raise ValueError("candidate identifiers and at least one leg are required")
        if self.capital_required < 0:
            raise ValueError("capital_required cannot be negative")
        if self.eligible and self.rejection_reasons:
            raise ValueError("an eligible candidate cannot have rejection reasons")
        if any(leg.contract.underlying != self.underlying for leg in self.legs):
            raise ValueError("all candidate legs must match the candidate underlying")


@dataclass(frozen=True)
class SimulationSummary(VersionedRecord):
    simulation_id: str
    candidate_id: str
    scenario_id: str
    simulated_at_utc: datetime
    entry_fill: Decimal
    exit_fill: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    capital_required: Decimal
    return_on_capital: float | None
    max_adverse_excursion: Decimal
    max_favorable_excursion: Decimal
    fees: Decimal
    slippage: Decimal
    assigned: bool = False
    exercised: bool = False
    rolled: bool = False
    lifecycle_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.simulated_at_utc, "simulated_at_utc")
        if not self.simulation_id or not self.candidate_id or not self.scenario_id:
            raise ValueError("simulation, candidate, and scenario identifiers are required")
        if any(value < 0 for value in (self.entry_fill, self.exit_fill, self.capital_required)):
            raise ValueError("fills and capital_required cannot be negative")
        if self.fees < 0 or self.slippage < 0:
            raise ValueError("fees and slippage cannot be negative")
