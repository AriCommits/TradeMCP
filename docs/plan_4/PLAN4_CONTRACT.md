# Plan 4 — Agnostic handoff contract (Futures evening CLI)

Kiro is **NOT** wired into any bot / MCP / Slack at runtime. The Futures evening
helper is a plain `#!/usr/bin/env python3` script under
`paper-trades/scripts/`, shipped as ordinary files (or a zip mirroring the
`paper-trades/` layout). Desks link purely through **stable paths + CLI flags**
— no agent bridge.

This matches Plan 2 (Scout) and Plan 3 (Options) v2 contracts.

## Required: `--out-dir`

```
--out-dir PATH     # REQUIRED. All writes go under this directory (create if missing).
```

- Refuse to run if `--out-dir` is missing.
- Never hardcode `/workspace/paper-trades/...` as a write target.
- Create `--out-dir` if absent.
- Assert every write path resolves under `--out-dir` (no escape).

## Optional: `--paper-trades-root` (inputs only)

```
--paper-trades-root PATH   # optional. Default inputs relative to this root.
                           # Also accepted via env PAPER_TRADES_ROOT.
```

- Locates **read** inputs only: `last-check.json`, `slack/paper-running-book.csv`,
  policy docs for human reference.
- **Writes always follow `--out-dir`.**
- Missing root / missing marks → still succeed with skeleton-only session md.

## Optional: `--as-of`

```
--as-of "YYYY-MM-DD HH:MM CT"   # optional session stamp label (default: now CT)
```

Used in filenames and the session header. Does not fetch historical marks by
itself (marks come from whatever freeze file is present under the root).

## CLI entrypoint

```
paper-trades/scripts/futures_desk_session.py
```

Stdlib only. No Composio, no Slack SDK, no Kraken private client imports.

## Fences

| Fence | Rule |
|-------|------|
| Paper only | Never submit live or paper **orders** (no buy/sell/cancel). |
| No Slack | Never post; never import Slack/Composio clients. |
| Futures only | Do not read/write scout, tape, invariants, or options DBs. |
| No invent marks | If inputs are missing, say so; do not fabricate prices. |
| Exit | Exit **0** after writing the session skeleton (marks optional). |

## Outputs under `--out-dir`

- `YYYY-MM-DD-HHMM-session.md` — always
- `YYYY-MM-DD-HHMM-marks.{md,json}` — when a marks/book source is found

Money Maker / Futures Desk later copy artifacts onto the box and (separately)
post to `#desk-futures` / `#ops-paper-metrics` if desired.

## Done when

- `python3 …/futures_desk_session.py --help` works.
- Run with only `--out-dir` writes a session skeleton and exits 0.
- Run with a paper-trades root that has `last-check.json` also freezes marks.
- No network broker/Slack calls in the script.
