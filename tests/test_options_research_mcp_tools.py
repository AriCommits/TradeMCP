from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from trading.forecasts import ForecastBundle
from trading.mcp.research_tools import build_research_tools, register_research_tools
from trading.options.quotes import OptionChainSnapshot
from trading.strategies.registry import StrategyRegistry
from trading.strategies.weekend_short_put import WEEKEND_SHORT_PUT


DECISION = datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc)


class _Services:
    def __init__(self) -> None:
        self.last_call: tuple[str, dict[str, Any]] | None = None

    def get_options_chain(self, **kwargs: Any) -> OptionChainSnapshot:
        self.last_call = ("get_options_chain", kwargs)
        return OptionChainSnapshot(
            chain_id="chain-1",
            underlying=kwargs["underlying"],
            session_date=date(2026, 7, 10),
            as_of_utc=DECISION,
            contracts=(),
            quotes=(),
            source="saved-test-data",
            ingested_at_utc=DECISION,
        )

    def get_market_state(self, **kwargs: Any) -> ForecastBundle:
        self.last_call = ("get_market_state", kwargs)
        return ForecastBundle(
            bundle_id="bundle-1",
            decision_at_utc=kwargs["decision_at_utc"],
            symbol=kwargs["symbol"],
            forecasts=(),
        )

    def validate_research_data(self, **kwargs: Any) -> dict[str, Any]:
        self.last_call = ("validate_research_data", kwargs)
        return {"valid": True, "point_in_time": True, "defects": []}

    def run_options_walkforward(self, **kwargs: Any) -> Any:
        self.last_call = ("run_options_walkforward", kwargs)
        return {"evaluation_id": "walk-forward-test", "scope": "research_estimate"}

    def backtest_option_strategy(self, **kwargs: Any) -> dict[str, Any]:
        self.last_call = ("backtest_option_strategy", kwargs)
        return {"backtest_id": "backtest-test", "scope": "research_estimate"}


class _Server:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}

    def register_tool(self, **kwargs: Any) -> None:
        self.tools[kwargs["name"]] = kwargs


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(WEEKEND_SHORT_PUT)
    return registry


def _tool(name: str, services: _Services | None = None) -> Any:
    definitions = build_research_tools(services or _Services(), _registry())
    return next(item for item in definitions if item.name == name).handler


def _provenance(**extra: str) -> dict[str, str]:
    return {"data_version": "saved-2026-07-10", **extra}


def test_registration_is_explicit_complete_and_read_only() -> None:
    server = _Server()
    names = register_research_tools(server, _Services(), _registry())

    assert names == (
        "get_options_chain",
        "get_market_state",
        "validate_research_data",
        "list_option_strategies",
        "validate_strategy_spec",
        "run_options_walkforward",
        "backtest_option_strategy",
    )
    assert set(server.tools) == set(names)
    assert all("order" not in name and "execute" not in name for name in names)
    assert all(tool["schema"]["additionalProperties"] is False for tool in server.tools.values())


def test_chain_handler_enforces_point_in_time_and_has_stable_ids() -> None:
    services = _Services()
    handler = _tool("get_options_chain", services)
    request = {
        "decision_at_utc": "2026-07-10T20:00:00Z",
        "underlying": "SPY",
        "provenance": _provenance(),
    }

    first = handler(request)
    second = handler(request)

    assert first == second
    assert first["read_only"] is True
    assert first["result"]["chain_id"] == "chain-1"
    assert first["unit_conventions"]["option_quantity"].startswith("contracts")
    assert services.last_call is not None
    assert services.last_call[1]["as_of_utc"] == DECISION


def test_all_tools_reject_implicit_or_naive_time() -> None:
    handler = _tool("list_option_strategies")

    with pytest.raises(ValueError, match="ending in Z"):
        handler(
            {
                "decision_at_utc": "2026-07-10T20:00:00",
                "provenance": {"registry_version": "1.0.0"},
            }
        )


def test_market_state_requires_horizon_clock_and_provenance_versions() -> None:
    handler = _tool("get_market_state")
    base = {
        "decision_at_utc": "2026-07-10T20:00:00Z",
        "symbol": "SPY",
        "horizons": [{"kind": "overnight_intervals", "count": 1}],
        "provenance": _provenance(model_version="ewma-1", feature_version="features-1"),
    }

    result = handler(base)
    assert result["result"]["decision_at_utc"] == "2026-07-10T20:00:00Z"

    broken = {**base, "provenance": _provenance(model_version="ewma-1")}
    with pytest.raises(ValueError, match="feature_version"):
        handler(broken)


def test_strategy_validation_normalizes_defaults() -> None:
    result = _tool("validate_strategy_spec")(
        {
            "decision_at_utc": "2026-07-10T20:00:00Z",
            "strategy_id": "weekend_short_put",
            "strategy_version": "1.0.0",
            "strategy_parameters": {},
            "provenance": {"registry_version": "1.0.0"},
        }
    )["result"]

    assert result["valid"] is True
    assert result["normalized_parameters"]["max_contracts"] == 1


def test_backtest_requires_objective_and_account_assumptions() -> None:
    handler = _tool("backtest_option_strategy")
    request = {
        "decision_at_utc": "2026-07-10T20:00:00Z",
        "strategy_id": "weekend_short_put",
        "strategy_version": "1.0.0",
        "strategy_parameters": {},
        "objective_id": "tail_adjusted_return",
        "objective_assumptions": {"tail_probability": 0.05},
        "account_assumptions": {"margin_type": "cash", "currency": "USD"},
        "provenance": _provenance(
            model_version="ewma-1",
            objective_version="1.0.0",
            config_version="1.0.0",
            code_version="test-sha",
        ),
    }

    response = handler(request)
    assert response["result"]["scope"] == "research_estimate"

    with pytest.raises(ValueError, match="account_assumptions"):
        handler({**request, "account_assumptions": {}})
