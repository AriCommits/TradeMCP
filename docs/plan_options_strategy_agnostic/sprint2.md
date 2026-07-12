# Sprint 2 — Options Data and Pricing Foundation

**Status:** Complete — 2026-07-12

## Goal

Load a historical option chain at a known timestamp and compute trustworthy baseline theoretical values and Greeks without treating theory as an executable quote.

## Dependencies

- Sprint 1 canonical contracts complete.
- Timestamp and unit conventions frozen for Version 1.

## Parallel Work Groups

### Group A — Point-in-time data foundation (`D1`)

- Implement CSV/Parquet provider first.
- Normalize option contracts, quotes, daily volume/open interest, and underlying bars.
- Add partitioned Parquet storage and DuckDB query support.
- Build chain snapshots with freshness, crossed-market, zero-bid, and missing-side flags.
- Store raw/provider-derived values separately from internally derived values.

### Group B — Pricing, IV, and Greeks (`Q1`)

- Implement a canonical Python Black-Scholes-Merton baseline.
- Implement bounded IV solving with convergence diagnostics.
- Implement an American-option numerical baseline.
- Port the subtree Rust pricer behind tests only; do not expose it as the canonical path yet.
- Add Python/Rust parity fixtures and document theta/time conventions.
- Remove or explicitly report silent time/volatility clamps.

### Group C — Carry, events, and account inputs (`A1`)

- Implement rate, dividend, corporate-action, exchange-calendar, and event interfaces.
- Implement account snapshot and broker-capability records.
- Provide saved-fixture adapters so development does not require credentials.
- Track `announced_at` separately from `effective_at` for events.

## Integration Order

1. Group A publishes a stable `OptionChainSnapshot` fixture.
2. Groups B and C consume the same snapshot and time conventions.
3. Integrate pricing outputs as derived records, never by overwriting quotes.
4. Run a complete saved-chain reconstruction test.

## Exit Criteria

- A saved SPY chain can be reconstructed as of a historical timestamp.
- Stale, crossed, and incomplete quotes are handled deterministically.
- IV and Greeks pass trusted fixtures and failure-case tests.
- American price is never below the equivalent European value within tolerance.
- Python/Rust values agree within declared bounds for supported cases.
- Rates, dividends, and events used in a calculation have point-in-time provenance.

## Handoff

- Chain snapshots and pricing unblock lifecycle simulation.
- Historical normalized data unblock forecast dataset construction.
- Account/carry interfaces unblock capital modeling.
## Completion Record

Implemented:

- Typed saved CSV/Parquet provider contracts with point-in-time chain reconstruction.
- Lossless raw quote records, deterministic quality assessments, partitioned Parquet storage, and DuckDB queries.
- Validated Black-Scholes-Merton pricing, daily/percentage-point Greeks, bounded IV inversion, and a validated CRR American/European tree.
- Point-in-time rates, borrow/carry, dividends, corporate actions, exchange expiration timestamps, events, broker capabilities, and credential-free account fixtures.
- Cross-lane integration from a canonical chain and saved rate/calendar inputs through IV and Greeks.

Integration decisions:

- Missing-sided quotes are retained for audit but cannot become canonical executable quotes.
- Stale and crossed quotes are rejected by default; locked and zero-bid quotes remain explicitly flagged for downstream policy.
- Canonical Greeks use currency per calendar day for theta and currency per one percentage point for vega/rho.
- Market-input snapshots reject records announced or ingested after the decision timestamp and fail closed outside declared coverage windows.

Verified:

- Python, Django, Parquet, and DuckDB: 69 tests passed.
- Ruff: all Sprint 2 files passed.
- Scoped mypy: 22 data/account/options modules passed.
- Base Rust engine: 2 tests passed.
- Subtree Rust prototype: 31 tests passed; 8 existing compiler warnings remain.
