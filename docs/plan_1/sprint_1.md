# Sprint 1: Research Foundation and Immutable Contracts

## Wave Outcome

Create the package skeleton, freeze or visibly block the essential research decisions, and establish canonical time/data/artifact contracts. This wave permits fixture-based work only; it does not authorize a full market-data download.

**Estimated effort:** 12-20 engineering hours across two agents, excluding user decision latency.

## Before This Wave Starts

- Read `docs/plan_1/OVERVIEW.md` and the original project brief.
- Preserve all existing `src/trading/` behavior and the current uncommitted options/MCP work.
- Confirm no concurrent agent owns the same files. Use separate branches/worktrees for concurrent implementation.
- Treat all timestamps as timezone-aware UTC and all anchors as completed candles.

## Parallel Agents

### Agent A - P0: Research Decisions, Environment, and Project Skeleton

**Files:** `.gitignore`; `README.md`; `pyproject.toml`; `src/crypto_movement/__init__.py`; `src/crypto_movement/config.py`; `config/crypto_movement/project.yaml`; `config/crypto_movement/pilot.yaml`; `scripts/audit_crypto_environment.py`; `docs/decision_log.md`; `docs/crypto_movement/storage_runtime_estimate.md`; `docs/crypto_movement/fold_calendar.md`; `tests/crypto_movement/test_config.py`; `tests/crypto_movement/test_environment_audit.py`

**Instructions:**

1. Create an isolated `crypto_movement` package and typed, path-configurable YAML loading. Do not hard-code a desktop path.
2. Audit CPU, RAM, disk, Python, GPU, CUDA, and relevant package support without printing credentials.
3. Record venue/instrument, candle boundaries, fees, spread/slippage, funding, prop rules, rate limits, coverage, pilot interval, fold calendar, purge/embargo, and lockbox status.
4. Mark missing production decisions as `BLOCKING_FULL_DOWNLOAD`; fixture/synthetic scaffolding may still run.
5. Estimate pilot/mature/full storage and training ranges with assumptions shown.
6. Add git-ignore entries for raw/interim/processed data, API caches, large predictions, and model weights. Preserve lightweight manifests/configs/reports.
7. Add optional ML dependencies only after the local environment is checked; keep the basic package CPU-testable.

**Definition of done:**

- Config loading is deterministic, typed, and tested for invalid paths/unknown values.
- The audit runs on a clean machine without secrets and writes a reviewable summary.
- The decision log distinguishes confirmed choices, proxy assumptions, and blockers with sources/dates.
- The full-download command has a machine-checkable gate, not just a warning in prose.
- Focused tests and existing smoke tests pass.

### Agent B - C0: Canonical Contracts, Time Semantics, and Artifact Provenance

**Files:** `src/crypto_movement/contracts.py`; `src/crypto_movement/time.py`; `src/crypto_movement/artifacts.py`; `tests/crypto_movement/test_contracts.py`; `tests/crypto_movement/test_time_semantics.py`; `tests/crypto_movement/test_artifacts.py`

**Instructions:**

1. Define immutable contracts for venue/symbol identities, raw/resampled bars, completed anchors, horizons, labels, ambiguity, feature availability, folds, and artifacts.
2. Enforce timezone-aware UTC, positive prices, valid OHLC, aligned intervals, and `feature_timestamp <= anchor < label_timestamp` semantics.
3. Centralize horizons and the arithmetic barrier conversions `log(1.04)` and `log(0.96)`.
4. Give artifacts stable identities containing data/config/code/fold/model/preprocessor/seed provenance.
5. Do not import venue clients or model frameworks into the contract layer.

**Definition of done:**

- Hand-worked tests cover exact boundaries, invalid OHLC, naive time, incomplete candles, and future predictors.
- Stable identities are order-independent where intended and change when relevant provenance changes.
- Contracts support both 15-minute/96-step and 30-minute/48-step inputs plus 1/3/6/12-hour outputs.
- The module imports without optional GPU or venue dependencies.

## Integration Gate

- Merge Agent B before or alongside Agent A's final config validation; P0 may reference C0 types, but C0 must remain independent of P0 configuration.
- Run all new Sprint 1 tests, the repository test suite, and static checks.
- Review the decision log manually. Unanswered venue/prop questions are acceptable only if the full-download gate remains closed.

## This Wave Unblocks

- D0 venue-aware collection and universe snapshots.
- L0 first-barrier label generation.
- All downstream data, split, feature, and model work through stable contracts.

