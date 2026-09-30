> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `SLACK_BRIDGE.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# Slack bridge — Money Maker ↔ Open Law

Workspace: `tradingdesk-hq`


## Connector
Slack posts go through **Composio** (same `tradingdesk-hq` account as arian.moridani). No native Slack plugin. Discover Slack tools each run; do not assume a dedicated Slack MCP.

X/Twitter is **not** on Composio. Desk X skims stay on the box browser as `@AriCommits`. Do not start Twitter OAuth unless asked.


## Channel map

| Channel | ID | Job |
|---------|-----|-----|
| `#exploringstrategies` | `C0C0JGZBBB5` | Cross-desk + Open Law strategy talk |
| `#ops-paper-metrics` | `C0C0PHV9DB8` | Shared CSV, R digests, charts, book-check wraps |
| `#ops-spot-tape` | `C0C1KSL1HDE` | Spot prices / movers / marks (no thesis) |
| `#desk-options` | `C0C0PHUPUA2` | Options Desk: timestamped book + reasoning |
| `#desk-scout` | `C0C0K923ZK5` | Scout: book + reasoning (spot `scout`) |
| `#desk-tape` | `C0C0M075QLV` | Tape: confirm/fade book + reasoning (spot `tape`) |
| `#desk-futures` | `C0C0K920J91` | Futures Desk: book + reasoning |

## Desk post format
```
[Sep 9 3:20 CT] CLOSE BTC · −0.75R · Risk $60
Thesis: …
Book: … · tags <desk>
```
Top-level = decision; debate in thread. Always Stop + Risk $ on opens; R = P&L÷Risk$ on closes.

## Shared running book (free Slack)
Lists/Canvas unavailable on free teams. CSV:
- Path: `/workspace/paper-trades/slack/paper-running-book.csv`
- Export: `scripts/export_running_book.py`
- Upload target: **`#ops-paper-metrics`** (not exploringstrategies)

## Routing
- Strategy / Open Law ↔ `#exploringstrategies`
- Metrics artifacts ↔ `#ops-paper-metrics`
- Spot marks ↔ `#ops-spot-tape`
- Per-desk thesis ↔ `#desk-*`

## Daily brief
Weekday 8:20 CT Fed + feeds writeup posts to **`#exploringstrategies`** (digest + `.md` file) so humans can read it without the box desktop. Optional one-line majors to `#ops-spot-tape`. File still written to `/workspace/paper-trades/daily/YYYY-MM-DD.md`.
