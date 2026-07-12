# Sprint 7 — Broker-Aware Paper Execution

## Goal

Connect approved plans to a paper account while preserving quote revalidation, broker capabilities, idempotency, auditability, and PnL reconciliation.

## Dependencies

- Sprint 6 MCP plan and intent contracts.
- Existing execution-control and broker-router safety services.

## Parallel Work Groups

### Group A — Option broker capability contract (`B1-A`)

- Chain, account, positions, orders, fills, and buying-power capabilities.
- Single-leg option order representation first.
- Capability rejection for unsupported legs, order types, and approval levels.
- Saved fixture and paper adapters.

### Group B — Paper order lifecycle (`B1-B`)

- Revalidate quote, account, buying power, positions, open orders, and portfolio risk immediately before submission.
- Require idempotency keys.
- Handle submit, acknowledge, partial fill, fill, cancel, reject, and expire states.
- Reconcile assignment and resulting underlying positions.

### Group C — Reconciliation, PnL, and audit (`B1-C`)

- Reconcile plan price, broker acknowledgment, actual fills, fees, positions, and PnL.
- Persist append-only lifecycle events.
- Explain plan-versus-fill and simulated-versus-realized differences.
- Add restart and duplicate-submit tests.

## Integration Order

1. Group A publishes capability and order schemas.
2. Group B implements only the paper adapter.
3. Group C validates the complete lifecycle under retries and restarts.
4. Expose paper submission through existing review controls.

## Exit Criteria

- Paper orders cannot bypass review, freshness, risk, or idempotency gates.
- Repeated requests do not create duplicate orders.
- Fills, positions, assignment, and PnL reconcile.
- Unsupported broker behavior fails closed with actionable reasons.
- Live mode remains disabled by configuration and tests.

## Handoff

- Stable paper execution provides evidence for or against adding live support.
