from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ._config_utils import env_or_none, load_yaml


@dataclass
class ForexComConfig:
    enabled: bool
    base_url: str
    auth_endpoint: str
    positions_endpoint: str
    orders_endpoint: str
    api_key_env: str | None
    username_env: str | None
    password_env: str | None
    bearer_token_env: str | None
    timeout_seconds: int
    dry_run: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "ForexComConfig":
        raw = load_yaml(path)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            base_url=str(raw.get("base_url", "https://api-demo.forex.com")),
            auth_endpoint=str(raw.get("auth_endpoint", "/session")),
            positions_endpoint=str(raw.get("positions_endpoint", "/positions")),
            orders_endpoint=str(raw.get("orders_endpoint", "/orders")),
            api_key_env=raw.get("api_key_env"),
            username_env=raw.get("username_env"),
            password_env=raw.get("password_env"),
            bearer_token_env=raw.get("bearer_token_env"),
            timeout_seconds=int(raw.get("timeout_seconds", 20)),
            dry_run=bool(raw.get("dry_run", True)),
        )


class ForexComAdapter:
    def __init__(self, config: ForexComConfig):
        self.config = config
        self._session_token: str | None = None

    @classmethod
    def from_config_file(cls, path: str | Path) -> "ForexComAdapter":
        return cls(ForexComConfig.from_file(path))

    def _url(self, endpoint: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = env_or_none(self.config.api_key_env)
        if api_key:
            headers["X-API-KEY"] = api_key

        bearer = self._session_token or env_or_none(self.config.bearer_token_env)
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        return headers

    def ping(self) -> dict[str, Any]:
        return {
            "adapter": "forex_com",
            "enabled": self.config.enabled,
            "configured": bool(env_or_none(self.config.api_key_env) or env_or_none(self.config.bearer_token_env)),
            "base_url": self.config.base_url,
        }

    def authenticate(self) -> dict[str, Any]:
        username = env_or_none(self.config.username_env)
        password = env_or_none(self.config.password_env)

        if not username or not password:
            return {
                "adapter": "forex_com",
                "authenticated": False,
                "reason": "username/password env vars not configured",
            }

        payload = {"username": username, "password": password}
        response = requests.post(
            self._url(self.config.auth_endpoint),
            json=payload,
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("session") or data.get("token") or data.get("accessToken")
        if token:
            self._session_token = str(token)

        return {
            "adapter": "forex_com",
            "authenticated": token is not None,
        }

    def get_positions(self) -> dict[str, Any]:
        response = requests.get(
            self._url(self.config.positions_endpoint),
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side.lower(),
            "quantity": quantity,
            "type": order_type.lower(),
        }
        if stop_loss is not None:
            payload["stop_loss"] = stop_loss
        if take_profit is not None:
            payload["take_profit"] = take_profit

        if self.config.dry_run:
            return {"adapter": "forex_com", "dry_run": True, "payload": payload}

        response = requests.post(
            self._url(self.config.orders_endpoint),
            json=payload,
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {"adapter": "forex_com", "dry_run": True, "order_id": order_id}

        response = requests.delete(
            self._url(f"{self.config.orders_endpoint.rstrip('/')}/{order_id}"),
            headers=self._headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json() if response.content else {"status": "cancelled", "order_id": order_id}
