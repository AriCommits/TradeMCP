from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ._config_utils import env_or_none, load_yaml


@dataclass
class GeminiConfig:
    enabled: bool
    sandbox: bool
    base_url: str
    symbols_endpoint: str
    balances_endpoint: str
    order_new_endpoint: str
    order_cancel_endpoint: str
    api_key_env: str
    api_secret_env: str
    timeout_seconds: int
    dry_run: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "GeminiConfig":
        raw = load_yaml(path)
        sandbox = bool(raw.get("sandbox", True))
        base = raw.get("base_url")
        if not base:
            base = "https://api.sandbox.gemini.com" if sandbox else "https://api.gemini.com"

        return cls(
            enabled=bool(raw.get("enabled", False)),
            sandbox=sandbox,
            base_url=str(base),
            symbols_endpoint=str(raw.get("symbols_endpoint", "/v1/symbols")),
            balances_endpoint=str(raw.get("balances_endpoint", "/v1/balances")),
            order_new_endpoint=str(raw.get("order_new_endpoint", "/v1/order/new")),
            order_cancel_endpoint=str(raw.get("order_cancel_endpoint", "/v1/order/cancel")),
            api_key_env=str(raw.get("api_key_env", "GEMINI_API_KEY")),
            api_secret_env=str(raw.get("api_secret_env", "GEMINI_API_SECRET")),
            timeout_seconds=int(raw.get("timeout_seconds", 20)),
            dry_run=bool(raw.get("dry_run", True)),
        )


class GeminiAdapter:
    def __init__(self, config: GeminiConfig):
        self.config = config

    @classmethod
    def from_config_file(cls, path: str | Path) -> "GeminiAdapter":
        return cls(GeminiConfig.from_file(path))

    def _url(self, endpoint: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _api_key(self) -> str:
        key = env_or_none(self.config.api_key_env)
        if not key:
            raise ValueError(f"Missing Gemini API key env: {self.config.api_key_env}")
        return key

    def _api_secret(self) -> str:
        secret = env_or_none(self.config.api_secret_env)
        if not secret:
            raise ValueError(f"Missing Gemini API secret env: {self.config.api_secret_env}")
        return secret

    def _signed_headers(self, payload: dict[str, Any]) -> dict[str, str]:
        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode("utf-8"))
        signature = hmac.new(
            self._api_secret().encode("utf-8"),
            payload_b64,
            hashlib.sha384,
        ).hexdigest()

        return {
            "X-GEMINI-APIKEY": self._api_key(),
            "X-GEMINI-PAYLOAD": payload_b64.decode("utf-8"),
            "X-GEMINI-SIGNATURE": signature,
            "Content-Type": "text/plain",
            "Content-Length": "0",
            "Cache-Control": "no-cache",
        }

    def ping(self, check_remote: bool = False) -> dict[str, Any]:
        base = {
            "adapter": "gemini",
            "enabled": self.config.enabled,
            "sandbox": self.config.sandbox,
            "base_url": self.config.base_url,
        }
        if not check_remote:
            return {**base, "remote_checked": False}

        try:
            response = requests.get(self._url(self.config.symbols_endpoint), timeout=self.config.timeout_seconds)
            response.raise_for_status()
            symbols = response.json()
            return {
                **base,
                "remote_checked": True,
                "reachable": True,
                "symbols_count": len(symbols) if isinstance(symbols, list) else None,
            }
        except Exception as exc:
            return {
                **base,
                "remote_checked": True,
                "reachable": False,
                "error": str(exc),
            }

    def get_symbols(self) -> list[str]:
        response = requests.get(self._url(self.config.symbols_endpoint), timeout=self.config.timeout_seconds)
        response.raise_for_status()
        out = response.json()
        return out if isinstance(out, list) else []

    def get_balances(self) -> dict[str, Any]:
        payload = {
            "request": self.config.balances_endpoint,
            "nonce": str(int(time.time() * 1000)),
        }
        response = requests.post(
            self._url(self.config.balances_endpoint),
            headers=self._signed_headers(payload),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        order_type: str = "exchange limit",
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request": self.config.order_new_endpoint,
            "nonce": str(int(time.time() * 1000)),
            "symbol": symbol,
            "side": side.lower(),
            "amount": str(amount),
            "price": str(price),
            "type": order_type,
        }
        if client_order_id:
            payload["client_order_id"] = client_order_id

        if self.config.dry_run:
            return {"adapter": "gemini", "dry_run": True, "payload": payload}

        response = requests.post(
            self._url(self.config.order_new_endpoint),
            headers=self._signed_headers(payload),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        payload = {
            "request": self.config.order_cancel_endpoint,
            "nonce": str(int(time.time() * 1000)),
            "order_id": order_id,
        }
        if self.config.dry_run:
            return {"adapter": "gemini", "dry_run": True, "payload": payload}

        response = requests.post(
            self._url(self.config.order_cancel_endpoint),
            headers=self._signed_headers(payload),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
