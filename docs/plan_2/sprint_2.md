# Plan 2 — Sprint 2 (Wave 2): Input Loaders (read-only)

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (single L task; feeds all analysis modules)
**Blocks:** S3, S4, S5 (and downstream)
**Prereqs:** Sprint 1 (S1) complete — imports `scout_context.paths`, `scout_context.timeparse`

Ships as plain files under `scripts/`. Reads resolve against
`--paper-trades-root`/env (explicit paths override); no writes in this task.

---

## Agent A — S2: Input loaders + fixtures

**Complexity:** L

**Files to create:**
- `scripts/scout_context/loaders.py`
- `scripts/scout_context/fixtures/` (sample inputs for offline dev/tests)

**Instructions:**
Implement read-only loaders, all **fail-closed** (missing/stale → explicit
empty/None + quality flag, never fabricated values). All loaders take an input
root (from `paths.input_root(args)`) or an explicit path:
1. `load_ohlcv_5m(symbols)` — Kraken **public** 5m OHLCV for
   BTC/ETH/SOL/XRP/LINK. Provide an offline fixture/cache path so tests never
   hit the network. **Do not import or call any Kraken private/paper buy/sell
   API** — public market data or fixtures only.
2. `load_ring(path)` — `feeds/signals/ring.json`.
3. `load_snapshot(path)` — frozen `wake-snapshot-*.json` (board + ring).
4. `load_latest()` — `feeds/signals/latest.json` (ts/alerts fallback when no
   snapshot given).
5. `load_squeeze()` — `feeds/squeeze/latest.md` or squeeze history CSV if
   present; **BTC/ETH/SOL tags only**. Return a documented "absent" marker if
   missing.
- Keep total runtime budget in mind (<30s for ≤5 names × 3–5 days of 5m bars).
- Add fixture files under `scripts/scout_context/fixtures/` covering a normal
  case and a thin-data case.

**Definition of done:**
- Each loader returns typed, documented structures with quality flags.
- With network disabled, loaders resolve from fixtures without error.
- Missing squeeze/ring inputs return graceful "absent" states, not exceptions.
- Grep confirms no Kraken order/buy/sell symbols imported.

**What this unblocks:** S3 (regime), S4 (vol features), S5 (ring/squeeze).
