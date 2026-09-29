# Plan 2 — Sprint 3 (Wave 3): Analysis Modules (PARALLEL)

**Agents this wave:** up to 3 (Agents A, B, C) — no shared files
**Parallelizable:** Yes
**Blocks:** S6 (bundle serialization)
**Prereqs:** Sprint 1 (S1) + Sprint 2 (S2) complete

Ships as plain files under `scripts/`. All three agents import
`scout_context.loaders` (S2) and shared contracts from S1. They write
**disjoint files**, so run concurrently.

---

## Agent A — S3: Regime clustering + confidence

**Complexity:** L
**File:** `scripts/scout_context/regime.py`

- Produce a regime label from the enum:
  `trend_up | trend_down | mean_revert | high_vol_chop | low_vol_chop | unknown`
  plus a confidence in `[0,1]`.
- Frozen, offline, deterministic heuristic/clustering over loaded 5m bars
  (e.g. trend slope + realized-vol banding + mean-reversion test).
- Insufficient data → `unknown` + low confidence, **never NaN**.
- Document the enum and decision rule inline (README consumes it in Sprint 8).

**DoD:** deterministic label+confidence for a fixed fixture; enum-valid; no NaN.

---

## Agent B — S4: Short-horizon vol features

**Complexity:** M
**File:** `scripts/scout_context/vol_features.py`

- Compute: realized vol (20-bar), `vol_ratio` vs ring (name RV ÷ ring-median RV
  — confirm definition), and a 3–12 bar ahead vol forecast **or** expansion
  flag.
- All values **finite (no NaN)**; thin-data → documented sentinels.

**DoD:** all three feature groups present and finite for the fixture.

---

## Agent C — S5: Ring summary + Squeeze overlay

**Complexity:** M
**Files:** `scripts/scout_context/ring_summary.py`, `scripts/scout_context/squeeze_overlay.py`

- `ring_summary.py`: summarize ring/snapshot board+ring data for the embed.
- `squeeze_overlay.py`: overlay restricted to **BTC/ETH/SOL** tags; renders a
  documented "no squeeze data" state when input absent.

**DoD:** both render valid section payloads for present and absent inputs.

---

**What this wave unblocks:** S6 assembles all three outputs into the JSON bundle.
