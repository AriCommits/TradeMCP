# Typing Roadmap

Date: 2026-03-26

## Goal

Reach strict, maintainable type coverage across all Python code with CI enforcement and minimal runtime regressions.

## Target Standards

- Every public function and method has explicit parameter and return types.
- Shared payloads use typed models (`dataclass`, `TypedDict`, or `pydantic` models).
- Adapter contracts use `Protocol` interfaces.
- No new untyped public APIs are merged.
- `mypy` and `pyright` pass in CI.

## Tooling Baseline

- Static checkers:
- `mypy`
- `pyright`
- Lint integration:
- `ruff` typing-focused rules
- Runtime boundaries:
- `pydantic` validation at external I/O boundaries

## Rollout Phases

## Phase 0: Baseline and Guardrails

- Add CI jobs:
- `mypy` (incremental strictness)
- `pyright` (report mode, then fail mode)
- Freeze a baseline report so existing gaps are visible and measurable.
- Gate rule:
- changed files cannot introduce new untyped public functions.

## Phase 1: Core Types and Interfaces

- Add foundational types:
- `OrderIntent`, `OrderSummary`, `PnLSnapshot`, `ReviewReport`
- `ExecutionState` enum for order lifecycle
- Introduce adapter `Protocol` contracts for broker behavior.
- Add typed config loading wrappers for YAML configuration inputs.

## Phase 2: Core Pipeline Modules

- Migrate the main pipeline modules to explicit typing.
- Ensure numerical/dataframe interfaces are typed consistently.
- Add type-safe return objects for intermediate computation outputs.

## Phase 3: Adapters, CLI, and Scripts

- Type adapter modules end-to-end.
- Type CLI and operational scripts.
- Ensure prompt/confirmation flows have typed state transitions.

## Phase 4: Tests and Strict Mode

- Type test helpers and fixtures.
- Enable strict flags package-by-package until full strict mode is reached.
- Set CI to fail on any typing regressions.

## Strictness Escalation Plan

1. Enable:
- `check_untyped_defs = true`
- `warn_return_any = true`
- `warn_unused_ignores = true`

2. Then enable:
- `disallow_incomplete_defs = true`
- `disallow_untyped_defs = true`

3. Finally enable:
- `disallow_any_generics = true`
- `no_implicit_optional = true`

## File-by-File Migration Checklist

## Core package

- [ ] `src/trading/__init__.py`
- [ ] `src/trading/config.py`
- [ ] `src/trading/data_ingestion.py`
- [ ] `src/trading/regime.py`
- [ ] `src/trading/volatility.py`
- [ ] `src/trading/forecasting.py`
- [ ] `src/trading/risk.py`
- [ ] `src/trading/backtest.py`
- [ ] `src/trading/execution_client.py`
- [ ] `src/trading/indicators.py`
- [ ] `src/trading/viz.py`
- [ ] `src/trading/app.py`

## Adapters

- [ ] `src/trading/adapters/__init__.py`
- [ ] `src/trading/adapters/_config_utils.py`
- [ ] `src/trading/adapters/broker_router.py`
- [ ] `src/trading/adapters/tradingview_adapter.py`
- [ ] `src/trading/adapters/fidelity_active_trader_adapter.py`
- [ ] `src/trading/adapters/robinhood_crypto_adapter.py`
- [ ] `src/trading/adapters/gemini_adapter.py`
- [ ] `src/trading/adapters/forex_com_adapter.py`

## Scripts

- [ ] `scripts/generate_sample_data.py`
- [ ] `scripts/run_pipeline.py`
- [ ] `scripts/ping_adapters.py`
- [ ] `scripts/scrape_finviz.py`

## Tests

- [ ] `tests/test_regime_and_risk.py`
- [ ] `tests/adapters/test_router.py`

## Definition of Done

- 100% of public functions/methods typed.
- `mypy` and `pyright` pass in CI with strict settings enabled.
- Typed models used for order lifecycle, review output, and PnL output.
- No `Any` in critical execution paths except explicitly justified and documented.

## Suggested CI Commands

```bash
mypy src/trading scripts tests
pyright
ruff check src scripts tests
```
