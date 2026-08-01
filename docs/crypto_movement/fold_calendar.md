# Fold Calendar

## Fixture fold (active)

| Fold | Train | Validation | Test | Purge | Embargo |
|---|---|---|---|---:|---:|
| fixture_2024q1 | 2024-01-01 to 2024-02-01 UTC | 2024-02-01 12:00 to 2024-03-01 UTC | 2024-03-01 12:00 to 2024-04-01 UTC | 12h | 0h |

This fold validates code paths only and does not support a market conclusion.

## Candidate research calendar (not frozen)

Subject to verified venue coverage, use globally synchronized quarterly outer tests from 2023Q1 through 2025Q4 for the first full sweep, with monthly outer tests preferred when compute permits. Each training history is rolling 1, 3, or 5 years. Inner selection uses three chronological expanding blocks inside each history, with at least a 12-hour purge between adjacent partitions.

Initial embargo is 0 hours and must be revisited after measuring anchor concurrency. A candidate 2026H1 final lockbox is recorded only as a planning placeholder. Exact lockbox dates remain `BLOCKING_FULL_DOWNLOAD` and must not be opened until the universe, model, calibration, thresholds, agreement rule, and search budget are frozen.
