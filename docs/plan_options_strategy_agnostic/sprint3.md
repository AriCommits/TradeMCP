# Sprint 3 — Lifecycle Simulation, Forecasts, and Capital

## Goal

Produce realistic single-leg option cashflows, reusable horizon forecasts, and explicit capital requirements as independent services.

## Dependencies

- Sprint 2 chain snapshots and pricing baseline.
- Sprint 1 leakage-safe walk-forward utilities.

## Parallel Work Groups

### Group A — Fill and lifecycle engine (`S1`)

- Implement bid/ask, midpoint, and configurable limit fill policies.
- Implement fees, multipliers, expiration, settlement, exercise, and assignment.
- Add early-assignment hooks for dividends.
- Record lifecycle events and reconcile every cashflow.
- Support cash-secured short puts first; add covered calls only after put accounting passes.

### Group B — Horizon-indexed forecasts (`Q2`)

- Implement forecast registry and distribution output contract.
- Add historical, EWMA, GARCH, and simple statistical baselines.
- Forecast realized volatility, weekend/overnight gaps, excursions, touch probability, and finish probability.
- Add calibration reports, naive comparisons, and fold-local transformations.
- Keep strategy returns out of this layer.

### Group C — Capital and portfolio constraints (`C1`)

- Calculate cash collateral, covered-share requirements, estimated buying-power reduction, and capital opportunity cost.
- Apply account type, approval level, broker capability, and concentration gates.
- Aggregate delta, gamma, vega, theta, expiration, symbol, and sector exposure.
- Label broker-independent margin calculations as estimates.

## Integration Order

1. Integrate Groups A and C using deterministic payoff fixtures.
2. Join Group B forecasts by decision timestamp and horizon, not by future outcome timestamp.
3. Produce a strategy-neutral `SimulationContext` fixture for Sprint 4.

## Exit Criteria

- Single-leg short-put cashflows reconcile across entry, close, expiration, and assignment.
- Pessimistic and midpoint fill results are both reported.
- Forecast calibration and baseline comparisons are persisted.
- Capital requirements reconcile with deterministic cash-account fixtures.
- Missing account, quote, event, or carry inputs fail closed.

## Handoff

- `SimulationContext`, `ForecastBundle`, and `CapitalRequirement` unblock the strategy framework.
