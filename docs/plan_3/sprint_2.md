# Plan 3 — Sprint 2 (Wave 2): `screen` CLI + PNG Viz CLI (PARALLEL)

**Agents this wave:** 2 (Agents A, B) — different files
**Parallelizable:** Yes
**Blocks:** O3/O4/O5 (via O2); O7/O8 (via O6)
**Prereqs:** Sprint 1 (O1) complete

Ships as plain files under `scripts/`. Both CLIs **require `--out-dir`** and
write only under it; inputs resolve via `--paper-trades-root`/env.

> **Ship order note:** if credits are tight, do **Agent B (O6 PNG viz) first** —
> it is the recommended first deliverable and is fully independent of the plan
> CLI chain.

---

## Agent A — O2: `screen` subcommand + plan CLI skeleton

**Complexity:** M
**Files:**
- `scripts/options_desk_plan.py` (new — `#!/usr/bin/env python3`; argparse with `screen | compare | stress | plan` subcommands + **required** `--out-dir`; optional `--paper-trades-root`; implement `screen` now, stubs for the rest)
- `scripts/options_desk/screen.py` (new)

**Instructions:**
- `options_desk_plan.py screen --underlying SPY --structure csp --dte 7-14
  --out-dir <dir>` returns **≥1 liquid candidate** with mid + a width note;
  exit 0. **Refuses without `--out-dir`.**
- Use `marks` + `trademcp_bridge.screen_option_candidates` from O1.
- Register `compare`/`stress`/`plan` subparsers now with handler stubs that
  dispatch to their modules, so O3–O5 only attach handler bodies (minimizes
  churn on this shared file).

**DoD:** `screen ... --out-dir <dir>` returns a liquid candidate (mid + width
note), exit 0; runs refuse without `--out-dir`.

**NOTE — file ownership:** Agent A owns `options_desk_plan.py` this wave. O3, O4,
O5 edit it in later waves and **must not** run concurrently with each other on it.

---

## Agent B — O6: PNG viz — book/marks reader + 3-panel figure + CLI

**Complexity:** L
**Files:**
- `scripts/options_desk/viz_data.py`
- `scripts/options_desk/viz_figure.py`
- `scripts/options_desk_slack_viz.py` (`#!/usr/bin/env python3` CLI)

**Instructions:**
- `viz_data.py`: read open book from `PAPERTRADE_DB` (options account) + current
  marks (`marks.py`) + optional journal PnL from `trade-journal.xlsx`.
  Read-only; do not modify schema. Apply DB (`options/papertrade.db`) + Kraken
  fences from O1.
- `viz_figure.py`: build a **single figure, three panels** → PNG:
  1. Net book Greeks strip (Δ / Θ; Γ/vega optional) — session sparkline if
     history exists, else current bars.
  2. Per-leg R path (entry → mid → stop line) for open positions.
  3. Day PnL $ / R bars (open uPnL + today's closed R if in journal).
  Degrade gracefully when journal/history absent.
- `options_desk_slack_viz.py`: **require `--out-dir`**; build the figure and
  write the PNG to `<out-dir>/YYYY-MM-DD-HHMM.png`. **File only — NO Slack /
  Composio / posting / OAuth.** (Name kept for desk continuity; it performs no
  Slack action.)

**DoD:** given a stub book+marks fixture and `--out-dir <tmp>`, writes a 3-panel
PNG under `<tmp>`; imports no Slack/Composio module; refuses without `--out-dir`.

---

**Integration:** A and B touch disjoint files — merge independently.
