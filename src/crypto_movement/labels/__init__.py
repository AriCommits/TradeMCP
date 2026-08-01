"""First-barrier labels and event-rate catalogs."""

from crypto_movement.labels.barriers import (
    AUXILIARY_ARITHMETIC_BARRIERS,
    PRIMARY_BARRIER,
    BarrierKind,
    BarrierLabel,
    BarrierSpec,
    EvidenceKind,
    FineBarEvidence,
    IncompleteLabelWindowError,
    InvalidFineEvidenceError,
    LabelConstructionError,
    TradeEvidence,
    TradeTick,
    generate_barrier_label,
    generate_required_horizon_labels,
)
from crypto_movement.labels.event_catalog import (
    AmbiguityPolicy,
    EventCatalogRow,
    build_event_catalog,
    catalog_records,
)

__all__ = [
    "AUXILIARY_ARITHMETIC_BARRIERS",
    "PRIMARY_BARRIER",
    "AmbiguityPolicy",
    "BarrierKind",
    "BarrierLabel",
    "BarrierSpec",
    "EventCatalogRow",
    "EvidenceKind",
    "FineBarEvidence",
    "IncompleteLabelWindowError",
    "InvalidFineEvidenceError",
    "LabelConstructionError",
    "TradeEvidence",
    "TradeTick",
    "build_event_catalog",
    "catalog_records",
    "generate_barrier_label",
    "generate_required_horizon_labels",
]
