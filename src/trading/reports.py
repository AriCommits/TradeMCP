from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _format_html_table(df: pd.DataFrame, *, max_rows: int = 10) -> str:
    if df.empty:
        return "<p>No rows available.</p>"
    return df.head(max_rows).to_html(index=False, border=0, classes="summary-table")


def write_markdown_report(
    *,
    output_dir: str | Path,
    metrics: dict[str, object],
    executed_orders: pd.DataFrame,
    top_n: int = 5,
    title: str = "Backtest Report",
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(metrics, indent=2, default=str))
    lines.append("```")
    lines.append("")

    if executed_orders.empty or "symbol" not in executed_orders.columns or "executed_pnl" not in executed_orders.columns:
        lines.append("## Symbol Ranking")
        lines.append("")
        lines.append("No executed orders were found for this run.")
        lines.append("")
    else:
        symbol_pnl = (
            executed_orders.groupby("symbol", dropna=False)["executed_pnl"]
            .sum()
            .reset_index()
            .rename(columns={"executed_pnl": "net_pnl"})
            .sort_values("net_pnl", ascending=False)
        )
        lines.append(f"## Top {top_n} Symbols by Net PnL")
        lines.append("")
        lines.append(_format_html_table(symbol_pnl, max_rows=top_n))
        lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append("- `metrics.json`")
    lines.append("- `executed_orders.csv`")
    if (out_dir / "equity_curve.png").exists():
        lines.append("- `equity_curve.png`")
    if (out_dir / "regime_vi.png").exists():
        lines.append("- `regime_vi.png`")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
