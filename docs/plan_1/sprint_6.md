# Sprint 6: Neural Sequence Model Ladder

## Wave Outcome

Implement and evaluate the sequence architecture ladder in scientific order: a small causal TCN first, then lightweight time-mixing and PatchTST-style comparators only after the TCN promotion decision. The work is serial because all architectures share the neural training path and because the model ladder is an experimental gate, not merely a coding dependency.

**Estimated effort:** 40-72 engineering hours for one agent, excluding GPU training wall time.

## Before This Wave Starts

- Sprint 5 baseline predictions, metrics, trial registry, and promote/stop memo are immutable.
- The neural search budget, seeds, outer folds, early-stopping policy, and comparison metrics are fixed before results.
- Chronological contiguous blocks are the default; random row sampling is forbidden.
- The local GPU/CUDA audit is complete. CPU fixture tests remain mandatory even when GPU training is enabled.

## Serial Agent

### Agent A - N0: Neural Sequence Ladder (TCN First)

**Files:** `src/crypto_movement/datasets/torch.py`; `src/crypto_movement/models/tcn.py`; `src/crypto_movement/models/time_mixing.py`; `src/crypto_movement/models/patchtst.py`; `src/crypto_movement/training/neural.py`; `config/crypto_movement/neural.yaml`; `scripts/run_crypto_sequence_pilot.py`; `tests/crypto_movement/datasets/test_torch_dataset.py`; `tests/crypto_movement/models/test_tcn.py`; `tests/crypto_movement/models/test_time_mixing.py`; `tests/crypto_movement/models/test_patchtst.py`; `tests/crypto_movement/training/test_neural_training.py`

**Instructions:**

1. Implement a stateless causal TCN with a receptive field compatible with the 96/48-step input and separate horizon outputs.
2. Consume contiguous chronological anchor blocks and preserve oldest-to-newest timesteps. Save the batch manifest and deterministic seed/state.
3. Use mixed precision only when numerically stable; early-stop on the inner chronological validation segment only.
4. Compare against Sprint 5 under the identical eligible rows, folds, calibration policy, horizons, lookbacks, and cadence.
5. Record the TCN promotion decision across multiple outer folds before running time-mixing or PatchTST studies.
6. If promoted, add small time-mixing and PatchTST-style models with controlled capacity and the same budget. Do not use pretrained time-series weights with unauditable market-history overlap.
7. Serialize architecture, preprocessing, calibration, and metadata as one reloadable package.

**Definition of done:**

- Causality and receptive-field tests prove no future sequence access.
- The data loader never randomly samples rows; whole-block shuffling is off by default and, if studied, is a named ablation.
- Saved/reloaded models reproduce selected probabilities and quantiles within declared numerical tolerances.
- 15/30-minute and 1/3/5-year comparisons use common untouched periods.
- Every architecture has a promote/stop record based on proper scoring, calibration, or useful-signal precision across multiple folds, including failed runs.

## Integration Gate

- Run the complete leakage suite, future-feature sentinel, batch-manifest checks, and model-reload tests.
- Compare wall time/memory and out-of-sample quality against classical baselines; training loss alone is not evidence.
- Freeze the selected Stage B encoder candidates before Sprint 7.

## This Wave Unblocks

- H0 multitask/competing-risk heads.
- O0 generic nested walk-forward model-selection and robustness orchestration.

