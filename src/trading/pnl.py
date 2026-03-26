from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class PnLConfig:
    fee_bps: float = 1.0
    quote_staleness_seconds: int = 30
    mark_source: str = "last"

    @classmethod
    def from_file(cls, path: str | Path) -> "PnLConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return cls(
            fee_bps=float(raw.get("fee_bps", 1.0)),
            quote_staleness_seconds=int(raw.get("quote_staleness_seconds", 30)),
            mark_source=str(raw.get("mark_source", "last")),
        )


@dataclass(frozen=True)
class PnLSnapshot:
    as_of_utc: str
    realized_pnl: float
    unrealized_pnl: float
    daily_pnl: float
    fees: float
    net_pnl: float
    by_symbol: dict[str, float]
    exposure_by_symbol: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PnLService:
    def __init__(self, config: PnLConfig) -> None:
        self.config = config

    @staticmethod
    def _position_rows(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            for key in ("positions", "results", "holdings"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    return [r for r in nested if isinstance(r, dict)]
            return [payload]
        return []

    def snapshot(
        self,
        *,
        executed_orders: pd.DataFrame,
        positions_payload: Any = None,
        as_of: datetime | None = None,
    ) -> PnLSnapshot:
        ts = as_of or datetime.now(timezone.utc)

        if executed_orders.empty:
            realized = 0.0
            daily = 0.0
            fees = 0.0
            by_symbol: dict[str, float] = {}
        else:
            pnl_col = "executed_pnl" if "executed_pnl" in executed_orders.columns else "realized_pnl"
            pos_col = "exec_position" if "exec_position" in executed_orders.columns else "position"

            realized = float(executed_orders[pnl_col].sum()) if pnl_col in executed_orders.columns else 0.0
            by_symbol = (
                executed_orders.groupby("symbol")[pnl_col].sum().astype(float).to_dict()
                if "symbol" in executed_orders.columns and pnl_col in executed_orders.columns
                else {}
            )
            daily = 0.0
            if "date" in executed_orders.columns and pnl_col in executed_orders.columns:
                daily_df = executed_orders.assign(_date=pd.to_datetime(executed_orders["date"]).dt.date)
                daily = float(daily_df[daily_df["_date"] == ts.date()][pnl_col].sum())

            if pos_col in executed_orders.columns:
                notional_proxy = float(executed_orders[pos_col].abs().sum())
                fees = notional_proxy * self.config.fee_bps / 10000.0
            else:
                fees = 0.0

        positions = self._position_rows(positions_payload)
        unrealized = 0.0
        exposure_by_symbol: dict[str, float] = {}
        for row in positions:
            symbol = str(row.get("symbol") or row.get("asset") or row.get("instrument") or "UNKNOWN")
            unrealized += float(row.get("unrealized_pnl") or row.get("unrealizedPnL") or 0.0)

            qty = float(row.get("quantity") or row.get("qty") or row.get("size") or 0.0)
            mark_price = float(row.get("mark_price") or row.get("mark") or row.get("price") or 0.0)
            explicit_exposure = row.get("exposure")
            if explicit_exposure is not None:
                exposure = abs(float(explicit_exposure))
            else:
                exposure = abs(qty * mark_price)
            exposure_by_symbol[symbol] = exposure_by_symbol.get(symbol, 0.0) + exposure

        net = realized + unrealized - fees
        return PnLSnapshot(
            as_of_utc=ts.isoformat(),
            realized_pnl=float(realized),
            unrealized_pnl=float(unrealized),
            daily_pnl=float(daily),
            fees=float(fees),
            net_pnl=float(net),
            by_symbol=by_symbol,
            exposure_by_symbol=exposure_by_symbol,
        )
