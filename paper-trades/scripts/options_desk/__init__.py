"""Options Desk MVP package (paper-only).

Agnostic handoff contract: every CLI requires ``--out-dir`` and writes all
artifacts there only. ``--paper-trades-root`` (or env ``PAPER_TRADES_ROOT``)
locates read inputs only. No Slack/Composio/OAuth and no live brokers; the
viz path writes a PNG to disk only. TradeMCP logic is soft-imported from a
local checkout when present, else an inline paper implementation is used.
"""

__all__ = ["config", "marks", "risk", "trademcp_bridge"]
