# Plan 2: Scout Wake Context — Offline Regime & Vol Research Block

## Summary

Scout's 5m ring wake-reviews fire frequently on single-bar residual/z spikes
(XRP/ETH/SOL) with little regime context, forcing PASS/TAKE notes to rely on
ad-hoc judgment. This plan delivers a **frozen, offline research block** — a
regime cluster label plus short-horizon volatility features — that is
embeddable into `wake-review-*.md` at ping time. The output is **context only,
never an order**. It is a deterministic, reproducible CLI that reads
read-only market and signal inputs and writes a machine JSON + a human Markdown
embed block, with an optional flag to inject that block into an existing
wake-review file.

**Agnostic handoff contract (v2).** Kiro is NOT wired into any bot/MCP/Slack at
runtime. This CLI is a plain `#!/usr/bin/env python3` script under `scripts/`
that ships as ordinary files (or a zip mirroring the `paper-trades/` layout).
Desks "link" to it purely through stable paths + CLI flags — no agent bridge.
Two rules drive the interface:

- **`--out-dir PATH` is REQUIRED.** All writes go under `--out-dir` only. The
  CLI refuses to run if it is missing. No hardcoded `/workspace/...` write
  targets anywhere. `--out-dir` is created if absent.
- **`--paper-trades-root PATH` is OPTIONAL and inputs-only** (or an env var). It
  locates read inputs (snapshots, ring, latest, squeeze). Writes always follow
  `--out-dir`.

Planning artifacts live in this repo under `docs/plan_2/`.

## Goals

- Ship a single CLI `scripts/scout_wake_context.py` that turns a timestamp
  and/or a frozen wake snapshot into a regime + vol-feature context bundle.
- **Require `--out-dir`**; write all artifacts under it only.
- Emit both machine (`.json`) and human (`.md`) artifacts with five fixed
  Markdown headings: Regime, Vol features, Ring summary, Squeeze overlay
  (BTC/ETH/SOL), Caveats.
- Provide **optional, file-local** `--inject-review PATH` to insert the embed
  under a `## Offline wake context` heading without touching Decision/Judgment
  lines. Standalone `.md` + `.json` are the primary deliverable; injection is a
  convenience.
- Document the regime enum + vol-feature definitions in the script docstring and
  README so wake-reviews can cite them by name.
- Be deterministic: byte-stable JSON across identical runs (excluding
  `generated_at`).
- Fail closed: never invent missing quotes; label regime `unknown` and set
  finite (non-NaN) vol numbers when data is thin.
- No dependence on any bot/MCP/Slack/Kraken-private API being online at runtime.
- Runtime < 30s on box for ≤5 names × ~3–5 days of 5m bars.
- Ship deterministic fixture-driven tests.

## Non-Goals

- Live trading / autopilot TAKE/PASS decisions.
- Position sizing or a competing risk sizer.
- Futures, options, or tape workspaces; no writes under `options/` or
  `futures/` subpaths of `--out-dir`.
- **Slack / Composio uploads from Kiro.** No Slack OAuth, no posting. Posting
  stays on the box via existing scripts. Kiro writes files only.
- No Kraken private API, no paper buy/sell. Public OHLCV or fixture CSVs only.
- Changing `scout_signal_monitor.py` alert thresholds or daemon cadence.
- Online retraining; no GPU requirement.

## Background / Context

Inputs (all read-only), located under an optional `--paper-trades-root`
(or env `PAPER_TRADES_ROOT`); explicit input paths like `--snapshot` override:

- Kraken **public** OHLCV 5m for BTC/ETH/SOL/XRP/LINK (same pairs as monitor).
- `feeds/signals/ring.json` and/or frozen `wake-snapshot-*.json` (board+ring).
- `feeds/signals/latest.json` for ts/alerts when no snapshot path is given.
- `feeds/squeeze/latest.md` or squeeze history CSV if present (BTC/ETH/SOL
  tags only).

Argument precedence: prefer `--snapshot` over `--ts-ct` when both present.
Timestamps are Central Time (`"YYYY-MM-DD HH:MM:SS CDT|CT"`).

Output naming: `<out-dir>/wake-context-YYYY-MM-DD-HHMM.{json,md}` where the
timestamp is derived from the snapshot/ts. **`--out-dir` is required**; nothing
is written outside it.

Regime enum (documented in docstring + README): `trend_up | trend_down |
mean_revert | high_vol_chop | low_vol_chop | unknown`, plus confidence in
`[0,1]`.

Vol features must include at minimum: realized vol (20-bar), `vol_ratio` vs
ring, and a 3–12 bar ahead vol forecast or expansion flag — all finite, no NaN.

Constraints: spot Scout paper research only; hard fence against
futures/options/tape and against Slack/Kraken-private. Prefer stdlib +
pandas/numpy already on the box; any new dep pinned in a one-line README note.

## Features / Tasks

### S1: Project scaffold, arg parsing & path/time contracts

**Files:**
- `scripts/scout_wake_context.py` (new — CLI entrypoint, argparse skeleton)
- `scripts/scout_context/__init__.py` (new — internal package)
- `scripts/scout_context/paths.py` (new — path root, output-name derivation, fence guards)
- `scripts/scout_context/timeparse.py` (new — CT timestamp parsing → UTC + HHMM key)

**Complexity:** M
**Depends on:** none

Establish the CLI surface: `--out-dir` (**required**), `--paper-trades-root`
(optional, inputs only), `--ts-ct`, `--snapshot`, `--inject-review` flags.
Refuse to run when `--out-dir` is missing; create it if absent. Derive the
`YYYY-MM-DD-HHMM` output key from snapshot or ts, build output paths under
`--out-dir` only, and implement the hard fence that refuses any resolved write
path outside `--out-dir` or under `options/`/`futures/` subpaths. Resolve read
inputs against `--paper-trades-root`/env (explicit `--snapshot` overrides).
Central Time parsing (CDT/CT) → normalized key and UTC anchor. This module
defines the shared contracts every other task imports; keep it dependency-light
(stdlib only) so downstream tasks can build in parallel against stable
signatures. Snapshot-over-ts precedence lives here.

### S2: Input loaders (read-only) — Kraken OHLCV, ring/snapshot, latest, squeeze

**Files:**
- `scripts/scout_context/loaders.py` (new)
- `scripts/scout_context/fixtures/` (new dir — sample inputs for offline dev)

**Complexity:** L
**Depends on:** S1

Read-only loaders for: Kraken public 5m OHLCV (BTC/ETH/SOL/XRP/LINK),
`ring.json`, frozen `wake-snapshot-*.json` (board+ring), `latest.json`
(ts/alerts fallback), and `feeds/squeeze/latest.md` / squeeze history CSV
(BTC/ETH/SOL tags only). Inputs resolve against `--paper-trades-root`/env or
explicit path args. Must fail closed: missing/stale inputs surface as
explicit empty/None with quality flags rather than fabricated values. Provide
an offline path (fixtures / cached bars) so tests never hit the network and
runtime stays < 30s. No Kraken private API / paper buy/sell imports — public
data or fixtures only.

### S3: Regime clustering + confidence

**Files:**
- `scripts/scout_context/regime.py` (new)

**Complexity:** L
**Depends on:** S1, S2

Compute the regime label from the enum (`trend_up | trend_down | mean_revert |
high_vol_chop | low_vol_chop | unknown`) with a confidence in `[0,1]`. Frozen,
offline heuristic/clustering over the loaded 5m bars (e.g., trend slope +
realized-vol banding + mean-reversion test). Deterministic given identical
inputs. When data is insufficient, return `unknown` with low confidence rather
than NaN. Document the enum and the decision rule inline and for the README.

### S4: Short-horizon vol features

**Files:**
- `scripts/scout_context/vol_features.py` (new)

**Complexity:** M
**Depends on:** S1, S2

Compute realized vol (20-bar), `vol_ratio` vs ring, and a 3–12 bar ahead vol
forecast or expansion flag. All values finite (no NaN); thin-data paths return
documented sentinels. Reuses loaders from S2 and the shared contracts from S1.
Independent of S3 (regime) so it can be built in parallel with it.

### S5: Ring summary + Squeeze overlay assembly

**Files:**
- `scripts/scout_context/ring_summary.py` (new)
- `scripts/scout_context/squeeze_overlay.py` (new)

**Complexity:** M
**Depends on:** S1, S2

Build the Ring summary section from ring/snapshot data and the Squeeze overlay
restricted to BTC/ETH/SOL tags (from `feeds/squeeze/latest.md` or history CSV).
Squeeze overlay is optional-input tolerant (renders a documented "no squeeze
data" state when absent). Parallel with S3/S4.

### S6: Context bundle serialization (machine JSON) — byte-stable

**Files:**
- `scripts/scout_context/bundle.py` (new — dataclasses + JSON serializer)

**Complexity:** M
**Depends on:** S3, S4, S5

Assemble regime + vol features + ring summary + squeeze overlay into a single
context dataclass and serialize to `<out-dir>/wake-context-*.json` (via the S1
path helper + fence). Serialization must be **byte-stable** across identical
runs excluding a single `generated_at` field (sorted keys, fixed float
formatting, stable ordering). This is the integration point for the three
analysis modules.

### S7: Markdown embed renderer (five fixed headings)

**Files:**
- `scripts/scout_context/render_md.py` (new)

**Complexity:** M
**Depends on:** S6

Render the human embed block with fixed headings in order: **Regime**,
**Vol features**, **Ring summary**, **Squeeze overlay (BTC/ETH/SOL)**,
**Caveats** (one line: not a trade signal). Consumes the S6 bundle. Output
written to `<out-dir>/wake-context-*.md`.

### S8: `--inject-review` injector (optional, file-local)

**Files:**
- `scripts/scout_context/inject.py` (new)

**Complexity:** M
**Depends on:** S7

Optional convenience: insert the rendered embed under a `## Offline wake
context` heading into an **explicit** target path passed via `--inject-review
PATH` (never assume `feeds/signals/`), only if that heading is missing
(idempotent — exactly one section, never duplicated). Must not overwrite or
alter `Decision` / `Judgment` lines. Consumes the S7 renderer output. Standalone
`.md`/`.json` remain the primary deliverable, so this is not on the critical
delivery path.

### S9: CLI wiring (end-to-end orchestration)

**Files:**
- `scripts/scout_wake_context.py` (edit — wire loaders → analysis → bundle → render → optional inject)

**Complexity:** M
**Depends on:** S6, S7, S8 (and transitively S2–S5)

Wire the full pipeline in the entrypoint: require `--out-dir`, resolve inputs
(snapshot precedence; inputs from `--paper-trades-root`/env), run loaders,
compute regime/vol/ring/squeeze, serialize JSON, render MD (both under
`--out-dir`), and optionally inject into an explicit `--inject-review` path.
Enforce fence guards (no writes outside `--out-dir`; no options/futures; no
Slack/Kraken-private) and <30s runtime. Exit non-zero with a clear message when
`--out-dir` is missing. This task owns the top-level `scout_wake_context.py`
(S1 created the skeleton; S9 fills orchestration) — sequenced after S1 to avoid
file contention.

### S10: Tests — fixture snapshot → deterministic context files

**Files:**
- `scripts/tests/test_scout_wake_context.py` (new)
- `scripts/tests/fixtures/wake-snapshot-2026-09-28-1500.json` (new)

**Complexity:** M
**Depends on:** S9

Unit/smoke tests driven by fixture `wake-snapshot-2026-09-28-1500.json`, all
using a temp `--out-dir`:
CLI **refuses to run without `--out-dir`** (non-zero exit); with `--out-dir`,
exits 0 and writes both `wake-context-2026-09-28-1500.json` + `.md` under it
with all five headings; regime label is in the enum with confidence in `[0,1]`;
vol features finite (no NaN); `--inject-review <tmp>` adds exactly one section
and leaves Decision/Judgment unchanged; running twice is byte-stable for JSON
(excluding `generated_at`); script never imports Kraken private/buy/sell or
Slack, and never writes outside `--out-dir` (nor under options/ or futures/).

### S11: README / docs blurb (Scout subsection)

**Files:**
- `scripts/SCOUT_WAKE_CONTEXT.md` (new — standalone doc shipped beside the CLI)

**Complexity:** S
**Depends on:** S9

Document the CLI, all flags (**required `--out-dir`**, optional
`--paper-trades-root`, `--ts-ct`, `--snapshot`, `--inject-review`), input/output
paths, the regime enum, vol-feature definitions, and any newly pinned dependency
(one-line pin note). A standalone doc (not `feeds/signals/README.md`) so the
handoff zip is self-contained. Independent of tests (S10) — parallel once CLI
behavior is frozen.

## New Dependencies

- None expected beyond stdlib + `pandas`/`numpy` (already common on box). If a
  clustering helper (e.g. `scikit-learn`) is introduced, pin it in a one-line
  note in `scripts/SCOUT_WAKE_CONTEXT.md`. Prefer a stdlib/numpy heuristic to
  avoid new deps.

## File Change Summary

| Path | Task(s) | New/Edit |
|------|---------|----------|
| `scripts/scout_wake_context.py` | S1, S9 | New (S1) → Edit (S9) |
| `scripts/scout_context/__init__.py` | S1 | New |
| `scripts/scout_context/paths.py` | S1 | New |
| `scripts/scout_context/timeparse.py` | S1 | New |
| `scripts/scout_context/loaders.py` | S2 | New |
| `scripts/scout_context/fixtures/` | S2 | New |
| `scripts/scout_context/regime.py` | S3 | New |
| `scripts/scout_context/vol_features.py` | S4 | New |
| `scripts/scout_context/ring_summary.py` | S5 | New |
| `scripts/scout_context/squeeze_overlay.py` | S5 | New |
| `scripts/scout_context/bundle.py` | S6 | New |
| `scripts/scout_context/render_md.py` | S7 | New |
| `scripts/scout_context/inject.py` | S8 | New |
| `scripts/tests/test_scout_wake_context.py` | S10 | New |
| `scripts/tests/fixtures/wake-snapshot-2026-09-28-1500.json` | S10 | New |
| `scripts/SCOUT_WAKE_CONTEXT.md` | S11 | New |

## Open Questions

- Exact Kraken 5m fetch mechanism on the box (cached parquet vs. live public
  REST). Assumed: a read-only fetch with an offline fixture fallback for tests.
  Noted as a decision in S2.
- Precise `vol_ratio` "vs ring" definition (ratio of name RV to ring-median
  RV assumed). Confirm during S4.
- Whether squeeze history CSV has a fixed schema/path; S5 renders a graceful
  "no data" state if absent.
