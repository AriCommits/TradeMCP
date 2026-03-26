from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def save_regime_vi_plot(vi_df: pd.DataFrame, out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(10, 4))
    if not vi_df.empty:
        plt.plot(vi_df["date"], vi_df["vi"], marker="o")
    plt.title("Regime Stability (Variation of Information)")
    plt.ylabel("VI (lower is more stable)")
    plt.xlabel("Date")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def save_equity_curve_plot(orders: pd.DataFrame, out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    daily = orders.groupby("date")["executed_pnl"].sum().sort_index() if not orders.empty else pd.Series(dtype=float)
    equity = (1.0 + daily).cumprod() if not daily.empty else daily

    plt.figure(figsize=(10, 4))
    if not equity.empty:
        plt.plot(equity.index, equity.values)
    plt.title("Executed Equity Curve")
    plt.ylabel("Equity")
    plt.xlabel("Date")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
