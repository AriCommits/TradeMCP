# Sprint 9: Frozen-Model Weekend Diagnostic

## Wave Outcome

Evaluate whether event incidence, probability quality, calibration, or conservative expected value changes on weekends, using only the frozen general-model predictions and rules. This wave is serial to prevent weekend findings from feeding back into selection.

**Estimated effort:** 16-24 engineering hours for one agent.

## Before This Wave Starts

- Sprint 8 produced immutable IDs for the final general model, preprocessing, calibration, thresholds, lookback, universe, folds, and cost rules.
- The weekend evaluator refuses any unfrozen or in-sample prediction rows.
- The first-generation baseline is preserved separately if available. Its previous conclusion is a comparator, not a prior to optimize toward.

## Serial Agent

### Agent A - W0: Frozen-Model Weekend Diagnostic

**Files:** `src/crypto_movement/evaluation/weekend.py`; `src/crypto_movement/reporting/weekend.py`; `config/crypto_movement/weekend.yaml`; `scripts/run_crypto_weekend_diagnostic.py`; `tests/crypto_movement/evaluation/test_weekend_slices.py`; `tests/crypto_movement/reporting/test_weekend_report.py`

**Instructions:**

1. Define tested UTC/session boundaries for weekday, Friday evening, Saturday, Sunday, and full weekend slices.
2. Evaluate frozen predictions for ETC, AVAX, SOL, each other eligible asset, and pooled results.
3. Compare observed event rates, multiclass/quantile metrics, calibration, signal coverage, and cost-aware outcomes to the already-frozen general forecast.
4. Use dependence-aware uncertainty and appropriate repeated-test reporting/correction.
5. Do not infer unconditional weekend bullishness or alternating-weekend behavior.
6. If adding a calendar feature is proposed, record it as a future model version requiring new untouched data; do not train it in this wave.

**Definition of done:**

- Slice boundaries/timezone tests cover daylight-saving transitions even though source candles are UTC.
- The evaluator rejects changed model/calibration/threshold IDs.
- Results distinguish incidence shift, calibration shift, forecast-quality shift, and economic shift.
- The report compares Gen-1 conclusions when the baseline is present and states when it is absent.
- Negative/null findings are reported without post-hoc threshold changes.

## Integration Gate

- Recompute the weekend report from the frozen prediction artifact and match its identity/hash.
- Audit every config difference from Sprint 8; only slice/report settings may differ.
- Sign off that no weekend result altered the general model or economic rules.

## This Wave Unblocks

- R0 clean-environment replay, final study, and release packaging.

