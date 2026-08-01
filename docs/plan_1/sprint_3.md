# Sprint 3: Data Integrity and Chronological Dataset Construction

## Wave Outcome

Turn collected candles into quality-approved 15/30-minute panels and build leakage-safe global folds, lazy windows, and sequential batch manifests. The two lanes run in parallel, then integrate on the five-asset pilot.

**Estimated effort:** 24-36 engineering hours across two agents.

## Before This Wave Starts

- Sprint 2 collection/storage and label contracts are merged.
- Use fixture data when a real venue download remains blocked.
- Preserve raw partitions immutably; repairs belong in derived data with explicit lineage.
- Maximum label horizon is 12 hours, so every adjacent partition requires at least a 12-hour purge.

## Parallel Agents

### Agent A - Q0: Data Quality, Quarantine, and Cadence Construction

**Files:** `src/crypto_movement/data/bars.py`; `src/crypto_movement/data/quality.py`; `src/crypto_movement/data/quarantine.py`; `src/crypto_movement/reporting/__init__.py`; `src/crypto_movement/reporting/data_quality.py`; `tests/crypto_movement/data/test_bar_building.py`; `tests/crypto_movement/data/test_quality.py`; `tests/crypto_movement/data/test_quarantine.py`; `tests/crypto_movement/reporting/test_data_quality_report.py`

**Instructions:**

1. Detect every quality condition in the overview, with severity and affected interval.
2. Fail or quarantine explicitly; do not forward-fill price bars used for labels.
3. Build 30-minute candles only from complete, aligned 15-minute constituents and retain source lineage.
4. Make extreme-print checks corroboration-aware but deterministic; never silently delete data.
5. Write the required Parquet report, exclusion log, and Markdown summary under configurable output roots.

**Definition of done:**

- Corrupt fixtures trigger the correct issue/severity and deterministic quarantine interval.
- Complete 15-to-30-minute aggregation preserves OHLCV semantics and rejects incomplete pairs.
- Critical unacknowledged issues stop the pilot gate.
- Reports contain venue/symbol/partition/checksum provenance and stable schemas.

### Agent B - S0: Global Walk-Forward Splits, Lazy Windows, and Sequential Batches

**Files:** `src/crypto_movement/splits/__init__.py`; `src/crypto_movement/splits/walk_forward.py`; `src/crypto_movement/splits/purging.py`; `src/crypto_movement/splits/manifests.py`; `src/crypto_movement/datasets/__init__.py`; `src/crypto_movement/datasets/windows.py`; `src/crypto_movement/datasets/batching.py`; `src/crypto_movement/datasets/cache.py`; `config/crypto_movement/splits.yaml`; `tests/crypto_movement/splits/test_global_cutoffs.py`; `tests/crypto_movement/splits/test_purging.py`; `tests/crypto_movement/datasets/test_windows.py`; `tests/crypto_movement/datasets/test_batches.py`

**Instructions:**

1. Build common cross-asset cutoff calendars for 1/3/5-year rolling histories, inner chronological folds, outer tests, purge/embargo, and lockbox.
2. Keep all assets at a timestamp in the same partition; no correlated-asset future leakage.
3. Create lazy indexed 96 x 15-minute and 48 x 30-minute windows ending at completed anchors.
4. Default anchor stride to 60 minutes; allow 15/30-minute studies only with recorded overlap handling.
5. Yield contiguous anchor-time blocks with rows and sequence steps ordered oldest-to-newest. Never use a random row sampler.
6. Persist deterministic fold and sample batch manifests with feature/sequence/label endpoints.

**Definition of done:**

- Tests cover common cutoffs, 12-hour purge, optional embargo, no duplicates, no crossing target windows, and lockbox access denial.
- Lazy and cached windows are equivalent and do not pre-materialize the full sequence tensor.
- Batches are contiguous and chronological; their manifests reproduce membership.
- Missing or incomplete anchors are excluded with reasons.

## Integration Gate

- Run both lanes over the same small stored fixture and join only quality-approved bars to labels/windows.
- Assert every feature source timestamp is `<= anchor`, every label timestamp is `> anchor`, and each training label ends before validation/test begins.
- Generate sample `data_quality_report`, `fold_manifest`, and `batch_manifest_sample` artifacts for review.

## This Wave Unblocks

- F0 causal feature construction.
- E0 metrics, calibration, agreement, and uncertainty services.

