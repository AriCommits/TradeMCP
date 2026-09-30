> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `feeds/signals/HOUSE_WAKE_REVIEW.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# House rule — signal wake reviews

**Effective 2026-09-22 (user decision):** every signal wake that pings Options Desk, Futures Desk, or Signal Scout requires:

1. Wake timestamp (CT)
2. **Frozen snapshot embedded in the file** (not a “look it up later” pointer)
3. One short paragraph — TAKE or PASS reasoning

File: `wake-review-YYYY-MM-DD-HHMM.md` under that desk’s signals dir (Scout: signals root).

PASS → file only, no user ping.
TAKE → file + normal user/Slack ping on the fill.

## Why embed (Options AND Futures)
Charts and later public history do **not** faithfully recreate what the desk saw:
- **Options:** mid, IV, Greeks, R, stop — ephemeral; not the same on a later options chart.
- **Futures:** mark, funding, OI, L/S, liq imbalance, squeeze tags — same problem; venue prints and our derived scores won’t match a later OHLC rebuild.
- **Scout:** same — embed spot board / residual / squeeze overlay used at wake.

So every wake review pastes the relevant block from `latest.json` (and open-book marks if judged) **into the markdown**. Citing the path alone is not enough.

`history.csv` remains the quantitative tape; the embedded block + paragraph is the forensic tape.
