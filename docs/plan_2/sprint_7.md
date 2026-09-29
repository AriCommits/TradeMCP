# Plan 2 — Sprint 7 (Wave 7): CLI Wiring (end-to-end orchestration)

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (owns the top-level entrypoint)
**Blocks:** S10 (tests), S11 (README)
**Prereqs:** Sprint 4 (S6), Sprint 5 (S7), Sprint 6 (S8) complete

Ships as a plain `#!/usr/bin/env python3` script under `scripts/`.

---

## Agent A — S9: CLI wiring

**Complexity:** M
**File (edit):** `scripts/scout_wake_context.py`

**Instructions:**
Replace the S1 `run(args)` stub with the full pipeline:
1. **Require `--out-dir`** (argparse enforces; also guard in `run`) and
   `ensure_out_dir`. Resolve read inputs against `--paper-trades-root`/env.
2. Resolve inputs — **snapshot precedence** over `--ts-ct`; fall back to
   `latest.json` for ts/alerts when neither snapshot nor ts is usable.
3. `loaders` (S2) → load OHLCV / ring / snapshot / squeeze.
4. Compute `regime` (S3), `vol_features` (S4), `ring_summary` + `squeeze_overlay` (S5).
5. Assemble + serialize JSON (S6); render + write MD (S7) — both under `--out-dir`.
6. If `--inject-review PATH`, call `inject.inject_review(PATH, render_block(bundle))` (S8) — explicit path only.
7. Enforce fence guards on every out-dir write; keep runtime < 30s.
8. Exit 0 on success; non-zero with a clear message on failure or missing `--out-dir` (fail closed).

**Definition of done:**
- Running without `--out-dir` exits non-zero.
- End-to-end run from a snapshot writes both `.json` + `.md` under `--out-dir` and exits 0.
- `--inject-review` explicit path adds the section without touching Decision/Judgment.
- No Kraken private/buy/sell or Slack imports; no writes outside `--out-dir` (nor options/ / futures/).

**What this unblocks:** S10 tests the full CLI; S11 documents it.
