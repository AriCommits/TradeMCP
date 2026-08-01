"""Lazy causal windows, deterministic caches, and chronological batches."""

from crypto_movement.datasets.batching import SequentialBlockBatcher, WindowBatch
from crypto_movement.datasets.cache import (
    CachedWindowDataset,
    WindowCacheIntegrityError,
    WindowIndexSnapshot,
    build_window_index_snapshot,
    read_window_index_cache,
    write_window_index_cache,
)
from crypto_movement.datasets.windows import (
    ApprovedBarPanel,
    BarWindow,
    LazyBarWindowDataset,
    OverlapHandling,
    WindowExclusion,
    WindowExclusionReason,
    WindowIndexEntry,
    WindowSpec,
)

__all__ = [
    "ApprovedBarPanel",
    "BarWindow",
    "CachedWindowDataset",
    "LazyBarWindowDataset",
    "OverlapHandling",
    "SequentialBlockBatcher",
    "WindowBatch",
    "WindowCacheIntegrityError",
    "WindowExclusion",
    "WindowExclusionReason",
    "WindowIndexEntry",
    "WindowIndexSnapshot",
    "WindowSpec",
    "build_window_index_snapshot",
    "read_window_index_cache",
    "write_window_index_cache",
]
