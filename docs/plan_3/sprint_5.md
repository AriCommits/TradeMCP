# Plan 3 — Sprint 5 (Wave 5): `plan` subcommand + JSON/MD emitter

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (final edit to shared `options_desk_plan.py`; depends on O2–O4)
**Blocks:** O7 (docs), O8 (tests)
**Prereqs:** Sprint 4 (O4) complete — and transitively O2, O3

Ships as plain files under `scripts/`. Writes go under `--out-dir` only.

---

## Agent A — O5: `plan` subcommand + emitter

**Complexity:** L
**Files:**
- `scripts/options_desk/plan.py` (new)
- `scripts/options_desk/emit.py` (new)
- `scripts/options_desk_plan.py` (edit — attach `plan` handler)

**Instructions:**
1. `plan ... --out-dir <dir>` calls `trademcp_bridge.build_option_trade_plan`.
2. `emit.py`: write JSON + human-readable Markdown to
   `<out-dir>/YYYY-MM-DD-HHMM-<underlying>.{json,md}` via the O1
   `out_path`/`assert_write_allowed` helpers (owns `--out-dir` path construction
   so viz/tests can reuse it).
3. Plan **must include**: OCC symbols, qty, entry mid, **Stop**, **Risk $**,
   thesis one-liner, structure type (CSP/PCS/debit/etc.), expiry, collateral if
   CSP.
4. Respect **max 8 themes** in plan text. Risk $ math from `risk.py` (O1).

**Definition of done:**
- `plan --underlying SPY ... --out-dir <dir>` writes both `.json` + `.md` under `<dir>`.
- MD is human-readable and contains every required field incl. Stop + Risk $.
- CSP plans include collateral; Risk $ matches `R_REPORTING.md`.
- Refuses without `--out-dir`.

**What this unblocks:** O7 docs + O8 tests (final wave).
