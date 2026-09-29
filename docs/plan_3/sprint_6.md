# Plan 3 — Sprint 6 (Wave 6): Docs + Tests (PARALLEL)

**Agents this wave:** 2 (Agents A, B) — different files
**Parallelizable:** Yes
**Blocks:** none (final wave)
**Prereqs:** Sprint 5 (O5) + Sprint 2 (O6) complete — A+B behavior frozen

Ships as plain files under `scripts/` / `options/`.

---

## Agent A — O7: Docs (`KIRO_MVP.md`)

**Complexity:** S
**File:** `options/KIRO_MVP.md`

**Instructions:** Document running A + B once end to end:
- required `--out-dir` on every CLI; optional `--paper-trades-root`/env for inputs;
- `options_desk_plan.py` `screen | compare | stress | plan` with examples
  (each showing `--out-dir`);
- `options_desk_slack_viz.py` PNG usage (writes `<out-dir>/*.png`, **no posting**);
- how posting happens **separately on the box** (existing scripts), not from Kiro;
- output paths (all under `--out-dir`);
- fences (DB must end with `options/papertrade.db`, no Kraken, no synthetic
  `greeks_viz` marks, no Slack from Kiro);
- Risk $ formulas (long premium + CSP/PCS);
- pin any new dep (matplotlib / openpyxl).

**DoD:** a reader can run A+B from scratch using only this file, passing
`--out-dir`, with no agent/Slack config.

---

## Agent B — O8: Tests (screen/compare, Risk $, viz smoke, fences)

**Complexity:** M
**Files:**
- `scripts/tests/test_options_desk_plan.py`
- `scripts/tests/test_options_desk_viz.py`
- `scripts/tests/fixtures/` (stub DB / marks / book)

**Acceptance tests to encode** (all use a temp `--out-dir`):
0. Both CLIs **refuse to run without `--out-dir`** (non-zero exit).
1. `screen --underlying SPY --structure csp --dte 7-14 --out-dir <tmp>` → ≥1
   liquid candidate (mid + width note); exit 0.
2. `compare` → ≥2 structures ranked by Risk $ / credit quality.
3. `stress` + `plan` emit Stop + Risk $ matching `R_REPORTING.md`; plan md
   human-readable and written under `<tmp>`.
4. Risk $ long premium = `abs(entry−stop)×qty×100`; CSP/PCS documented in plan
   output.
5. `options_desk_slack_viz.py --out-dir <tmp>` writes a **3-panel PNG under
   `<tmp>`** without crashing, and **performs no Slack call** — assert no
   Composio/Slack module is imported.
6. Scripts **refuse / no-op** unless `PAPERTRADE_DB` ends with
   `options/papertrade.db`; **never call Kraken**; never write outside `--out-dir`.

**DoD:** all tests pass offline against fixtures (network/Slack not required);
inputs via `--paper-trades-root`/fixtures, writes to temp `--out-dir`.

---

**Integration:** disjoint files — merge independently.
