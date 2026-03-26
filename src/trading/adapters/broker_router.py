from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fidelity_active_trader_adapter import FidelityActiveTraderAdapter
from .forex_com_adapter import ForexComAdapter
from .gemini_adapter import GeminiAdapter
from .robinhood_crypto_adapter import RobinhoodCryptoAdapter
from .tradingview_adapter import TradingViewAdapter


@dataclass
class RouterResult:
    adapter: str
    action: str
    result: Any


class BrokerRouter:
    """
    Loose-coupling intermediary API.

    Each adapter stays independent (no shared base class), while this router provides
    common routing methods for cross-venue orchestration.
    """

    def __init__(self):
        self._adapters: dict[str, Any] = {}

    def register(self, name: str, adapter: Any) -> None:
        self._adapters[name] = adapter

    def registered(self) -> list[str]:
        return sorted(self._adapters.keys())

    def ping_all(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, adapter in self._adapters.items():
            if hasattr(adapter, "ping"):
                out[name] = adapter.ping()
            else:
                out[name] = {"adapter": name, "error": "ping_not_supported"}
        return out

    def submit_order(self, adapter_name: str, order: dict[str, Any]) -> RouterResult:
        adapter = self._adapters[adapter_name]

        if hasattr(adapter, "place_order"):
            result = adapter.place_order(**order)
            return RouterResult(adapter=adapter_name, action="submit_order", result=result)

        if hasattr(adapter, "create_order_ticket"):
            result = adapter.create_order_ticket(order)
            return RouterResult(adapter=adapter_name, action="submit_order", result=result)

        if hasattr(adapter, "send_alert"):
            result = adapter.send_alert(order)
            return RouterResult(adapter=adapter_name, action="submit_order", result=result)

        raise NotImplementedError(f"Adapter '{adapter_name}' does not support submit_order")

    def cancel_order(self, adapter_name: str, order_id: str) -> RouterResult:
        adapter = self._adapters[adapter_name]
        if not hasattr(adapter, "cancel_order"):
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support cancel_order")
        result = adapter.cancel_order(order_id)
        return RouterResult(adapter=adapter_name, action="cancel_order", result=result)

    def get_positions(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]

        if hasattr(adapter, "get_positions"):
            result = adapter.get_positions()
        elif hasattr(adapter, "get_holdings"):
            result = adapter.get_holdings()
        else:
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support position retrieval")
        return RouterResult(adapter=adapter_name, action="get_positions", result=result)

    def get_balances(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]

        if hasattr(adapter, "get_balances"):
            result = adapter.get_balances()
        elif hasattr(adapter, "get_accounts"):
            result = adapter.get_accounts()
        else:
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support balances retrieval")
        return RouterResult(adapter=adapter_name, action="get_balances", result=result)


def build_router_from_config_dir(config_dir: str | Path) -> BrokerRouter:
    base = Path(config_dir)
    router = BrokerRouter()

    tv_cfg = base / "tradingview.yaml"
    if tv_cfg.exists():
        router.register("tradingview", TradingViewAdapter.from_config_file(tv_cfg))

    fidelity_cfg = base / "fidelity_active_trader.yaml"
    if fidelity_cfg.exists():
        router.register("fidelity_active_trader", FidelityActiveTraderAdapter.from_config_file(fidelity_cfg))

    robinhood_cfg = base / "robinhood_crypto.yaml"
    if robinhood_cfg.exists():
        router.register("robinhood_crypto", RobinhoodCryptoAdapter.from_config_file(robinhood_cfg))

    gemini_cfg = base / "gemini.yaml"
    if gemini_cfg.exists():
        router.register("gemini", GeminiAdapter.from_config_file(gemini_cfg))

    forex_cfg = base / "forex_com.yaml"
    if forex_cfg.exists():
        router.register("forex_com", ForexComAdapter.from_config_file(forex_cfg))

    return router
