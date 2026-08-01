# Sprint 5: Classical Baseline Gate

## Wave Outcome

Produce the first honest out-of-sample five-asset results and a reusable model/trial registry. This is intentionally serial: neural work does not begin until the relevant lower-complexity baselines exist and their results are recorded.

**Estimated effort:** 24-40 engineering hours for one agent, excluding data download and training wall time.

## Before This Wave Starts

- Sprint 4 training-batch and evaluation interfaces are frozen.
- Five-asset event counts are published before choosing class/loss weights.
- Exact outer/inner dates, 12-hour purge, optional embargo, and search budget are frozen.
- If real pilot data is unavailable, implement/test the runner on fixtures but do not claim scientific results.

## Serial Agent

### Agent A - B0: Classical Baselines and Reproducible Pilot Training

**Files:** `src/crypto_movement/models/__init__.py`; `src/crypto_movement/models/protocols.py`; `src/crypto_movement/models/baselines.py`; `src/crypto_movement/models/classical.py`; `src/crypto_movement/training/__init__.py`; `src/crypto_movement/training/registry.py`; `src/crypto_movement/training/classical.py`; `config/crypto_movement/baselines.yaml`; `scripts/run_crypto_baselines.py`; `tests/crypto_movement/models/test_baselines.py`; `tests/crypto_movement/models/test_classical.py`; `tests/crypto_movement/training/test_classical_training.py`; `tests/crypto_movement/training/test_trial_registry.py`

**Instructions:**

1. Implement global and shrunk per-asset class rates, `neither`, and recent-volatility barrier baselines.
2. Implement regularized multinomial/elastic-net classification, linear/quantile regression, and a gradient-boosted tree baseline.
3. Train/evaluate under nested purged chronological folds only; never request a randomized validation split.
4. Search a bounded, predeclared space and record every config, seed, fold, metric, runtime, artifact, and failure.
5. Serialize preprocessing with the model and emit fold-level out-of-sample probabilities/quantiles.
6. Compare each candidate to fold-specific naive/recent-rate baselines and report calibration plus signal coverage.

**Definition of done:**

- A deterministic pilot produces reload-identical predictions and complete provenance.
- The trial registry is append-only/write-once for finished outer folds.
- Model APIs cannot fit preprocessing outside the training fold.
- Results include all horizons, terminal return/MFE/MAE quantiles, ambiguity sensitivities, and 1/3/5-year lookbacks where coverage permits.
- A promote/stop memo records what a neural model must beat; weak/no-skill results are retained.

## Integration Gate

- Re-run selected folds from saved manifests and match prediction hashes/tolerances.
- Verify no outer-test result changed the search space or threshold policy.
- Review event frequency and class support before authorizing neural loss choices.

## This Wave Unblocks

- N0 small causal TCN followed, conditionally, by time-mixing and PatchTST comparators.

