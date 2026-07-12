# Sprint 4 — Strategy Plug-ins, Candidate Filters, and Objectives

## Goal

Make strategy behavior configurable and versioned so new options strategies can use the same data, forecasts, simulation, and capital services.

## Dependencies

- Sprint 3 lifecycle, forecast, and capital contracts.

## Parallel Work Groups

### Group A — Strategy plug-in framework (`D2-A`)

- Implement `OptionStrategy` protocol and registry.
- Validate strategy parameter schemas and versions.
- Define data and forecast requirements.
- Define entry, exit, roll, sizing, and capital policies.
- Add deterministic plug-in discovery tests.

### Group B — Candidate generation and eligibility (`D2-B`)

- Enumerate expiration and strike candidates from a chain snapshot.
- Apply quote freshness, spread, volume, open-interest, event, account, and broker gates.
- Persist machine-readable rejection reasons.
- Guarantee deterministic results for a fixed snapshot and strategy version.

### Group C — Objective and stress framework (`D2-C`)

- Implement expected PnL, return on collateral, tail-adjusted return, and opportunity-cost-aware objectives.
- Implement spot × IV × time × liquidity stress grids.
- Require explicit objective weights.
- Separate estimated distributions from realized backtest outcomes.

## Integration Order

1. Freeze the `CandidatePosition` interface across Groups A and B.
2. Group C scores saved candidate/simulation fixtures.
3. Integrate the full chain: plug-in → candidates → simulation → objective score.

## Exit Criteria

- A synthetic strategy can be added without changing core data or simulation services.
- Every rejected candidate has a stable reason code.
- Every score decomposes into return, tail, capital, liquidity, and concentration components.
- Stress results reproduce from the same run metadata.

## Handoff

- The generic framework unblocks reference strategies without adding strategy-specific branches to the pipeline.
