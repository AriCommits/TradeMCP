from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import yaml


@dataclass(frozen=True)
class ReviewConfig:
    min_approval_rate: float = 0.6
    max_predicted_shortfall_bps: float = 20.0
    max_daily_loss: float = 0.03
    max_symbol_exposure: float = 0.25
    require_orders: bool = True

    @classmethod
    def from_file(cls, path: str | Path) -> "ReviewConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return cls(
            min_approval_rate=float(raw.get("min_approval_rate", 0.6)),
            max_predicted_shortfall_bps=float(raw.get("max_predicted_shortfall_bps", 20.0)),
            max_daily_loss=float(raw.get("max_daily_loss", 0.03)),
            max_symbol_exposure=float(raw.get("max_symbol_exposure", 0.25)),
            require_orders=bool(raw.get("require_orders", True)),
        )


@dataclass(frozen=True)
class ReviewReport:
    decision: str
    go_no_go: bool
    breached_checks: tuple[str, ...]
    mitigations: tuple[str, ...]
    stats: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ReviewService:
    def __init__(self, config: ReviewConfig) -> None:
        self.config = config

    def build_report(self, orders: pd.DataFrame, executed_orders: pd.DataFrame) -> ReviewReport:
        breaches: list[str] = []
        mitigations: list[str] = []
        stats: dict[str, float] = {}

        if self.config.require_orders and orders.empty:
            breaches.append("no_orders")
            mitigations.append("Re-run analyze/suggest until at least one order is generated.")

        if not executed_orders.empty and "approve" in executed_orders.columns:
            approval_rate = float(executed_orders["approve"].mean())
            stats["approval_rate"] = approval_rate
            if approval_rate < self.config.min_approval_rate:
                breaches.append("approval_rate_below_threshold")
                mitigations.append("Lower position sizing or improve execution edge before live submit.")

        if not executed_orders.empty and "predicted_shortfall_bps" in executed_orders.columns:
            max_shortfall = float(executed_orders["predicted_shortfall_bps"].max())
            stats["max_predicted_shortfall_bps"] = max_shortfall
            if max_shortfall > self.config.max_predicted_shortfall_bps:
                breaches.append("shortfall_limit_exceeded")
                mitigations.append("Tighten slippage caps or reduce turnover for this run.")

        if not executed_orders.empty:
            pnl_col = "executed_pnl" if "executed_pnl" in executed_orders.columns else "realized_pnl"
            if pnl_col in executed_orders.columns:
                daily = (
                    executed_orders.assign(_date=pd.to_datetime(executed_orders["date"]).dt.date)
                    .groupby("_date")[pnl_col]
                    .sum()
                )
                worst_day = float(daily.min()) if not daily.empty else 0.0
                stats["worst_daily_pnl"] = worst_day
                if worst_day < -abs(self.config.max_daily_loss):
                    breaches.append("max_daily_loss_exceeded")
                    mitigations.append("Pause execution and reduce risk budget before resuming.")

            pos_col = "exec_position" if "exec_position" in executed_orders.columns else "position"
            if pos_col in executed_orders.columns:
                max_exposure = float(executed_orders[pos_col].abs().max())
                stats["max_symbol_exposure"] = max_exposure
                if max_exposure > self.config.max_symbol_exposure:
                    breaches.append("symbol_exposure_exceeded")
                    mitigations.append("Reduce per-symbol max position cap and regenerate orders.")

        go_no_go = len(breaches) == 0
        return ReviewReport(
            decision="GO" if go_no_go else "NO_GO",
            go_no_go=go_no_go,
            breached_checks=tuple(breaches),
            mitigations=tuple(mitigations),
            stats=stats,
        )
