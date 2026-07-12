# Sprint 5 — Reference Strategies and Walk-Forward Experiment

## Goal

Answer the first real research question: under the same account and objective assumptions, how does a Friday-to-Monday cash-secured short put compare with a 30-45 DTE cash-secured put?

## Dependencies

- Sprint 4 generic strategy and objective framework.
- Calibrated Sprint 3 forecasts.

## Parallel Work Groups

### Group A — Weekend short-put plug-in (`D3-A`)

- Friday entry-window and next-listed-expiration rules.
- Configurable delta, spread, open-interest, and event filters.
- Hold-to-expiration Version 1 exit policy.
- Weekend gap, touch, finish, IV, liquidity, and assignment inputs.
- Explicitly treat weekend decay as embedded in the Friday premium.

### Group B — 30-45 DTE cash-secured-put plug-in (`D3-B`)

- DTE and delta filters.
- 50% profit target and 21 DTE close defaults.
- Earnings/event exclusion policy.
- Volatility-risk-premium, skew, drawdown, touch, and assignment inputs.

### Group C — Walk-forward options evaluation (`E1`)

- Simulate both strategies using the same point-in-time folds.
- Report pessimistic bid/ask results as primary and midpoint as sensitivity.
- Add naive baselines, confidence intervals, regime concentration, and effective sample size.
- Produce attribution by premium, underlying move, IV change, fees, slippage, and capital cost.

## Integration Order

1. Groups A and B publish versioned strategy fixtures.
2. Group C runs both through the identical evaluation engine.
3. Review discrepancies in data eligibility and capital treatment before comparing scores.

## Exit Criteria

- Both strategies run without strategy-specific changes to the evaluator.
- The report compares returns, tail risk, assignment, capital use, and fill sensitivity.
- Results are reproducible from data, model, strategy, objective, config, and code versions.
- The platform can return “insufficient evidence” rather than forcing a winner.

## Handoff

- Validated comparison outputs unblock MCP planning and human-readable trade plans.
