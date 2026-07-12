"""Saved-fixture account provider; intentionally contains no live broker calls."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from trading.options.contracts import require_utc
from trading.options.market_inputs import MissingMarketInputError, StaleMarketInputError
from trading.strategies.specifications import AccountSnapshot

from .records import BrokerCapabilities


class SavedAccountProvider:
    """Select immutable snapshots that existed by a requested decision time."""

    def __init__(
        self,
        snapshots: tuple[AccountSnapshot, ...],
        capabilities: tuple[BrokerCapabilities, ...],
    ) -> None:
        self._snapshots = snapshots
        self._capabilities = capabilities

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SavedAccountProvider":
        snapshots = tuple(AccountSnapshot.from_dict(item) for item in payload.get("snapshots", ()))
        capabilities = tuple(
            BrokerCapabilities.from_dict(item) for item in payload.get("capabilities", ())
        )
        return cls(snapshots, capabilities)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "SavedAccountProvider":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("saved account fixture must be a JSON object")
        return cls.from_dict(payload)

    def account_snapshot(
        self,
        account_id_hash: str,
        decision_at_utc: datetime,
        max_age: timedelta,
    ) -> AccountSnapshot:
        require_utc(decision_at_utc, "decision_at_utc")
        eligible = tuple(
            snapshot
            for snapshot in self._snapshots
            if snapshot.account_id_hash == account_id_hash and snapshot.as_of_utc <= decision_at_utc
        )
        if not eligible:
            raise MissingMarketInputError(f"no account snapshot for {account_id_hash}")
        selected = max(eligible, key=lambda snapshot: snapshot.as_of_utc)
        if decision_at_utc - selected.as_of_utc > max_age:
            raise StaleMarketInputError(f"account snapshot for {account_id_hash} is stale")
        return selected

    def broker_capabilities(
        self, adapter: str, decision_at_utc: datetime, max_age: timedelta
    ) -> BrokerCapabilities:
        require_utc(decision_at_utc, "decision_at_utc")
        eligible = tuple(
            record
            for record in self._capabilities
            if record.adapter == adapter
            and record.as_of_utc <= decision_at_utc
            and record.published_at_utc <= decision_at_utc
        )
        if not eligible:
            raise MissingMarketInputError(f"no broker capabilities for {adapter}")
        selected = max(eligible, key=lambda record: (record.as_of_utc, record.published_at_utc))
        if decision_at_utc - selected.as_of_utc > max_age:
            raise StaleMarketInputError(f"broker capabilities for {adapter} are stale")
        return selected
