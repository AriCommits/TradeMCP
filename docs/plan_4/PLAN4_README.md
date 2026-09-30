# Plan 4: Futures Desk evening session — paper marks freeze + HOLD/TRIM/EXIT skeleton

## Summary

Weekday Futures Desk fires around **~6:20 CT** to re-judge the open Kraken
futures paper book: freeze marks + Risk$/R, skim geo/oil/rates (human diet),
and post HOLD / TRIM / EXIT with commodity kill-line reminders. Today that is
hand-built markdown under `/workspace/paper-trades/futures/`.

Plan 4 ships a **paper-only evening session helper CLI** that:

1. Requires `--out-dir` and writes **only** there (agnostic / Kiro-not-wired).
2. Optionally reads a paper book / marks snapshot under `--paper-trades-root`
   (`last-check.json` futures block, or an open Futures rows slice of the
   running-book CSV) and freezes a marks board + Risk$/R stub table.
3. Always writes a session markdown skeleton with HOLD/TRIM/EXIT sections,
   STOP_POLICY band reminders, and commodity kill lines
   (**Hormuz reopen** / **weekly Brent under $85**).
4. Never posts Slack, never calls brokers, never submits orders.

Planning artifacts: `docs/plan_4/`. Contract: [`CONTRACT.md`](CONTRACT.md).
Canon policies: [`docs/desk-ops/`](../desk-ops/README.md).

## Goals

- One stdlib CLI: `paper-trades/scripts/futures_desk_session.py`.
- **`--out-dir` required**; create if missing; refuse without it.
- **`--paper-trades-root` optional** (or env `PAPER_TRADES_ROOT`) — inputs only.
- **`--as-of` optional** — label for the session stamp (default: now CT).
- Outputs under `--out-dir`:
  - `YYYY-MM-DD-HHMM-session.md` — always (skeleton + kill lines + sections).
  - `YYYY-MM-DD-HHMM-marks.md` (+ optional `.json`) — when marks/book inputs
    are found; otherwise a short “no marks” note inside the session file.
- Embed STOP_POLICY bands (equity/crypto perps ~3–6%; commodities ~12–20%
  catastrophe + evening re-judge).
- Commodity kill-line reminders on every run (Hormuz reopen / weekly Brent under $85).
- Exit 0 on success (including “no marks found, skeleton only”).
- Fence: **Futures paper only** — no scout/tape spot books, no TradingCLI options.

## Non-Goals

- Live Kraken private API / `futures paper` buy·sell·cancel.
- **Any Slack / Composio post from the CLI.** Posting stays on-box after review.
- Spot Scout / Tape / invariants workspaces.
- Options Desk / TradingCLI paths.
- Autopilot HOLD/TRIM/EXIT decisions (skeleton only; human fills judgment).
- Rewriting operational files under `/workspace/paper-trades`.

## Background / inputs

Read-only under `--paper-trades-root` (first hit wins for marks):

1. `last-check.json` → `futures_paper.positions` (preferred freeze).
2. Else `slack/paper-running-book.csv` rows with `Desk=Futures` and
   `Status=open` (stub Risk$/R from CSV columns when present).
3. Else no marks — still write the session skeleton.

Policy references (canon copies in repo):

- `docs/desk-ops/STOP_POLICY.md`
- `docs/desk-ops/R_REPORTING.md`
- `docs/desk-ops/BOT_MAP.md` / `RISK_RULES.md`

## Outputs (under `--out-dir` only)

| File | When |
|------|------|
| `YYYY-MM-DD-HHMM-session.md` | Always |
| `YYYY-MM-DD-HHMM-marks.md` | When marks/book found |
| `YYYY-MM-DD-HHMM-marks.json` | When marks/book found |

Session skeleton sections:

- Header (as-of CT, paper-only fence)
- Marks board (embedded or “unavailable”)
- Geo / oil / rates skim **placeholder** (human fills; CLI does not scrape)
- **HOLD / TRIM / EXIT** tables (empty rows for desk fill-in)
- Commodity kill lines
- STOP_POLICY band reminder
- Fence note (no scout/tape/options; no Slack from CLI)

## Usage

From the TradeMCP repo root (or any checkout that has the script):

```bash
# skeleton only (no paper-trades root)
python3 paper-trades/scripts/futures_desk_session.py \
    --out-dir ~/kiro-out/futures-session

# freeze marks from a paper-trades tree (box or synced copy)
python3 paper-trades/scripts/futures_desk_session.py \
    --paper-trades-root /workspace/paper-trades \
    --out-dir ~/kiro-out/futures-session \
    --as-of "2026-09-28 18:20 CT"
```

`--help` lists flags. Exit code **0** on success. **No Slack. No brokers.**

## Related

- Desk ops canon: [`../desk-ops/README.md`](../desk-ops/README.md)
- Plan 2 (Scout): [`../plan_2/OVERVIEW.md`](../plan_2/OVERVIEW.md)
- Plan 3 (Options): [`../plan_3/OVERVIEW.md`](../plan_3/OVERVIEW.md)
- Agnostic handoff: [`CONTRACT.md`](CONTRACT.md)
