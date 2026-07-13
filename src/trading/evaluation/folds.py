"""Leakage-safe expanding and rolling point-in-time fold construction."""

from __future__ import annotations

from hashlib import sha256

from .records import FoldKind, SavedOutcomeObservation, WalkForwardConfig, WalkForwardFold


def build_folds(
    observations: tuple[SavedOutcomeObservation, ...], config: WalkForwardConfig
) -> tuple[WalkForwardFold, ...]:
    """Build folds whose labels were available strictly before each test window.

    Multiple candidates may share a decision timestamp. They stay together in a
    window so a fold cannot split contemporaneous candidate selection decisions.
    """

    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("observation ids must be unique")
    ordered = sorted(observations, key=lambda item: (item.decision_at_utc, item.observation_id))
    folds: list[WalkForwardFold] = []
    cursor = config.min_train_observations
    while cursor < len(ordered):
        # Move forward instead of splitting candidates from one decision instant.
        while (
            cursor < len(ordered)
            and cursor > 0
            and ordered[cursor - 1].decision_at_utc == ordered[cursor].decision_at_utc
        ):
            cursor += 1
        if cursor >= len(ordered):
            break
        test_start = cursor
        test_end = min(test_start + config.test_observations, len(ordered))
        while (
            test_end < len(ordered)
            and ordered[test_end].decision_at_utc == ordered[test_end - 1].decision_at_utc
        ):
            test_end += 1
        test = ordered[test_start:test_end]
        eligible_train = [
            item
            for item in ordered[:test_start]
            if item.outcome_available_at_utc < test[0].decision_at_utc
        ]
        if config.fold_kind is FoldKind.ROLLING:
            assert config.rolling_train_observations is not None
            eligible_train = eligible_train[-config.rolling_train_observations :]
        if len(eligible_train) >= config.min_train_observations:
            identity_items = [
                *(item.observation_id for item in eligible_train),
                "TEST",
                *(item.observation_id for item in test),
            ]
            identity = sha256("|".join(identity_items).encode()).hexdigest()
            folds.append(
                WalkForwardFold(
                    fold_id=f"fold-{identity}",
                    train_observation_ids=tuple(item.observation_id for item in eligible_train),
                    test_observation_ids=tuple(item.observation_id for item in test),
                    test_started_at_utc=test[0].decision_at_utc,
                    test_ended_at_utc=test[-1].decision_at_utc,
                )
            )
        cursor = test_start + config.step_observations
    return tuple(folds)
