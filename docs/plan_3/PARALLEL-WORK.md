# Plan 3 — Parallel Work & Coordination Guide (Options Desk MVP)

Ships as plain files under `scripts/` (agnostic handoff — no bot/MCP/Slack at
runtime). **Every CLI requires `--out-dir`; all writes (plans, PNGs) go there
only.** `--paper-trades-root`/env locates read inputs only. Viz is **PNG-only —
no Slack/Composio from Kiro** (posting stays on the box). Planning docs:
`docs/plan_3/`.

## Task → File → Wave Matrix

| Task | Files | Complexity | Depends on | Wave |
|------|-------|-----------|------------|------|
| O1 core (config/fences/marks/risk/bridge) | `options_desk/__init__.py`, `config.py`, `marks.py`, `risk.py`, `trademcp_bridge.py` | L | — | 1 |
| O2 `screen` + plan CLI skeleton | `options_desk_plan.py`(new), `options_desk/screen.py` | M | O1 | 2 |
| O6 viz data + figure + PNG CLI | `options_desk/viz_data.py`, `viz_figure.py`, `options_desk_slack_viz.py` | L | O1 | 2 |
| O3 `compare` | `options_desk/compare.py`, `options_desk_plan.py`(edit) | M | O1,O2 | 3 |
| O4 `stress` | `options_desk/stress.py`, `options_desk_plan.py`(edit) | M | O1,O2 | 4 |
| O5 `plan` + emitter | `options_desk/plan.py`, `emit.py`, `options_desk_plan.py`(edit) | L | O1–O4 | 5 |
| O7 docs | `options/KIRO_MVP.md` | S | O5,O6 | 6 |
| O8 tests | `scripts/tests/test_options_desk_plan.py`, `test_options_desk_viz.py`, `tests/fixtures/` | M | O5,O6 | 6 |

## Wave Execution Diagram

```text
Wave 1:                 [O1 shared core]
                              |
        +---------------------+---------------------+
Wave 2: [O2 screen + plan CLI skel]        [O6 viz data+figure+PNG CLI]  (PARALLEL x2)
                              |                       |
Wave 3: [O3 compare (locks plan CLI)]                | (viz track done)
                              |                       |
Wave 4: [O4 stress (locks plan CLI)]                 |
                              |                       |
Wave 5: [O5 plan + emitter (locks plan CLI)]         |
                              |                       |
        +---------------------+-----------+-----------+
Wave 6: [O7 docs]                        [O8 tests]           (PARALLEL x2)
        +---------------------+---------------------+
```

## Conflict Table

| Task A | Task B | Conflict | Resolution |
|--------|--------|----------|------------|
| O2, O3, O4, O5 | each other | All edit `options_desk_plan.py` | **Serial chain** O2→O3→O4→O5. O2 registers all subparser stubs (dispatching to modules) so later tasks only attach handler bodies. |
| O2 | O6 | None — plan CLI vs viz modules/CLI | Parallel in Wave 2 |
| O7 | O8 | None — docs vs tests | Parallel in Wave 6 |

The dominant constraint is `options_desk_plan.py` contention: the four
subcommand tasks (O2–O5) must not edit it concurrently, forcing the plan-CLI
track serial (Waves 2→3→4→5). The **PNG viz track (O6) is a single self-contained
task** — it now includes its own CLI entrypoint (`options_desk_slack_viz.py`),
so it finishes entirely in Wave 2 and needs nothing further.

> Slack posting task removed vs the earlier plan: Kiro writes the PNG only.
> Posting is a separate on-box shell step (`post_options_charts.sh`).

> Optimization option: if O2 stubs each subcommand handler to call a module
> function (e.g. `compare.run(args)`), O3/O4/O5 can avoid editing
> `options_desk_plan.py` entirely and only add their own module files —
> collapsing Waves 3–5 into a single parallel wave. Prefer this for maximum
> parallelism; the sprint files assume the conservative handler-attach approach.

## Integration Git Workflow (per wave)

1. Branch per task: `plan3/o<N>-<slug>` off `plan3/integration`.
2. Merge a wave's tasks after each passes DoD.
3. Smoke checkpoints (always pass `--out-dir <tmp>`):
   - End of Wave 2 (viz): `options_desk_slack_viz.py --out-dir <tmp>` writes a PNG.
   - End of Wave 2 (plan CLI): `options_desk_plan.py screen --underlying SPY --structure csp --dte 7-14 --out-dir <tmp>` exits 0.
   - End of Wave 5: `plan` writes JSON+MD with Stop + Risk $ under `<tmp>`.
4. Fence audit in CI/local: assert **`--out-dir` required**; refuse `PAPERTRADE_DB`
   not ending in `options/papertrade.db`; grep for any Kraken import/call and any
   Composio/Slack import (both must be zero); confirm no synthetic `greeks_viz`
   marks used as trading input; no writes outside `--out-dir`.

## Recommended Assignments

**Single agent (serial, ship-order-first):** O1 → **O6** → O5-support → O2 → O3
→ O4 → O5 → (O7 | O8). (O6 first honors the "viz PNG writer first" ship order.)

**2-agent team (recommended — matches the two tracks):**
- Wave 1: A does O1 (B reviews policy docs, preps fixtures).
- Viz track (B): O6 in Wave 2, then B starts O8 test scaffolding.
- Plan-CLI track (A): O2 → O3 → O4 → O5.
- Wave 6: A=O7, B=O8.

**3-agent team:**
- Wave 1: A=O1.
- Wave 2: A=O2, B=O6, C=fixtures/test harness prep.
- Waves 3–5: A drives the O3→O4→O5 plan-CLI chain; B (done with viz) builds O8
  tests against frozen bridge signatures; C drafts O7 docs.
- Wave 6: finalize O7 + O8.

## Critical Path

O1 → O2 → O3 → O4 → O5 → (O7 | O8)

≈ 6 waves. The viz track (O6) is a single Wave-2 task fully hidden under the
plan-CLI critical path, so a second agent delivers the PNG one-pager at zero
extra wall-clock cost — and, per the ship order, it can be the very first thing
shipped. The serial O2→O5 chain on `options_desk_plan.py` is the true
bottleneck; collapse it via the handler-dispatch optimization above if faster
delivery is needed.
