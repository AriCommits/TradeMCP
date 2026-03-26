from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._config_utils import load_yaml


@dataclass
class FidelityActiveTraderConfig:
    enabled: bool
    export_dir: str
    account_label: str
    manual_review_required: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "FidelityActiveTraderConfig":
        raw = load_yaml(path)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            export_dir=str(raw.get("export_dir", "artifacts/fidelity_tickets")),
            account_label=str(raw.get("account_label", "Fidelity")),
            manual_review_required=bool(raw.get("manual_review_required", True)),
        )


class FidelityActiveTraderAdapter:
    def __init__(self, config: FidelityActiveTraderConfig):
        self.config = config
        self._ticket_dir = Path(self.config.export_dir)
        self._ticket_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config_file(cls, path: str | Path) -> "FidelityActiveTraderAdapter":
        return cls(FidelityActiveTraderConfig.from_file(path))

    def ping(self) -> dict[str, Any]:
        return {
            "adapter": "fidelity_active_trader",
            "enabled": self.config.enabled,
            "mode": "manual_ticket",
            "manual_review_required": self.config.manual_review_required,
            "ticket_dir": str(self._ticket_dir),
        }

    def create_order_ticket(self, order: dict[str, Any]) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        symbol = str(order.get("symbol", "UNKNOWN"))
        path = self._ticket_dir / f"fidelity_ticket_{symbol}_{stamp}.json"

        payload = {
            "adapter": "fidelity_active_trader",
            "account_label": self.config.account_label,
            "manual_review_required": self.config.manual_review_required,
            "created_at_utc": stamp,
            "order": order,
            "status": "pending_manual_submission",
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return {
            "adapter": "fidelity_active_trader",
            "ticket_path": str(path),
            "status": payload["status"],
        }

    def list_order_tickets(self) -> list[str]:
        return [str(p) for p in sorted(self._ticket_dir.glob("fidelity_ticket_*.json"))]
