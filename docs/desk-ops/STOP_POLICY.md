> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `STOP_POLICY.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# Stop policy (class-based, discretionary) — 2026-09-10

Bands are **defaults**, not handcuffs. Desk may set wider/tighter with a one-line reason in journal Setup/Thesis. Always set Stop + Risk $; R = P&L÷Risk $ on close.

| Class | Default stop width | Style |
|-------|-------------------|--------|
| **Futures — equity / crypto perps** | **~3–6%** from entry | Mechanical hard stop |
| **Futures — commodities** (oil, metals, etc.) | **~12–20%** catastrophe floor, or an explicit thesis-kill level in that neighborhood | Wide mechanical floor + **evening HOLD/TRIM/EXIT** re-judge |
| **Options** | Mechanical always; avoid hair-trigger **~5%**; default leeway **~10–20%** (underlying-move sense) or a premium floor that risks a sensible debit slice — desk discretion | Mechanical, not “hold forever” |
| **Spot** (scout / tape / invariants) | Unchanged for now (**~3–7%** typical) | Mechanical |

## Commodities extra (Futures Desk only)
- Kraken `PF_*` are **cash-settled perps** (no physical delivery).
- At open: write a short **kill line** in journal `Setup / Thesis` (what story dies the trade — e.g. Hormuz reopen / weekly close under $X).
- Each evening session: re-read open commodity cards → post `HOLD` / `TRIM` / `EXIT` + one sentence to `#desk-futures`.
- Do **not** use tight 3–5% noise stops as the primary exit on geo oil/gold.

## Anti-scope-creep
No new book or dashboards — kill line lives in existing journal fields; Slack desk channel gets the same lines.

## Signal monitors
Desk wake loops (scout / options / futures) live under `feeds/signals/` — see `feeds/signals/README.md`. Stops above still apply on any wake; monitors are not autopilot.

## Signal wake reviews
On every Futures signal wake (take or pass), write `feeds/signals/futures/wake-review-YYYY-MM-DD-HHMM.md` with wake ts + **embedded** mark/funding/OI/L-S/liq/score board from `latest.json` (and open-book marks if judged) + one short judgment paragraph. Same freeze rule as Options — later charts cannot recreate the ping-time board. PASS = file only; TAKE = file + user/Slack on fill. See `feeds/signals/HOUSE_WAKE_REVIEW.md`.

