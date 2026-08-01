"""Deterministic event-count catalogs for barrier-label diagnostics."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import Enum

from crypto_movement.contracts import AmbiguityState
from crypto_movement.labels.barriers import BarrierLabel


class AmbiguityPolicy(str, Enum):
    """Declared treatment of unresolved within-candle event order."""

    RETAIN = "retain_ambiguous"
    EXCLUDE = "exclude_ambiguous"
    ASSUME_UP_FIRST = "assume_up_first"
    ASSUME_DOWN_FIRST = "assume_down_first"
    ASSUME_NEITHER = "assume_neither"


CATALOG_CLASSES = ("up_first", "down_first", "neither", "ambiguous")


@dataclass(frozen=True, slots=True)
class EventCatalogRow:
    symbol: str
    anchor_year: int
    horizon: str
    threshold_id: str
    threshold_kind: str
    upper_log_return: float
    lower_log_return: float
    outcome_class: str
    ambiguity_policy: str
    count: int
    total: int
    eligible_anchor_count: int
    rate: float
    eligible_anchor_rate: float

    def as_record(self) -> dict[str, object]:
        return asdict(self)


def _catalog_class(label: BarrierLabel, policy: AmbiguityPolicy) -> str | None:
    if label.ambiguity is not AmbiguityState.UNRESOLVED:
        if label.outcome is None:
            raise ValueError("non-ambiguous label is missing its outcome")
        return label.outcome.value
    if policy is AmbiguityPolicy.RETAIN:
        return "ambiguous"
    if policy is AmbiguityPolicy.EXCLUDE:
        return None
    return {
        AmbiguityPolicy.ASSUME_UP_FIRST: "up_first",
        AmbiguityPolicy.ASSUME_DOWN_FIRST: "down_first",
        AmbiguityPolicy.ASSUME_NEITHER: "neither",
    }[policy]


def build_event_catalog(
    labels: Iterable[BarrierLabel],
    *,
    ambiguity_policies: Iterable[AmbiguityPolicy] = (
        AmbiguityPolicy.RETAIN,
        AmbiguityPolicy.EXCLUDE,
    ),
) -> tuple[EventCatalogRow, ...]:
    """Count every class, including zeros, by the required catalog dimensions.

    ``total`` is the denominator after applying a policy.  The separate
    ``eligible_anchor_count`` remains the pre-policy denominator, so excluding
    ambiguity never hides how many eligible anchors were removed.
    """

    policies = tuple(ambiguity_policies)
    if not policies or len(set(policies)) != len(policies):
        raise ValueError("ambiguity_policies must be non-empty and unique")
    if any(not isinstance(policy, AmbiguityPolicy) for policy in policies):
        raise TypeError("ambiguity_policies must contain AmbiguityPolicy values")

    BaseKey = tuple[str, int, str, str, str, float, float]
    grouped: dict[BaseKey, list[BarrierLabel]] = defaultdict(list)
    for label in labels:
        if not isinstance(label, BarrierLabel):
            raise TypeError("catalog inputs must be BarrierLabel values")
        key = (
            label.anchor.symbol.canonical_id,
            label.anchor.anchor_timestamp.year,
            label.horizon.value,
            label.barrier.threshold_id,
            label.barrier.kind.value,
            label.barrier.upper_log_return,
            label.barrier.lower_log_return,
        )
        grouped[key].append(label)

    rows = []
    for key, group in sorted(grouped.items()):
        (
            symbol,
            year,
            horizon,
            threshold_id,
            threshold_kind,
            upper_log_return,
            lower_log_return,
        ) = key
        eligible_count = len(group)
        for policy in policies:
            policy_counts = Counter(
                outcome_class
                for label in group
                if (outcome_class := _catalog_class(label, policy)) is not None
            )
            total = sum(policy_counts.values())
            for outcome_class in CATALOG_CLASSES:
                count = policy_counts[outcome_class]
                rows.append(
                    EventCatalogRow(
                        symbol=symbol,
                        anchor_year=year,
                        horizon=horizon,
                        threshold_id=threshold_id,
                        threshold_kind=threshold_kind,
                        upper_log_return=upper_log_return,
                        lower_log_return=lower_log_return,
                        outcome_class=outcome_class,
                        ambiguity_policy=policy.value,
                        count=count,
                        total=total,
                        eligible_anchor_count=eligible_count,
                        rate=count / total if total else 0.0,
                        eligible_anchor_rate=count / eligible_count,
                    )
                )
    return tuple(rows)


def catalog_records(rows: Iterable[EventCatalogRow]) -> tuple[dict[str, object], ...]:
    """Return serialization-ready records without requiring pandas."""

    return tuple(row.as_record() for row in rows)
