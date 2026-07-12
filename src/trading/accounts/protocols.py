"""Replaceable account and broker-capability input interfaces."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from trading.strategies.specifications import AccountSnapshot

from .records import BrokerCapabilities


class AccountProvider(Protocol):
    def account_snapshot(
        self, account_id_hash: str, decision_at_utc: datetime, max_age: timedelta
    ) -> AccountSnapshot: ...

    def broker_capabilities(
        self, adapter: str, decision_at_utc: datetime, max_age: timedelta
    ) -> BrokerCapabilities: ...
