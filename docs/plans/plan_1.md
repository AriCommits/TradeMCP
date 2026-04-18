# Agent Handoff Document: Multi-Asset Agentic Trading System — Architecture Addendum

**Prepared for implementation agent | Phases 1 & 2 revision**

## Overview & Purpose
This document captures architectural decisions and required changes identified during planning. The implementation agent must incorporate all items below before proceeding with or continuing Phases 1 and 2. These changes were omitted from the original plan and are non-negotiable for production readiness.

---

## 1. Model Routing Architecture
**Requirement:** Each agentic Chrome job must use a two-tier model routing strategy.
- Planning and high-level orchestration are handled by the high-capability model (Opus).
- Execution, monitoring, and low-level implementation are delegated to a configurable local model.

**Changes Required:**
- [ ] Add a `ModelRouter` class that accepts a job type and returns the appropriate model endpoint (cloud vs. local).
- [ ] Local model must be configurable via environment variable or config file — do not hardcode.
- [ ] All agentic Chrome jobs must pass through the router before dispatching any LLM calls.
- [ ] Log which model handled which task in every job execution record.

---

## 2. Testing Infrastructure
### MCP Server Testing
- [ ] Deterministic components of all MCP servers must have unit tests before Phase 2 is considered complete.
- [ ] Mock all external API responses at the adapter boundary.
- [ ] Test each MCP tool invocation independently with pre-recorded fixtures.
- [ ] Assert on output schema, not just non-null returns.

### Nondeterministic Agent Evaluation
LLM agent behavior must be evaluated against real financial time series data.
- **Source datasets:** Yahoo Finance, Alpha Vantage, Hugging Face, or Finnhub.
- **Evaluation strategy:** Mock the broker adapter with pre-recorded responses, then run agent logic against those fixtures. Separately, integration-test the broker adapter against the real API in a staging environment with paper trading credentials only.

---

## 3. Financial API Abstraction Layer
**Pattern:** Adapter + Abstract Base Class
All broker and financial data API interactions must go through a typed abstract base class. This decouples agent logic from any specific broker implementation.

**Abstract Base Class Must Include:**
- `get_quote(symbol, asset_class)`
- `place_order(order_config)`
- `cancel_order(order_id)`
- `get_order_status(order_id)`
- `get_account_balance()`
- `get_historical_data(symbol, timeframe, start, end)`

**Concrete Implementations:**
Each broker gets its own subclass (e.g., `RobinhoodAdapter(BrokerBase)`). Subclasses handle auth, rate limiting, and response normalization internally. Agent code must never reference broker-specific classes directly.

---

## 4. Trade & Execution Object Model
Core objects must be defined before execution logic is written:

- **AssetProfile:** `symbol`, `asset_class`, `liquidity_tier`, `typical_spread`, `avg_daily_volume`
- **ResearchConfig:** `model_id`, `model_type`, `hyperparameters`, `timeframe`, `entry_signal_threshold`, `confidence_score`, `asset_profile` reference
- **ExecutionContext:** Translates ResearchConfig into execution parameters. Owns `order_type`, `position_size`, `slippage_model`, `fee_estimate`, `stop_loss`, `take_profit`, `execution_window`. Primary key: `(model_id, execution_batch_id)`.
- **OrderConfig:** Derived from ExecutionContext. `order_type`, `side`, `quantity`, `price`, `time_in_force`.
- **OrderState (enum):** `PENDING`, `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, `EXPIRED`, `CANCELED`, `CANCELLATION_PENDING`
- **OrderResult:** `order_id`, `state`, `fill_price`, `fill_quantity`, `slippage_actual`, `fee_actual`, `timestamp`.

---

## 5. Realistic Execution Modeling
Must be modeled from day one across all asset classes and timeframes:

| Component | Priority | Phase |
| :--- | :--- | :--- |
| **Order Types** (Market, limit, stop) | CRITICAL | Phase 1 |
| **Slippage Model** (Size-relative to vol) | CRITICAL | Phase 1 |
| **Partial Fills** (esp. for crypto) | HIGH | Phase 1 |
| **Bid-Ask Spread** | HIGH | Phase 1 |
| **Order State Machine** (7 transitions) | CRITICAL | Phase 1 |
| **Volatility Impact** | HIGH | Phase 2 |
| **Asset-Class Params** | HIGH | Phase 1 |
| **Execution Latency** | MEDIUM | Phase 2 |
| **Fees & Commissions** | HIGH | Phase 1 |
| **Cancellation Logic** | HIGH | Phase 2 |

*Note: Sub-minute / high-frequency execution is explicitly OUT OF SCOPE for Phases 1 and 2.*

---

## 6. Execution Window & Batching
Discretize trade execution into atomic windows:
- Each execution window is a single unit. Individual orders inside cannot be canceled mid-execution.
- The entire batch can be canceled before it starts or after it completes.
- Window duration is derived from the ResearchConfig timeframe.
- Log batch details per window.

---

## 7. Database Schema Requirements
Two Logical Data Stores: **Research DB** and **Execution DB**, joined by `(model_id, execution_batch_id)`.

**Research DB Tables:**
- `model_registry`: model_id, model_type, hyperparameters, created_at, asset_class_tags
- `research_runs`: run_id, model_id, symbol, timeframe, start_date, end_date, confidence_score, rank
- `model_evaluations`: eval_id, model_id, symbol, metric_name, metric_value, evaluated_at

**Execution DB Tables:**
- `execution_batches`: batch_id, model_id, asset_profile_id, execution_window_start, execution_window_end, status
- `orders`: order_id, batch_id, order_config, order_result, state, created_at, updated_at
- `audit_log`: log_id, batch_id, order_id, event_type, payload, timestamp

---

## 8. Logging & Audit Trail
- Structured and machine-readable (JSON log format). No print statements.
- **Log Levels:**
  - `DEBUG` (internal reasoning)
  - `INFO` (findings, decisions, placements)
  - `WARNING` (unexpected states, partial fills, high slippage)
  - `ERROR` (API failures, rejections)
  - `CRITICAL` (kill switch, data integrity, auth failure)

---

## 9. Security Hardening (Deferred)
Deferred until research loop is validated end-to-end on paper trading:
- Circuit breaker / kill switch for API interactions.
- Pre-trade validation service layer.
- Air-gap / reverse proxy.
- Cache layer.
- **Not Deferred:** Secrets management (no hardcoded API keys anywhere — enforce via environment variables).

---

## 10. Phase Assignment Summary

- **CRITICAL / Phase 1:** ModelRouter, BrokerBase ABC, AssetProfile, ResearchConfig, ExecutionContext, OrderConfig/Result, OrderState machine, Slippage model, Research & Execution DB schemas.
- **HIGH / Phase 1:** Partial fill handling, Structured logging, Asset-Class Params, Fees & Commissions, Bid-Ask Spread.
- **HIGH / Phase 2:** MCP unit tests, Agent eval dataset, Execution batching, Volatility impact, Cancellation Logic.
- **MEDIUM / Phase 2:** Execution latency sim.
- **HIGH / Post Phase 2:** Security hardening.

**Implementation Notes:**
- Do not skip or defer any CRITICAL item.
- HIGH items in Phase 1 must be completed before Phase 2 begins.
- Sub-minute/HFT is out of scope.
- All broker API credentials must be loaded from environment variables (NEVER committed).
- Paper trading mode must be the default. Live trading requires explicit configuration absent from test environments.
