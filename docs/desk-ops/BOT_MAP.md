> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `BOT_MAP.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# Four-bot map (staggered information)

| Bot | Book | Session (CT weekdays) | Info diet timing |
|-----|------|----------------------|------------------|
| **Options Desk** | TradingCLI `options` | 9:45 AM | Cash open — chains + morning X |
| **Signal Scout** | Kraken spot `scout` | 2:20 PM | Afternoon movers + X |
| **Tape + Narrative** | Kraken spot `tape` | 3:20 PM | Later afternoon confirm/fade + own X |
| **Futures Desk** | Kraken futures paper | 6:20 PM | Evening 24/5 book + own X |

## Shared morning brief
- 8:20 CT **Daily Fed + feeds pull** writes `/workspace/paper-trades/daily/YYYY-MM-DD.md` only — **no fan-out** to all bots.
- Specialists must not all trade off the same 8:20 snapshot.

## Context “purge”
- Each session is a fresh routine wake. After logging, stop.
- Do not carry multi-hour chat context; next run re-reads files + live marks.

## Fences
- See RISK_RULES.md. No cross-book access.

## Scoring
- Cross-desk comparison uses **R-multiples** (see R_REPORTING.md), not raw dollars.
