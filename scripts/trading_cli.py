from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import typer

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
MPL_CACHE = ROOT / "downloads_misc" / "mplcache"
MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE))

from trading.adapters import build_router_from_config_dir  # noqa: E402
from trading.backtest import run_pipeline  # noqa: E402
from trading.compute import ComputeBackend, ComputeConfig  # noqa: E402
from trading.config import load_config  # noqa: E402
from trading.data_ingestion import read_ohlcv  # noqa: E402
from trading.errors import load_error_policy, persist_error_report  # noqa: E402
from trading.execution_controls import (  # noqa: E402
    ExecutionControlService,
    ExecutionControlsConfig,
    ExecutionState,
    OrderIntent,
    OrderTransactionCoordinator,
)
from trading.pnl import PnLConfig, PnLService  # noqa: E402
from trading.research import ResearchOrchestrator  # noqa: E402
from trading.review import ReviewConfig, ReviewService  # noqa: E402

app = typer.Typer(add_completion=False)


def _run_id(value: str | None = None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _raise_with_report(exc: Exception, command: str, run_id: str, context: dict[str, Any] | None = None) -> None:
    policy = load_error_policy(ROOT / "config/error_policy.yaml")
    report = persist_error_report(
        exc,
        command=command,
        run_id=run_id,
        policy=policy,
        config_version="arch_plan_01",
        context=context,
    )
    typer.echo(f"{type(exc).__name__}: {exc}")
    typer.echo(f"Detailed report: {report}")
    raise typer.Exit(code=1)


def _order_payload(adapter: str, symbol: str, side: str, quantity: float, order_type: str, price: float) -> dict[str, Any]:
    if adapter == "gemini":
        return {
            "symbol": symbol,
            "side": side,
            "amount": quantity,
            "price": price,
            "order_type": "exchange market" if order_type == "market" else "exchange limit",
        }
    if adapter == "tradingview":
        return {"symbol": symbol, "side": side, "quantity": quantity, "order_type": order_type}
    return {"symbol": symbol, "side": side, "quantity": quantity, "order_type": order_type}


@app.command()
def analyze(
    config: str = typer.Option("config/markets/stocks_base.yaml", help="Path to YAML config"),
    input: str = typer.Option("data/sample_ohlcv.csv", help="Input OHLCV CSV/Parquet"),
    output: str = typer.Option("artifacts", help="Output artifact directory"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    rid = _run_id(run_id)
    try:
        cfg = load_config(config).raw
        ohlcv = read_ohlcv(input)
        out = Path(output)
        out.mkdir(parents=True, exist_ok=True)

        result = run_pipeline(ohlcv, cfg, output_dir=out)
        typer.echo(f"Analyze complete for {rid}.")
        typer.echo(json.dumps(result["metrics"], indent=2))
    except Exception as exc:
        _raise_with_report(exc, "analyze", rid, {"config": config, "input": input, "output": output})


@app.command()
def simulate(
    config: str = typer.Option("config/markets/stocks_base.yaml", help="Path to YAML config"),
    input: str = typer.Option("data/sample_ohlcv.csv", help="Input OHLCV CSV/Parquet"),
    output: str = typer.Option("artifacts", help="Output artifact directory"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    analyze(config=config, input=input, output=output, run_id=run_id)


@app.command()
def suggest(
    market: str = typer.Option("stocks", help="Market key: stocks|forex|crypto|intl_stocks"),
    artifacts_dir: str = typer.Option("artifacts", help="Directory with exported pipeline artifacts"),
    top_n: int = typer.Option(3, min=1, help="Number of strategy suggestions to return"),
    max_shortfall_bps: float = typer.Option(20.0, help="Execution shortfall cap for ranking"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    rid = _run_id(run_id)
    try:
        artifacts = Path(artifacts_dir)
        predictions = _load_csv(artifacts / "predictions.csv")
        vol_forecasts = _load_csv(artifacts / "vol_forecasts.csv")
        vi_scores = _load_csv(artifacts / "vi_scores.csv")

        orchestrator = ResearchOrchestrator()
        ranked = orchestrator.rank_strategies(
            market=market,
            predictions=predictions,
            vol_forecasts=vol_forecasts,
            vi_scores=vi_scores,
            max_shortfall_bps=max_shortfall_bps,
        )
        payload = [row.to_dict() for row in ranked[:top_n]]
        typer.echo(json.dumps(payload, indent=2))
    except Exception as exc:
        _raise_with_report(exc, "suggest", rid, {"market": market, "artifacts_dir": artifacts_dir})


@app.command()
def review(
    artifacts_dir: str = typer.Option("artifacts", help="Directory with exported pipeline artifacts"),
    risk_controls: str = typer.Option("config/risk_controls.yaml", help="Review/risk control config"),
    output: str = typer.Option("", help="Optional output file path for report JSON"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    rid = _run_id(run_id)
    try:
        artifacts = Path(artifacts_dir)
        orders = _load_csv(artifacts / "orders.csv")
        executed_orders = _load_csv(artifacts / "executed_orders.csv")

        review_service = ReviewService(ReviewConfig.from_file(risk_controls))
        report = review_service.build_report(orders=orders, executed_orders=executed_orders).to_dict()

        out_path = Path(output) if output else artifacts / "review_report.json"
        _write_json(out_path, report)
        typer.echo(json.dumps(report, indent=2))
        typer.echo(f"Review report saved to: {out_path}")
    except Exception as exc:
        _raise_with_report(exc, "review", rid, {"artifacts_dir": artifacts_dir, "risk_controls": risk_controls})


@app.command()
def execute(
    adapter: str = typer.Option(..., help="Adapter name"),
    symbol: str = typer.Option(..., help="Tradable symbol"),
    side: str = typer.Option("buy", help="Order side"),
    quantity: float = typer.Option(..., min=0.0, help="Order quantity"),
    order_type: str = typer.Option("market", help="Order type"),
    expected_edge_bps: float = typer.Option(0.0, help="Expected edge in bps"),
    predicted_shortfall_bps: float = typer.Option(0.0, help="Predicted shortfall in bps"),
    portfolio_exposure: float = typer.Option(0.0, help="Current total portfolio exposure proxy"),
    daily_pnl: float = typer.Option(0.0, help="Current daily pnl"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
    idempotency_key: str | None = typer.Option(None, help="Idempotency key"),
    live: bool = typer.Option(False, help="Set true for live mode"),
    confirmed: bool = typer.Option(False, help="Explicit confirmation for live actions"),
    submit: bool = typer.Option(False, help="Actually submit to adapter (false keeps local dry-run)"),
    price: float = typer.Option(1.0, help="Price for adapters that require it"),
    adapters_dir: str = typer.Option("config/integrations/adapters", help="Adapter config directory"),
    execution_controls: str = typer.Option("config/execution_controls.yaml", help="Execution control config"),
) -> None:
    rid = _run_id(run_id)
    order_id = f"{rid}:{adapter}:{symbol}:{side}:{quantity}"
    try:
        router = build_router_from_config_dir(adapters_dir)
        controls = ExecutionControlsConfig.from_file(execution_controls)
        control_service = ExecutionControlService(router, controls)

        valid, breaches = control_service.validate_order_intent(
            quantity=quantity,
            symbol_exposure=quantity,
            portfolio_exposure=portfolio_exposure,
            daily_pnl=daily_pnl,
        )
        if not valid:
            raise ValueError(f"Order blocked by policy gates: {', '.join(breaches)}")

        if live and controls.confirmation_required and not confirmed:
            raise ValueError("Live execution requires --confirmed")

        coordinator = OrderTransactionCoordinator()
        intent = OrderIntent(
            order_id=order_id,
            run_id=rid,
            symbol=symbol,
            side=side,
            quantity=quantity,
            expected_edge_bps=expected_edge_bps,
            predicted_shortfall_bps=predicted_shortfall_bps,
            notional=quantity * price,
            idempotency_key=idempotency_key or order_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

        coordinator.start(intent)
        coordinator.transition(order_id, ExecutionState.CALCULATING)
        coordinator.transition(order_id, ExecutionState.READY_FOR_REVIEW)
        coordinator.transition(order_id, ExecutionState.COUNTDOWN, {"countdown_seconds": controls.countdown_seconds})

        if live and controls.confirmation_required:
            should_continue = typer.confirm("Confirm order?", default=False)
            if not should_continue:
                raise ValueError("User cancelled order confirmation")

        coordinator.transition(order_id, ExecutionState.CONFIRMED)

        payload = _order_payload(adapter, symbol, side, quantity, order_type, price)
        if submit:
            submit_result = router.submit_order(adapter, payload)
            result_payload = asdict_router_result(submit_result)
        else:
            result_payload = {
                "adapter": adapter,
                "action": "submit_order",
                "result": {"dry_run": True, "payload": payload},
            }

        coordinator.transition(order_id, ExecutionState.SUBMITTED, {"submit": submit})
        coordinator.transition(order_id, ExecutionState.ACKED, {"adapter": adapter})
        typer.echo(json.dumps(result_payload, indent=2))
    except Exception as exc:
        _raise_with_report(exc, "execute", rid, {"adapter": adapter, "symbol": symbol})


@app.command()
def pnl(
    adapter: str = typer.Option(..., help="Adapter name"),
    artifacts_dir: str = typer.Option("artifacts", help="Directory with exported pipeline artifacts"),
    pnl_config: str = typer.Option("config/pnl.yaml", help="PnL config file"),
    adapters_dir: str = typer.Option("config/integrations/adapters", help="Adapter config directory"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    rid = _run_id(run_id)
    try:
        router = build_router_from_config_dir(adapters_dir)
        artifacts = Path(artifacts_dir)
        executed_orders = _load_csv(artifacts / "executed_orders.csv")

        positions_payload: Any = {}
        try:
            positions_payload = router.get_positions(adapter).result
        except Exception:
            positions_payload = {}

        service = PnLService(PnLConfig.from_file(pnl_config))
        snapshot = service.snapshot(executed_orders=executed_orders, positions_payload=positions_payload).to_dict()
        typer.echo(json.dumps(snapshot, indent=2))
    except Exception as exc:
        _raise_with_report(exc, "pnl", rid, {"adapter": adapter, "artifacts_dir": artifacts_dir})


@app.command()
def close(
    adapter: str = typer.Option(..., help="Adapter name"),
    symbol: str = typer.Option(..., help="Symbol to close"),
    mode: str = typer.Option("flatten", help="Close mode"),
    qty: str = typer.Option("all", help="Quantity or 'all'"),
    live: bool = typer.Option(False, help="Set true for live mode"),
    confirmed: bool = typer.Option(False, help="Explicit confirmation for live actions"),
    submit: bool = typer.Option(False, help="Actually mutate adapter state"),
    adapters_dir: str = typer.Option("config/integrations/adapters", help="Adapter config directory"),
    execution_controls: str = typer.Option("config/execution_controls.yaml", help="Execution control config"),
    run_id: str | None = typer.Option(None, help="Optional run ID"),
) -> None:
    rid = _run_id(run_id)
    try:
        router = build_router_from_config_dir(adapters_dir)
        controls = ExecutionControlsConfig.from_file(execution_controls)
        service = ExecutionControlService(router, controls)

        qty_value: float | str = qty
        if qty != "all":
            qty_value = float(qty)

        result = service.close_symbol(
            adapter_name=adapter,
            symbol=symbol,
            mode=mode,
            qty=qty_value,
            dry_run=not submit,
            live=live,
            confirmed=confirmed,
        )
        typer.echo(json.dumps(result, indent=2))
    except Exception as exc:
        _raise_with_report(exc, "close", rid, {"adapter": adapter, "symbol": symbol})


@app.command()
def terminate(
    run_id: str = typer.Option(..., help="Run ID to terminate"),
    reason: str = typer.Option("manual_request", help="Termination reason"),
    live: bool = typer.Option(False, help="Set true for live mode"),
    confirmed: bool = typer.Option(False, help="Explicit confirmation for live actions"),
    submit: bool = typer.Option(False, help="Actually persist termination"),
    adapters_dir: str = typer.Option("config/integrations/adapters", help="Adapter config directory"),
    execution_controls: str = typer.Option("config/execution_controls.yaml", help="Execution control config"),
) -> None:
    try:
        router = build_router_from_config_dir(adapters_dir)
        controls = ExecutionControlsConfig.from_file(execution_controls)
        service = ExecutionControlService(router, controls)

        result = service.terminate_strategy_run(
            run_id,
            dry_run=not submit,
            live=live,
            confirmed=confirmed,
            reason=reason,
        )
        typer.echo(json.dumps(result, indent=2))
    except Exception as exc:
        _raise_with_report(exc, "terminate", run_id, {"reason": reason})


@app.command("compute-info")
def compute_info(
    compute_config: str = typer.Option("config/compute.yaml", help="Compute config file"),
) -> None:
    cfg = ComputeConfig.from_file(compute_config)
    backend = ComputeBackend(device=cfg.device)
    typer.echo(json.dumps({"config": cfg.__dict__, "telemetry": backend.telemetry()}, indent=2))


def asdict_router_result(result: Any) -> dict[str, Any]:
    return {
        "adapter": getattr(result, "adapter", "unknown"),
        "action": getattr(result, "action", "unknown"),
        "result": getattr(result, "result", {}),
    }


if __name__ == "__main__":
    app()
