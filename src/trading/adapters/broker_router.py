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

    def get_account_balances(self, adapter_name: str) -> RouterResult:
        return self.get_balances(adapter_name)

    def get_open_orders(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]

        if hasattr(adapter, "get_open_orders"):
            result = adapter.get_open_orders()
        elif hasattr(adapter, "get_orders"):
            result = adapter.get_orders()
        else:
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support open order retrieval")
        return RouterResult(adapter=adapter_name, action="get_open_orders", result=result)

    def get_recent_fills(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]
        if not hasattr(adapter, "get_recent_fills"):
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support fills retrieval")
        result = adapter.get_recent_fills()
        return RouterResult(adapter=adapter_name, action="get_recent_fills", result=result)

    def close_position(self, adapter_name: str, symbol: str, qty: float | str = "all") -> RouterResult:
        adapter = self._adapters[adapter_name]
        if not hasattr(adapter, "close_position"):
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support close_position")
        result = adapter.close_position(symbol=symbol, qty=qty)
        return RouterResult(adapter=adapter_name, action="close_position", result=result)

    def close_all_positions(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]
        if not hasattr(adapter, "close_all_positions"):
            raise NotImplementedError(f"Adapter '{adapter_name}' does not support close_all_positions")
        result = adapter.close_all_positions()
        return RouterResult(adapter=adapter_name, action="close_all_positions", result=result)

    def cancel_all_orders(self, adapter_name: str) -> RouterResult:
        open_orders = self.get_open_orders(adapter_name).result
        order_ids = self._extract_order_ids(open_orders)
        cancelled: list[dict[str, Any]] = []
        for order_id in order_ids:
            res = self.cancel_order(adapter_name, order_id)
            cancelled.append({"order_id": order_id, "result": res.result})
        return RouterResult(
            adapter=adapter_name,
            action="cancel_all_orders",
            result={"cancelled_count": len(cancelled), "cancelled": cancelled},
        )

    def capabilities(self, adapter_name: str) -> RouterResult:
        adapter = self._adapters[adapter_name]
        capability_map = {
            "submit_order": any(hasattr(adapter, name) for name in ("place_order", "create_order_ticket", "send_alert")),
            "cancel_order": hasattr(adapter, "cancel_order"),
            "get_positions": any(hasattr(adapter, name) for name in ("get_positions", "get_holdings")),
            "get_account_balances": any(hasattr(adapter, name) for name in ("get_balances", "get_accounts")),
            "get_open_orders": any(hasattr(adapter, name) for name in ("get_open_orders", "get_orders")),
            "get_recent_fills": hasattr(adapter, "get_recent_fills"),
            "close_position": hasattr(adapter, "close_position"),
            "close_all_positions": hasattr(adapter, "close_all_positions"),
        }
        return RouterResult(adapter=adapter_name, action="capabilities", result=capability_map)

    @staticmethod
    def _extract_order_ids(payload: Any) -> list[str]:
        if isinstance(payload, dict):
            for key in ("orders", "results", "open_orders"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    payload = nested
                    break
            else:
                payload = [payload]

        if not isinstance(payload, list):
            return []

        out: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            oid = item.get("order_id") or item.get("id")
            if oid is not None:
                out.append(str(oid))
        return out


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
