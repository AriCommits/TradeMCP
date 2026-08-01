# Plan 1: Second-Generation Cryptocurrency Movement Model

## Summary

Build an auditable, leakage-resistant cryptocurrency research pipeline that consumes information available at a completed 15-minute candle and forecasts first-barrier direction, terminal return, maximum favorable excursion (MFE), and maximum adverse excursion (MAE) at 1-, 3-, 6-, and 12-hour horizons. The implementation will live in a new `crypto_movement` package inside this repository so the existing `trading` and options work remains stable. The first-generation `crypto_weekend_seasonality/` project, when supplied, remains an immutable reproducible baseline.

The plan deliberately advances through data, label, feature, baseline, neural, expansion, economic, and weekend gates. It does not assume a weekend edge, connect to an execution account, or allow the final test period to become a tuning surface.

## Goals

- Produce restartable, idempotent, venue-aware 15- and 30-minute market-data pipelines with immutable Parquet raw data, provenance, integrity manifests, and quarantine reports.
- Generate reproducible competing first-event labels for +/-4% barriers at 1, 3, 6, and 12 hours, resolving intrabar ambiguity only with finer data and never guessing OHLC order.
- Construct 24-hour recent sequences and longer-history context using only information available at or before each anchor.
- Enforce globally synchronized chronological folds, a 12-hour minimum purge, optional embargoes, fold-local preprocessing, and contiguous sequential mini-batches.
- Evaluate 1-, 3-, and 5-year rolling histories, 15-minute inputs versus a 30-minute ablation, and a staged model ladder using proper classification and quantile-regression metrics.
- Freeze model, calibration, thresholds, and agreement rules before full weekend diagnostics.
- Produce cost-aware research results, reproducible model packages, and a final conclusion that may legitimately be "no robust edge."

## Non-Goals

- Automated trade execution, broker authentication, order placement, or live capital management.
- Training a weekend-specific primary model or adding weekend/day-of-week inputs before the frozen-model diagnostic.
- Treating +4% and -4% events as independent binary targets.
- Using one-minute candles or trades as predictors; finer data is label-resolution evidence only.
- Random train/test splits, global preprocessing, centered decompositions, full-series Fourier fitting, or any future-aware transformation.
- Replacing the Gen-1 project, rewriting the existing `src/trading/` architecture, or coupling this work to current uncommitted options/MCP changes.
- Claiming economic transferability from a proxy venue to a prop-firm instrument.

## Background / Context

The repository is currently a Python quantitative trading pipeline with reusable Parquet, forecast-contract, walk-forward, and reporting concepts under `src/trading/`. It does not currently contain `crypto_weekend_seasonality/`. Existing generic ideas may be adapted behind explicit interfaces, but the movement study needs stricter candle, competing-risk, sequence, and global-cutoff semantics than the current option-oriented modules provide. A separate `src/crypto_movement/` namespace keeps those semantics testable and prevents accidental changes to existing behavior.

The attached specification fixes the core research design: 96 x 15-minute observations over 24 hours are primary; 48 x 30-minute observations are an ablation; each horizon gets its own output; anchors initially stride 60 minutes; rolling histories are 1, 3, and 5 years; and weekend analysis is last. Phase 0 still requires the actual venue/instrument, fee, funding, slippage, and prop drawdown details. Reversible scaffolding and synthetic/local-fixture tests may proceed, but the full download is gated on those decisions.

Generated raw data, model weights, caches, and bulk predictions remain outside git. Code, configuration, tests, schemas, lightweight manifests, and Markdown reports are versioned. Every artifact must identify the venue, instrument, universe snapshot, data checksum, code/config version, fold, seed, model, preprocessing package, and prediction cutoff.

## Features / Tasks

### P0: Research Decisions, Environment, and Project Skeleton

**Files:** `.gitignore`; `README.md`; `pyproject.toml`; `src/crypto_movement/__init__.py`; `src/crypto_movement/config.py`; `config/crypto_movement/project.yaml`; `config/crypto_movement/pilot.yaml`; `scripts/audit_crypto_environment.py`; `docs/decision_log.md`; `docs/crypto_movement/storage_runtime_estimate.md`; `docs/crypto_movement/fold_calendar.md`; `tests/crypto_movement/test_config.py`; `tests/crypto_movement/test_environment_audit.py`

**Complexity:** M

**Depends on:** None

Create the isolated package, typed configuration loader, environment audit, git-ignore rules, and initial research documentation. Record the selected venue/API, spot versus perpetual instrument, quote currency, candle boundary convention, fee/slippage/funding assumptions, prop drawdown mechanics, data coverage, rate limits, storage estimate, compute inventory, pilot dates, outer folds, inner folds, purge/embargo, and final lockbox. Add optional ML dependencies only after compatibility with the local GPU/Python environment is verified. Do not authorize the full-universe download merely by filling placeholder defaults.

Definition of done: the configuration round-trips deterministically, the environment audit runs without secrets, unresolved production assumptions are visibly marked `BLOCKING_FULL_DOWNLOAD`, and the decision log records who/what supplied each choice and when.

### C0: Canonical Contracts, Time Semantics, and Artifact Provenance

**Files:** `src/crypto_movement/contracts.py`; `src/crypto_movement/time.py`; `src/crypto_movement/artifacts.py`; `tests/crypto_movement/test_contracts.py`; `tests/crypto_movement/test_time_semantics.py`; `tests/crypto_movement/test_artifacts.py`

**Complexity:** M

**Depends on:** None

Define immutable, typed contracts for UTC candle boundaries, completed-candle anchors, canonical venue/symbol mappings, raw and resampled bars, label horizons, class outcomes, ambiguity state, feature timestamps, fold identity, artifact identity, and model/prediction metadata. Centralize the arithmetic-to-log barrier conversion: `log(1.04)` for the upper barrier and `log(0.96)` for the lower barrier. Make invalid OHLC, naive timestamps, nonpositive prices, inconsistent horizons, and future-dated predictors unrepresentable or fail fast.

Definition of done: contract tests cover UTC requirements, interval alignment, horizon conversion, barrier constants, stable identities, and rejection of incomplete/future data.

### D0: Venue-Aware Collection, Storage, and Universe Snapshots

**Files:** `src/crypto_movement/data/__init__.py`; `src/crypto_movement/data/providers.py`; `src/crypto_movement/data/collector.py`; `src/crypto_movement/data/storage.py`; `src/crypto_movement/data/universe.py`; `src/crypto_movement/data/manifest.py`; `config/crypto_movement/data.yaml`; `config/crypto_movement/universe.yaml`; `scripts/download_crypto_pilot.py`; `tests/crypto_movement/data/test_providers.py`; `tests/crypto_movement/data/test_collector.py`; `tests/crypto_movement/data/test_storage.py`; `tests/crypto_movement/data/test_universe.py`; `tests/crypto_movement/data/test_manifest.py`

**Complexity:** L

**Depends on:** P0, C0

Implement a provider boundary for the chosen venue plus a deterministic fixture provider. The collector must be restartable, idempotent, rate-limit aware, and able to cache response pages. Store immutable raw candles as partitioned Parquet by venue, interval, symbol, year, and month; store funding/open interest where available; and generate checksummed download manifests. Freeze pilot, mature, and full-universe snapshots with every exclusion reason. The script defaults to the five-asset pilot (BTC, ETH, ETC, AVAX, SOL) and refuses full-universe mode while Phase 0 blockers remain.

Definition of done: interrupted fixture downloads resume without duplicates, the same request produces the same partition identities, provenance is complete, stablecoins/redundant wrappers can be excluded by reason, and no secrets or bulk data enter git.

### L0: Competing First-Barrier Labels and Event Catalog

**Files:** `src/crypto_movement/labels/__init__.py`; `src/crypto_movement/labels/barriers.py`; `src/crypto_movement/labels/event_catalog.py`; `config/crypto_movement/labels.yaml`; `tests/crypto_movement/labels/test_barriers.py`; `tests/crypto_movement/labels/test_ambiguity.py`; `tests/crypto_movement/labels/test_event_catalog.py`; `tests/fixtures/crypto_movement/label_cases.parquet`

**Complexity:** L

**Depends on:** C0

Generate, for each anchor and each 1/3/6/12-hour horizon, terminal log return, MFE, MAE, up/down reach indicators, first event, time to event, neither, and ambiguous state. Resolve a candle containing both barriers with one-minute/trade evidence when available; otherwise emit `ambiguous`. Support +/-1%, +/-2%, +/-4%, and volatility-normalized auxiliary catalog entries without changing the primary +/-4% target. Never forward-fill bars into a label window.

Definition of done: hand-computed fixtures pass for single hits, no hits, hits on exact boundaries, both-hit ambiguity, finer-data resolution, missing future bars, and every horizon; event counts group by symbol, year, horizon, threshold, class, and ambiguity treatment.

### Q0: Data Quality, Quarantine, and Cadence Construction

**Files:** `src/crypto_movement/data/bars.py`; `src/crypto_movement/data/quality.py`; `src/crypto_movement/data/quarantine.py`; `src/crypto_movement/reporting/__init__.py`; `src/crypto_movement/reporting/data_quality.py`; `tests/crypto_movement/data/test_bar_building.py`; `tests/crypto_movement/data/test_quality.py`; `tests/crypto_movement/data/test_quarantine.py`; `tests/crypto_movement/reporting/test_data_quality_report.py`

**Complexity:** L

**Depends on:** D0

Validate duplicates, monotonicity, interval alignment, gaps, OHLC consistency, positive prices, volume validity, stale runs, discontinuities, and extreme prints. Produce 15-minute bars and causal 30-minute bars only from complete constituent candles. Quarantine or fail explicitly; never silently repair label prices. Write `outputs/data_quality_report.parquet`, an excluded-period log, and a concise Markdown summary with provenance.

Definition of done: every required quality failure has a fixture, quarantine boundaries are deterministic, report schemas are versioned, and the five-asset pilot cannot advance while unacknowledged critical failures remain.

### S0: Global Walk-Forward Splits, Lazy Windows, and Sequential Batches

**Files:** `src/crypto_movement/splits/__init__.py`; `src/crypto_movement/splits/walk_forward.py`; `src/crypto_movement/splits/purging.py`; `src/crypto_movement/splits/manifests.py`; `src/crypto_movement/datasets/__init__.py`; `src/crypto_movement/datasets/windows.py`; `src/crypto_movement/datasets/batching.py`; `src/crypto_movement/datasets/cache.py`; `config/crypto_movement/splits.yaml`; `tests/crypto_movement/splits/test_global_cutoffs.py`; `tests/crypto_movement/splits/test_purging.py`; `tests/crypto_movement/datasets/test_windows.py`; `tests/crypto_movement/datasets/test_batches.py`

**Complexity:** L

**Depends on:** P0, C0, D0, L0

Build common timestamp cutoffs across all assets for rolling 1-, 3-, and 5-year histories, inner chronological selection folds, monthly or quarterly outer tests, a minimum 12-hour purge, optional embargo, and a final lockbox. Generate 96-step 15-minute and 48-step 30-minute windows lazily from quality-approved data. Start with a configurable 60-minute anchor stride and support 15/30-minute ablations with concurrency weights or purged sampling. Yield contiguous anchor-time blocks in chronological row order; record sequence and label endpoints.

Definition of done: `outputs/fold_manifest.parquet` and `outputs/batch_manifest_sample.parquet` schemas are reproducible; tests prove common cross-asset cutoffs, no duplicate partition membership, no target overlap, no incomplete anchors, correct oldest-to-newest order, and deterministic caching.

### F0: Causal Recent-Sequence and Multiscale Features

**Files:** `src/crypto_movement/features/__init__.py`; `src/crypto_movement/features/recent.py`; `src/crypto_movement/features/context.py`; `src/crypto_movement/features/market.py`; `src/crypto_movement/features/transforms.py`; `src/crypto_movement/features/pipeline.py`; `config/crypto_movement/features.yaml`; `tests/crypto_movement/features/test_recent.py`; `tests/crypto_movement/features/test_context.py`; `tests/crypto_movement/features/test_transforms.py`; `tests/crypto_movement/features/test_causality.py`; `tests/fixtures/crypto_movement/causal_prefixes.parquet`

**Complexity:** L

**Depends on:** Q0, S0

Implement stationary recent inputs, market-relative returns, residual returns from past-only beta, and causal longer-history summaries for trend, volatility, downside risk, skew/tails, liquidity, breadth, dispersion, and supported seasonal scales. Keep explicit weekend/day-of-week/Friday features out of the primary model. If hour-of-day is enabled, document it as general microstructure. Fit imputers, winsorization, robust scaling, encoders, feature selection, and any decomposition only on each training fold.

Definition of done: truncating the source history at an anchor reproduces exactly the features previously computed for that anchor; signed variables retain sign; no target/future OHLC columns enter feature tensors; a deliberately shifted future-feature sentinel fails the leakage suite.

### E0: Proper Metrics, Calibration, Agreement Rules, and Uncertainty

**Files:** `src/crypto_movement/evaluation/__init__.py`; `src/crypto_movement/evaluation/metrics.py`; `src/crypto_movement/evaluation/calibration.py`; `src/crypto_movement/evaluation/agreement.py`; `src/crypto_movement/evaluation/uncertainty.py`; `src/crypto_movement/reporting/performance.py`; `config/crypto_movement/evaluation.yaml`; `tests/crypto_movement/evaluation/test_metrics.py`; `tests/crypto_movement/evaluation/test_calibration.py`; `tests/crypto_movement/evaluation/test_agreement.py`; `tests/crypto_movement/evaluation/test_uncertainty.py`

**Complexity:** L

**Depends on:** L0, S0

Implement multiclass log loss, Brier scores, class PR-AUC, ECE/calibration curves, threshold precision/recall/coverage, pinball loss, empirical quantile coverage, median MAE, interval sharpness, and dependence-aware uncertainty. Provide inner-validation-only calibration and agreement-rule selection. Treat ambiguity via explicit exclusion and conservative sensitivity policies. Accuracy and ROC AUC remain secondary.

Definition of done: metrics match hand-calculated/reference cases, calibration objects reject out-of-fold fitting, threshold selection records its validation interval, bootstrap samples whole time blocks, and report tables always include naive/recent-rate comparators.

### B0: Classical Baselines and Reproducible Pilot Training

**Files:** `src/crypto_movement/models/__init__.py`; `src/crypto_movement/models/protocols.py`; `src/crypto_movement/models/baselines.py`; `src/crypto_movement/models/classical.py`; `src/crypto_movement/training/__init__.py`; `src/crypto_movement/training/registry.py`; `src/crypto_movement/training/classical.py`; `config/crypto_movement/baselines.yaml`; `scripts/run_crypto_baselines.py`; `tests/crypto_movement/models/test_baselines.py`; `tests/crypto_movement/models/test_classical.py`; `tests/crypto_movement/training/test_classical_training.py`; `tests/crypto_movement/training/test_trial_registry.py`

**Complexity:** L

**Depends on:** F0, E0

Implement global/per-asset shrunk class rates, neither classifier, volatility barrier baseline, regularized multinomial models, linear/quantile regression, and a boosted-tree baseline. Use nested chronological validation and record every config, seed, fold, metric, runtime, and failure. Emit fold-level predictions and saved preprocessing/model packages. Publish five-asset event rates before choosing loss weights.

Definition of done: a deterministic pilot run produces out-of-sample probabilities/quantiles, baseline comparisons, a trial registry, and reload-identical predictions; no randomized validation split or outer-test-guided tuning is possible through the API.

### N0: Neural Sequence Ladder (TCN First)

**Files:** `src/crypto_movement/datasets/torch.py`; `src/crypto_movement/models/tcn.py`; `src/crypto_movement/models/time_mixing.py`; `src/crypto_movement/models/patchtst.py`; `src/crypto_movement/training/neural.py`; `config/crypto_movement/neural.yaml`; `scripts/run_crypto_sequence_pilot.py`; `tests/crypto_movement/datasets/test_torch_dataset.py`; `tests/crypto_movement/models/test_tcn.py`; `tests/crypto_movement/models/test_time_mixing.py`; `tests/crypto_movement/models/test_patchtst.py`; `tests/crypto_movement/training/test_neural_training.py`

**Complexity:** L

**Depends on:** B0, F0, E0

Implement a small stateless causal TCN first, with deterministic chronological block batches, mixed precision where stable, early stopping only on inner chronological validation, and saved batch manifests. Promote it only for repeated outer-fold improvement in proper scoring, calibration, or useful-signal precision. After that gate, add lightweight time-mixing and small PatchTST-style comparators under the same folds and search budget. Compare 15/30-minute cadence and 1/3/5-year histories without changing untouched periods.

Definition of done: causality/receptive-field tests pass, chronological batches are proven, reload predictions match, failures are retained, and each higher-complexity architecture has a recorded promote/stop decision against the appropriate baseline.

### H0: Multitask Quantiles and Optional Competing-Risk Hazard

**Files:** `src/crypto_movement/models/losses.py`; `src/crypto_movement/models/hazard.py`; `src/crypto_movement/models/multitask.py`; `src/crypto_movement/training/multitask.py`; `config/crypto_movement/multitask.yaml`; `scripts/run_crypto_multitask_pilot.py`; `tests/crypto_movement/models/test_losses.py`; `tests/crypto_movement/models/test_hazard.py`; `tests/crypto_movement/models/test_multitask.py`; `tests/crypto_movement/training/test_multitask_training.py`

**Complexity:** L

**Depends on:** N0, E0

After separate heads are stable, implement shared-encoder heads for multiclass or discrete-time competing risks, terminal-return quantiles, MFE/MAE quantiles, and optional realized volatility. Hazards must be conditional on no earlier event and derive coherent cumulative horizon probabilities. Tune loss weights inside inner folds only. Agreement is a decision rule over correlated outputs, never described as independent votes.

Definition of done: hazard probabilities are nonnegative/coherent, quantiles do not cross after the configured remedy, all horizon outputs are separate, and multitask promotion is justified by held-out proper scoring/calibration/decision utility rather than training loss.

### O0: Nested Walk-Forward Selection and Robustness Orchestration

**Files:** `src/crypto_movement/training/search.py`; `src/crypto_movement/training/orchestration.py`; `src/crypto_movement/evaluation/walk_forward.py`; `src/crypto_movement/evaluation/robustness.py`; `src/crypto_movement/reporting/model_selection.py`; `scripts/run_crypto_pilot_study.py`; `docs/crypto_movement/experiment_registry.md`; `tests/crypto_movement/training/test_search_budget.py`; `tests/crypto_movement/training/test_orchestration.py`; `tests/crypto_movement/evaluation/test_walk_forward.py`; `tests/crypto_movement/evaluation/test_robustness.py`

**Complexity:** L

**Depends on:** B0, N0

Create the controlled hyperparameter/search-budget orchestrator, global nested walk-forward runner, model promotion records, final lockbox guard, and robustness slices for fold/year, lookback, cadence, horizon, regime, liquidity tier, and asset maturity. The orchestrator accepts any registered model, allowing H0 outputs to join after its parallel implementation without changing fold definitions. Outer-test results are write-once and cannot be used to extend the search budget.

Definition of done: a small end-to-end pilot reproduces fold-level predictions and promotion decisions from hashes/configs; attempting to reopen the lockbox or expand a search after outer results fails loudly; all models share identical eligible timestamps per comparison.

### U0: Mature and Full-Universe Expansion

**Files:** `src/crypto_movement/data/universe_history.py`; `src/crypto_movement/evaluation/slices.py`; `src/crypto_movement/reporting/universe.py`; `config/crypto_movement/full_study.yaml`; `scripts/run_crypto_universe_study.py`; `tests/crypto_movement/data/test_universe_history.py`; `tests/crypto_movement/evaluation/test_slices.py`; `tests/crypto_movement/reporting/test_universe_report.py`

**Complexity:** L

**Depends on:** D0, Q0, H0, O0

Expand first to 10-15 mature liquid assets, then to the eligible 50-70 asset universe after fresh quality/event-frequency gates. Prefer point-in-time membership; otherwise label current-survivor bias and run the mature-asset sensitivity analysis. Reuse frozen folds, search budgets, and promotion rules. Report pooled and per-asset outcomes without allowing an asset's future period into another asset's training data.

Definition of done: universe snapshots and exclusions are auditable, comparable common-time panels are built, current-survivor limitations are prominent when applicable, and the final general model/calibration/threshold package is frozen before W0.

### X0: Conservative Economic and Prop-Rule Evaluation

**Files:** `src/crypto_movement/evaluation/costs.py`; `src/crypto_movement/evaluation/prop_rules.py`; `src/crypto_movement/evaluation/economic.py`; `src/crypto_movement/reporting/economic.py`; `config/crypto_movement/costs.yaml`; `scripts/run_crypto_economic_study.py`; `tests/crypto_movement/evaluation/test_costs.py`; `tests/crypto_movement/evaluation/test_prop_rules.py`; `tests/crypto_movement/evaluation/test_economic.py`

**Complexity:** L

**Depends on:** P0, H0, O0

Apply predeclared taker fees, spread, volatility/liquidity-sensitive slippage, funding, latency, and trailing/intraday/end-of-day drawdown mechanics to frozen out-of-sample predictions. Never fill at an unavailable candle extreme. Evaluate preselected probability and classification/regression agreement rules for expected value, frequency, hit rate, average win/loss, turnover, exposure, and drawdown.

Definition of done: units and sign conventions have hand-worked fixtures; results change monotonically under higher costs where expected; missing venue/prop assumptions produce proxy-research labels rather than fabricated precision; and predictive value is clearly separated from tradability.

### W0: Frozen-Model Weekend Diagnostic

**Files:** `src/crypto_movement/evaluation/weekend.py`; `src/crypto_movement/reporting/weekend.py`; `config/crypto_movement/weekend.yaml`; `scripts/run_crypto_weekend_diagnostic.py`; `tests/crypto_movement/evaluation/test_weekend_slices.py`; `tests/crypto_movement/reporting/test_weekend_report.py`

**Complexity:** M

**Depends on:** U0, X0, H0, O0

Using only frozen predictions, model version, calibration, thresholds, lookback, and cost rules, compare weekdays, Friday evening, Saturday, Sunday, the full weekend, ETC/AVAX/SOL, and the pooled eligible universe. Test changes in event incidence, calibration, forecast quality, and expected value relative to the already-frozen general forecast; do not assume bullishness or alternating weekends. A calendar-feature model is a new version and requires new untouched evaluation, not a retrofit.

Definition of done: code refuses unfrozen inputs, all slice boundaries and timezone conversions are tested, multiplicity/dependence are addressed, and the report explicitly compares the first-generation conclusion when that baseline becomes available.

### R0: Reproducibility Audit, Final Study, and Release Bundle

**Files:** `README.md`; `src/crypto_movement/reporting/final_study.py`; `scripts/reproduce_crypto_sample.py`; `scripts/package_crypto_release.py`; `docs/crypto_movement/reproducibility.md`; `docs/crypto_movement/final_study.md`; `tests/crypto_movement/test_model_reload.py`; `tests/crypto_movement/test_reproducibility.py`; `tests/crypto_movement/test_release_bundle.py`

**Complexity:** L

**Depends on:** W0

Rebuild a small sample from immutable raw inputs in a clean environment, rerun selected labels/features/predictions, verify all manifests/hashes/seeds/configs/package versions, and produce the final methods/results/limitations/go-no-go study. Package code, configs, lightweight manifests, selected predictions/metrics, saved model/preprocessor metadata, and recreation instructions while excluding raw caches and unnecessarily large weights.

Definition of done: the clean replay reproduces selected predictions within declared tolerances, model reload is equivalent, the ZIP inventory and checksums validate, README instructions work, and the final report is willing to conclude no robust edge.

## New Dependencies

- Add an optional `crypto-ml` dependency group after P0 validates the environment. Expected candidates are PyTorch for neural models, LightGBM or an equivalent well-supported gradient booster, Optuna or a small internal search runner, SciPy for statistical utilities, and statsmodels only if a causal state-space baseline is promoted.
- Choose a venue SDK or CCXT only after the venue decision. Keep it behind `data/providers.py`; do not make the research package depend directly on an exchange client.
- Existing NumPy, pandas, scikit-learn, PyArrow, DuckDB, PyYAML, MLflow, matplotlib, Plotly, and requests dependencies cover much of the pilot.
- Pin exact resolved versions in the reproducibility output rather than inventing versions before the environment/GPU audit.

## File Change Summary

```text
.gitignore, README.md, pyproject.toml
config/crypto_movement/
  project.yaml, pilot.yaml, data.yaml, universe.yaml, labels.yaml
  splits.yaml, features.yaml, evaluation.yaml, baselines.yaml
  neural.yaml, multitask.yaml, full_study.yaml, costs.yaml, weekend.yaml
docs/
  decision_log.md
  crypto_movement/
    storage_runtime_estimate.md, fold_calendar.md, experiment_registry.md
    reproducibility.md, final_study.md
scripts/
  audit_crypto_environment.py, download_crypto_pilot.py
  run_crypto_baselines.py, run_crypto_sequence_pilot.py
  run_crypto_multitask_pilot.py, run_crypto_pilot_study.py
  run_crypto_universe_study.py, run_crypto_economic_study.py
  run_crypto_weekend_diagnostic.py, reproduce_crypto_sample.py
  package_crypto_release.py
src/crypto_movement/
  config.py, contracts.py, time.py, artifacts.py
  data/          # providers, collection, storage, manifests, quality, universe
  labels/        # competing barriers, ambiguity, event catalogs
  splits/        # global walk-forward cutoffs, purge/embargo, manifests
  datasets/      # lazy windows, deterministic caches, sequential batches
  features/      # recent, market-relative, multiscale causal context
  models/        # baselines, TCN, time-mixing, PatchTST, hazard, multitask
  training/      # registries, classical/neural loops, search/orchestration
  evaluation/    # metrics, calibration, robustness, costs, weekend slices
  reporting/     # data, model, economic, weekend, and final reports
tests/crypto_movement/ and tests/fixtures/crypto_movement/
```

Runtime outputs (not versioned except selected lightweight artifacts): `data/raw/crypto_movement/`, `data/interim/crypto_movement/`, `data/processed/crypto_movement/`, `models/crypto_movement/`, `outputs/crypto_movement/`, and API caches.

## Open Questions

1. What exact venue, API, spot/perpetual instrument, quote currency, candle-boundary convention, and timezone should represent the eventual prop-firm product?
2. What are the maker/taker fees, typical spread/slippage, funding history/timing, latency assumptions, and prop-account trailing/intraday/end-of-day drawdown rules?
3. Is one-minute or trade data available from the same venue for ambiguous-label resolution, and how far back does it extend?
4. Where is the Gen-1 `crypto_weekend_seasonality/` bundle? It is not present in the current repository and must be imported without editing its data, models, or outputs.
5. Can point-in-time universe membership be licensed/reconstructed, or must the main study carry a current-survivor limitation?
6. Which calendar dates are reserved as the untouched lockbox after confirming actual data coverage? The plan defaults to monthly outer tests when compute permits and quarterly otherwise, but P0 must freeze exact dates.
7. Does the local 24 GB GPU assumption still hold, and which CUDA/PyTorch combination is stable? Until audited, CPU-compatible test paths are required.
8. What gap tolerance and delisting/relisting policy are appropriate for the selected venue? Defaults must not be silently promoted from fixtures to production research.

