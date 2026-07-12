# Sprint 6 — MCP Trade Planning and Reproducible Reporting

## Goal

Expose the research system through typed MCP tools that can screen, compare, stress, explain, and prepare—but not silently submit—option orders.

## Dependencies

- Sprint 5 reference strategies and evaluation artifacts.

## Parallel Work Groups

### Group A — Market and research MCP tools (`M1-A`)

- `get_options_chain`
- `get_market_state`
- `validate_research_data`
- `list_option_strategies`
- `validate_strategy_spec`
- `run_options_walkforward`
- `backtest_option_strategy`

### Group B — Decision and plan MCP tools (`M1-B`)

- `screen_option_candidates`
- `compare_option_strategies`
- `stress_option_candidate`
- `build_option_trade_plan`
- `review_option_trade_plan`
- `create_option_order_intent`

All mutation-capable tools default to dry-run. Order-intent creation is broker-neutral and does not submit.

### Group C — Reports and observability (`O1`)

- Generate matching JSON and Markdown trade plans.
- Include selected and rejected alternatives.
- Include quote timestamps, spreads, capital, payoff, forecasts, calibration, stresses, and limitations.
- Persist data quality, feature manifest, run metadata, errors, and correlation IDs.
- Add report schema and snapshot tests.

## Integration Order

1. Register read-only Group A tools.
2. Add Group B tools against saved/paper contexts.
3. Attach Group C artifacts to every long-running research or planning response.
4. Run a complete MCP-client acceptance flow.

## Exit Criteria

- An MCP client can reproduce the weekend-versus-longer-DTE comparison without direct filesystem access.
- Tool schemas reject ambiguous timestamps, units, objectives, and account assumptions.
- A trade plan clearly distinguishes observations, estimates, simulations, and broker state.
- No tool submits a live order in this sprint.
- Identical inputs and versions reproduce identical candidate generation and plan content.

## Handoff

- Reviewed trade plans and broker-neutral intents unblock paper broker integration.
