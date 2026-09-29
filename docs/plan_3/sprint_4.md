# Plan 3 — Sprint 4 (Wave 4): `stress` subcommand

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (edits shared `options_desk_plan.py` after O3)
**Blocks:** O5 (`plan`)
**Prereqs:** Sprint 3 — O3 complete (owns `options_desk_plan.py` lock)

Ships as plain files under `scripts/`. Writes go under `--out-dir` only.

---

## Agent A — O4: `stress` subcommand

**Complexity:** M
**Files:**
- `scripts/options_desk/stress.py` (new)
- `scripts/options_desk_plan.py` (edit — attach `stress` handler)

**Instructions:**
- `stress ... --out-dir <dir>` applies deterministic shocks via
  `trademcp_bridge.stress_option_candidate`.
- Emit **Stop + Risk $** consistent with `R_REPORTING.md`.

**DoD:** `stress` on a candidate returns Stop + Risk $ matching the R formula;
refuses without `--out-dir`.

**FILE LOCK:** holds `options_desk_plan.py`; O5 edits it next — sequential.
