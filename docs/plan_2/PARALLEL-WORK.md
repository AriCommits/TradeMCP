# Plan 2 — Parallel Work & Coordination Guide (Scout Wake Context)

Ships as plain files under `scripts/` (agnostic handoff — no bot/MCP/Slack at
runtime). **`--out-dir` is required on the CLI; all writes go there only.**
`--paper-trades-root`/env locates read inputs only. Planning docs:
`docs/plan_2/`.

## Task → File → Wave Matrix

| Task | Files | Complexity | Depends on | Wave |
|------|-------|-----------|------------|------|
| S1 scaffold/args/paths/time | `scripts/scout_wake_context.py`(skel), `scout_context/__init__.py`, `paths.py`, `timeparse.py` | M | — | 1 |
| S2 loaders + fixtures | `scout_context/loaders.py`, `scout_context/fixtures/` | L | S1 | 2 |
| S3 regime | `scout_context/regime.py` | L | S1,S2 | 3 |
| S4 vol features | `scout_context/vol_features.py` | M | S1,S2 | 3 |
| S5 ring+squeeze | `scout_context/ring_summary.py`, `squeeze_overlay.py` | M | S1,S2 | 3 |
| S6 bundle JSON | `scout_context/bundle.py` | M | S3,S4,S5 | 4 |
| S7 md renderer | `scout_context/render_md.py` | M | S6 | 5 |
| S8 injector | `scout_context/inject.py` | M | S7 | 6 |
| S9 CLI wiring | `scripts/scout_wake_context.py`(edit) | M | S6,S7,S8 | 7 |
| S10 tests | `scripts/tests/test_scout_wake_context.py`, `tests/fixtures/...json` | M | S9 | 8 |
| S11 docs | `scripts/SCOUT_WAKE_CONTEXT.md` | S | S9 | 8 |

## Wave Execution Diagram

```text
Wave 1:            [S1 scaffold/paths/time]
                          |
Wave 2:            [S2 loaders + fixtures]
                          |
        +-----------------+-----------------+
Wave 3: [S3 regime]  [S4 vol features]  [S5 ring+squeeze]   (PARALLEL x3)
        +-----------------+-----------------+
                          |
Wave 4:            [S6 bundle JSON]
                          |
Wave 5:            [S7 md renderer]
                          |
Wave 6:            [S8 injector]
                          |
Wave 7:            [S9 CLI wiring]   (owns top-level script)
                          |
        +-----------------+-----------------+
Wave 8: [S10 tests]                 [S11 docs]              (PARALLEL x2)
        +-----------------+-----------------+
```

## Conflict Table

| Task A | Task B | Conflict | Resolution |
|--------|--------|----------|------------|
| S1 | S9 | Both touch `scout_wake_context.py` | Sequenced: S1 writes skeleton (Wave 1), S9 fills orchestration (Wave 7) |
| S3/S4/S5 | each other | None — disjoint files | Run concurrently in Wave 3 |
| S10 | S11 | None — test dir vs docs file | Run concurrently in Wave 8 |

The only file contention is the top-level `scout_wake_context.py` (S1 → S9),
resolved by wave separation. All analysis modules and the pipeline stages write
distinct files, so contention is otherwise nil.

## Integration Git Workflow (per wave)

1. Branch per task: `plan2/s<N>-<slug>` off the integration branch.
2. After a wave's tasks pass their DoD, merge them into `plan2/integration`.
3. Run the smoke path
   (`python3 scripts/scout_wake_context.py --snapshot <fixture> --out-dir <tmp>`)
   at the end of Waves 4, 7, and 8.
4. Enforce the fence in CI/local: assert **`--out-dir` required**, no writes
   outside `--out-dir` (nor under `options/`/`futures/` subpaths), and no
   Kraken private/buy/sell or Slack imports.
5. Keep `generated_at` the only volatile JSON field; verify byte-stability in
   Wave 4 and again in Wave 8 (S10).

## Recommended Assignments

**Single agent (serial):** S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10 → S11.

**2-agent team:**
- Waves 1–2: Agent A does S1 then S2 (Agent B reviews contracts / preps fixtures).
- Wave 3: A=S3+S5, B=S4.
- Waves 4–7: A drives S6→S7→S8→S9; B writes test scaffolding against frozen contracts.
- Wave 8: A=S10, B=S11.

**3-agent team:**
- Wave 3 is the peak: A=S3, B=S4, C=S5 fully parallel.
- Wave 8: A=S10, B=S11, C=integration smoke + fence audit.

## Critical Path

S1 → S2 → (S3|S4|S5) → S6 → S7 → S8 → S9 → (S10|S11)

Longest chain ≈ 8 waves. Parallelism only compresses Waves 3 and 8; the
mid-pipeline (S6→S9) is inherently serial because each stage consumes the
previous stage's contract.
