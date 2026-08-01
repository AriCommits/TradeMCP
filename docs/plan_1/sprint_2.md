# Sprint 2: Five-Asset Data and Label Primitives

## Wave Outcome

Create a restartable pilot-data lane and a rigorously tested competing first-barrier label lane. They run in parallel against the Sprint 1 contracts and meet at the pilot audit, not through shared source files.

**Estimated effort:** 24-40 engineering hours across two agents, excluding API download time.

## Before This Wave Starts

- Sprint 1 contracts and config schema are merged and passing.
- The Phase 0 gate determines whether real pilot data may be downloaded. If blocked, both agents use deterministic local fixtures.
- The primary pilot universe is BTC, ETH, ETC, AVAX, and SOL.
- One-minute/trade data is label-resolution evidence only and must never enter predictors.

## Parallel Agents

### Agent A - D0: Venue-Aware Collection, Storage, and Universe Snapshots

**Files:** `src/crypto_movement/data/__init__.py`; `src/crypto_movement/data/providers.py`; `src/crypto_movement/data/collector.py`; `src/crypto_movement/data/storage.py`; `src/crypto_movement/data/universe.py`; `src/crypto_movement/data/manifest.py`; `config/crypto_movement/data.yaml`; `config/crypto_movement/universe.yaml`; `scripts/download_crypto_pilot.py`; `tests/crypto_movement/data/test_providers.py`; `tests/crypto_movement/data/test_collector.py`; `tests/crypto_movement/data/test_storage.py`; `tests/crypto_movement/data/test_universe.py`; `tests/crypto_movement/data/test_manifest.py`

**Instructions:**

1. Implement provider protocols and a deterministic fixture provider before the selected venue adapter.
2. Make page collection restartable, idempotent, cache-aware, and rate-limit respectful.
3. Preserve base/quote volume, optional trades/flow/open interest/funding, source, and download time.
4. Write immutable Parquet partitions by venue/interval/symbol/year/month using atomic finalization and checksummed manifests.
5. Freeze universe snapshots and explicit exclusions for stablecoins, redundant wrappers, tokenized assets, inactivity, insufficient history, or illiquidity.
6. Default the CLI to the five assets and reject full-universe mode until Phase 0 is cleared.

**Definition of done:**

- Replaying or resuming fixture pages introduces no duplicates and does not mutate completed raw partitions.
- Manifest checksums detect tampering and include request/provenance metadata.
- Symbol mapping is explicit and canonical; API symbols never become implicit asset IDs.
- A blocked decision prevents a real full download but still allows fixture tests.
- Provider/network tests are isolated from the default unit suite.

### Agent B - L0: Competing First-Barrier Labels and Event Catalog

**Files:** `src/crypto_movement/labels/__init__.py`; `src/crypto_movement/labels/barriers.py`; `src/crypto_movement/labels/event_catalog.py`; `config/crypto_movement/labels.yaml`; `tests/crypto_movement/labels/test_barriers.py`; `tests/crypto_movement/labels/test_ambiguity.py`; `tests/crypto_movement/labels/test_event_catalog.py`; `tests/fixtures/crypto_movement/label_cases.parquet`

**Instructions:**

1. Compute terminal log return, MFE, MAE, barrier reaches, first event, first-hit time, neither, and ambiguity separately at 1/3/6/12 hours.
2. Use arithmetic barrier conversions from C0; never substitute symmetric +/- log thresholds.
3. Resolve both-hit 15-minute bars only from eligible finer data. Otherwise emit `ambiguous` and retain the row for sensitivity policies.
4. Reject incomplete/missing future label windows; never forward-fill them.
5. Produce event counts by symbol/year/horizon/threshold/class and ambiguity policy before loss weights are chosen.
6. Support auxiliary +/-1%, +/-2%, and volatility-normalized catalogs without changing the primary target.

**Definition of done:**

- Hand-computed fixtures pass for up-first, down-first, neither, exact touch, both-hit, finer-data resolution, and gaps.
- Each horizon is calculated independently from the anchor.
- The output schema clearly distinguishes unresolved ambiguity from neither.
- Tests prove finer data is consumed only by label resolution.

## Integration Gate

- Run D0 and L0 suites independently, then exercise labels over a small fixture dataset written through D0 storage.
- Manually audit a random label sample plus every ambiguous example in a short fixture interval.
- Do not start the five-asset network download if Sprint 1 still reports a blocking venue or storage decision.

## This Wave Unblocks

- Q0 data-quality/bar construction.
- S0 globally synchronized splits, lazy windows, and batch manifests.

