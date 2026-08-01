# Sprint 7: Multitask Heads and Model-Selection Orchestration

## Wave Outcome

In parallel, add the optional shared-encoder multitask/competing-risk model and build a model-agnostic nested walk-forward orchestration layer. The orchestration lane uses the frozen Stage A/B registries and can ingest H0 after both branches merge without changing folds or search budgets.

**Estimated effort:** 40-64 engineering hours across two agents, excluding training wall time.

## Before This Wave Starts

- Sprint 6 selected encoder candidates and promotion records are frozen.
- Separate classification and regression outputs are stable enough to justify a multitask test; otherwise H0 records a stop decision and supplies only interface tests.
- Outer folds and lockbox are unchanged from Sprints 5-6.
- Agent A and Agent B must not introduce a shared registry file; integration happens through the B0 model protocol and configuration.

## Parallel Agents

### Agent A - H0: Multitask Quantiles and Optional Competing-Risk Hazard

**Files:** `src/crypto_movement/models/losses.py`; `src/crypto_movement/models/hazard.py`; `src/crypto_movement/models/multitask.py`; `src/crypto_movement/training/multitask.py`; `config/crypto_movement/multitask.yaml`; `scripts/run_crypto_multitask_pilot.py`; `tests/crypto_movement/models/test_losses.py`; `tests/crypto_movement/models/test_hazard.py`; `tests/crypto_movement/models/test_multitask.py`; `tests/crypto_movement/training/test_multitask_training.py`

**Instructions:**

1. Add shared-encoder classification/competing-risk, terminal-return quantile, MFE/MAE quantile, and optional realized-volatility heads.
2. Keep 1/3/6/12-hour outputs explicit. If using discrete hazards, predict conditional up/down risk per future 15-minute step given no earlier event and derive coherent cumulative probabilities.
3. Tune loss weights only inside inner validation and log head-specific gradients/losses for collapse detection.
4. Apply a documented noncrossing quantile strategy and test it.
5. Evaluate agreement rules using E0; state explicitly that shared heads are correlated.
6. Stop rather than promote if the shared model does not improve held-out metrics or useful decision precision at adequate coverage.

**Definition of done:**

- Hazard/cumulative probabilities are finite, nonnegative, mutually coherent, and monotone across time.
- Quantile outputs and separate horizon shapes are validated.
- Reload predictions match and contain the exact encoder/head/loss-weight provenance.
- Promotion uses held-out proper scoring/calibration/decision utility, not training loss.

### Agent B - O0: Nested Walk-Forward Selection and Robustness Orchestration

**Files:** `src/crypto_movement/training/search.py`; `src/crypto_movement/training/orchestration.py`; `src/crypto_movement/evaluation/walk_forward.py`; `src/crypto_movement/evaluation/robustness.py`; `src/crypto_movement/reporting/model_selection.py`; `scripts/run_crypto_pilot_study.py`; `docs/crypto_movement/experiment_registry.md`; `tests/crypto_movement/training/test_search_budget.py`; `tests/crypto_movement/training/test_orchestration.py`; `tests/crypto_movement/evaluation/test_walk_forward.py`; `tests/crypto_movement/evaluation/test_robustness.py`

**Instructions:**

1. Orchestrate nested global walk-forward training, inner selection/calibration, one-time outer evaluation, artifact registration, and promotion decisions for any B0 protocol implementation.
2. Freeze search spaces/budgets before outer results and make completed outer partitions write-once.
3. Enforce identical eligible timestamps for model comparisons.
4. Produce robustness slices by outer fold/year, 1/3/5-year lookback, cadence, horizon, volatility/liquidity/regime, and asset maturity.
5. Guard the final lockbox with an explicit release action recorded in provenance.
6. Accept H0 as another registered model after merge without changing fold dates or reopening prior tests.

**Definition of done:**

- A fixture end-to-end run reproduces predictions, metrics, promotion records, and artifact identities.
- Attempts to tune after outer results or reopen the lockbox fail loudly.
- Robustness comparisons use common samples or explain exclusions.
- Trial failures and wall time/compute are retained, not filtered from the registry.

## Integration Gate

- Merge O0 first, then register H0 through the existing model protocol without changing O0-owned files unless a reviewed interface defect requires it.
- Run a small all-model orchestration over deterministic fixtures, followed by the eligible five-asset folds.
- Freeze the pilot model/calibration/threshold candidate and document whether H0 was promoted.

## This Wave Unblocks

- U0 mature/full-universe expansion.
- X0 conservative economic and prop-rule evaluation.

