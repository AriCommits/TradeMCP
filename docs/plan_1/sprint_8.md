# Sprint 8: Universe Expansion and Economic Reality Check

## Wave Outcome

Expand the frozen general-model study to broader liquid assets while independently evaluating whether its frozen predictions survive realistic costs and prop-account constraints. The lanes run in parallel and merge before any weekend slicing.

**Estimated effort:** 32-56 engineering hours across two agents, excluding download/training wall time.

## Before This Wave Starts

- Sprint 7 pilot model candidates, calibration method, thresholds, fold calendar, and search budget are frozen.
- Phase 0 venue, cost, funding, and prop-rule decisions are confirmed or every result is explicitly marked proxy-venue research.
- The full-download gate, storage budget, and rate-limit plan are approved.
- Weekend slices remain inaccessible to selection/tuning code.

## Parallel Agents

### Agent A - U0: Mature and Full-Universe Expansion

**Files:** `src/crypto_movement/data/universe_history.py`; `src/crypto_movement/evaluation/slices.py`; `src/crypto_movement/reporting/universe.py`; `config/crypto_movement/full_study.yaml`; `scripts/run_crypto_universe_study.py`; `tests/crypto_movement/data/test_universe_history.py`; `tests/crypto_movement/evaluation/test_slices.py`; `tests/crypto_movement/reporting/test_universe_report.py`

**Instructions:**

1. Expand first to 10-15 mature liquid assets and rerun quality/event gates.
2. Expand to 50-70 eligible liquid non-pegged large caps only after the mature gate passes.
3. Reconstruct point-in-time membership when feasible. Otherwise label current-survivor bias prominently and run the mature-asset sensitivity study.
4. Preserve common global cutoffs and frozen model/search/calibration rules.
5. Report pooled and per-asset outcomes, coverage, class support, and exclusion reasons.
6. Freeze the final general model package before the weekend branch starts.

**Definition of done:**

- Universe snapshots/checksums and all exclusion reasons are versioned.
- No asset exposes a contemporaneous shock across train/test boundaries.
- Quality/event reports exist for mature and full panels.
- General-model selection is complete without viewing weekend-specific performance.

### Agent B - X0: Conservative Economic and Prop-Rule Evaluation

**Files:** `src/crypto_movement/evaluation/costs.py`; `src/crypto_movement/evaluation/prop_rules.py`; `src/crypto_movement/evaluation/economic.py`; `src/crypto_movement/reporting/economic.py`; `config/crypto_movement/costs.yaml`; `scripts/run_crypto_economic_study.py`; `tests/crypto_movement/evaluation/test_costs.py`; `tests/crypto_movement/evaluation/test_prop_rules.py`; `tests/crypto_movement/evaluation/test_economic.py`

**Instructions:**

1. Apply taker fees unless maker fills are credibly modeled, plus spread, volatility/liquidity-sensitive slippage, funding, and latency.
2. Model the confirmed trailing, intraday, or end-of-day prop drawdown mechanics as research constraints.
3. Use only frozen out-of-sample predictions and inner-selected decision/agreement rules.
4. Never fill at an unavailable candle extreme or use execution information unavailable at the decision timestamp.
5. Report expected value, trade count, hit rate, average win/loss, turnover, drawdown, exposure, and cost decomposition.
6. Keep predictive-quality conclusions separate from economic/tradability conclusions.

**Definition of done:**

- Hand-worked fee/funding/drawdown cases pass with explicit units/signs.
- Higher costs have the expected monotonic impact in controlled tests.
- Missing assumptions force proxy labels/ranges rather than silent point estimates.
- Agreement rules are compared to each component at similar coverage.

## Integration Gate

- Reconcile X0's cost inputs with the exact venue/instrument represented by U0 data.
- Freeze model, preprocessing, calibration, thresholds, lookback, universe, and cost-rule artifact IDs.
- Confirm weekend reports have not been generated or inspected during selection.

## This Wave Unblocks

- W0 frozen-model weekend diagnostics.

