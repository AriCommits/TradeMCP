# Plan 2 — Sprint 6 (Wave 6): `--inject-review` Injector (optional, file-local)

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No
**Blocks:** S9 (CLI wiring)
**Prereqs:** Sprint 5 (S7) complete

Ships as plain files under `scripts/`. This is a convenience feature — the
standalone `.json`/`.md` under `--out-dir` are the primary deliverable.

---

## Agent A — S8: Review injector

**Complexity:** M
**File:** `scripts/scout_context/inject.py`

**Instructions:**
1. `inject_review(review_path, block_text)`:
   - `review_path` is the **explicit path** passed via `--inject-review` — never
     assume `feeds/signals/`. Operate only on that exact file; do not derive or
     write to any other location.
   - Insert `block_text` under a `## Offline wake context` heading.
   - **Idempotent:** if the heading already exists, do nothing (never duplicate).
     Result must contain **exactly one** `## Offline wake context` section.
   - **Never** modify `Decision` or `Judgment` lines — preserve them verbatim.
2. Consume the exact `render_block(...)` string from S7.

**Definition of done:**
- Injecting into a stub review adds exactly one section; second run is a no-op.
- Decision/Judgment lines byte-unchanged before/after injection.
- Writes only the explicit `--inject-review` path (nothing under `--out-dir`).

**What this unblocks:** S9 wires optional `--inject-review` end to end.
