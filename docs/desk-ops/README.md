# Desk ops canon (TradeMCP snapshot)

Paper-only house procedures for the Money Maker trading desk experiment.
This folder is a **versioned canon snapshot** of the operational policy docs
that live on the shared box under `/workspace/paper-trades/`.

**Live ops still use `/workspace/paper-trades` until wired.** Paths, Slack
channel IDs, and session artifacts on the box remain the runtime source of
truth. Treat these files as the portable, PR-reviewable copy for TradeMCP /
Kiro handoffs — not a second operational root.

## Paper only

- No live broker adapters, no live orders, no secrets in this tree.
- CLI plans that consume these policies write **only** under caller-supplied
  `--out-dir` (see Plans 2–4). They never post to Slack and never submit
  orders.

## Desks

| Desk | Book | Typical weekday session (CT) |
|------|------|------------------------------|
| **Futures** | Kraken futures paper | ~6:20 PM evening routine |
| **Options** | TradingCLI `options` | ~9:45 AM cash open |
| **Scout** | Kraken spot `scout` | ~2:20 PM |
| **Tape** | Kraken spot `tape` | ~3:20 PM |
| **Money Maker** | Orchestration + spot `invariants` (legacy) | morning brief / book checks |

Hard fences (no cross-book trading) live in `RISK_RULES.md` and `BOT_MAP.md`.

## Files in this pack

| File | Origin under `/workspace/paper-trades/` |
|------|------------------------------------------|
| `STOP_POLICY.md` | `STOP_POLICY.md` |
| `R_REPORTING.md` | `R_REPORTING.md` |
| `SLACK_BRIDGE.md` | `SLACK_BRIDGE.md` |
| `BOT_MAP.md` | `BOT_MAP.md` |
| `RISK_RULES.md` | `RISK_RULES.md` (companion to BOT_MAP) |
| `WAKE_REVIEW_TEMPLATE.md` | `feeds/signals/WAKE_REVIEW_TEMPLATE.md` |
| `HOUSE_WAKE_REVIEW.md` | `feeds/signals/HOUSE_WAKE_REVIEW.md` |

### Gaps / not copied

- Per-desk signal monitor READMEs and daemon scripts stay on the box
  (`feeds/signals/README.md`, `scripts/*_signal_*.py`) — runtime, not canon.
- Session journals (`futures/*.md`, `options/*-session.md`, scout/tape air
  notes) and Slack CSV digests are operational artifacts, not policy.
- Options-only setup (`options/SETUP.md`) and Scout wake routine prompts are
  desk-local; Options Plan 3 / Scout Plan 2 point at them via
  `--paper-trades-root`.

## Related plans

- [Plan 2 — Scout wake context](../plan_2/OVERVIEW.md) · CLI:
  `paper-trades/scripts/scout_wake_context.py`
- [Plan 3 — Options Desk MVP](../plan_3/OVERVIEW.md) · CLI:
  `paper-trades/scripts/options_desk_plan.py`
- [Plan 4 — Futures evening session](../plan_4/README.md) · CLI:
  `paper-trades/scripts/futures_desk_session.py`
