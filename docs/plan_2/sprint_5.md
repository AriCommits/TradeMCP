# Plan 2 — Sprint 5 (Wave 5): Markdown Embed Renderer

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No
**Blocks:** S8 (injector)
**Prereqs:** Sprint 4 (S6) complete

Ships as plain files under `scripts/`. Writes go under `--out-dir` only.

---

## Agent A — S7: Markdown embed renderer (five fixed headings)

**Complexity:** M
**File:** `scripts/scout_context/render_md.py`

**Instructions:**
Render the human embed block from the S6 bundle with these **fixed headings,
in order**:
1. `Regime`
2. `Vol features`
3. `Ring summary`
4. `Squeeze overlay (BTC/ETH/SOL)`
5. `Caveats` — one line: **not a trade signal**.

Write to `<out_dir>/wake-context-<key>.md` via
`paths.context_md_path(out_dir, key)` and
`paths.assert_write_allowed(out_dir, path)`. The rendered block is also the
exact string later injected by S8, so expose a `render_block(bundle) -> str`
that returns the block without writing (for reuse + tests).

**Definition of done:**
- Output `.md` contains all five headings in order.
- `render_block` returns the same content that is written to disk.
- Fence guard invoked before write.

**What this unblocks:** S8 injects `render_block` output into a review file.
