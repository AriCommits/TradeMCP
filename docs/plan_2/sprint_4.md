# Plan 2 — Sprint 4 (Wave 4): Context Bundle Serialization (byte-stable JSON)

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (integration point for the three analysis modules)
**Blocks:** S7 (Markdown renderer)
**Prereqs:** Sprint 3 (S3, S4, S5) complete

Ships as plain files under `scripts/`. Writes go under `--out-dir` only.

---

## Agent A — S6: Context bundle serialization

**Complexity:** M
**File:** `scripts/scout_context/bundle.py`

**Instructions:**
1. Define dataclasses assembling: regime (label + confidence), vol features,
   ring summary, squeeze overlay, plus metadata (key, source provenance,
   `generated_at`).
2. Serialize to `<out_dir>/wake-context-<key>.json` via
   `paths.context_json_path(out_dir, key)` and
   `paths.assert_write_allowed(out_dir, path)`.
3. **Byte-stable requirement:** identical inputs → identical bytes **except**
   the `generated_at` field. Achieve via `json.dumps(..., sort_keys=True,
   ensure_ascii=False)`, fixed float formatting (e.g. round to a documented
   precision), and stable ordering of any lists.
4. All numeric fields finite — assert no NaN/inf before writing.

**Definition of done:**
- Running serialization twice on the same bundle produces byte-identical JSON
  after stripping `generated_at`.
- No NaN/inf in output; fence guard invoked before write.

**What this unblocks:** S7 renders the human embed from this bundle.
