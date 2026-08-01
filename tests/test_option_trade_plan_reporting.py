from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading.reporting import (
    AlternativeDisposition,
    BrokerStateEvidence,
    CapitalPayoffSummary,
    DataQualityIssue,
    DataQualitySummary,
    EvidenceKind,
    EvidenceRecord,
    FeatureManifest,
    FeatureManifestEntry,
    ForecastSummary,
    InMemoryArtifactStore,
    PlanAlternative,
    QuoteSummary,
    RootedArtifactStore,
    RunMetadata,
    StressSummary,
    TradePlanReport,
    build_report_bundle,
    persist_report_bundle,
)


UTC = timezone.utc
DECISION = datetime(2026, 7, 10, 19, 55, tzinfo=UTC)


def _alternative(
    candidate_id: str, disposition: AlternativeDisposition, *, strike: str
) -> PlanAlternative:
    return PlanAlternative(
        candidate_id=candidate_id,
        label=f"SPY {strike} put",
        disposition=disposition,
        rationale=("best tail-adjusted score",)
        if disposition is AlternativeDisposition.SELECTED
        else ("relative spread exceeded policy",),
        quote=QuoteSummary(
            contract_id=f"SPY-{strike}-P",
            observed_at_utc=datetime(2026, 7, 10, 19, 54, tzinfo=UTC),
            bid=Decimal("1.20"),
            ask=Decimal("1.30")
            if disposition is AlternativeDisposition.SELECTED
            else Decimal("1.55"),
            bid_size=120,
            ask_size=85,
        ),
        capital_payoff=CapitalPayoffSummary(
            currency="USD",
            capital_required=Decimal("49880"),
            premium=Decimal("120"),
            maximum_profit=Decimal("120"),
            maximum_loss=Decimal("49880"),
            break_even_underlying=Decimal("498.80"),
            assignment_obligation="Buy 100 SPY shares at USD 500 if assigned.",
        ),
        objective_score=Decimal("0.018")
        if disposition is AlternativeDisposition.SELECTED
        else None,
    )


def _report() -> TradePlanReport:
    return TradePlanReport(
        title="SPY weekend short-put research plan",
        decision_at_utc=DECISION,
        strategy_id="weekend-short-put",
        strategy_version="1.0",
        selected=_alternative("candidate-500", AlternativeDisposition.SELECTED, strike="500"),
        rejected=(_alternative("candidate-495", AlternativeDisposition.REJECTED, strike="495"),),
        forecasts=(
            ForecastSummary(
                forecast_id="forecast-gap-1",
                target="overnight_gap",
                horizon="1 overnight interval",
                point_estimate=Decimal("-0.002"),
                unit="decimal return",
                training_cutoff_utc=datetime(2026, 7, 10, 19, 45, tzinfo=UTC),
                calibration_metrics={"mae": Decimal("0.006"), "coverage": Decimal("0.91")},
            ),
        ),
        stresses=(
            StressSummary(
                stress_result_id="stress-1",
                scenario_count=16,
                worst_scenario_id="spot-down-10",
                worst_pnl=Decimal("-4880"),
                best_scenario_id="spot-flat",
                best_pnl=Decimal("120"),
                axes=("spot", "iv", "time", "liquidity"),
            ),
        ),
        evidence=(
            EvidenceRecord(
                evidence_id="obs-quote",
                kind=EvidenceKind.OBSERVATION,
                label="NBBO",
                value="1.20 x 1.30",
                source_id="saved-chain-42",
                as_of_utc=datetime(2026, 7, 10, 19, 54, tzinfo=UTC),
            ),
            EvidenceRecord(
                evidence_id="est-gap",
                kind=EvidenceKind.ESTIMATE,
                label="weekend gap",
                value="-0.002 decimal return",
                source_id="forecast-gap-1",
                as_of_utc=datetime(2026, 7, 10, 19, 45, tzinfo=UTC),
            ),
            EvidenceRecord(
                evidence_id="sim-tail",
                kind=EvidenceKind.SIMULATION,
                label="worst stress P&L",
                value="USD -4880",
                source_id="stress-1",
                as_of_utc=datetime(2026, 7, 10, 19, 55, tzinfo=UTC),
            ),
            EvidenceRecord(
                evidence_id="broker-bp",
                kind=EvidenceKind.BROKER_STATE,
                label="option buying power",
                value="USD 75000",
                source_id="paper-broker-snapshot",
                as_of_utc=datetime(2026, 7, 10, 19, 53, tzinfo=UTC),
            ),
        ),
        broker_state=BrokerStateEvidence(
            adapter_id="paper-broker",
            account_id_redacted="***4321",
            observed_at_utc=datetime(2026, 7, 10, 19, 53, tzinfo=UTC),
            option_buying_power=Decimal("75000"),
            option_approval_level=2,
            capabilities_version="2026-07",
        ),
        data_quality=DataQualitySummary(
            checked_at_utc=DECISION,
            source_count=3,
            accepted_record_count=410,
            rejected_record_count=1,
            issues=(
                DataQualityIssue(
                    code="STALE_ALT",
                    severity="warning",
                    source_id="candidate-495",
                    message="Rejected alternative quote exceeded spread threshold.",
                ),
            ),
        ),
        feature_manifest=FeatureManifest(
            manifest_id="features-v4",
            features=(
                FeatureManifestEntry(
                    name="overnight_gap_20d",
                    version="1.1",
                    source_id="daily-bars-v3",
                    available_at_utc=datetime(2026, 7, 10, 19, 45, tzinfo=UTC),
                ),
            ),
        ),
        run=RunMetadata(
            run_id="run-20260710-001",
            correlation_id="corr-plan-007",
            generated_at_utc=datetime(2026, 7, 10, 19, 56, tzinfo=UTC),
            code_version="abc1234",
            config_version="options-v6",
            data_version="snapshot-20260710",
            input_identities=("saved-chain-42", "forecast-gap-1", "account-snapshot-3"),
        ),
        limitations=(
            "Fill prices are estimates and are not executable quotes.",
            "Weekend jump risk can exceed the historical stress grid.",
        ),
    )


def test_bundle_is_deterministic_and_json_matches_markdown_snapshot() -> None:
    first = build_report_bundle(_report(), relative_directory="research/plans")
    second = build_report_bundle(_report(), relative_directory="research/plans")

    assert first == second
    assert first.artifact_identity.startswith("trade-plan-sha256-")
    assert first.run_id == "run-20260710-001"
    assert first.correlation_id == "corr-plan-007"
    assert first.json_relative_path == f"research/plans/{first.artifact_identity}.json"
    assert first.markdown_relative_path == f"research/plans/{first.artifact_identity}.md"
    payload = json.loads(first.json_text)
    assert payload["artifact_identity"] == first.artifact_identity
    assert payload["report"]["selected"]["candidate_id"] == "candidate-500"
    assert payload["report"]["rejected"][0]["candidate_id"] == "candidate-495"

    expected_fragments = (
        "# SPY weekend short-put research plan",
        "Research plan only. This artifact does not submit or authorize a broker order.",
        "spread 0.10",
        "## Rejected alternatives",
        "calibration: coverage=0.91, mae=0.006",
        "16 scenarios across spot, iv, time, liquidity",
        "**observation** `obs-quote`",
        "**estimate** `est-gap`",
        "**simulation** `sim-tail`",
        "**broker_state** `broker-bp`",
        "Rejected alternative quote exceeded spread threshold.",
        "Fill prices are estimates and are not executable quotes.",
    )
    for fragment in expected_fragments:
        assert fragment in first.markdown_text


def test_in_memory_and_explicit_root_persistence(tmp_path: Path) -> None:
    bundle = build_report_bundle(_report())
    memory = InMemoryArtifactStore()
    persist_report_bundle(bundle, memory)
    assert memory.artifacts[bundle.json_relative_path] == bundle.json_text
    assert memory.artifacts[bundle.markdown_relative_path] == bundle.markdown_text

    rooted = RootedArtifactStore(tmp_path)
    persist_report_bundle(bundle, rooted)
    assert (tmp_path / bundle.json_relative_path).read_text(encoding="utf-8") == bundle.json_text
    assert (tmp_path / bundle.markdown_relative_path).read_text(
        encoding="utf-8"
    ) == bundle.markdown_text


@pytest.mark.parametrize("unsafe", ("../escape", "/absolute", "C:/escape", "safe/../escape"))
def test_artifact_paths_reject_unsafe_locations(unsafe: str) -> None:
    with pytest.raises(ValueError, match="artifact path"):
        build_report_bundle(_report(), relative_directory=unsafe)


def test_report_rejects_lookahead_evidence() -> None:
    report = _report()
    future = EvidenceRecord(
        evidence_id="future",
        kind=EvidenceKind.OBSERVATION,
        label="future quote",
        value="invalid",
        source_id="future-source",
        as_of_utc=datetime(2026, 7, 10, 19, 56, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="after the decision"):
        TradePlanReport(
            **{
                **{field: getattr(report, field) for field in report.__dataclass_fields__},
                "evidence": (*report.evidence, future),
            }
        )
