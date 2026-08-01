"""Collect the fixture pilot; real venue and full-universe modes fail closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_movement.config import load_pilot_config, load_project_config
from crypto_movement.data.collector import MarketDataCollector, PageCache
from crypto_movement.data.manifest import build_manifest, verify_manifest, write_manifest
from crypto_movement.data.providers import (
    CollectionMode,
    DataRequest,
    DeterministicFixtureProvider,
    UnavailableVenueProvider,
    VenueProviderUnavailable,
    load_data_config,
)
from crypto_movement.data.storage import ParquetBarStore
from crypto_movement.data.universe import (
    build_universe_snapshot,
    load_universe_config,
    write_universe_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--project-config",
        type=Path,
        default=Path("config/crypto_movement/project.yaml"),
    )
    parser.add_argument(
        "--pilot-config",
        type=Path,
        default=Path("config/crypto_movement/pilot.yaml"),
    )
    parser.add_argument(
        "--data-config",
        type=Path,
        default=Path("config/crypto_movement/data.yaml"),
    )
    parser.add_argument(
        "--universe-config",
        type=Path,
        default=Path("config/crypto_movement/universe.yaml"),
    )
    parser.add_argument("--scope", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--provider", choices=("fixture", "venue"), default=None)
    return parser


def _rooted(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    project = load_project_config(_rooted(root, args.project_config), root=root)
    pilot = load_pilot_config(_rooted(root, args.pilot_config), root=root)
    data = load_data_config(_rooted(root, args.data_config), root=root)
    universe_config = load_universe_config(_rooted(root, args.universe_config))
    snapshot = build_universe_snapshot(universe_config)

    if data.venue != universe_config.venue or data.quote_asset != universe_config.quote_asset:
        raise ValueError("data and universe venue mappings must match")
    if args.scope == "full":
        project.require_full_download_ready()

    selected_mode = CollectionMode(args.provider) if args.provider else data.mode
    if selected_mode is CollectionMode.VENUE:
        project.require_full_download_ready()
        unavailable = UnavailableVenueProvider(
            data.provider_name,
            data.minimum_request_interval_seconds,
        )
        raise VenueProviderUnavailable(
            f"{unavailable.name}: Phase 0 may be clear, but no reviewed real-venue adapter exists"
        )
    provider = DeterministicFixtureProvider(
        name=data.provider_name,
        minimum_request_interval_seconds=data.minimum_request_interval_seconds,
    )

    included = {item.canonical_asset: item for item in snapshot.included}
    assets = pilot.assets if args.scope == "pilot" else tuple(sorted(included))
    missing = sorted(set(assets) - set(included))
    if missing:
        raise ValueError(f"requested assets are absent from universe snapshot: {missing}")

    snapshot_path = write_universe_snapshot(snapshot, data.manifest_path / "universes")
    store = ParquetBarStore(data.raw_path)
    manifests: list[Path] = []
    totals = {"bars": 0, "cache_hits": 0, "provider_fetches": 0}
    for asset in assets:
        configured = data.symbol_identity(asset)
        if configured != included[asset]:
            raise ValueError(f"explicit symbol mappings disagree for {asset}")
        request = DataRequest(
            symbol=configured,
            interval=data.interval,
            start=pilot.start,
            end=pilot.end_exclusive,
            page_size=data.page_size,
        )
        collection = MarketDataCollector(provider, PageCache(data.cache_path)).collect(request)
        partitions = store.write_bars(collection.bars)
        manifest = build_manifest(
            collection,
            provider_name=provider.name,
            universe_snapshot_id=snapshot.snapshot_id,
            partition_root=data.raw_path,
            partitions=partitions,
        )
        verify_manifest(manifest, data.raw_path)
        manifests.append(write_manifest(manifest, data.manifest_path))
        totals["bars"] += len(collection.bars)
        totals["cache_hits"] += collection.cache_hits
        totals["provider_fetches"] += collection.provider_fetches

    print(
        json.dumps(
            {
                "mode": selected_mode.value,
                "scope": args.scope,
                "universe_snapshot": str(snapshot_path),
                "manifests": [str(path) for path in manifests],
                **totals,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
