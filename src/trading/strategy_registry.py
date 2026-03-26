from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    market: str
    family: str
    required_features: tuple[str, ...]
    risk_profile: str
    execution_constraints: tuple[str, ...]


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies = self._default_strategies()

    @staticmethod
    def _default_strategies() -> list[StrategySpec]:
        return [
            StrategySpec(
                strategy_id="stocks_regime_momentum",
                market="stocks",
                family="momentum",
                required_features=("log_return", "regime", "vol_forecast"),
                risk_profile="balanced",
                execution_constraints=("daylight_hours", "max_slippage_guard"),
            ),
            StrategySpec(
                strategy_id="stocks_mean_reversion",
                market="stocks",
                family="mean_reversion",
                required_features=("z_score", "regime", "realized_vol"),
                risk_profile="conservative",
                execution_constraints=("max_position_cap",),
            ),
            StrategySpec(
                strategy_id="forex_session_breakout",
                market="forex",
                family="breakout",
                required_features=("session_overlap", "macro_event_flag", "vol_forecast"),
                risk_profile="balanced",
                execution_constraints=("spread_guard", "max_slippage_guard"),
            ),
            StrategySpec(
                strategy_id="crypto_24x7_trend",
                market="crypto",
                family="trend",
                required_features=("funding_bias", "liquidity_score", "regime"),
                risk_profile="aggressive",
                execution_constraints=("always_on_risk_checks", "max_drawdown_stop"),
            ),
            StrategySpec(
                strategy_id="intl_fx_neutral_momentum",
                market="intl_stocks",
                family="momentum",
                required_features=("exchange_calendar", "fx_decomposition", "regime"),
                risk_profile="balanced",
                execution_constraints=("session_alignment", "fx_hedge_required"),
            ),
        ]

    def for_market(self, market: str) -> list[StrategySpec]:
        norm = market.strip().lower()
        return [s for s in self._strategies if s.market == norm]

    def all(self) -> list[StrategySpec]:
        return list(self._strategies)
