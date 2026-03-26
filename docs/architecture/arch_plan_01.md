# Architecture Plan 01: Multi-Market Extension + Review/Close/PnL + Typing/GPU

Date: 2026-03-26

## Scope

Extend the current modular quant pipeline with:

- CLI + MCP orchestration for strategy research/suggestion/execution flows
- Multi-market strategy support (stocks, forex, crypto, international stocks)
- Stronger secrets/key handling abstraction
- Trade review workflow
- Strategy termination / close controls
- Current PnL reporting
- Strict Python type coverage across the codebase
- GPU-accelerated compute paths when hardware is available
- Verbose Python-side error reporting and deterministic failure handling
- Atomic order execution with explicit pre-submit verification gates

## Prioritized Build Plan

1. Add a strategy registry layer:
- Market to strategy-family mapping
- Required features, risk profile, and execution constraints per strategy

2. Add a research orchestrator:
- Score candidate strategies by symbol, regime, volatility, and execution feasibility
- Produce ranked suggestions with confidence and expected edge

3. Add CLI workflow (`Typer`):
- `analyze`, `suggest`, `simulate`, `review`, `execute`, `pnl`, `close`, `terminate`

4. Add MCP server workflow:
- `research_asset`
- `rank_strategies`
- `run_walkforward`
- `review_trade`
- `submit_order_intent`
- `get_current_pnl`
- `close_positions`
- `terminate_run`

5. Add centralized execution policy gates:
- Max slippage guardrail
- Max symbol/portfolio exposure
- Max daily drawdown/loss stop
- Live-trading kill switch

6. Expand adapter capability profiles:
- Per-broker support matrix (order types, cancel/replace, paper/live, rate limits)
- Route through existing intermediary broker router

7. Add secrets and token abstraction:
- Dev/local: OS keychain via `keyring`
- Team/prod: vault-style manager (Vault/OpenBao/Infisical/cloud secrets)
- Runtime token broker for short-lived scoped credentials/tokens
- Avoid exposing long-lived provider keys to UI/client layers

8. Add market-specific feature packs:
- Forex: session overlap and macro/event flags
- Crypto: funding/liquidity/24x7 structure features
- International stocks: exchange calendars, timezone alignment, FX decomposition

9. Enforce strict Python typing everywhere:
- Add type hints to all functions, methods, class attributes, and module-level constants
- Use typed data models for configs, signals, orders, and PnL snapshots
- Add static checking gates (`mypy` + `pyright`) in CI
- Raise quality bar incrementally to `disallow_untyped_defs = true`
- Add runtime validation boundaries for external data (`pydantic` models or equivalent)

10. Add GPU-aware execution path with safe fallback:
- Add capability detection (`cuda`, `mps`, then `cpu`)
- Route model training/inference and heavy numerical ops through device-aware wrappers
- Keep parity tests so CPU and GPU produce numerically consistent outputs (within tolerance)
- Add config flags for `device: auto|cpu|cuda|mps` and memory limits
- Keep all paths deterministic where possible (seed controls + reproducibility notes)

11. Add verbose Python error policy:
- Centralized exception middleware for CLI/MCP/services
- Always log full traceback + correlation/run/order IDs
- Standardized error taxonomy (`ValidationError`, `DataError`, `ComputeError`, `ExecutionError`, `BrokerError`)
- User-facing errors remain readable while diagnostics remain complete in logs/artifacts
- Fail closed for execution-critical paths (no partial submit after compute failure)

12. Enforce atomic order lifecycle:
- Introduce `OrderTransactionCoordinator` with strict state machine
- Required state flow:
- `DRAFT -> CALCULATING -> READY_FOR_REVIEW -> COUNTDOWN -> CONFIRMED -> SUBMITTED -> ACKED`
- Submission is blocked unless calculation state is complete and validated
- Use idempotency keys + optimistic lock/version checks to prevent duplicate submits
- Persist lifecycle transitions in append-only audit log

## New Functional Requirements

## Trade Review Function

Introduce `ReviewReport` prior to execution:

- Inputs:
- Forecast output
- Regime assignment/stability
- Vol forecast
- Risk sizing
- Predicted slippage / implementation shortfall
- Current exposure and limit state
- Output:
- `GO` or `NO_GO`
- Explicit breached checks and mitigation suggestions

## Terminate / Close Function

Introduce `ExecutionControlService`:

- `terminate_strategy_run(run_id)`:
- Stops additional order generation for that run
- `close_symbol(symbol, mode)`:
- Cancel open orders then flatten (if mode=`flatten`)
- `panic_close_all()`:
- Global emergency flatten + cancel workflow

Safety requirements:

- Confirmation required for live mode
- Audit log for all terminate/close operations
- Dry-run support for validation

## Current PnL Feature

Introduce `PnLService` with `PnLSnapshot`:

- Realized PnL
- Unrealized mark-to-market PnL
- Daily PnL
- Fees and net PnL
- Per-symbol and portfolio roll-up
- Net exposure summary

Expose by:

- CLI: `trading pnl --broker <name> --group-by symbol`
- MCP: `get_current_pnl`

## Python Type Suggestions Everywhere

Introduce a typing standard for all Python modules:

- Required:
- Function/method signatures fully annotated
- Return types always explicit
- `TypedDict`/`dataclass`/`pydantic` models for shared payloads
- `Protocol` interfaces for adapters and strategy engines
- Type-safe config loading layer for all YAML files
- Enforced checks:
- `mypy` strict mode staged rollout by package
- `pyright` in CI as secondary checker
- `ruff` typing-related rules enabled
- Deliverables:
- `docs/architecture/typing_roadmap.md` with file-by-file migration checklist
- CI job that fails on new untyped public APIs

## GPU Compute Support

Introduce `ComputeBackend` abstraction:

- `ComputeBackend(device="auto")` resolves:
- `cuda` when NVIDIA GPU is available
- `mps` on Apple Silicon when available
- fallback `cpu` otherwise
- Target workloads for acceleration:
- Forecast model training/inference
- Regime embedding transforms for large universes
- Vectorized risk and scenario calculations
- Optional slippage model training
- Operational controls:
- Configurable batch sizing to avoid GPU OOM
- Graceful downgrade to CPU on runtime failures
- Device telemetry logging in artifacts/MLflow
- Benchmark harness:
- Compare runtime + memory + metric parity for CPU vs GPU paths
- Persist benchmark outputs under `artifacts/benchmarks/`

## Verbose Error Handling (Python)

Execution and compute services should expose verbose, traceable failure diagnostics:

- Capture and persist:
- Full traceback
- Input snapshot hashes (not raw secrets)
- Config version + commit/run identifiers
- Device context (`cpu`/`cuda`/`mps`)
- Error propagation rules:
- Computation errors prevent transition to executable order states
- Broker/API errors include retry classification (`retryable` vs `terminal`)
- Human-facing output:
- Print concise failure summary + where to find full diagnostic report
- Write full structured report to `artifacts/errors/<timestamp>_<run_id>.json`

## Atomicity + Interactive Two-Step Confirmation

Before live submission, enforce a two-step confirmation gate:

- Step 1: Print order summary only after calculations are complete:
- Symbol, side, qty/notional
- Expected edge and predicted slippage
- Risk impact (exposure, stop level, max loss)
- Strategy/run IDs and timestamp
- Step 2: Require second verification with countdown:
- Prompt: `Confirm order? (y/n)`
- Start a 10-second countdown timer
- During countdown:
- `y` confirms at end of countdown
- `n` cancels immediately
- Any non-whitelisted key cancels immediately
- `Shift+P` pushes immediate submit without waiting for countdown expiry

Implementation note:
- Use an input/event loop capable of key-level capture (`prompt_toolkit`/`textual`/equivalent) for reliable `Shift+P` and cancel-any-key behavior in terminal mode.

## Adapter Interface Additions

Each adapter should implement:

- `get_positions()`
- `get_open_orders()`
- `get_account_balances()`
- `get_recent_fills()`
- `cancel_order(order_id)`
- `close_position(symbol, qty|all)`
- `close_all_positions()`

## Config Additions

- `config/risk_controls.yaml`:
- max daily loss, symbol caps, kill switch settings
- `config/pnl.yaml`:
- quote staleness threshold, fee model, mark source settings
- `config/integrations/adapters/*.yaml`:
- close/cancel capability flags and runtime restrictions
- `config/compute.yaml`:
- device selection (`auto|cpu|cuda|mps`), precision mode, memory cap, batch size
- `config/typing.yaml`:
- typing enforcement level per module/package
- `config/error_policy.yaml`:
- verbosity mode, traceback retention, retry policy, artifact error report path
- `config/execution_controls.yaml`:
- atomicity mode, confirmation required, countdown seconds (default 10), hotkeys (`shift+p`), cancel-on-unrecognized-key

## Testing and Validation

1. Unit tests:
- PnL computation correctness
- Review gate pass/fail behavior
- Type-check fixtures and typed model serialization checks

2. Adapter contract tests:
- Mocked broker behavior for close/cancel and account reads

3. End-to-end dry-run:
- `suggest -> review -> execute -> pnl -> close`

4. Live safety checks:
- Ensure terminate/close flows require explicit confirmation in live mode

5. Typing quality gates:
- `mypy` and `pyright` must pass in CI before merge

6. GPU validation:
- CPU/GPU parity tests with tolerance bands
- Device fallback tests when GPU is unavailable

7. Error-path validation:
- Force failures in data/compute/execution layers and assert verbose artifact reports
- Ensure no execution occurs when compute fails

8. Atomicity/confirmation validation:
- Verify submit is impossible before `CALCULATING` completes
- Verify countdown/keypress behavior:
- `y` + timeout path submits
- `n` cancels
- random key cancels
- `Shift+P` submits immediately
- Verify idempotency prevents double submission on repeated confirm events

## Incremental Delivery Order

1. Read-only features:
- `review` and `pnl` (no live order mutation)

2. Controlled mutation features:
- `close` and `terminate` with hard safety gates

3. Typing hardening:
- Type hints across all Python modules and strict CI gating

4. GPU enablement:
- Device abstraction + accelerated compute paths + fallback

5. Error/atomicity hardening:
- Verbose Python error policy + transaction coordinator + two-step confirmation UX

6. MCP exposure:
- Mirror CLI workflows through MCP tools

7. Multi-market strategy deepening:
- Add incremental strategy packs and market-specific execution models

## Implementation Summary (codex_1, 2026-03-26)

Implemented in this iteration:

- Added strategy registry + ranked research orchestration (`StrategyRegistry`, `ResearchOrchestrator`).
- Added operational services for review, PnL snapshots, and execution controls (`ReviewService`, `PnLService`, `ExecutionControlService`).
- Added atomic order lifecycle coordinator with explicit states (`OrderTransactionCoordinator`) and append-only audit logging.
- Added verbose Python error taxonomy and structured error artifact persistence (`ValidationError`, `DataError`, `ComputeError`, `ExecutionError`, `BrokerError`, `persist_error_report`).
- Added compute backend abstraction with device detection/fallback (`auto|cpu|cuda|mps`).
- Added unified Typer CLI workflow for `analyze`, `suggest`, `simulate`, `review`, `execute`, `pnl`, `close`, `terminate`, and `compute-info`.
- Added MCP workflow scaffold exposing `research_asset`, `rank_strategies`, `run_walkforward`, `review_trade`, `submit_order_intent`, `get_current_pnl`, `close_positions`, `terminate_run`.
- Expanded broker router + adapters with close/cancel/open-order/fills/balance/positions capabilities and capability profiling support.
- Added config files for risk controls, pnl, compute, typing, error policy, and execution controls.
- Normalized key runtime/config defaults away from machine-specific absolute paths to repo-relative defaults.
- Added coverage for new router/service behavior in tests; full local suite passed: `9 passed`.

Planned but not fully complete yet:

- Full strict typing coverage across all modules.
- CI gating for `mypy` + `pyright`.
- GPU acceleration integrated into heavy compute paths with parity tests.
- Full two-step interactive countdown/hotkey UX for terminal order confirmation.
