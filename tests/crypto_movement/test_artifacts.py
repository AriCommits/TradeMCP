from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta

import pytest

from crypto_movement.artifacts import (
    ArtifactProvenance,
    ArtifactRecord,
    ModelIdentity,
    PredictionMetadata,
    PreprocessorIdentity,
    canonical_json,
    stable_digest,
)
from crypto_movement.contracts import (
    FoldIdentity,
    InstrumentType,
    LabelHorizon,
    SymbolIdentity,
    VenueIdentity,
)
from crypto_movement.time import UTC


@pytest.fixture
def provenance() -> ArtifactProvenance:
    venue = VenueIdentity("fixture", InstrumentType.SPOT)
    instrument = SymbolIdentity(venue, "BTC", "USD", "BTC-USD")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    fold = FoldIdentity(
        fold_id="outer-001",
        train_start=start,
        train_end=start + timedelta(days=365),
        validation_start=start + timedelta(days=365, hours=12),
        validation_end=start + timedelta(days=395),
        test_start=start + timedelta(days=395, hours=12),
        test_end=start + timedelta(days=425),
    )
    return ArtifactProvenance(
        artifact_kind="fold_predictions",
        venue=venue,
        instrument=instrument,
        universe_snapshot_id="pilot-v1",
        data_checksum="sha256:data",
        config_checksum="sha256:config",
        code_version="git:abc123",
        fold=fold,
        model=ModelIdentity(
            "multinomial",
            "1",
            {"alpha": 0.1, "class_weights": {"up_first": 2, "neither": 1}},
        ),
        preprocessor=PreprocessorIdentity(
            "robust-scaler", "1", {"features": ["return", "range"]}
        ),
        seed=17,
        prediction_cutoff=start + timedelta(days=425),
        extra={"cadence": "15m", "horizons": {"12h", "6h", "3h", "1h"}},
    )


def test_canonical_digest_is_order_independent_for_mappings_and_sets() -> None:
    left = {
        "model": {"depth": 3, "width": 32},
        "features": {"volume", "return", "range"},
    }
    right = {
        "features": {"range", "return", "volume"},
        "model": {"width": 32, "depth": 3},
    }
    assert canonical_json(left) == canonical_json(right)
    assert stable_digest(left) == stable_digest(right)


def test_nonfinite_values_cannot_enter_artifact_identity() -> None:
    with pytest.raises(ValueError, match="finite"):
        stable_digest({"loss": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        ModelIdentity("model", "1", {"loss": float("inf")})


def test_provenance_payload_is_deeply_immutable(provenance: ArtifactProvenance) -> None:
    with pytest.raises(TypeError):
        provenance.model.parameters["alpha"] = 2  # type: ignore[index]
    assert provenance.preprocessor.parameters["features"] == ("return", "range")
    with pytest.raises(FrozenInstanceError):
        provenance.seed = 18  # type: ignore[misc]


def test_artifact_identity_is_stable_for_equivalent_parameter_order(
    provenance: ArtifactProvenance,
) -> None:
    reordered_model = ModelIdentity(
        "multinomial",
        "1",
        {"class_weights": {"neither": 1, "up_first": 2}, "alpha": 0.1},
    )
    reordered_extra = {"horizons": {"1h", "3h", "6h", "12h"}, "cadence": "15m"}
    reordered = replace(provenance, model=reordered_model, extra=reordered_extra)
    assert reordered.identity == provenance.identity
    assert str(provenance.identity).startswith("crypto-artifact-v1-")


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("artifact_kind", "model_package"),
        ("universe_snapshot_id", "pilot-v2"),
        ("data_checksum", "sha256:new-data"),
        ("config_checksum", "sha256:new-config"),
        ("code_version", "git:def456"),
        ("seed", 18),
    ],
)
def test_artifact_identity_changes_with_relevant_provenance(
    provenance: ArtifactProvenance,
    field_name: str,
    replacement: object,
) -> None:
    changed = replace(provenance, **{field_name: replacement})
    assert changed.identity != provenance.identity


def test_model_preprocessor_fold_and_cutoff_change_identity(
    provenance: ArtifactProvenance,
) -> None:
    changes = (
        replace(provenance, model=ModelIdentity("tcn", "1", {"width": 16})),
        replace(
            provenance,
            preprocessor=PreprocessorIdentity("robust-scaler", "2", {"features": ["return"]}),
        ),
        replace(provenance, fold=replace(provenance.fold, fold_id="outer-002")),
        replace(
            provenance,
            prediction_cutoff=provenance.prediction_cutoff + timedelta(minutes=15),
        ),
    )
    assert all(item.identity != provenance.identity for item in changes)


def test_venue_and_instrument_must_match(provenance: ArtifactProvenance) -> None:
    other_venue = VenueIdentity("other", InstrumentType.SPOT)
    with pytest.raises(ValueError, match="must match"):
        replace(provenance, venue=other_venue)


def test_artifact_record_validates_storage_metadata(provenance: ArtifactProvenance) -> None:
    record = ArtifactRecord(
        provenance=provenance,
        relative_path="predictions/outer-001.parquet",
        content_checksum="sha256:content",
        byte_size=1024,
        created_at=provenance.prediction_cutoff + timedelta(seconds=1),
    )
    assert record.identity == provenance.identity

    with pytest.raises(ValueError, match="artifact root"):
        replace(record, relative_path="../outside.parquet")
    with pytest.raises(ValueError, match="predate"):
        replace(record, created_at=provenance.prediction_cutoff - timedelta(seconds=1))


def test_prediction_identity_includes_horizon_and_anchor_range(
    provenance: ArtifactProvenance,
) -> None:
    latest = provenance.prediction_cutoff
    predictions = PredictionMetadata(
        provenance=provenance,
        horizon=LabelHorizon.SIX_HOURS,
        earliest_anchor=latest - timedelta(days=30),
        latest_anchor=latest,
        row_count=100,
        generated_at=latest + timedelta(seconds=1),
    )
    assert replace(predictions, horizon=LabelHorizon.TWELVE_HOURS).identity != predictions.identity
    assert replace(predictions, row_count=101).identity != predictions.identity
    with pytest.raises(ValueError, match="cannot exceed"):
        replace(predictions, latest_anchor=latest + timedelta(minutes=15))
