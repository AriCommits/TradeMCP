"""Venue-aware cryptocurrency market-data collection and storage."""

from crypto_movement.data.collector import CollectionResult, MarketDataCollector, PageCache
from crypto_movement.data.manifest import (
    DownloadManifest,
    ManifestIntegrityError,
    build_manifest,
    load_manifest,
    verify_manifest,
    write_manifest,
)
from crypto_movement.data.providers import (
    CollectionMode,
    DataCollectionConfig,
    DataRequest,
    DeterministicFixtureProvider,
    MarketDataProvider,
    ProviderError,
    ProviderPage,
    UnavailableVenueProvider,
    VenueProviderUnavailable,
    load_data_config,
)
from crypto_movement.data.storage import (
    ImmutablePartitionError,
    ParquetBarStore,
    PartitionWrite,
)
from crypto_movement.data.universe import (
    ExclusionReason,
    UniverseCandidate,
    UniverseConfig,
    UniverseExclusion,
    UniverseSnapshot,
    build_universe_snapshot,
    load_universe_config,
    write_universe_snapshot,
)

__all__ = [
    "CollectionMode",
    "CollectionResult",
    "DataCollectionConfig",
    "DataRequest",
    "DeterministicFixtureProvider",
    "DownloadManifest",
    "ExclusionReason",
    "ImmutablePartitionError",
    "ManifestIntegrityError",
    "MarketDataCollector",
    "MarketDataProvider",
    "PageCache",
    "ParquetBarStore",
    "PartitionWrite",
    "ProviderError",
    "ProviderPage",
    "UnavailableVenueProvider",
    "UniverseCandidate",
    "UniverseConfig",
    "UniverseExclusion",
    "UniverseSnapshot",
    "VenueProviderUnavailable",
    "build_manifest",
    "build_universe_snapshot",
    "load_data_config",
    "load_manifest",
    "load_universe_config",
    "verify_manifest",
    "write_manifest",
    "write_universe_snapshot",
]
