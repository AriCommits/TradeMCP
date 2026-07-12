# TradeMCP Strategy-Agnostic Options Planning

## Technical Specification Outline

**Status:** Draft outline
**Primary implementation language:** Python
**Optional performance layer:** Existing Rust execution engine
**Primary purpose:** Research, compare, and prepare options trades across multiple strategies and horizons
**Initial reference strategies:** Weekend short options and 30-45 DTE cash-secured puts
**Non-goals:** High-frequency trading, autonomous portfolio management, sub-millisecond execution, or claims of guaranteed return

**Delivery plan:** [docs/plan_options_strategy_agnostic/overview.md](../plan_options_strategy_agnostic/overview.md)

---

## 1. Executive Summary

TradeMCP should evolve from an equity-return forecasting pipeline into a strategy-agnostic options research and trade-planning server. The server should not permanently answer one question such as "Will this trade make money?" Instead, it should:

1. capture the observable market and account state;
2. estimate reusable, horizon-specific market outcomes;
3. let strategy plug-ins generate candidate option positions;
4. simulate each candidate with realistic option lifecycle and execution rules;
5. score candidates using an explicit user-selected objective;
6. produce an explainable trade plan and order intent for human review; and
7. reuse the existing execution safety controls if the user chooses to submit it.

The central architecture is:

```text
Market and account data
        |
        v
Point-in-time market state and features
        |
        v
Horizon-indexed forecasts
        |
        v
Strategy plug-in -> candidate positions
        |
        v
Lifecycle and execution simulation
        |
        v
Objective scoring and portfolio constraints
        |
        v
MCP trade plan -> review -> order intent -> optional confirmed submission
```

Python remains the correct primary language because this platform targets research, chain screening, minute-to-daily data, and human-reviewed execution. The existing Rust backend should remain a narrow execution and performance boundary until profiling identifies a real Python bottleneck.

---

## 2. Problem Statement

### 2.1 User questions the platform must support

- Is the premium on this option sufficient for its forecast risk?
- Should I sell a Friday option expiring Monday or use a longer-duration option?
- Which strike and expiration best match my willingness to own or sell the underlying?
- How much cash or buying power will the trade reserve?
- What are the maximum loss, breakeven, expected return, tail risk, assignment risk, and opportunity cost?
- How did the same fully specified rule perform in prior point-in-time data?
- How sensitive is the recommendation to fills, volatility, gaps, dividends, and early assignment?
- Can the same platform evaluate a cash-secured put, covered call, collar, vertical spread, or later strategy without replacing its core pipeline?

### 2.2 Current repository capabilities to retain

- `TradingMCPWorkflow` as the MCP-facing orchestration boundary.
- `StrategyRegistry` as the starting point for strategy discovery.
- Walk-forward evaluation and model abstraction in `forecasting.py`.
- EWMA/GARCH volatility components in `volatility.py`.
- Risk, review, PnL, execution controls, broker routing, and audit concepts.
- Parquet support and artifact/run metadata generation.
- Rust execution filtering as an optional downstream safety/performance service.

### 2.3 Additional capabilities in the `Agent_00Quant/TradeMCP` subtree snapshot

The subtree snapshot at `C:\Users\arian\Github\Agent_00Quant\TradeMCP` contains three Rust modules that are not present in the base TradeMCP workspace:

- `backend/rust_exec_engine/src/options.rs`
  - Black-Scholes price and delta, gamma, theta, vega, and rho.
  - European and American binomial-tree pricing.
  - Tests for standard prices, put-call parity, boundary cases, American put value, and binomial convergence.
- `backend/rust_exec_engine/src/backtest.rs`
  - Bar-based long/short equity simulation.
  - Commission and slippage assumptions.
  - Equity curve, Sharpe ratio, drawdown, win rate, and profit factor.
- `backend/rust_exec_engine/src/indicators.rs`
  - SMA, EMA, RSI, ATR, OBV, MACD, Bollinger Bands, stochastic oscillator, ADX, and VWAP.

The snapshot's Rust test suite passes 31 tests. These modules should be treated as tested numerical prototypes, not completed server features, because they are only declared by `main.rs`; the process still accepts and returns only the existing execution-shortfall JSON protocol. The option pricer has no IV solver, discrete-dividend model, quote integration, serialization API, or Python/MCP bridge. It also clamps time to expiry to at least one day, so it cannot yet represent sub-day or expiration-day pricing accurately. The backtester is an underlying bar simulator and does not implement option contracts or lifecycle events.

Recommended integration treatment:

- Port or subtree-merge `options.rs` into the base workspace after review, then wrap it behind a versioned pricing interface.
- Use its Black-Scholes implementation as a cross-language analytical baseline.
- Use the binomial tree as the starting American-option numerical method, with convergence, performance, dividend, and edge-case hardening.
- Keep the Python implementation as the canonical research path initially and require Python/Rust parity fixtures.
- Retain the equity backtester as a possible fast underlying-path kernel, but do not extend it directly into a monolithic options backtester.
- Treat Rust indicators as optional feature kernels; do not make canned indicators mandatory inputs to options strategies.
- Preserve the base workspace's executable path safety validation in `execution_client.py`; the subtree snapshot removes that guard and must not overwrite it wholesale.

### 2.4 Current gaps to close

- No normalized option contract, quote, chain snapshot, rate, dividend, event, or account buying-power schemas.
- Current target is next-period underlying return rather than reusable market outcomes.
- Preprocessing uses future-aware interpolation and full-sample scaling.
- Current strategy ranking is heuristic and not based on simulated option payoffs.
- The Python Greeks service is a mock surface and cannot support pricing decisions; the subtree's tested Rust pricer is not yet exposed to Python or MCP.
- No option lifecycle engine for expiration, exercise, assignment, early exercise, or multi-leg positions.
- No point-in-time options backtester with executable bid/ask assumptions.
- Existing order types do not fully describe option legs or complex orders.
- The workflow class exists, but the repository lacks a complete MCP server registration/transport layer for the trading workflow.

---

## 3. Design Principles

1. **Forecast market behavior, simulate strategy behavior.** Models estimate reusable outcomes; strategies define trades and payoffs.
2. **Point-in-time correctness is mandatory.** Every feature, chain, event, and model fit must contain only information available at the decision timestamp.
3. **Strategy rules are data.** Entry, exit, roll, sizing, and objective parameters must be versioned and reproducible.
4. **Execution is separate from analysis.** A displayed quote, modeled value, simulated fill, broker order intent, and actual fill are distinct objects.
5. **Raw and derived data remain distinguishable.** Preserve provenance, vendor, timestamp, entitlement, and model version.
6. **No scalar recommendation without decomposition.** Return score, risk, uncertainty, assumptions, and rejection reasons together.
7. **Fail closed for stale or incomplete data.** The server must not silently invent missing quotes, rates, dividends, or account state.
8. **Human review is the default.** Research tools may prepare an order intent; live submission retains the existing confirmation and risk gates.
9. **Baselines precede complex models.** Historical volatility, EWMA, GARCH, and simple statistical/boosted models must be benchmarks for later neural models.
10. **Research and production paths share contracts, not mutable state.** Backtests and live planning use the same strategy and payoff interfaces with different data providers.

---

## 4. Scope

### 4.1 Version 1 scope

- U.S. listed equity and ETF options.
- Single-leg short puts and calls.
- Cash-secured puts and covered calls.
- Protective puts and collars.
- Defined-risk vertical spreads after single-leg accounting is validated.
- Friday-to-Monday/weekend comparison.
- 30-45 DTE underwriting comparison.
- Historical research and paper-trade order preparation.
- Delayed or snapshot data support first; real-time support through entitled providers later.

### 4.2 Deferred scope

- Portfolio margin replication.
- Full broker-specific margin parity.
- Pin-risk automation.
- Intraday delta hedging.
- Volatility surface arbitrage execution.
- Full exchange-level tick replay.
- Futures options, index settlement edge cases, FLEX options, and OTC derivatives.
- Autonomous live order submission or automatic rolling.

---

## 5. Target Package Architecture

```text
src/trading/
  mcp/
    server.py
    tools_market.py
    tools_research.py
    tools_strategy.py
    tools_trade_plan.py
    schemas.py

  data/
    providers/
      base.py
      csv_parquet.py
      vendor_adapter.py
      broker_market_data.py
    catalog.py
    point_in_time.py
    quality.py

  options/
    contracts.py
    quotes.py
    symbology.py
    calendars.py
    pricing.py
    iv_solver.py
    greeks.py
    surface.py
    corporate_actions.py

  features/
    underlying.py
    realized_volatility.py
    implied_volatility.py
    skew_term_structure.py
    liquidity.py
    gaps.py
    events.py

  forecasts/
    base.py
    registry.py
    targets.py
    distribution.py
    realized_volatility.py
    iv_change.py
    liquidity.py
    calibration.py

  strategies/
    base.py
    registry.py
    specifications.py
    weekend_short_option.py
    cash_secured_put.py
    covered_call.py
    collar.py
    vertical_spread.py

  simulation/
    fills.py
    lifecycle.py
    exercise.py
    assignment.py
    dividends.py
    margin.py
    portfolio.py
    engine.py

  objectives/
    base.py
    expected_pnl.py
    return_on_capital.py
    expected_utility.py
    tail_adjusted_return.py

  evaluation/
    walk_forward.py
    backtest.py
    attribution.py
    stress.py
    reports.py
```

Existing modules should be migrated incrementally. Do not move files solely to match this tree before interfaces and tests exist.

---

## 6. Domain Model and Storage Schemas

### 6.1 Required identifiers

All records should include enough identity and provenance to reproduce a decision:

- `as_of_utc`
- `source`
- `source_record_id` where available
- `ingested_at_utc`
- `data_version`
- `quality_flags`
- `run_id` for derived records
- `model_id` and `model_version` for forecasts
- `strategy_id` and `strategy_version` for candidates

### 6.2 Core tables

#### `underlying_bars`

```text
timestamp_utc, symbol, interval, open, high, low, close, volume,
trade_session, adjusted, source, ingested_at_utc, quality_flags
```

#### `option_contracts`

```text
option_id, occ_symbol, underlying, option_type, strike, expiration_date,
exercise_style, settlement_type, multiplier, deliverable, listing_exchange,
first_seen_utc, last_seen_utc
```

#### `option_quotes`

```text
timestamp_utc, option_id, bid, ask, bid_size, ask_size, last,
last_size, quote_condition, underlying_price, source, quality_flags
```

#### `option_daily_state`

```text
session_date, option_id, volume, open_interest, settlement_price,
source, published_at_utc
```

#### `rates_and_carry`

```text
as_of_utc, currency, tenor_days, risk_free_rate, borrow_rate,
forward_price, source
```

#### `dividends_and_events`

```text
event_id, symbol, event_type, announced_at_utc, effective_at_utc,
expected_value, actual_value, source, confidence
```

#### `account_snapshots`

```text
timestamp_utc, adapter, account_id_hash, cash, net_liquidation,
buying_power, option_buying_power, margin_type, option_level,
positions_json, open_orders_json
```

#### `forecast_values`

```text
decision_timestamp_utc, symbol, target_name, horizon_kind, horizon_value,
point_estimate, quantiles_json, probability_json, model_id, model_version,
training_cutoff_utc, calibration_metrics_json
```

#### `strategy_candidates`

```text
candidate_id, decision_timestamp_utc, strategy_id, strategy_version,
underlying, legs_json, entry_rules_json, exit_rules_json, capital_required,
market_snapshot_id, forecast_bundle_id, eligibility_flags
```

#### `simulation_results`

```text
simulation_id, candidate_id, scenario_id, entry_fill, exit_fill,
gross_pnl, net_pnl, capital_required, return_on_capital,
max_adverse_excursion, max_favorable_excursion, assigned, exercised,
rolled, fees, slippage, lifecycle_events_json
```

#### `trade_plans`

```text
trade_plan_id, created_at_utc, candidate_id, objective_id, score,
rank, rationale_json, assumptions_json, risk_summary_json,
stress_results_json, data_freshness_json, status
```

### 6.3 Storage design

- Use partitioned Parquet for append-heavy historical market data.
- Use DuckDB initially for analytical queries across Parquet.
- Retain SQLite for lightweight operational metadata only if concurrency is not required.
- Introduce PostgreSQL only when concurrent clients, durable job state, or remote deployment requires it.
- Never use JSON or CSV as the canonical large historical quote store.
- Partition option quotes by `underlying/session_date` initially; benchmark before adding expiration partitions.

---

## 7. Market Data Provider Contract

```python
class OptionsMarketDataProvider(Protocol):
    def get_chain_snapshot(
        self,
        underlying: str,
        as_of_utc: datetime,
        expiration_range: DateRange | None = None,
    ) -> OptionChainSnapshot: ...

    def get_option_quotes(
        self,
        option_ids: Sequence[str],
        start_utc: datetime,
        end_utc: datetime,
        interval: str,
    ) -> Iterable[OptionQuote]: ...

    def get_underlying_bars(...): ...
    def get_rates(...): ...
    def get_dividends(...): ...
    def get_events(...): ...
```

Provider requirements:

- capability metadata for history depth, latency, interval, Greeks availability, and entitlement;
- explicit timestamp semantics and exchange calendar;
- pagination, retry, and rate-limit behavior;
- raw payload retention policy and normalized record validation;
- no silent fallback from real-time to delayed data;
- provider-derived Greeks are stored separately from internally computed Greeks;
- licensing metadata distinguishes internal research, non-display use, derived outputs, and redistribution limits.

---

## 8. Point-in-Time Data and Leakage Controls

The following controls are release blockers for trustworthy research:

- Replace bidirectional interpolation in `data_ingestion.py`.
- Do not interpolate option quotes across missing intervals or market closures.
- Fit scalers and imputers inside each walk-forward training fold only.
- Preserve `published_at_utc` separately from an event's effective date.
- Use historical constituent membership when universe selection depends on an index.
- Use only open interest published by the decision timestamp.
- Apply corporate actions using point-in-time contract deliverables.
- Record quote staleness, locked/crossed markets, zero bids, and missing sides.
- Deduplicate by provider sequence or deterministic precedence rules.
- Make calendar days, trading days, sessions, and overnight intervals explicit types.
- Require `training_cutoff_utc < decision_timestamp_utc` for every forecast.

Required tests:

- future rows cannot change an earlier feature row;
- a later event revision cannot appear in an earlier training fold;
- scaling statistics equal training-fold statistics only;
- Friday-to-Monday labels use the configured market-close/open/expiration timestamps;
- stale, crossed, or incomplete quotes are rejected or flagged deterministically.

---

## 9. Pricing, Implied Volatility, and Greeks

### 9.1 Role of the pricing layer

The market quote remains the observed executable reference. The pricing layer should:

- solve implied volatility from bid, ask, midpoint, or configured mark;
- compute consistent Greeks from the internally selected model;
- produce theoretical value ranges for analysis and stress testing;
- construct an arbitrage-checked implied volatility surface;
- expose confidence, input timestamp, and model version;
- never replace a missing executable quote with theoretical value without an explicit simulation policy.

### 9.2 Initial models

- Black-Scholes-Merton for European-style analytical baselines. Review and reuse the subtree's tested Rust implementation where it satisfies the canonical interface.
- A documented American-option approximation or numerical tree for equity options. The subtree's binomial tree is the starting prototype, not yet the final production implementation.
- Discrete dividend handling for early exercise and assignment analysis.
- Robust IV solver with bounds, convergence status, and no-solution diagnostics.

### 9.3 Surface outputs

```text
underlying, as_of_utc, expiration, forward, log_moneyness,
observed_iv_bid, observed_iv_ask, fitted_iv, fit_error,
arbitrage_flags, model_id, model_version
```

The current mocked `greeks_viz` calculator must be clearly labeled as non-quantitative until it is replaced by this service.

### 9.4 Python/Rust boundary

The first release should keep orchestration, schemas, data access, model training, strategy logic, and reporting in Python. Rust pricing should be introduced only through a narrow versioned interface, such as a subprocess JSON protocol, PyO3 extension, or service boundary selected after benchmarking.

Required Rust pricing request fields:

```text
request_id, model, spot, strike, valuation_timestamp_utc,
expiration_timestamp_utc, rate, dividend_inputs, volatility,
option_type, exercise_style, numerical_settings
```

Required response fields:

```text
request_id, price, delta, gamma, theta, vega, rho,
converged, warnings, model_id, model_version, runtime_micros
```

Acceptance requirements:

- exact units and theta convention are documented;
- no silent clamping of invalid inputs without a returned warning;
- American pricing supports the chosen dividend representation;
- Rust and Python reference outputs agree within declared tolerances;
- failure is explicit and cannot silently fall back to a materially different model;
- batch pricing is supported before the Rust path is used for full chains.

---

## 10. Strategy-Neutral Forecast Layer

### 10.1 Forecast contract

```python
class ForecastModel(Protocol):
    target_name: str

    def fit(self, training_set: PointInTimeDataset) -> FittedForecast: ...

    def predict(
        self,
        market_state: MarketState,
        horizon: ForecastHorizon,
    ) -> ForecastDistribution: ...
```

`ForecastDistribution` should provide a point estimate, calibrated quantiles or probabilities, model identity, training cutoff, and calibration statistics.

### 10.2 Initial reusable targets

- future underlying return distribution;
- realized volatility over 1, 3, 5, 20, and 45 trading days;
- close-to-open and weekend gap distribution;
- maximum upward and downward excursion;
- probability of touching a price or strike;
- probability of finishing above/below a price or strike;
- expected implied-volatility change;
- expected skew and term-structure change;
- expected bid/ask spread and liquidity degradation.

### 10.3 Baseline model sequence

1. unconditional and rolling historical distributions;
2. historical volatility;
3. EWMA;
4. GARCH-family baseline;
5. regularized linear or generalized linear model;
6. gradient-boosted trees;
7. neural sequence models only after baselines and dataset size justify them.

### 10.4 Required evaluation

- Walk-forward only.
- Regression: MAE/RMSE plus calibration by horizon and regime.
- Quantiles: pinball loss and empirical coverage.
- Probabilities: Brier score, log loss, and reliability curves.
- Distributions: proper scoring rule such as CRPS where practical.
- Compare against naive baselines and include confidence intervals.

---

## 11. Strategy Plug-In Contract

```python
class OptionStrategy(Protocol):
    strategy_id: str
    version: str

    def validate_parameters(self, params: Mapping[str, object]) -> ValidationReport: ...
    def required_data(self, params: Mapping[str, object]) -> DataRequirements: ...
    def required_forecasts(self, params: Mapping[str, object]) -> ForecastRequirements: ...
    def generate_candidates(self, context: StrategyContext) -> list[CandidatePosition]: ...
    def entry_policy(self, candidate: CandidatePosition) -> EntryPolicy: ...
    def exit_policy(self, candidate: CandidatePosition) -> ExitPolicy: ...
    def capital_policy(self, candidate: CandidatePosition, account: AccountState) -> CapitalRequirement: ...
```

### 11.1 Strategy specification fields

- stable ID and semantic version;
- human-readable description;
- eligible underlyings;
- option type, side, and leg relationships;
- expiration selection rule;
- strike/delta/moneyness selection rule;
- entry time and quote freshness rule;
- limit-price or fill policy;
- exit, profit-target, stop, and roll rules;
- assignment and exercise handling;
- sizing and concentration constraints;
- account capability requirements;
- required forecasts and features;
- allowed objectives;
- known unsupported lifecycle cases.

### 11.2 Reference strategy: weekend short put

Example parameterization:

```yaml
strategy_id: weekend_short_put
entry_window: friday_15_30_to_15_50_et
expiration_rule: next_listed_expiration
option_type: put
short_delta_range: [0.10, 0.25]
collateral: cash_secured
exit_rule: hold_to_expiration
exclude_events: [earnings]
min_open_interest: 500
max_relative_spread: 0.10
```

Primary forecasts:

- Friday close-to-Monday open gap distribution;
- weekend and Monday realized volatility;
- probability of touch and expiration ITM;
- expected IV repricing;
- downside tail quantiles;
- entry and exit liquidity.

The strategy must treat weekend decay as already reflected in Friday's market premium. Its decision criterion is whether retained premium compensates for gap, tail, liquidity, assignment, and capital risks.

### 11.3 Reference strategy: 30-45 DTE cash-secured put

Example parameterization:

```yaml
strategy_id: cash_secured_put_30_45_dte
dte_range: [30, 45]
short_delta_range: [0.15, 0.30]
collateral: cash_secured
profit_target_pct: 0.50
close_at_dte: 21
earnings_policy: exclude_before_expiration
min_open_interest: 500
max_relative_spread: 0.10
```

Primary forecasts:

- 20-45 day realized volatility distribution;
- IV minus forecast realized volatility;
- probability of touch and expiration ITM;
- maximum downside excursion;
- skew richness;
- event exposure;
- expected holding period and capital usage.

---

## 12. Candidate Generation and Eligibility

Candidate generation should be deterministic for a given market snapshot and strategy version.

Required gates:

- valid contract and non-expired quote;
- bid and ask present and non-crossed;
- quote age under strategy threshold;
- minimum open interest and/or volume;
- maximum absolute and relative spread;
- allowed expiration and strike range;
- known multiplier and deliverable;
- required rates, dividends, events, and account state present;
- sufficient cash, shares, or buying power;
- broker supports the order type and number of legs;
- portfolio concentration and risk limits pass.

Every rejected candidate should retain machine-readable rejection reasons.

---

## 13. Simulation and Option Lifecycle Engine

### 13.1 Simulation inputs

- point-in-time chain and underlying path;
- strategy version and parameters;
- forecast bundle where used for ranking;
- fill policy;
- fees and slippage model;
- account and margin policy;
- event calendar and corporate actions;
- exit and roll policy.

### 13.2 Fill models

At minimum support:

- pessimistic executable side: sell at bid, buy at ask;
- midpoint with configurable probability/slippage;
- limit-order model using subsequent quote path;
- configurable commissions, contract fees, and regulatory fees;
- no fills outside quoted size without a documented market-impact rule.

Backtest reports must show results under at least pessimistic-side and midpoint assumptions.

### 13.3 Lifecycle events

- entry, partial fill, cancel, and replace;
- mark-to-market snapshots;
- profit target, stop, timed close, or roll;
- expiration and settlement;
- assignment and exercise;
- early assignment risk around dividends;
- stock delivery/acquisition and resulting position;
- multi-leg partial-fill policy;
- insufficient buying power or risk-gate rejection.

### 13.4 Result metrics per candidate

- gross and net PnL;
- return on cash collateral and broker buying power;
- maximum loss and breakeven;
- maximum adverse/favorable excursion;
- probability of profit, touch, and assignment;
- expected shortfall and selected downside quantiles;
- time in trade;
- fees, slippage, and opportunity cost;
- stress losses under specified spot/IV/time scenarios.

---

## 14. Objective and Ranking Layer

The system must not hardcode "highest premium" or "highest probability of profit" as the definition of a good trade.

```python
class TradeObjective(Protocol):
    objective_id: str

    def score(
        self,
        candidate: CandidatePosition,
        forecast: ForecastBundle,
        simulation: SimulationSummary,
        account: AccountState,
    ) -> ObjectiveScore: ...
```

Initial objectives:

- expected net PnL;
- expected return on cash collateral;
- expected return on buying power;
- expected log growth;
- expected return minus tail-risk penalty;
- return per unit of expected shortfall;
- assignment-adjusted utility;
- benchmark-relative expected return after capital opportunity cost.

Example utility:

```text
score = expected_net_return
        - lambda_tail * expected_shortfall
        - lambda_capital * capital_opportunity_cost
        - lambda_liquidity * expected_execution_cost
        - lambda_concentration * incremental_concentration_risk
```

All penalty weights must be explicit in the trade plan.

---

## 15. MCP Tool Surface

The MCP API should expose small, typed operations rather than one unconstrained "recommend a trade" tool.

### 15.1 Market and data tools

#### `get_options_chain`

Returns a normalized, filtered chain snapshot with freshness and quality flags.

#### `get_market_state`

Returns underlying, volatility, skew, term structure, events, liquidity, and forecast summaries as of a timestamp.

#### `validate_research_data`

Reports coverage, missing fields, stale quotes, leakage checks, and provider limitations.

### 15.2 Strategy tools

#### `list_option_strategies`

Returns strategy IDs, versions, required inputs, supported account types, and parameter schemas.

#### `validate_strategy_spec`

Validates a user-authored strategy definition without running it.

#### `screen_option_candidates`

Generates and filters candidate positions for a strategy and market snapshot.

#### `compare_option_strategies`

Compares candidates across strategies or horizons using the same objective and account constraints.

### 15.3 Research tools

#### `run_options_walkforward`

Runs point-in-time model evaluation and candidate simulation for a fixed strategy version.

#### `backtest_option_strategy`

Returns performance, tail risk, calibration, fill sensitivity, and attribution artifacts.

#### `stress_option_candidate`

Applies deterministic spot, IV, time, liquidity, dividend, and event shocks.

### 15.4 Trade-planning tools

#### `build_option_trade_plan`

Returns:

- candidate legs and proposed limit prices;
- market data timestamp and freshness;
- strategy and objective versions;
- premium, collateral, buying power, breakeven, and maximum loss;
- forecast distributions and uncertainty;
- base, adverse, and severe stress outcomes;
- assignment/exercise implications;
- benchmark/opportunity-cost comparison;
- reasons for selection and rejected alternatives;
- unsupported assumptions and data limitations.

#### `review_option_trade_plan`

Runs data, account, portfolio, execution, and policy gates and returns `GO`, `NO_GO`, or `NEEDS_INPUT` with reasons.

#### `create_option_order_intent`

Converts an approved plan into a broker-neutral complex order. It does not submit the order.

#### `submit_order_intent`

Reuse and extend the existing tool. Require explicit live mode, confirmation, idempotency key, current quote revalidation, and a final risk review.

### 15.5 Example comparison request

```json
{
  "underlying": "SPY",
  "strategies": [
    {"strategy_id": "weekend_short_put", "params": {"collateral": "cash_secured"}},
    {"strategy_id": "cash_secured_put_30_45_dte", "params": {"collateral": "cash_secured"}}
  ],
  "objective": {
    "objective_id": "tail_adjusted_return_on_collateral",
    "lambda_tail": 1.5,
    "capital_benchmark": "configured_cash_yield"
  },
  "account_adapter": "paper",
  "as_of": "latest"
}
```

---

## 16. Trade Plan Output Contract

Every trade plan should be both machine-readable and readable in Markdown.

Required sections:

1. **Decision summary**: selected, rejected, or insufficient evidence.
2. **Position**: each leg, quantity, side, strike, expiration, and proposed limit.
3. **Capital**: cash collateral, estimated buying power, portfolio exposure, and opportunity cost.
4. **Payoff**: credit/debit, maximum profit/loss, breakevens, and expiration payoff.
5. **Forecasts**: relevant distributions, not only point estimates.
6. **Risk**: tail loss, gap risk, touch/assignment probability, early exercise, event exposure, and liquidity.
7. **Stress table**: spot x IV x time scenarios.
8. **Execution**: quote timestamp, bid/ask, spread, size, fill policy, fees, and slippage.
9. **Alternatives**: closest rejected strikes, expirations, or strategies and rejection reasons.
10. **Evidence quality**: data coverage, model calibration, sample size, and limitations.
11. **Reproduction**: run, data, forecast, strategy, objective, and code versions.

The wording must distinguish observations, model estimates, simulations, and actual broker state.

---

## 17. Account, Capital, and Portfolio Constraints

The platform must model at least:

- cash account versus margin account;
- option approval level;
- contract multiplier;
- shares available for covered calls;
- cash reserved for cash-secured puts;
- estimated broker buying-power reduction;
- maximum symbol, sector, strategy, and expiration concentration;
- aggregate delta, gamma, vega, theta, and downside exposure;
- assignment effects on cash and stock exposure;
- a configurable capital benchmark such as cash or short-term Treasury yield;
- margin requirement uncertainty and possible expansion under stress.

Broker buying-power estimates should be labeled estimates unless calculated by the broker adapter itself.

---

## 18. Safety, Compliance, and Operational Controls

- Default all broker mutations to `dry_run=True`.
- Revalidate quotes, account state, buying power, position, open orders, and risk immediately before submission.
- Reject plans created from data older than a configured threshold.
- Require an idempotency key for every order intent and submit request.
- Preserve append-only audit events for plan creation, review, confirmation, submission, acknowledgment, fill, cancel, and failure.
- Keep research model credentials separate from broker execution credentials.
- Never expose raw provider data through MCP if the provider license does not permit redistribution.
- Store and return data provenance and derived-output model version.
- Present expected values as estimates, not guarantees or personalized fiduciary advice.
- Do not let an LLM invent strikes, quotes, premiums, account balances, or broker capabilities.
- On incomplete data, return `NEEDS_INPUT` or `NO_GO`, not a synthetic recommendation.

---

## 19. Configuration

Suggested additions:

```text
config/options/
  data_sources.yaml
  pricing.yaml
  quality.yaml
  simulation.yaml
  objectives.yaml
  portfolio_limits.yaml
  strategies/
    weekend_short_put.yaml
    cash_secured_put_30_45_dte.yaml
    covered_call.yaml
    collar.yaml
```

Configuration must validate at startup and include schema versions. Secrets, provider tokens, and broker credentials must remain outside committed YAML.

---

## 20. Testing Strategy

### 20.1 Unit tests

- OCC symbology and contract normalization.
- Quote validation and staleness.
- IV solver convergence and failure cases.
- Greeks against trusted numerical fixtures.
- Expiration payoff for every supported leg combination.
- Assignment, exercise, dividends, multipliers, and fees.
- Strategy parameter validation and deterministic candidate generation.
- Objective calculations and capital opportunity cost.

### 20.2 Property and invariant tests

- Call/put payoff monotonicity where applicable.
- No-arbitrage option price bounds.
- Increasing fees cannot improve net PnL.
- A worse fill cannot improve otherwise identical seller PnL.
- Defined-risk strategy loss does not exceed the calculated bound.
- Future data mutations cannot alter prior point-in-time features.

### 20.3 Integration tests

- Historical provider payload -> normalized Parquet -> chain snapshot.
- Chain snapshot -> forecasts -> candidates -> simulation -> trade plan.
- Trade plan -> review -> dry-run order intent.
- Broker adapter capability rejection for unsupported multi-leg orders.
- Restart/retry does not duplicate an order intent.

### 20.4 Golden scenario tests

- Friday SPY put expiring Monday with no assignment.
- Weekend downside gap and assignment.
- 45 DTE put closed at 50% profit.
- 45 DTE put held through a drawdown and assigned.
- Covered call called away before/at expiration.
- Collar with both expiration payoff boundaries.
- Ex-dividend early call assignment case.
- Locked, crossed, stale, and zero-bid chain cases.

### 20.5 Backtest validation

- Compare pessimistic bid/ask and midpoint fill assumptions.
- Include delisted/expired contracts present in the historical source.
- Verify open-interest publication timing.
- Report trade count, effective sample size, and regime concentration.
- Include benchmark and naive strategy comparisons.
- Use bootstrap or block-bootstrap confidence intervals where appropriate.

---

## 21. Observability and Reproducibility

Each run should persist:

- normalized input coverage summary;
- provider and entitlement metadata;
- data-quality report;
- feature manifest;
- training cutoff and fold definitions;
- model parameters and calibration results;
- strategy and objective specifications;
- simulation assumptions;
- candidate rejection funnel;
- selected trade plan;
- code commit, config hash, environment, and random seed;
- structured errors with correlation IDs.

Suggested artifact layout:

```text
artifacts/options/<run_id>/
  run_metadata.json
  data_quality.json
  feature_manifest.json
  forecast_metrics.json
  candidates.parquet
  simulations.parquet
  stress_results.parquet
  trade_plan.json
  trade_plan.md
  errors/
```

---

## 22. Implementation Phases

### Phase 0: Correctness prerequisites

Deliverables:

- remove future-aware interpolation;
- move scaling inside walk-forward folds;
- define time/horizon types;
- add point-in-time regression tests;
- label the current Greeks view as mocked/non-trading.

Exit criteria:

- future observations cannot alter an earlier prediction input;
- current equity pipeline tests still pass.

### Phase 1: Options data foundation

Deliverables:

- option contract and quote schemas;
- CSV/Parquet provider;
- chain snapshot service;
- quote-quality rules;
- partitioned Parquet and DuckDB query path;
- rates, dividends, and events interfaces.

Exit criteria:

- reproduce a saved chain at a historical timestamp;
- reject stale/crossed/incomplete records deterministically.

### Phase 2: Pricing and lifecycle correctness

Deliverables:

- port/review the subtree's Rust Black-Scholes and binomial prototypes;
- IV solver, canonical Python pricing baseline, internally computed Greeks, and Python/Rust parity fixtures;
- single-leg fill, expiration, exercise, assignment, fees, and collateral;
- golden tests for short puts and covered calls.

Exit criteria:

- trusted fixtures pass;
- subtree pricing tests remain green after integration and parity tests pass;
- simulated cashflows reconcile exactly.

### Phase 3: Strategy-neutral forecasts

Deliverables:

- forecast registry and horizon contract;
- realized-volatility, gap, excursion, and touch-probability baselines;
- fold-local transformations and calibration reports.

Exit criteria:

- all forecasts beat or clearly contextualize naive baselines;
- calibration is reported, not assumed.

### Phase 4: First strategy plug-ins

Deliverables:

- weekend short put;
- 30-45 DTE cash-secured put;
- deterministic candidate generation;
- objective and stress layers;
- direct comparison report.

Exit criteria:

- same pipeline compares both strategies using identical account and objective assumptions;
- every selected and rejected candidate has an explanation.

### Phase 5: MCP trade-planning interface

Deliverables:

- actual MCP server registration and typed schemas;
- market, strategy, research, comparison, plan, and review tools;
- Markdown and JSON plan outputs;
- dry-run order intent creation.

Exit criteria:

- an MCP client can reproduce the end-to-end reference workflow without direct filesystem manipulation.

### Phase 6: Broker-aware paper execution

Deliverables:

- option-chain/account capability adapters;
- broker-neutral option order model;
- paper submission, fill reconciliation, PnL, and audit trail;
- current quote and risk revalidation.

Exit criteria:

- paper order lifecycle reconciles plan, broker acknowledgment, fills, positions, and PnL.

### Phase 7: Additional strategies and optional live execution

Deliverables:

- collar and vertical spread plug-ins;
- multi-leg atomicity policy;
- explicitly approved live adapter path using existing confirmation controls.

Exit criteria:

- no live submission can bypass quote, account, risk, confirmation, and idempotency gates.

---

## 23. Initial End-to-End Acceptance Scenario

Given:

- a saved Friday SPY chain;
- underlying history available before that Friday;
- rates, dividends, calendar, and event data;
- a paper account with a defined cash balance;
- weekend-short-put and 30-45 DTE cash-secured-put specifications;
- a tail-adjusted return-on-collateral objective;

The server must:

1. validate the point-in-time data;
2. build the Friday market state;
3. generate relevant horizon forecasts;
4. enumerate eligible contracts for both strategies;
5. reject contracts that fail liquidity, event, account, or risk gates;
6. simulate eligible candidates using pessimistic and midpoint fills;
7. calculate collateral, opportunity cost, assignment effects, and tail loss;
8. rank candidates with explicit objective weights;
9. produce JSON and Markdown plans with selected and rejected alternatives;
10. create a dry-run broker-neutral order intent only after review approval; and
11. reproduce the result from persisted run metadata.

---

## 24. Architecture Decisions to Resolve Before Implementation

1. Which historical options provider and license will be used for the first dataset?
2. Which broker, if any, is the first source of live/delayed chains and account buying power?
3. Should Version 1 support only cash-secured/covered positions, or margin underwriting too?
4. What is the canonical early-exercise model for American equity options?
5. Which rate and dividend sources are acceptable for research and live planning?
6. What is the first objective: return on cash collateral, tail-adjusted return, or expected utility?
7. What is the default fill policy for headline backtest results?
8. Will Friday-to-Monday trades be held to expiration or allow Monday exits?
9. Which expiration timestamp conventions are required for SPY versus index options?
10. Is the first MCP release strictly read-only plus dry-run intent creation?

Recommended defaults for the first vertical slice:

- saved Parquet snapshots before a paid/live adapter;
- SPY only;
- cash-secured short puts only;
- Friday entry and hold-to-expiration for the weekend variant;
- 30-45 DTE entry with 50% profit/21 DTE exit for the longer variant;
- pessimistic executable-side fills as the primary result, midpoint as sensitivity;
- tail-adjusted return on cash collateral;
- read-only research plus dry-run order intent creation.

---

## 25. Definition of Done

This improvement is complete when TradeMCP can accept a versioned options strategy, use only point-in-time data to create strategy-neutral forecasts, simulate realistic option cashflows and lifecycle events, compare candidates under explicit account and objective constraints, explain the result, and generate a safe, reviewable order intent through MCP without hardcoding one strategy or forecast target.
