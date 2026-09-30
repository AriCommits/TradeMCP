> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `RISK_RULES.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# Shared paper risk rules

## Bots / books
| Bot | Owns |
|-----|------|
| Signal Scout | Kraken spot `scout` |
| Tape + Narrative | Kraken spot `tape` |
| Options Desk | TradingCLI account `options` |
| Futures Desk | Kraken futures paper (sole trader) |
| Money Maker | Orchestration + spot `invariants` (legacy wave1); does not trade other bots’ books |

1. Spot / futures paper accounts: each is a **5% portfolio sleeve** of the experiment.
2. **Options Desk exception (2026-09-10):** full TradingCLI `options` cash is capital under management (not 5% of the $100k paper balance); still ≈5% of the larger personal sheet conceptually. Advanced structures OK (see options/SETUP.md).
3. Max **8** open positions per account.
4. Diversify; conviction OK when economics + sentiment are real (up to ~3/8 one theme OK).
5. Staggered sessions — do not clone another bot’s trades from an earlier skim.
6. Paper only. Never live without explicit user OK.

## Hard fences
- Never trade another bot’s workspace/DB.
- Futures paper is shared infrastructure but **only Futures Desk** may trade it.
- Options DB only Options Desk.
- Spot workspaces stay isolated (`scout` / `tape` / `invariants`).

## R-multiple (cross-desk score)
- See `R_REPORTING.md (desk-ops canon; box: /workspace/paper-trades/R_REPORTING.md)`.
- Every open must set **Stop** and fill **Risk $** = abs(Entry−Stop)×Qty×mult (options mult=100).
- On close: **R** = P&L $ ÷ Risk $. Compare desks by avg/sum R, not raw $.
- Book checks quote both $ and R when Risk $ is present.

## Stops (class-based)
See `STOP_POLICY.md (desk-ops canon; box: /workspace/paper-trades/STOP_POLICY.md)` — equity/crypto futures ~3–6% mechanical; commodity futures ~12–20% catastrophe + thesis re-judge; options mechanical with ~10–20% leeway (discretion). Bands are defaults.
