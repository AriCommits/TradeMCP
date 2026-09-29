# Options Desk MVP — how to run (paper only)

Two plain-Python CLIs under `paper-trades/scripts/`, shipped as ordinary files.
**No Slack/Composio/OAuth and no live brokers** — Kiro writes files only;
posting stays on the box via existing scripts.

- **A. `options_desk_plan.py`** — `screen | compare | stress | plan`.
- **B. `options_desk_slack_viz.py`** — writes a 3-panel PNG one-pager (file only).

## Contract

- **`--out-dir PATH` is REQUIRED** on every CLI. All writes go there only; the
  CLI refuses to run without it and creates it if missing. No hardcoded
  `/workspace/...` write targets.
- **`--paper-trades-root PATH`** (or env `PAPER_TRADES_ROOT`) locates read
  inputs only (the options DB). Never a write target.
- **DB fence:** `PAPERTRADE_DB` must end with `options/papertrade.db` (read-only).
- **No Kraken**, no synthetic `greeks_viz` marks as trading input, no live orders.
- TradeMCP logic is **soft-imported** from a local checkout if present, else an
  inline paper implementation is used.

## Requirements

- Python 3.11+.
- `matplotlib` for the PNG viz (pin: `matplotlib>=3.8`). `plan/screen/compare/
  stress` need only the standard library.
- `pytest` for the test suite (dev only).

## A. Plan CLI

```bash
# screen liquid candidates
python3 scripts/options_desk_plan.py screen \
    --underlying SPY --structure csp --dte 7-14 \
    --paper-trades-root /path/to/paper-trades \
    --out-dir ~/kiro-out/options-plans

# compare / rank structures by credit quality (>=2 structures)
python3 scripts/options_desk_plan.py compare \
    --underlying SPY --structures csp,pcs \
    --out-dir ~/kiro-out/options-plans

# stress the top candidate (Stop + Risk $ + spot shocks)
python3 scripts/options_desk_plan.py stress \
    --underlying SPY --structure csp --out-dir ~/kiro-out/options-plans

# build a trade plan -> json + md under --out-dir
python3 scripts/options_desk_plan.py plan \
    --underlying SPY --structure csp --dte 7-14 \
    --out-dir ~/kiro-out/options-plans
```

Plan output (`<out-dir>/YYYY-MM-DD-HHMM-<underlying>.{json,md}`) includes:
OCC symbols, qty, entry mid, **Stop**, **Risk $**, thesis one-liner, structure
type, expiry, and collateral (for CSP). Plan text respects a max of 8 themes.

## B. PNG viz CLI

```bash
python3 scripts/options_desk_slack_viz.py \
    --paper-trades-root /path/to/paper-trades \
    --out-dir ~/kiro-out/options-viz
```

Writes `<out-dir>/YYYY-MM-DD-HHMM.png` with three panels: net book Greeks strip
(Δ/Θ), per-leg R path (entry → mark, stop line), and Day PnL $/R. **No posting.**
Posting the PNG to Slack is a separate on-box step (existing chart helpers).

## Risk $ formulas

- Long premium: `risk_usd = abs(entry - stop) * qty * 100`
- CSP (cash-secured put): `risk_usd = (strike - credit) * qty * 100`
- PCS (put credit spread): `risk_usd = (width - credit) * qty * 100`

Source of truth on the box: `options/R_REPORTING.md` and `STOP_POLICY.md`.

## Tests

```bash
python3 -m pytest scripts/tests -q
```
