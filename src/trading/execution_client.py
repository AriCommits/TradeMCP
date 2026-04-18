from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd


def _python_fallback(rows: list[dict], max_shortfall_bps: float) -> list[dict]:
    out = []
    for row in rows:
        shortfall = 4.0 + 120.0 * abs(row["size"]) * max(row["forecast_vol"], 1e-4) + 16.0 * abs(row["pofi"])
        approve = (shortfall <= row["expected_edge_bps"]) and (shortfall <= max_shortfall_bps)
        out.append(
            {
                "order_id": row["order_id"],
                "symbol": row["symbol"],
                "approve": bool(approve),
                "predicted_shortfall_bps": float(shortfall),
                "reason": "ok" if approve else "shortfall_exceeds_edge",
                "adjusted_size": float(row["size"] if approve else 0.0),
            }
        )
    return out


def apply_execution_filter(orders: pd.DataFrame, backend_bin: str, max_shortfall_bps: float) -> pd.DataFrame:
    if orders.empty:
        return orders

    work = orders.copy()
    work = work.reset_index(drop=True)
    work["order_id"] = work.index.astype(int)
    work["side"] = np.where(work["position"] >= 0, "BUY", "SELL")
    work["size"] = work["position"].abs()
    work["pofi"] = work.groupby("date")["position"].transform(lambda s: s.sum())

    request_rows = [
        {
            "order_id": int(r.order_id),
            "symbol": r.symbol,
            "side": r.side,
            "size": float(r.size),
            "expected_edge_bps": float(max(r.expected_edge_bps, 0.0)),
            "forecast_vol": float(max(r.vol_forecast, 1e-6)),
            "pofi": float(r.pofi),
        }
        for r in work.itertuples(index=False)
    ]

    decisions = None
    bin_path = Path(backend_bin).resolve()
    
    # Security check: Ensure the bin_path is within the repository or is a known safe executable name
    repo_root = Path(__file__).resolve().parents[2]
    is_safe_path = str(bin_path).startswith(str(repo_root)) or bin_path.name in ("rust_exec_engine", "rust_exec_engine.exe")
    
    if is_safe_path and bin_path.exists() and bin_path.is_file():
        payload = {"orders": request_rows, "max_shortfall_bps": max_shortfall_bps}
        proc = subprocess.run(
            [str(bin_path)],
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode == 0:
            try:
                decisions = json.loads(proc.stdout.decode("utf-8"))["decisions"]
            except Exception:
                decisions = None

    if decisions is None:
        decisions = _python_fallback(request_rows, max_shortfall_bps=max_shortfall_bps)

    decision_df = pd.DataFrame(decisions)
    out = work.merge(decision_df, on="order_id", how="left")
    if "symbol_y" in out.columns:
        out = out.rename(columns={"symbol_x": "symbol"}).drop(columns=["symbol_y"])
    out["approve"] = out["approve"].fillna(False)
    out["adjusted_size"] = out["adjusted_size"].fillna(0.0)
    out["exec_position"] = np.where(out["side"] == "BUY", out["adjusted_size"], -out["adjusted_size"])
    out["executed_pnl"] = out["exec_position"] * out["target"]
    return out
