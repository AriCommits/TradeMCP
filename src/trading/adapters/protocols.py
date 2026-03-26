from __future__ import annotations

from typing import Any, Protocol, TypeGuard


class AdapterReadProtocol(Protocol):
    def ping(self) -> dict[str, Any]: ...
    def get_positions(self) -> dict[str, Any]: ...
    def get_open_orders(self) -> dict[str, Any]: ...
    def get_balances(self) -> dict[str, Any]: ...
    def get_recent_fills(self) -> dict[str, Any]: ...


class AdapterExecutionProtocol(Protocol):
    def submit_order_intent(self, order: dict[str, Any]) -> dict[str, Any]: ...
    def cancel_order(self, order_id: str) -> dict[str, Any]: ...
    def close_position(self, symbol: str, qty: float | str = "all") -> dict[str, Any]: ...
    def close_all_positions(self) -> dict[str, Any]: ...


class AdapterProtocol(AdapterReadProtocol, AdapterExecutionProtocol, Protocol):
    """Full read + execution contract."""


def supports_read(adapter: object) -> TypeGuard[AdapterReadProtocol]:
    return all(
        hasattr(adapter, attr)
        for attr in (
            "ping",
            "get_positions",
            "get_open_orders",
            "get_balances",
            "get_recent_fills",
        )
    )


def supports_execution(adapter: object) -> TypeGuard[AdapterExecutionProtocol]:
    return all(
        hasattr(adapter, attr)
        for attr in (
            "submit_order_intent",
            "cancel_order",
            "close_position",
            "close_all_positions",
        )
    )
