from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .errors import ExecutionError, ValidationError


class ExecutionState(str, Enum):
    DRAFT = "DRAFT"
    CALCULATING = "CALCULATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COUNTDOWN = "COUNTDOWN"
    CONFIRMED = "CONFIRMED"
    SUBMITTED = "SUBMITTED"
    ACKED = "ACKED"


_ALLOWED_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.DRAFT: {ExecutionState.CALCULATING},
    ExecutionState.CALCULATING: {ExecutionState.READY_FOR_REVIEW},
    ExecutionState.READY_FOR_REVIEW: {ExecutionState.COUNTDOWN},
    ExecutionState.COUNTDOWN: {ExecutionState.CONFIRMED},
    ExecutionState.CONFIRMED: {ExecutionState.SUBMITTED},
    ExecutionState.SUBMITTED: {ExecutionState.ACKED},
    ExecutionState.ACKED: set(),
}


@dataclass(frozen=True)
class ExecutionControlsConfig:
    atomicity_mode: str = "strict"
    confirmation_required: bool = True
    countdown_seconds: int = 10
    hotkey: str = "shift+p"
    cancel_on_unrecognized_key: bool = True
    max_symbol_exposure: float = 0.25
    max_portfolio_exposure: float = 1.0
    max_daily_loss: float = 0.03
    live_kill_switch_enabled: bool = True

    @classmethod
    def from_file(cls, path: str | Path) -> "ExecutionControlsConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return cls(
            atomicity_mode=str(raw.get("atomicity_mode", "strict")),
            confirmation_required=bool(raw.get("confirmation_required", True)),
            countdown_seconds=int(raw.get("countdown_seconds", 10)),
            hotkey=str(raw.get("hotkey", "shift+p")),
            cancel_on_unrecognized_key=bool(raw.get("cancel_on_unrecognized_key", True)),
            max_symbol_exposure=float(raw.get("max_symbol_exposure", 0.25)),
            max_portfolio_exposure=float(raw.get("max_portfolio_exposure", 1.0)),
            max_daily_loss=float(raw.get("max_daily_loss", 0.03)),
            live_kill_switch_enabled=bool(raw.get("live_kill_switch_enabled", True)),
        )


@dataclass(frozen=True)
class OrderIntent:
    order_id: str
    run_id: str
    symbol: str
    side: str
    quantity: float
    expected_edge_bps: float
    predicted_shortfall_bps: float
    notional: float
    idempotency_key: str
    timestamp_utc: str


class OrderTransactionCoordinator:
    def __init__(self, audit_log_path: str | Path = "artifacts/audit/order_lifecycle.jsonl") -> None:
        self._states: dict[str, ExecutionState] = {}
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def start(self, intent: OrderIntent) -> ExecutionState:
        self._states[intent.order_id] = ExecutionState.DRAFT
        self._append(intent.order_id, ExecutionState.DRAFT, {"intent": asdict(intent)})
        return ExecutionState.DRAFT

    def transition(self, order_id: str, new_state: ExecutionState, metadata: dict[str, Any] | None = None) -> ExecutionState:
        current = self._states.get(order_id)
        if current is None:
            raise ExecutionError(f"Unknown order_id '{order_id}'")

        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_state not in allowed:
            raise ExecutionError(f"Invalid state transition: {current.value} -> {new_state.value}")

        self._states[order_id] = new_state
        self._append(order_id, new_state, metadata or {})
        return new_state

    def state(self, order_id: str) -> ExecutionState:
        if order_id not in self._states:
            raise ExecutionError(f"Unknown order_id '{order_id}'")
        return self._states[order_id]

    def _append(self, order_id: str, state: ExecutionState, metadata: dict[str, Any]) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "order_id": order_id,
            "state": state.value,
            "metadata": metadata,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")


class ExecutionControlService:
    def __init__(
        self,
        router: Any,
        controls: ExecutionControlsConfig,
        *,
        audit_log_path: str | Path = "artifacts/audit/execution_controls.jsonl",
        terminated_runs_path: str | Path = "artifacts/control/terminated_runs.json",
    ) -> None:
        self.router = router
        self.controls = controls
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.terminated_runs_path = Path(terminated_runs_path)
        self.terminated_runs_path.parent.mkdir(parents=True, exist_ok=True)

    def terminate_strategy_run(
        self,
        run_id: str,
        *,
        dry_run: bool = True,
        live: bool = False,
        confirmed: bool = False,
        reason: str = "manual_request",
    ) -> dict[str, Any]:
        self._require_confirmation_if_live(live=live, confirmed=confirmed)

        terminated_runs = self._load_terminated_runs()
        already_terminated = run_id in terminated_runs
        if not dry_run and not already_terminated:
            terminated_runs.add(run_id)
            self._save_terminated_runs(terminated_runs)

        event = {
            "action": "terminate_strategy_run",
            "run_id": run_id,
            "dry_run": dry_run,
            "live": live,
            "already_terminated": already_terminated,
            "reason": reason,
        }
        self._audit(event)
        return event

    def close_symbol(
        self,
        *,
        adapter_name: str,
        symbol: str,
        mode: str = "flatten",
        qty: float | str = "all",
        dry_run: bool = True,
        live: bool = False,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        self._require_confirmation_if_live(live=live, confirmed=confirmed)

        cancelled: list[dict[str, Any]] = []
        try:
            open_orders = self.router.get_open_orders(adapter_name).result
            for order_id in self._extract_open_order_ids(open_orders):
                if not dry_run:
                    cancelled.append(asdict(self.router.cancel_order(adapter_name, order_id)))
                else:
                    cancelled.append({"adapter": adapter_name, "action": "cancel_order", "result": {"order_id": order_id, "dry_run": True}})
        except Exception:
            cancelled = []

        close_result: dict[str, Any] | None = None
        if mode == "flatten":
            if dry_run:
                close_result = {
                    "adapter": adapter_name,
                    "action": "close_position",
                    "result": {"symbol": symbol, "qty": qty, "dry_run": True},
                }
            else:
                close_result = asdict(self.router.close_position(adapter_name, symbol=symbol, qty=qty))

        event = {
            "action": "close_symbol",
            "adapter": adapter_name,
            "symbol": symbol,
            "mode": mode,
            "qty": qty,
            "dry_run": dry_run,
            "live": live,
            "cancelled": cancelled,
            "close_result": close_result,
        }
        self._audit(event)
        return event

    def panic_close_all(
        self,
        *,
        dry_run: bool = True,
        live: bool = False,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        self._require_confirmation_if_live(live=live, confirmed=confirmed)

        results: dict[str, dict[str, Any]] = {}
        for adapter_name in self.router.registered():
            adapter_event: dict[str, Any] = {"cancel": None, "close": None}
            if dry_run:
                adapter_event["cancel"] = {"dry_run": True}
                adapter_event["close"] = {"dry_run": True}
            else:
                try:
                    adapter_event["cancel"] = asdict(self.router.cancel_all_orders(adapter_name))
                except Exception as exc:
                    adapter_event["cancel"] = {"error": str(exc)}

                try:
                    adapter_event["close"] = asdict(self.router.close_all_positions(adapter_name))
                except Exception as exc:
                    adapter_event["close"] = {"error": str(exc)}
            results[adapter_name] = adapter_event

        event = {
            "action": "panic_close_all",
            "dry_run": dry_run,
            "live": live,
            "results": results,
        }
        self._audit(event)
        return event

    def validate_order_intent(
        self,
        *,
        quantity: float,
        symbol_exposure: float,
        portfolio_exposure: float,
        daily_pnl: float,
    ) -> tuple[bool, tuple[str, ...]]:
        breaches: list[str] = []

        if abs(quantity) > self.controls.max_symbol_exposure:
            breaches.append("symbol_exposure_limit")
        if abs(portfolio_exposure) > self.controls.max_portfolio_exposure:
            breaches.append("portfolio_exposure_limit")
        if daily_pnl < -abs(self.controls.max_daily_loss):
            breaches.append("daily_loss_limit")
        return (len(breaches) == 0, tuple(breaches))

    def _require_confirmation_if_live(self, *, live: bool, confirmed: bool) -> None:
        if live and self.controls.confirmation_required and not confirmed:
            raise ValidationError("Live mode requires explicit confirmation")

    @staticmethod
    def _extract_open_order_ids(open_orders_payload: Any) -> list[str]:
        if isinstance(open_orders_payload, dict):
            for key in ("orders", "results", "open_orders"):
                nested = open_orders_payload.get(key)
                if isinstance(nested, list):
                    open_orders_payload = nested
                    break
            else:
                open_orders_payload = [open_orders_payload]

        if not isinstance(open_orders_payload, list):
            return []

        ids: list[str] = []
        for item in open_orders_payload:
            if not isinstance(item, dict):
                continue
            oid = item.get("order_id") or item.get("id")
            if oid is not None:
                ids.append(str(oid))
        return ids

    def _audit(self, event: dict[str, Any]) -> None:
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def _load_terminated_runs(self) -> set[str]:
        if not self.terminated_runs_path.exists():
            return set()
        try:
            raw = json.loads(self.terminated_runs_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return {str(item) for item in raw}
        except Exception:
            return set()
        return set()

    def _save_terminated_runs(self, runs: set[str]) -> None:
        self.terminated_runs_path.write_text(json.dumps(sorted(runs), indent=2), encoding="utf-8")
