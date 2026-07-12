# Sprint 1 — Correctness Baseline and Canonical Contracts

**Status:** Complete — 2026-07-12

## Goal

Establish time, data, and domain contracts that every later workstream can use without reinterpreting units or introducing look-ahead leakage.

## Entry Criteria

- Existing test suite is runnable.
- The architecture specification is accepted as the scope baseline.
- No options provider or broker is required yet.

## Parallel Work Groups

### Group A — Canonical domain contracts (`C0`)

- Add typed identifiers and records for option contracts, legs, positions, quotes, chains, forecasts, account snapshots, candidates, simulations, and trade plans.
- Define UTC timestamp, session date, calendar-day, trading-day, overnight, and expiration timestamp semantics.
- Define monetary, volatility, rate, Greeks, multiplier, and return units.
- Add schema versions and serialization round-trip tests.

Targets:

```text
src/trading/options/contracts.py
src/trading/options/quotes.py
src/trading/forecasts/targets.py
src/trading/strategies/specifications.py
src/trading/mcp/schemas.py
```

### Group B — Leakage remediation (`D0`)

- Remove bidirectional interpolation from the existing ingestion path.
- Move scalers and imputers inside each walk-forward training fold.
- Add missing-value flags rather than silently synthesizing invalid market observations.
- Add tests proving future rows cannot change earlier features or forecasts.

Targets:

```text
src/trading/data_ingestion.py
src/trading/forecasting.py
src/trading/backtest.py
tests/test_point_in_time.py
```

### Group C — Rust kernel audit (`R0`)

- Copy nothing automatically from the subtree.
- Review the subtree Black-Scholes, binomial, indicators, and equity backtest modules.
- Record units, clamps, numerical assumptions, unsupported cases, and security differences.
- Create language-neutral pricing fixtures for later Python/Rust parity.
- Preserve the base repository executable-path safety check.

Targets:

```text
docs/architecture/rust_kernel_assessment.md
tests/fixtures/options_pricing/
```

### Group D — Quality and configuration skeleton

- Add package skeletons and versioned configuration schemas.
- Add CI/test commands for new Python packages and existing Rust tests.
- Define artifact names and correlation/run identifiers.
- Mark the current Greeks visualization as mocked and non-trading.

## Integration Order

1. Merge Group A contracts first.
2. Rebase Groups B-D onto final contract names.
3. Run all point-in-time and serialization tests together.
4. Freeze Version 1 contract names at sprint review.

## Exit Criteria

- Canonical records serialize and validate.
- Exact units and time semantics are documented.
- Full-sample scaling and future-aware interpolation are removed.
- Point-in-time regression tests pass.
- Rust audit identifies the one-day expiry clamp and other unsupported cases.
- Existing behavior remains green except for intentionally corrected leakage behavior.

## Handoff

- Group A contracts unblock every Sprint 2 lane.
- Pricing fixtures unblock Rust/Python parity work.
- Leakage-safe folds unblock forecasting in Sprint 3.

## Completion Record

Implemented:

- Canonical UTC-aware, schema-versioned option, quote, forecast, account, candidate, simulation, and MCP trade-plan records.
- Leakage-safe ingestion with missingness flags, causal regime scaling, and fold-local forecast imputation/scaling.
- Versioned options platform configuration with explicit unit and dry-run defaults.
- Explicit demonstration-only warnings for the mocked Greeks dashboard and MCP description.
- Rust kernel assessment plus portable Black-Scholes and binomial pricing fixtures.

Verified:

- Python and Django: 44 tests passed.
- Ruff: all changed Sprint 1 files passed.
- Scoped mypy: 9 new domain modules passed.
- Base Rust engine: 2 tests passed.
- Subtree Rust prototype: 31 tests passed; 8 existing compiler warnings remain.
