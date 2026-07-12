# Sprint 3 — Lifecycle Simulation, Forecasts, and Capital

**Status:** Complete — 2026-07-12

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
## Completion Record

Implemented:

- Executable-side, midpoint, and marketable-limit fill policies with immutable cashflow and lifecycle records.
- Short-put close, worthless expiration, physical assignment, early-assignment hook, and covered-call expiration flows.
- Strategy-neutral historical, EWMA, optional-GARCH, gap, excursion, touch, and finish-probability forecasts with expanding calibration.
- Conservative cash-secured, covered-share, debit, and defined-risk capital requirements; opportunity cost; concentration gates; and signed Greek aggregation.
- Cross-lane decision context proving forecast, capital, and lifecycle services agree on timestamps and canonical units.

Integration decisions:

- Daily-bar models accept trading-day horizons only; calendar/expiration horizons require an explicit exchange-calendar conversion.
- Gap forecasts require one explicit overnight interval in Version 1.
- Locked quotes remain executable when other safety checks pass; stale, crossed, indicative, and unsafe zero-bid entries fail closed.
- Account and broker-capability inputs have explicit freshness limits.
- Covered-call maximum loss uses the marked value of committed shares less premium instead of reporting zero risk.

Verified:

- Python and Django: 108 tests passed.
- Ruff: all Sprint 3 files passed.
- Scoped mypy: 19 forecast/simulation/portfolio modules passed.
- Base Rust engine: 2 tests passed.
- Subtree Rust prototype: 31 tests passed; 8 existing compiler warnings remain.
