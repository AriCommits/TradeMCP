# Plan 3 — Sprint 1 (Wave 1): Shared Core (config, fences, marks, R math, bridge)

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (foundation — everything depends on it)
**Blocks:** all other sprints
**Prereqs:** none

Ships as plain files under `scripts/` (agnostic handoff — no bot/MCP/Slack at
runtime). **`--out-dir` required on CLIs; `--paper-trades-root`/env for inputs.**

---

## Agent A — O1: Shared core

**Complexity:** L

**Files to create:**
- `scripts/options_desk/__init__.py`
- `scripts/options_desk/config.py`
- `scripts/options_desk/marks.py`
- `scripts/options_desk/risk.py`
- `scripts/options_desk/trademcp_bridge.py`

**Read first:** `options/SETUP.md`, `STOP_POLICY.md`, `R_REPORTING.md` — lift
Risk $ / Stop formulas verbatim.

**Instructions:**
1. `config.py`:
   - Resolve `--out-dir` (**required**) + `ensure_out_dir(out_dir)`; resolve
     `--paper-trades-root` (optional; default env `PAPER_TRADES_ROOT`) for
     **inputs only**.
   - `out_path(out_dir, name)` and `assert_write_allowed(out_dir, path)` — raise
     on any write resolving outside `--out-dir`.
   - Resolve `PAPERTRADE_DB` (default `<root>/options/papertrade.db`), account
     `options`.
   - **DB fence:** `assert_db_fenced(db_path)` — refuse/no-op unless the path
     **ends with `options/papertrade.db`**.
   - **Kraken fence:** guard/assertion so nothing in this package imports or
     calls Kraken tools.
2. `marks.py`: mark resolution chain — TradingCLI / Yahoo →
   `options/greeks-latest.json` → CBOE delayed. **Never invent a mark**; fail
   closed with an explicit "no mark" result. Do **not** use synthetic
   `greeks_viz` demo marks as trading input.
3. `risk.py`: encode Risk $ per `R_REPORTING.md`:
   - long premium: `risk_usd = abs(entry - stop) * qty * 100`
   - CSP / PCS: documented formula (lift from policy docs).
   - `stop_for(...)` per `STOP_POLICY.md`.
4. `trademcp_bridge.py`: expose `screen_option_candidates`,
   `compare_option_strategies`, `stress_option_candidate`,
   `build_option_trade_plan`. **Soft-import** a local TradeMCP checkout when
   importable and delegate; else provide an inline paper implementation. Never
   call live broker adapters. **Freeze these signatures** — O2–O5 depend on them.

**Definition of done:**
- DB fence refuses a path not ending in `options/papertrade.db`.
- `assert_write_allowed` raises for paths outside a given `--out-dir`.
- `risk.py` returns `abs(entry−stop)×qty×100` for a long-premium sample.
- `marks.py` returns explicit no-mark on all-sources-missing (no fabrication).
- Bridge functions importable with stable signatures; soft-import falls back to
  inline helpers cleanly when no TradeMCP checkout is present.

**What this unblocks:** O2 (screen CLI) + O6 (viz PNG CLI) can start in parallel.
