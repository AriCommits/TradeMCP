# Storage and Runtime Planning Estimate

These are planning ranges, not measured commitments. Re-estimate after the venue, fields, compression, coverage, universe, and GPU environment are confirmed.

## Row-count assumptions

A complete 15-minute year has approximately 35,040 bars per asset. A complete one-minute year has approximately 525,600 bars per asset.

| Scope | Assumption | Approximate 15-minute rows |
|---|---|---:|
| Fixture validation | 5 assets x 3 months | 0.04 million |
| Five-asset model pilot | 5 assets x 1 year | 0.18 million |
| Mature study | 10 assets x 5 years | 1.75 million |
| Full study | 70 assets x 5 years | 12.26 million |

One-minute/trade evidence is retained only where required to resolve label ambiguity. It is not a predictor table.

## Working storage ranges

| Scope | Raw, resolver data, caches, processed features, predictions, models |
|---|---:|
| Pilot | 0.5-3 GB |
| Mature | 10-50 GB |
| Full | 75-300 GB |

The upper ranges allow for response caches, optional trades/open interest/funding, repeated fold-local feature caches, and model artifacts. Parquet compression, actual history, and selective finer-data retention can materially reduce them.

## Runtime ranges

- Data/label fixture validation: minutes on CPU.
- Five-asset classical pilot: tens of minutes to several hours depending on folds and search budget.
- Five-asset neural ladder: several GPU-hours to multiple days depending on the frozen budget.
- Mature/full nested studies: multiple days and must be bounded before outer results are inspected.

The environment audit must record actual CPU, RAM, disk, GPU, CUDA visibility, and package versions. Current planning must not assume a 24 GB single GPU until verified; multiple GPUs are not treated as pooled memory.
