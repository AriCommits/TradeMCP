# Sprint 4: Causal Features and Evaluation Services

## Wave Outcome

Build the predictor tensor/context pipeline and the proper-scoring/calibration framework in parallel. Together they define the stable interface consumed by every model stage.

**Estimated effort:** 32-48 engineering hours across two agents.

## Before This Wave Starts

- Sprint 3 quality, fold, window, and batch manifests pass all leakage assertions.
- Weekend/day-of-week/Friday-entry variables remain excluded from primary features.
- Every learned transform is training-fold-local and serializable with its model package.
- Accuracy is not a primary selection metric.

## Parallel Agents

### Agent A - F0: Causal Recent-Sequence and Multiscale Features

**Files:** `src/crypto_movement/features/__init__.py`; `src/crypto_movement/features/recent.py`; `src/crypto_movement/features/context.py`; `src/crypto_movement/features/market.py`; `src/crypto_movement/features/transforms.py`; `src/crypto_movement/features/pipeline.py`; `config/crypto_movement/features.yaml`; `tests/crypto_movement/features/test_recent.py`; `tests/crypto_movement/features/test_context.py`; `tests/crypto_movement/features/test_transforms.py`; `tests/crypto_movement/features/test_causality.py`; `tests/fixtures/crypto_movement/causal_prefixes.parquet`

**Instructions:**

1. Build stationary recent features: returns, ranges, candle position, transformed activity, relative volume, flow/liquidity, funding/OI changes, market returns, and past-only beta residuals.
2. Build one-sided context: trend/acceleration, distance, multi-horizon volatility/downside risk, skew/tails, beta, liquidity, breadth, dispersion, and supported past-only seasonal state.
3. Preserve sign for return/beta/funding/flow; apply log transforms only to appropriate nonnegative variables.
4. Fit imputation, winsorization, scaling, encoding, selection, and decomposition on training data only.
5. Add a future-shifted sentinel test that must fail the causality validator.

**Definition of done:**

- Prefix recomputation exactly matches features previously computed at the same anchor.
- Feature schemas identify availability timestamps and transformations.
- Raw nominal price is not a pooled comparable feature.
- 15/30-minute outputs share semantics and differ only where cadence requires.
- Missingness is explicit; no hidden price forward-fill enters labels/features.

### Agent B - E0: Proper Metrics, Calibration, Agreement Rules, and Uncertainty

**Files:** `src/crypto_movement/evaluation/__init__.py`; `src/crypto_movement/evaluation/metrics.py`; `src/crypto_movement/evaluation/calibration.py`; `src/crypto_movement/evaluation/agreement.py`; `src/crypto_movement/evaluation/uncertainty.py`; `src/crypto_movement/reporting/performance.py`; `config/crypto_movement/evaluation.yaml`; `tests/crypto_movement/evaluation/test_metrics.py`; `tests/crypto_movement/evaluation/test_calibration.py`; `tests/crypto_movement/evaluation/test_agreement.py`; `tests/crypto_movement/evaluation/test_uncertainty.py`

**Instructions:**

1. Implement all required classification and quantile metrics with explicit class ordering and sample weights.
2. Fit calibration only on the designated inner validation segment and record that interval.
3. Select probability/agreement thresholds only inside inner validation; report precision, recall, coverage, and event count.
4. Support explicit ambiguity exclusion and conservative sensitivity policies.
5. Bootstrap contiguous time blocks and support correction/report grouping for repeated tests.
6. Always render naive and recent-rate comparators next to promoted results.

**Definition of done:**

- Metrics and calibration match hand/reference cases, including missing classes and dominant `neither`.
- APIs reject fitting on outer-test rows or mismatched fold identities.
- Quantile coverage, sharpness, pinball loss, and MFE/MAE exceedance calibration are present.
- Agreement output states that heads sharing an encoder are correlated.

## Integration Gate

- Define one stable training-batch contract containing recent sequence, causal context, label bundle, fold identity, weights, and provenance.
- Run the future-feature sentinel, preprocessing-scope, and target-column leakage tests.
- Review a rendered performance table from deterministic dummy predictions before starting model training.

## This Wave Unblocks

- B0 classical baselines and reproducible pilot training.
- All later neural, multitask, robustness, and economic evaluation.

