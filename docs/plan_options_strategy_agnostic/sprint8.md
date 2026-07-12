# Sprint 8 — Strategy Expansion and Live-Readiness Review

## Goal

Prove the architecture supports additional multi-leg strategies and decide—using explicit evidence—whether any live execution path should be enabled.

## Dependencies

- Sprint 7 paper lifecycle is stable.
- Reference strategy backtests and MCP plans remain reproducible.

## Parallel Work Groups

### Group A — Collar strategy (`X1-A`)

- Stock, protective put, and short-call leg relationships.
- Covered-share and cashflow accounting.
- Dividend and early-call-assignment cases.
- Capped-upside and protected-downside plan presentation.

### Group B — Vertical spread strategy (`X1-B`)

- Defined-risk call/put verticals.
- Multi-leg quote, fill, partial-fill, and atomicity policy.
- Maximum-loss invariant tests.
- Broker complex-order capability gates.

### Group C — Live-readiness hardening (`L1`)

- Threat model, credential boundaries, licensing review, and operational runbook.
- Kill switch, daily loss, exposure, freshness, idempotency, and confirmation tests.
- Failure injection for provider, pricing, broker, network, and reconciliation errors.
- Paper-versus-live adapter parity review.
- Written go/no-go recommendation; live remains disabled unless separately approved.

## Integration Order

1. Add collar and vertical plug-ins without modifying core evaluation contracts.
2. Run them through research, MCP plan, and paper execution paths.
3. Conduct Group C review using evidence from all supported strategies.

## Exit Criteria

- Collar and vertical strategies require no forked data or forecasting pipelines.
- Defined-risk maximum-loss invariants pass.
- Multi-leg partial-fill behavior is explicit and tested.
- A live-readiness report identifies residual technical, operational, and licensing risks.
- Enabling live mode requires a separate explicit decision and configuration change.

## Final Deliverable

TradeMCP can ingest point-in-time option data, produce reusable forecasts, simulate supported option lifecycles, compare versioned strategies under explicit objectives and account constraints, expose explainable plans through MCP, and reconcile approved paper orders without hardcoding one strategy.
