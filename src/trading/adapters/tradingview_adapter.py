from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ._config_utils import env_or_none, load_yaml


@dataclass
class TradingViewConfig:
    enabled: bool
    webhook_url_env: str
    webhook_secret_env: str | None
    timeout_seconds: int
    dry_run: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "TradingViewConfig":
        raw = load_yaml(path)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            webhook_url_env=str(raw.get("webhook_url_env", "TRADINGVIEW_WEBHOOK_URL")),
            webhook_secret_env=raw.get("webhook_secret_env"),
            timeout_seconds=int(raw.get("timeout_seconds", 15)),
            dry_run=bool(raw.get("dry_run", True)),
        )


class TradingViewAdapter:
    def __init__(self, config: TradingViewConfig):
        self.config = config

    @classmethod
    def from_config_file(cls, path: str | Path) -> "TradingViewAdapter":
        return cls(TradingViewConfig.from_file(path))

    def ping(self) -> dict[str, Any]:
        url = env_or_none(self.config.webhook_url_env)
        return {
            "adapter": "tradingview",
            "enabled": self.config.enabled,
            "configured": url is not None,
            "mode": "webhook",
        }

    def send_alert(self, payload: dict[str, Any] | str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        url = env_or_none(self.config.webhook_url_env)
        if not url:
            raise ValueError(
                f"TradingView webhook URL missing. Set env var: {self.config.webhook_url_env}"
            )

        request_headers = dict(headers or {})
        secret = env_or_none(self.config.webhook_secret_env)
        if secret:
            request_headers.setdefault("X-Webhook-Secret", secret)

        if self.config.dry_run:
            return {
                "adapter": "tradingview",
                "dry_run": True,
                "webhook_url": url,
                "payload_type": "json" if isinstance(payload, dict) else "text",
            }

        if isinstance(payload, dict):
            response = requests.post(
                url,
                json=payload,
                headers=request_headers,
                timeout=self.config.timeout_seconds,
            )
        else:
            request_headers.setdefault("Content-Type", "text/plain")
            response = requests.post(
                url,
                data=payload.encode("utf-8"),
                headers=request_headers,
                timeout=self.config.timeout_seconds,
            )
        response.raise_for_status()
        return {
            "adapter": "tradingview",
            "status_code": response.status_code,
            "ok": True,
        }

    def get_positions(self) -> dict[str, Any]:
        return {"adapter": "tradingview", "positions": [], "note": "not_supported_for_webhook_mode"}

    def get_open_orders(self) -> dict[str, Any]:
        return {"adapter": "tradingview", "orders": [], "note": "not_supported_for_webhook_mode"}

    def get_balances(self) -> dict[str, Any]:
        return {"adapter": "tradingview", "balances": [], "note": "not_supported_for_webhook_mode"}

    def get_account_balances(self) -> dict[str, Any]:
        return self.get_balances()

    def get_recent_fills(self) -> dict[str, Any]:
        return {"adapter": "tradingview", "fills": [], "note": "not_supported_for_webhook_mode"}

    def close_position(self, symbol: str, qty: float | str = "all") -> dict[str, Any]:
        return {
            "adapter": "tradingview",
            "status": "not_supported_for_webhook_mode",
            "symbol": symbol,
            "qty": qty,
        }

    def close_all_positions(self) -> dict[str, Any]:
        return {"adapter": "tradingview", "status": "not_supported_for_webhook_mode"}
