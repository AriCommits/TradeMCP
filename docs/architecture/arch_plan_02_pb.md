# Architecture Plan 02B: Test Taxonomy + Backtesting Suite

Date: 2026-03-26

## Scope

Define a clean split between software correctness tests and strategy-performance backtests, and introduce a phased backtesting suite with parameter sweeps, plotting, and reporting.

## 1) Differentiate Code Tests vs Strategy Backtests

- Keep `tests/` for software correctness tests only.
- Split tests into:
- `tests/unit/` (pure function/class tests)
- `tests/integration/` (pipeline wiring, adapters with mocks)
- `tests/contracts/` (adapter interface contract tests)
- Create separate `backtests/` in project root for strategy-performance runs and fixtures.

### Pytest Markers

- `@pytest.mark.unit`
- `@pytest.mark.integration`
- `@pytest.mark.contract`
- `@pytest.mark.backtest`

### CI Lanes

- PR fast lane:
- `unit + integration + contract`
- Scheduled lane:
- `backtest` (long-running)

Recommendation maintained: use `tests/unit` rather than top-level `unittests` for pytest convention compatibility.

## 2) Backtesting Suite Plan

## Phase A: Core API + Parameter Grid

- Add typed models:
- `BacktestRequest`
- `BacktestRun`
- `BacktestSuiteResult`
- Add parameter expansion modes:
- `zip` (index-aligned arrays)
- `product` (cartesian sweep)
- Default mode: `product`.
- Add validation for ticker/date/timeframe ranges.

## Phase B: Engine + Data Providers

- Add `MarketDataProvider` interface.
- Implement providers:
- `CSVProvider` (immediate)
- `RemoteProvider` (later, optional)
- Execute each expanded run through existing pipeline/backtest logic.

## Phase C: Visual Outputs (Matplotlib)

Per-run charts:
- Price + trade markers
- Indicator panels (RSI/MACD/ATR)
- Equity curve
- Drawdown
- PnL distribution

Defaults:
- Save images under `artifacts/backtests/<suite_id>/<run_id>/`.
- Optional `--show` flag to spawn local GUI windows.

## Phase D: CLI

- New command entrypoint: `scripts/backtest_suite.py`

Inputs:
- Single params (e.g. `--ticker AAPL ...`)
- Repeated params (e.g. `--ticker AAPL --ticker MSFT ...`)
- Config file input (`--spec spec.yaml`)

Outputs:
- `summary.csv`
- `summary.json`
- PNG chart pack per run

## Phase E: Reporting + Ranking

- Rank runs by:
- Sharpe
- Max drawdown
- Net PnL
- Emit top-N runs report with links/paths to chart artifacts.
- Report format default is markdown-first; use HTML tables only where useful for compact ranking summaries.

## Defaults Chosen

- Root `backtests/` directory is used (not nested under `research/`).
- Parameter expansion default is `product` with `zip` as an explicit mode.
- Report format is markdown-first with selective HTML tables.
