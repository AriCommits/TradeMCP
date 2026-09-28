# Scout Wake Context

Offline, deterministic **regime + short-horizon volatility** research block for
Scout 5m wake-reviews. It is **context only, never an order** — a forensic aid
for a human PASS/TAKE decision, not a sizer or an autopilot.

The CLI reads read-only market/signal inputs and writes a machine `.json` plus a
human `.md` embed block. It has **no runtime dependency** on any bot, MCP
server, Slack, or Kraken private API — pure Python standard library.

## Install / requirements

- Python 3.11+ (uses `zoneinfo` when available; degrades gracefully if the IANA
  tz database is absent).
- **Dependencies: stdlib only.** No pandas/numpy required. No new pins.
- `pytest` is needed only to run the test suite (dev-only, not a runtime dep).

## Usage

```bash
python3 scout_wake_context.py \
    --out-dir /path/to/output \
    --paper-trades-root /path/to/paper-trades \
    --snapshot /path/to/wake-snapshot-2026-09-28-1500.json
```

or with a timestamp instead of a snapshot:

```bash
python3 scout_wake_context.py \
    --out-dir /path/to/output \
    --paper-trades-root /path/to/paper-trades \
    --ts-ct "2026-09-28 15:00:00 CDT"
```

### Flags

| Flag | Required | Purpose |
| --- | --- | --- |
| `--out-dir PATH` | **yes** | Directory for **all** outputs (created if missing). Nothing is written outside it. The CLI refuses to run without it. |
| `--paper-trades-root PATH` | no | Root for **read inputs** only (OHLCV, ring, latest, snapshot, squeeze). Defaults to env `PAPER_TRADES_ROOT`. Never a write target. |
| `--ts-ct "YYYY-MM-DD HH:MM:SS CDT\|CT"` | no | Central-Time wake timestamp. Ignored when `--snapshot` is given. |
| `--snapshot PATH` | no | Frozen `wake-snapshot-*.json` (board + ring). **Takes precedence** over `--ts-ct` for the output key and ring source. |
| `--inject-review PATH` | no | Optional. Insert the embed under a `## Offline wake context` heading in the **explicit** review file. Idempotent; never touches `Decision`/`Judgment` lines. |

Provide at least one of `--snapshot` or `--ts-ct`.

## Outputs

Written under `--out-dir` only:

- `wake-context-YYYY-MM-DD-HHMM.json` — machine bundle. **Byte-stable** across
  identical runs except the single `generated_at` field.
- `wake-context-YYYY-MM-DD-HHMM.md` — human embed block with five fixed
  headings, in order: **Regime**, **Vol features**, **Ring summary**,
  **Squeeze overlay (BTC/ETH/SOL)**, **Caveats**.

## Inputs (read-only)

Resolved under `--paper-trades-root` (or an explicit path):

- `feeds/ohlcv/<SYMBOL>-5m.csv` — public 5m OHLCV for BTC/ETH/SOL/XRP/LINK
  (header `ts,open,high,low,close,volume`, `ts` = epoch seconds UTC).
- `feeds/signals/ring.json` and/or a frozen `wake-snapshot-*.json`.
- `feeds/signals/latest.json` — ts/alerts fallback when no snapshot is given.
- `feeds/squeeze/latest.md` or `feeds/squeeze/history.csv` — BTC/ETH/SOL tags.

Missing or unreadable inputs **fail closed**: the affected field is marked
absent with a `quality_flags` entry — values are never fabricated.

## Regime enum

`label` is one of (documented so wake-reviews can cite by name):

| Label | Meaning |
| --- | --- |
| `trend_up` | persistent positive drift dominating noise |
| `trend_down` | persistent negative drift dominating noise |
| `mean_revert` | negatively autocorrelated returns, low net drift |
| `high_vol_chop` | no clear drift, elevated realized volatility |
| `low_vol_chop` | no clear drift, subdued realized volatility |
| `unknown` | insufficient/degenerate data (never guesses) |

Each label carries a `confidence` in `[0, 1]`.

## Vol features

| Field | Definition |
| --- | --- |
| `realized_vol_20` | sample stdev of the last 20 5m log returns (bar-scaled, not annualized) |
| `vol_ratio_vs_ring` | `realized_vol_20` ÷ cross-ring median `realized_vol_20`; `>1` = hotter than the ring, `~1` in-line, `<1` calmer |
| `vol_forecast_ratio` | realized vol of the last 6 returns ÷ the prior 6 (a 3–12-bar-ahead expansion proxy) |
| `expansion_flag` | `true` when `vol_forecast_ratio ≥ 1.25` |

All values are finite floats or an explicit `null` sentinel — never `NaN`/`inf`.

## Guarantees / fences

- **`--out-dir` required**; no writes outside it, and none under `options/` or
  `futures/` subpaths.
- No Slack/Composio/OAuth and no Kraken private/paper buy-sell — file writer only.
- Deterministic + offline; byte-stable JSON (excluding `generated_at`).

## Tests

```bash
python3 -m pytest scripts/tests -q
```
