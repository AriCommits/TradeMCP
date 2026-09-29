# Plan 3: Options Desk MVP — Paper-Only Screen → Compare → Stress → Plan + PNG Viz

## Summary

Cash-open and signal wakes still mean hand-walking Yahoo chains and posting
Greek/R dumps to Slack. The Desk needs **one paper-only path**:
screen → compare → stress → plan, plus a single 3-panel PNG one-pager for the
open book.

MVP slice #1 (ship first) delivers:
- **A.** `options_desk_plan.py` — a CLI with `screen | compare | stress | plan`
  subcommands wiring TradeMCP-style logic locally (soft-import a local TradeMCP
  checkout if present, else inline paper helpers), emitting JSON + Markdown
  plans.
- **B.** `options_desk_slack_viz.py` — a one-figure/three-panel **PNG writer**.
  It writes the PNG to disk only. **No Slack / Composio / posting from Kiro** —
  posting stays on the box via existing scripts (`post_options_charts.sh`).
- **C.** `KIRO_MVP.md` — how to run A+B once.

Paper only. Hard DB fence. No live brokers. No synthetic `greeks_viz` marks as
trading input. Every plan carries **Stop + Risk $**.

**Agnostic handoff contract (v2).** Kiro is NOT wired into any bot/MCP/Slack at
runtime. Both CLIs are plain `#!/usr/bin/env python3` scripts under `scripts/`
shipped as ordinary files (or a zip mirroring the `paper-trades/` layout).
The desks "link" purely through stable paths + CLI flags — no agent bridge:

- **`--out-dir PATH` is REQUIRED** on every CLI. All writes (plans, PNGs) go
  under `--out-dir` only; the CLI refuses to run without it and creates it if
  absent. No hardcoded `/workspace/...` write targets.
- **`--paper-trades-root PATH` is OPTIONAL and inputs-only** (or env). It locates
  read inputs — DB, marks, policy docs, journal, signal board. Writes always
  follow `--out-dir`.

Planning artifacts: `docs/plan_3/`.

## Goals

- One CLI covering screen/compare/stress/plan with JSON+MD outputs written under
  `--out-dir` as `YYYY-MM-DD-HHMM-<underlying>.{json,md}`.
- Plans include: OCC symbols, qty, entry mid, Stop, Risk $, thesis one-liner,
  structure type (CSP/PCS/debit/etc.), expiry, collateral if CSP.
- A single 3-panel PNG (Greeks strip, per-leg R path, Day PnL $/R) written under
  `--out-dir` as `YYYY-MM-DD-HHMM.png`. **File only — no posting.**
- Correct Risk $ per `R_REPORTING.md`: long premium = `abs(entry−stop)×qty×100`;
  CSP/PCS documented in plan output.
- Hard fences: refuse/no-op unless `PAPERTRADE_DB` ends with
  `options/papertrade.db` (read-only); never call Kraken tools; never invent
  marks; never use synthetic `greeks_viz` marks as trading input.
- No dependence on Composio/MCP/AriCommits/Kiro being online at runtime.
- Smoke/unit tests for candidate screening, comparison ranking, Risk $ math,
  and the PNG writer.

## Non-Goals

- Live broker adapters / live orders.
- **Any Slack / Composio / OAuth from Kiro.** Posting is a separate on-box shell
  step, not part of these CLIs.
- `greeks_viz` synthetic/demo marks as trading input.
- Full walkforward/backtest research UI.
- Autopilot trading (no auto-fill from plan).
- Rewriting TradingCLI / `papertrade.db` schema (read-only).
- Futures / Kraken / scout / tape books.

## Background / Context

Inputs (read-only; located under `--paper-trades-root`/env, explicit args
override):
- **DB:** `PAPERTRADE_DB` (default `options/papertrade.db` under root), account
  `options`. Read-only; **fence requires the path to end with
  `options/papertrade.db`**.
- **Marks:** TradingCLI / Yahoo; on rate-limit fall back to
  `options/greeks-latest.json` or CBOE delayed — **never invent**, never use
  synthetic `greeks_viz` demo marks as truth.
- **Policy docs:** `options/SETUP.md`, `STOP_POLICY.md`, `R_REPORTING.md`.
- **Journal (optional, PnL panel):** `trade-journal.xlsx` under root.
- **Signal board (optional context):** `feeds/signals/options/latest.json`.

TradeMCP-style operations to wire — **soft-import a local TradeMCP checkout if
present, else inline paper helpers** (never call live broker adapters):
`screen_option_candidates`, `compare_option_strategies`,
`stress_option_candidate`, `build_option_trade_plan`.

Outputs: everything under `--out-dir` — plans as
`<out-dir>/YYYY-MM-DD-HHMM-<underlying>.{json,md}`, PNG as
`<out-dir>/YYYY-MM-DD-HHMM.png`.

Constraints: paper only · DB fence (`options/papertrade.db`) · no live brokers ·
no Slack from Kiro · no synthetic `greeks_viz` marks · max 8 themes in plan text
· Stop + Risk $ required on every plan.

**Ship order if credits are tight:** (1) viz PNG writer (O6), (2) `plan` (O5),
(3) thin `screen`/`compare`/`stress` (O2–O4). The plan reflects the full
dependency graph, but O6 is deliberately independent of the plan-CLI chain so it
can ship first.

## Features / Tasks

### O1: Shared core — config, DB fence, marks provider, R math, TradeMCP bridge

**Files:**
- `scripts/options_desk/__init__.py` (new)
- `scripts/options_desk/config.py` (new — env, `--out-dir`/`--paper-trades-root` resolution, `PAPERTRADE_DB` fence, Kraken fence)
- `scripts/options_desk/marks.py` (new — TradingCLI/Yahoo → greeks-latest.json → CBOE fallback; never invent)
- `scripts/options_desk/risk.py` (new — Risk $ / Stop math per R_REPORTING.md)
- `scripts/options_desk/trademcp_bridge.py` (new — soft-import local TradeMCP, else inline helpers)

**Complexity:** L
**Depends on:** none

Foundation shared by both CLIs. `config.py`:
- resolves `--out-dir` (**required**; `ensure_out_dir`) and `--paper-trades-root`
  (optional, inputs only; default from env);
- `out_path(out_dir, name)` + `assert_write_allowed(out_dir, path)` fence
  (raise on any write outside `--out-dir`);
- `assert_db_fenced(db_path)` — refuse/no-op unless the path **ends with
  `options/papertrade.db`**;
- hard Kraken fence (no Kraken imports/calls anywhere in the package).

`marks.py` implements the mark chain with explicit fail-closed behavior (never
fabricate a mark; never use synthetic `greeks_viz` marks). `risk.py` encodes
Risk $: long premium = `abs(entry−stop)×qty×100`; documents CSP/PCS formulas
(lift verbatim from `R_REPORTING.md`/`STOP_POLICY.md`). `trademcp_bridge.py`
exposes the four operations, **soft-importing** a local TradeMCP checkout when
importable, else using an inline paper implementation. Freeze these signatures
early so O2–O5 build against them.

### O2: `screen` subcommand + plan CLI skeleton

**Files:**
- `scripts/options_desk_plan.py` (new — `#!/usr/bin/env python3`; argparse w/ subcommands + required `--out-dir`; owns `screen`)
- `scripts/options_desk/screen.py` (new)

**Complexity:** M
**Depends on:** O1

Implement `options_desk_plan.py screen --underlying SPY --structure csp
--dte 7-14 --out-dir <dir>`. Returns ≥1 liquid candidate with mid + a width
note; exit 0. Refuses without `--out-dir`. Uses `marks` +
`trademcp_bridge.screen_option_candidates`. Creates the top-level argparse
skeleton with `screen | compare | stress | plan` subcommands (each with a
handler stub dispatching to its module) so O3–O5 only attach handler bodies.

### O3: `compare` subcommand

**Files:**
- `scripts/options_desk/compare.py` (new)
- `scripts/options_desk_plan.py` (edit — attach `compare` handler)

**Complexity:** M
**Depends on:** O1, O2

`compare` on the same underlying outputs ≥2 structures ranked by
Risk $ / credit quality via `trademcp_bridge.compare_option_strategies`.

### O4: `stress` subcommand

**Files:**
- `scripts/options_desk/stress.py` (new)
- `scripts/options_desk_plan.py` (edit — attach `stress` handler)

**Complexity:** M
**Depends on:** O1, O2

`stress` applies deterministic shocks via
`trademcp_bridge.stress_option_candidate` and emits Stop + Risk $ consistent
with `R_REPORTING.md`.

### O5: `plan` subcommand + JSON/MD emitter

**Files:**
- `scripts/options_desk/plan.py` (new)
- `scripts/options_desk/emit.py` (new — JSON + Markdown writer, `--out-dir` paths)
- `scripts/options_desk_plan.py` (edit — attach `plan` handler)

**Complexity:** L
**Depends on:** O1, O2, O3, O4

`plan` calls `build_option_trade_plan` and emits JSON + human-readable Markdown
to `<out-dir>/YYYY-MM-DD-HHMM-<underlying>.{json,md}`. Plan must include:
OCC symbols, qty, entry mid, Stop, Risk $, thesis one-liner, structure type
(CSP/PCS/debit/etc.), expiry, collateral if CSP. Respect **max 8 themes** in
plan text. `emit.py` owns `--out-dir` path construction + both serializers so
the viz task and tests can reuse it.

### O6: PNG viz — book/marks reader + 3-panel figure + CLI

**Files:**
- `scripts/options_desk/viz_data.py` (new — open book + marks + journal PnL reader)
- `scripts/options_desk/viz_figure.py` (new — 3-panel matplotlib figure → PNG bytes)
- `scripts/options_desk_slack_viz.py` (new — `#!/usr/bin/env python3` CLI: build figure, write PNG under `--out-dir`)

**Complexity:** L
**Depends on:** O1

Read the open book from `PAPERTRADE_DB` (options account, read-only, fenced) +
current marks (`marks.py`) + optional journal PnL from `trade-journal.xlsx`.
Build a single figure with three panels:
1. Net book Greeks strip (Δ / Θ; Γ/vega optional) — session sparkline if history
   exists, else current bars.
2. Per-leg R path (entry → mid → stop line) for open positions.
3. Day PnL $ / R bars (open uPnL + today's closed R if in journal).

The CLI (`options_desk_slack_viz.py`) requires `--out-dir` and writes the PNG to
`<out-dir>/YYYY-MM-DD-HHMM.png` — **file only, no Slack/Composio/posting**.
Degrade gracefully when journal/history absent. Fully independent of the plan
CLI (O2–O5) — parallelizable after O1, and the recommended first ship.

> Note: the script name `options_desk_slack_viz.py` is retained for continuity
> with the desk's naming, but it performs **no Slack action** — it is a PNG
> writer. Posting is done separately on the box.

### O7: Docs — `KIRO_MVP.md`

**Files:**
- `options/KIRO_MVP.md` (new)

**Complexity:** S
**Depends on:** O5, O6

Document how to run A + B once end to end: required `--out-dir`, optional
`--paper-trades-root`, `options_desk_plan.py` subcommands with examples,
`options_desk_slack_viz.py` PNG usage, output paths (all under `--out-dir`),
fences (DB `options/papertrade.db`, no Kraken, no synthetic marks, no Slack from
Kiro), how posting happens separately on the box, and the Risk $ formulas.
Parallel with tests (O8).

### O8: Tests — screen/compare, Risk $ math, viz smoke, fences

**Files:**
- `scripts/tests/test_options_desk_plan.py` (new)
- `scripts/tests/test_options_desk_viz.py` (new)
- `scripts/tests/fixtures/` (new — stub DB / marks / book fixtures)

**Complexity:** M
**Depends on:** O5, O6

Encode the acceptance tests (all use a temp `--out-dir`):
- both CLIs **refuse to run without `--out-dir`**;
- `screen` returns ≥1 liquid candidate (mid + width), exit 0;
- `compare` ranks ≥2 structures by Risk $ / credit quality;
- `stress`+`plan` emit Stop + Risk $ matching `R_REPORTING.md` and a
  human-readable plan md written under `--out-dir`;
- Risk $ for long premium = `abs(entry−stop)×qty×100`, CSP/PCS documented;
- viz writes a **3-panel PNG under `--out-dir`** and **performs no Slack call**
  (assert no Composio/Slack import) without crashing;
- scripts refuse/no-op unless `PAPERTRADE_DB` ends with `options/papertrade.db`;
  never call Kraken; never write outside `--out-dir`.

## New Dependencies

- `matplotlib` for the viz PNG (pin version in `KIRO_MVP.md`).
- `openpyxl` (or pandas Excel engine) only if reading `trade-journal.xlsx`
  directly — pin if introduced.
- **No Composio/Slack dependency** — posting is out of scope for Kiro.
- Local TradeMCP checkout optional; the bridge soft-imports it or falls back to
  inline paper helpers.

## File Change Summary

| Path | Task(s) | New/Edit |
|------|---------|----------|
| `scripts/options_desk/__init__.py` | O1 | New |
| `scripts/options_desk/config.py` | O1 | New |
| `scripts/options_desk/marks.py` | O1 | New |
| `scripts/options_desk/risk.py` | O1 | New |
| `scripts/options_desk/trademcp_bridge.py` | O1 | New |
| `scripts/options_desk_plan.py` | O2 (new), O3/O4/O5 (edit) | New → Edit |
| `scripts/options_desk/screen.py` | O2 | New |
| `scripts/options_desk/compare.py` | O3 | New |
| `scripts/options_desk/stress.py` | O4 | New |
| `scripts/options_desk/plan.py` | O5 | New |
| `scripts/options_desk/emit.py` | O5 | New |
| `scripts/options_desk/viz_data.py` | O6 | New |
| `scripts/options_desk/viz_figure.py` | O6 | New |
| `scripts/options_desk_slack_viz.py` | O6 | New |
| `options/KIRO_MVP.md` | O7 | New |
| `scripts/tests/test_options_desk_plan.py` | O8 | New |
| `scripts/tests/test_options_desk_viz.py` | O8 | New |
| `scripts/tests/fixtures/` | O8 | New |

## Open Questions

- Is a local TradeMCP checkout importable on the box, or is the inline paper
  implementation required for MVP? The bridge (O1) supports both; default to the
  inline fallback if soft-import fails.
- Exact CSP/PCS Risk $ formula wording — must be lifted verbatim from
  `R_REPORTING.md` / `STOP_POLICY.md` during O1 (read those files first).
- `papertrade.db` schema for open positions (leg table shape) — read-only
  inspect during O6; do not modify schema.
- Journal (`trade-journal.xlsx`) sheet/column layout for the PnL panel —
  optional; panel degrades gracefully if absent.
