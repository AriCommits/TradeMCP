# Plan 2 — Sprint 8 (Wave 8): Tests + README (PARALLEL)

**Agents this wave:** 2 (Agents A, B) — different files
**Parallelizable:** Yes
**Blocks:** none (final wave)
**Prereqs:** Sprint 7 (S9) complete — CLI behavior frozen

Ships as plain files under `scripts/`.

---

## Agent A — S10: Tests (fixture snapshot → deterministic context files)

**Complexity:** M
**Files:**
- `scripts/tests/test_scout_wake_context.py`
- `scripts/tests/fixtures/wake-snapshot-2026-09-28-1500.json`

**Acceptance tests to encode** (all use a temp `--out-dir`):
0. CLI **refuses to run without `--out-dir`** (non-zero exit, nothing written).
1. Given fixture `wake-snapshot-2026-09-28-1500.json` + `--out-dir <tmp>`, CLI
   exits 0 and writes both `wake-context-2026-09-28-1500.json` + `.md` **under
   `<tmp>`** with **all five headings**.
2. Regime label ∈ enum (`trend_up|trend_down|mean_revert|high_vol_chop|
   low_vol_chop|unknown`); confidence ∈ `[0,1]`.
3. Vol features include ≥ realized vol (20-bar), `vol_ratio` vs ring, and a
   3–12 bar ahead vol forecast or expansion flag — **all finite, no NaN**.
4. `--inject-review <tmp-review>` on a stub review adds **exactly one**
   `## Offline wake context` section; Decision/Judgment lines unchanged; nothing
   else written.
5. Running twice on the same snapshot is **byte-stable** for JSON (excluding
   `generated_at`).
6. Script never imports/calls Kraken private/buy/sell or Slack; never writes
   outside `--out-dir` (nor under `options/` / `futures/` subpaths) — assert via
   fence.

**DoD:** all tests pass offline (inputs via `--paper-trades-root`/fixtures,
writes to a temp `--out-dir`); < 30s.

---

## Agent B — S11: Docs blurb (standalone)

**Complexity:** S
**File (new):** `scripts/SCOUT_WAKE_CONTEXT.md`

**Instructions:**
- Write a standalone doc documenting: the CLI invocation, **required
  `--out-dir`**, optional `--paper-trades-root`, `--ts-ct` / `--snapshot` /
  `--inject-review` flags and snapshot precedence, input paths (read-only) and
  output paths (under `--out-dir`), the regime enum, and vol-feature definitions
  (so wake-reviews can cite them by name).
- If any new dependency was introduced (e.g. a clustering lib), add a **one-line
  pin note**. Otherwise state "stdlib + pandas/numpy only".

**DoD:** doc accurately reflects the shipped CLI and the agnostic contract.

---

**Integration:** merge S10 and S11 independently; no file overlap.
