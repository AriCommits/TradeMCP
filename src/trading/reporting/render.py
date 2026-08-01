"""Stable Markdown projection for a canonical trade-plan report."""

from __future__ import annotations

from decimal import Decimal

from trading.reporting.records import PlanAlternative, TradePlanReport


def _decimal(value: Decimal | None) -> str:
    return "unbounded/not estimated" if value is None else format(value, "f")


def _alternative(item: PlanAlternative) -> list[str]:
    quote = item.quote
    payoff = item.capital_payoff
    score = "not scored" if item.objective_score is None else format(item.objective_score, "f")
    lines = [
        f"### {item.label} (`{item.candidate_id}`)",
        "",
        f"- Disposition: {item.disposition.value}",
        (
            f"- Quote observed: {quote.observed_at_utc.isoformat().replace('+00:00', 'Z')} "
            f"(bid {_decimal(quote.bid)}, ask {_decimal(quote.ask)}, "
            f"spread {_decimal(quote.spread)})"
        ),
        f"- Capital required: {payoff.currency} {_decimal(payoff.capital_required)}",
        f"- Premium: {payoff.currency} {_decimal(payoff.premium)}",
        f"- Maximum profit: {_decimal(payoff.maximum_profit)}",
        f"- Maximum loss: {_decimal(payoff.maximum_loss)}",
        f"- Break-even underlying: {_decimal(payoff.break_even_underlying)}",
        f"- Assignment obligation: {payoff.assignment_obligation}",
        f"- Objective score: {score}",
        f"- Rationale: {'; '.join(item.rationale)}",
        "",
    ]
    return lines


def render_markdown(report: TradePlanReport, artifact_identity: str) -> str:
    """Render without wall-clock access, locale dependence, or mutable globals."""

    lines = [
        f"# {report.title}",
        "",
        f"Artifact identity: `{artifact_identity}`  ",
        f"Run: `{report.run.run_id}`  ",
        f"Correlation: `{report.run.correlation_id}`  ",
        f"Decision time: {report.decision_at_utc.isoformat().replace('+00:00', 'Z')}  ",
        f"Strategy: `{report.strategy_id}` version `{report.strategy_version}`",
        "",
        "> Research plan only. This artifact does not submit or authorize a broker order.",
        "",
        "## Selected alternative",
        "",
        *_alternative(report.selected),
        "## Rejected alternatives",
        "",
    ]
    if report.rejected:
        for alternative in report.rejected:
            lines.extend(_alternative(alternative))
    else:
        lines.extend(["No rejected alternatives were retained.", ""])

    lines.extend(["## Forecasts and calibration", ""])
    for forecast in report.forecasts:
        calibration = (
            ", ".join(
                f"{key}={_decimal(value)}"
                for key, value in sorted(forecast.calibration_metrics.items())
            )
            or "none recorded"
        )
        lines.append(
            f"- `{forecast.forecast_id}`: {forecast.target} over {forecast.horizon} = "
            f"{_decimal(forecast.point_estimate)} {forecast.unit}; training cutoff "
            f"{forecast.training_cutoff_utc.isoformat().replace('+00:00', 'Z')}; "
            f"calibration: {calibration}"
        )
    if not report.forecasts:
        lines.append("- No forecast was used.")

    lines.extend(["", "## Stress simulations", ""])
    for stress in report.stresses:
        lines.append(
            f"- `{stress.stress_result_id}`: {stress.scenario_count} scenarios across "
            f"{', '.join(stress.axes)}; worst `{stress.worst_scenario_id}` = "
            f"{_decimal(stress.worst_pnl)}; best `{stress.best_scenario_id}` = "
            f"{_decimal(stress.best_pnl)}"
        )
    if not report.stresses:
        lines.append("- No stress simulation was supplied.")

    lines.extend(["", "## Evidence provenance", ""])
    for evidence in sorted(
        report.evidence, key=lambda value: (value.kind.value, value.evidence_id)
    ):
        lines.append(
            f"- **{evidence.kind.value}** `{evidence.evidence_id}` -- {evidence.label}: {evidence.value} "
            f"(source `{evidence.source_id}`, as of "
            f"{evidence.as_of_utc.isoformat().replace('+00:00', 'Z')})"
        )

    lines.extend(["", "## Broker state (read-only)", ""])
    if report.broker_state is None:
        lines.append("- No broker state was supplied; capital eligibility is not confirmed.")
    else:
        broker = report.broker_state
        lines.extend(
            [
                f"- Adapter: `{broker.adapter_id}`",
                f"- Account: `{broker.account_id_redacted}`",
                f"- Observed: {broker.observed_at_utc.isoformat().replace('+00:00', 'Z')}",
                f"- Option buying power: {_decimal(broker.option_buying_power)}",
                f"- Option approval level: {broker.option_approval_level}",
                f"- Capabilities version: `{broker.capabilities_version}`",
            ]
        )

    quality = report.data_quality
    lines.extend(
        [
            "",
            "## Data quality and feature manifest",
            "",
            f"- Sources checked: {quality.source_count}",
            f"- Accepted records: {quality.accepted_record_count}",
            f"- Rejected records: {quality.rejected_record_count}",
            f"- Feature manifest: `{report.feature_manifest.manifest_id}`",
        ]
    )
    for issue in quality.issues:
        lines.append(
            f"- Quality issue [{issue.severity}] `{issue.code}` from `{issue.source_id}`: "
            f"{issue.message}"
        )
    for feature in sorted(report.feature_manifest.features, key=lambda item: item.name):
        lines.append(
            f"- Feature `{feature.name}` version `{feature.version}` from `{feature.source_id}`, "
            f"available {feature.available_at_utc.isoformat().replace('+00:00', 'Z')}"
        )

    lines.extend(["", "## Run metadata and errors", ""])
    lines.extend(
        [
            f"- Code/config/data: `{report.run.code_version}` / `{report.run.config_version}` / "
            f"`{report.run.data_version}`",
            f"- Inputs: {', '.join(f'`{value}`' for value in report.run.input_identities)}",
        ]
    )
    if report.run.errors:
        for error in report.run.errors:
            lines.append(
                f"- Error `{error.code}` in `{error.component}` "
                f"(retryable={str(error.retryable).lower()}): {error.message}"
            )
    else:
        lines.append("- Errors: none")

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    return "\n".join(lines).rstrip() + "\n"
