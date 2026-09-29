"""3-panel PNG figure builder for the Options Desk viz.

Uses matplotlib with the headless ``Agg`` backend. Produces a single figure
with three panels:
  1. Net book Greeks strip (Delta / Theta) — current bars.
  2. Per-leg R path (entry -> mark -> stop line) for open positions.
  3. Day PnL $ / R bars (open uPnL + today's closed R if in journal).

Writes the PNG to an explicit path (the CLI passes one under --out-dir). This
module performs NO Slack/Composio/network action — file output only.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless; must precede pyplot import
import matplotlib.pyplot as plt  # noqa: E402

from .viz_data import BookView  # noqa: E402


def _net_greeks(book: BookView) -> tuple[float, float]:
    delta = sum((leg.delta or 0.0) * leg.qty for leg in book.legs)
    theta = sum((leg.theta or 0.0) * leg.qty for leg in book.legs)
    return delta, theta


def build_figure(book: BookView, *, title: str = "Options Desk — Open Book"):
    """Build and return a matplotlib Figure with the three panels."""
    fig, (ax_g, ax_r, ax_p) = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.suptitle(title)

    # Panel 1: net Greeks strip
    delta, theta = _net_greeks(book)
    ax_g.bar(["Δ", "Θ"], [delta, theta], color=["#3b7dd8", "#d8823b"])
    ax_g.axhline(0, color="black", linewidth=0.8)
    ax_g.set_title("Net book Greeks")
    ax_g.set_ylabel("net (contracts-weighted)")

    # Panel 2: per-leg R path (entry -> mark, with stop line)
    ax_r.set_title("Per-leg R path")
    if book.legs:
        for i, leg in enumerate(book.legs):
            xs = [0, 1]
            ys = [leg.entry, leg.mark if leg.mark is not None else leg.entry]
            ax_r.plot(xs, ys, marker="o", label=leg.occ_symbol)
            if leg.stop is not None:
                ax_r.axhline(leg.stop, linestyle="--", linewidth=0.7, alpha=0.5)
        ax_r.set_xticks([0, 1])
        ax_r.set_xticklabels(["entry", "mark"])
        ax_r.legend(fontsize=7)
    else:
        ax_r.text(0.5, 0.5, "no open legs", ha="center", va="center")
        ax_r.set_xticks([])

    # Panel 3: Day PnL $ / R
    ax_p.set_title("Day PnL")
    pnl_usd = book.day_pnl_usd if book.day_pnl_usd is not None else _uPnL(book)
    pnl_r = book.day_pnl_r if book.day_pnl_r is not None else 0.0
    ax_p.bar(["PnL $", "PnL R"], [pnl_usd, pnl_r], color=["#3bb273", "#7d3bd8"])
    ax_p.axhline(0, color="black", linewidth=0.8)

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def _uPnL(book: BookView) -> float:
    total = 0.0
    for leg in book.legs:
        if leg.mark is not None:
            total += (leg.mark - leg.entry) * leg.qty * 100
    return round(total, 2)


def write_png(book: BookView, out_path: str | Path, *, title: str | None = None) -> Path:
    """Build the figure and write a PNG to ``out_path`` (file only)."""
    fig = build_figure(book, title=title or "Options Desk — Open Book")
    target = Path(out_path)
    fig.savefig(target, dpi=110, format="png")
    plt.close(fig)
    return target
