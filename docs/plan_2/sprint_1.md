# Plan 2 — Sprint 1 (Wave 1): Scaffold, Args, Path & Time Contracts

**Agents this wave:** 1 (Agent A)
**Parallelizable:** No (foundation wave — everything depends on it)
**Blocks:** all other sprints
**Prereqs:** none

Ships as plain files under `scripts/` (agnostic handoff — no bot/MCP/Slack at
runtime). **`--out-dir` is required; all writes go there only.**
`--paper-trades-root`/env locates read inputs only.

---

## Agent A — S1: Project scaffold, arg parsing & path/time contracts

**Complexity:** M

**Files to create:**
- `scripts/scout_wake_context.py` — CLI entrypoint (argparse skeleton only; orchestration lands in Sprint 7 / S9)
- `scripts/scout_context/__init__.py`
- `scripts/scout_context/paths.py`
- `scripts/scout_context/timeparse.py`

**Agnostic handoff contract:** `--out-dir` is REQUIRED; the CLI refuses to run
without it and writes nothing outside it. `--paper-trades-root` is optional and
locates read inputs only. No hardcoded `/workspace/...` write targets.

**Instructions:**
1. `scout_wake_context.py`: `#!/usr/bin/env python3` shebang; define an argparse parser with:
   - `--out-dir PATH` (**required** — `parser.add_argument(..., required=True)`; create if missing)
   - `--paper-trades-root PATH` (optional; default from env `PAPER_TRADES_ROOT`) — **inputs only**
   - `--ts-ct "YYYY-MM-DD HH:MM:SS CDT|CT"` (optional)
   - `--snapshot PATH` (optional; explicit path overrides root)
   - `--inject-review PATH` (optional; **explicit path** — never assume `feeds/signals/`)
   - Precedence rule: when both `--snapshot` and `--ts-ct` are given, **prefer snapshot**.
   - Leave a `main()` that parses args and calls a `run(args)` stub raising `NotImplementedError` (Sprint 7 replaces this). Keep the stub tiny so S9 can overwrite cleanly.
2. `paths.py`:
   - `input_root(args)` → resolve `--paper-trades-root` or env `PAPER_TRADES_ROOT` for reads (may be `None`; explicit input paths override).
   - `derive_key(...)` → `YYYY-MM-DD-HHMM` from snapshot filename or `--ts-ct`.
   - `context_json_path(out_dir, key)` / `context_md_path(out_dir, key)` → `<out_dir>/wake-context-<key>.{json,md}`.
   - `ensure_out_dir(out_dir)` — create if missing.
   - `assert_write_allowed(out_dir, path)` — **hard fence**: raise unless the resolved path is inside `out_dir`, and also raise if it lands under an `options/` or `futures/` subpath. Every writer must call this.
3. `timeparse.py`:
   - Parse `"YYYY-MM-DD HH:MM:SS CDT|CT"` → normalized `HHMM` key + a UTC anchor datetime. Handle both `CDT` and bare `CT`.
   - Stdlib only (`datetime`, `zoneinfo`). No pandas here.

**Definition of done:**
- `python3 scripts/scout_wake_context.py --help` exits 0 and lists `--out-dir`, `--paper-trades-root`, `--ts-ct`, `--snapshot`, `--inject-review`.
- Running without `--out-dir` exits non-zero with a clear message.
- `paths.derive_key` produces identical keys from an equivalent snapshot name and `--ts-ct`.
- `assert_write_allowed` passes for `<out_dir>/wake-context-*`, raises for paths outside `out_dir` and for options/ / futures/ subpaths.
- No third-party imports in `paths.py` / `timeparse.py` (stdlib only).

**What this unblocks:** S2 (loaders) and, transitively, all analysis modules.
