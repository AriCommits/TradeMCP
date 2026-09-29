# Plan 3 — Sprint 3 (Wave 3): `compare` subcommand

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (edits shared `options_desk_plan.py` after O2)
**Blocks:** O4 (`stress`), then O5 (`plan`)
**Prereqs:** Sprint 2 — O2 complete (owns `options_desk_plan.py`)

Ships as plain files under `scripts/`. Writes go under `--out-dir` only.

> The PNG viz track (O6) already shipped in Wave 2 and needs nothing here — this
> wave is purely the plan-CLI chain.

---

## Agent A — O3: `compare` subcommand

**Complexity:** M
**Files:**
- `scripts/options_desk/compare.py` (new)
- `scripts/options_desk_plan.py` (edit — attach `compare` handler to the O2 stub)

**Instructions:**
- `compare --underlying SPY --out-dir <dir>` outputs **≥2 structures ranked by
  Risk $ / credit quality** via `trademcp_bridge.compare_option_strategies`.

**DoD:** `compare --underlying SPY --out-dir <dir>` returns ≥2 ranked
structures; exit 0.

**FILE LOCK:** Agent A holds `options_desk_plan.py` this wave. O4 (next wave)
edits the same file — do not run O4 concurrently with O3.
