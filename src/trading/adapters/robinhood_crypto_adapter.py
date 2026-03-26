from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ._config_utils import env_or_none, load_yaml


@dataclass
class RobinhoodCryptoConfig:
    enabled: bool
    base_url: str
    accounts_endpoint: str
    holdings_endpoint: str
    orders_endpoint: str
    api_key_env: str | None
    api_secret_env: str | None
    bearer_token_env: str | None
    timeout_seconds: int
    dry_run: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "RobinhoodCryptoConfig":
        raw = load_yaml(path)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            base_url=str(raw.get("base_url", "https://trading.robinhood.com")),
            accounts_endpoint=str(raw.get("accounts_endpoint", "/api/v1/crypto/trading/accounts/")),
            holdings_endpoint=str(raw.get("holdings_endpoint", "/api/v1/crypto/trading/holdings/")),
            orders_endpoint=str(raw.get("orders_endpoint", "/api/v1/crypto/trading/orders/")),
            api_key_env=raw.get("api_key_env"),
            api_secret_env=raw.get("api_secret_env"),
            bearer_token_env=raw.get("bearer_token_env"),
            timeout_seconds=int(raw.get("timeout_seconds", 20)),
            dry_run=bool(raw.get("dry_run", True)),
        )


class RobinhoodCryptoAdapter:
    def __init__(self, config: RobinhoodCryptoConfig):
        self.config = config

    @classmethod
    def from_config_file(cls, path: str | Path) -> "RobinhoodCryptoAdapter":
        return cls(RobinhoodCryptoConfig.from_file(path))

    def _url(self, endpoint: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        bearer = env_or_none(self.config.bearer_token_env)
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        api_key = env_or_none(self.config.api_key_env)
        api_secret = env_or_none(self.config.api_secret_env)
        if api_key:
            headers["x-api-key"] = api_key
        if api_secret:
            headers["x-api-secret"] = api_secret
        return headers

    def ping(self) -> dict[str, Any]:
        return {
            "adapter": "robinhood_crypto",
            "enabled": self.config.enabled,
            "configured": bool(self._auth_headers()),
            "base_url": self.config.base_url,
        }

    def get_accounts(self) -> dict[str, Any]:
        response = requests.get(
            self._url(self.config.accounts_endpoint),
            headers=self._auth_headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_holdings(self) -> dict[str, Any]:
        response = requests.get(
            self._url(self.config.holdings_endpoint),
            headers=self._auth_headers(),
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
        limit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side.lower(),
            "quantity": quantity,
            "type": order_type.lower(),
        }
        if limit_price is not None:
            payload["limit_price"] = limit_price
        if client_order_id:
            payload["client_order_id"] = client_order_id

        if self.config.dry_run:
            return {"adapter": "robinhood_crypto", "dry_run": True, "payload": payload}

        response = requests.post(
            self._url(self.config.orders_endpoint),
            json=payload,
            headers=self._auth_headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {"adapter": "robinhood_crypto", "dry_run": True, "order_id": order_id}

        response = requests.delete(
            self._url(f"{self.config.orders_endpoint.rstrip('/')}/{order_id}"),
            headers=self._auth_headers(),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json() if response.content else {"status": "cancelled", "order_id": order_id}
