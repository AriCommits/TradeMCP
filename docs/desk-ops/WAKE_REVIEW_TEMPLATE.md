> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `feeds/signals/WAKE_REVIEW_TEMPLATE.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# Wake review — {{DESK}} — {{YYYY-MM-DD HH:MM}} CT

- **Wake ts (CT):** {{ts}}
- **Decision:** TAKE | PASS

## Frozen snapshot (required — paste, do not link-only)

### Options
From `feeds/signals/options/latest.json` at wake time:
- each leg: symbol, mid, IV, delta/gamma/theta/vega, R, stop, spot
- net book Greeks; mark_source / errors

### Futures
From `feeds/signals/futures/latest.json` (+ squeeze if used) at wake time:
- each name: pts, mark, pct24, funding, L/S, crowd/OI, liq flags, bias
- open futures book marks/stops/R if those were part of the judgment

### Scout
From `feeds/signals/latest.json` + `ring.json` / `wake-snapshot-*.json` at wake time:
- board z / residual / vol / squeeze flags for alerted names
- rolling 5m ring (≤20 samples/~100 min): ts, close, ret, z pieces

## Judgment (required — one short paragraph)
{{Why take or pass.}}

## Actions (TAKE only)
- {{symbol / side / size / Stop / Risk $}}

## Tags
paper · {{desk}} · signal-wake
