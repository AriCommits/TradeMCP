"""Scout wake-context package.

Offline, deterministic regime + short-horizon volatility research block for
Scout 5m wake-reviews. Context only, never an order.

Agnostic handoff contract: the CLI requires ``--out-dir`` and writes all
artifacts there only. ``--paper-trades-root`` (or env ``PAPER_TRADES_ROOT``)
locates read inputs only. No dependence on any bot/MCP/Slack at runtime;
stdlib-only implementation.
"""

__all__ = ["paths", "timeparse"]
