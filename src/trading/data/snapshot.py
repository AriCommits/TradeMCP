"""Point-in-time option-chain reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from trading.options.contracts import require_utc
from trading.options.quotes import OptionChainSnapshot, OptionQuote

from .provider import OptionsMarketDataProvider
from .quality import QuoteQualityAssessment, QuoteQualityPolicy, assess_quote
from .records import RawOptionQuoteRecord


@dataclass(frozen=True)
class ChainReconstructionResult:
    snapshot: OptionChainSnapshot
    assessments: dict[str, QuoteQualityAssessment]
    rejected_records: dict[str, RawOptionQuoteRecord]


class OptionChainReconstructor:
    def __init__(
        self, provider: OptionsMarketDataProvider, quality_policy: QuoteQualityPolicy | None = None
    ) -> None:
        self.provider = provider
        self.quality_policy = quality_policy or QuoteQualityPolicy()

    def reconstruct(
        self,
        underlying: str,
        session_date: date,
        as_of_utc: datetime,
        *,
        chain_id: str | None = None,
    ) -> ChainReconstructionResult:
        require_utc(as_of_utc, "as_of_utc")
        contracts = self.provider.contracts(underlying, as_of_utc)
        contract_ids = {contract.contract_id for contract in contracts}
        latest: dict[str, RawOptionQuoteRecord] = {}
        for record in self.provider.quote_records(underlying, as_of_utc):
            if record.contract_id in contract_ids:
                current = latest.get(record.contract_id)
                if current is None or record.as_of_utc > current.as_of_utc:
                    latest[record.contract_id] = record
        assessments: dict[str, QuoteQualityAssessment] = {}
        rejected: dict[str, RawOptionQuoteRecord] = {}
        quotes: list[OptionQuote] = []
        sources: set[str] = set()
        ingested = as_of_utc
        for contract_id in sorted(latest):
            record = latest[contract_id]
            assessment = assess_quote(record, as_of_utc, self.quality_policy)
            assessments[contract_id] = assessment
            sources.add(record.source)
            ingested = max(ingested, record.ingested_at_utc)
            if not assessment.eligible_for_snapshot:
                rejected[contract_id] = record
                continue
            assert record.bid is not None and record.ask is not None
            quotes.append(
                OptionQuote(
                    contract_id=contract_id,
                    as_of_utc=record.as_of_utc,
                    bid=record.bid,
                    ask=record.ask,
                    bid_size=record.bid_size,
                    ask_size=record.ask_size,
                    underlying_price=record.underlying_price,
                    source=record.source,
                    ingested_at_utc=record.ingested_at_utc,
                    last=record.last,
                    last_size=record.last_size,
                    quality_flags=assessment.canonical_flags,
                    source_record_id=record.source_record_id,
                )
            )
        chain_flags = tuple(
            f"{cid}:{issue.value}"
            for cid, assessment in sorted(assessments.items())
            for issue in assessment.issues
        )
        snapshot = OptionChainSnapshot(
            chain_id=chain_id or f"{underlying}-{as_of_utc.isoformat()}",
            underlying=underlying,
            session_date=session_date,
            as_of_utc=as_of_utc,
            contracts=contracts,
            quotes=tuple(quotes),
            source=",".join(sorted(sources)) or "saved-data",
            ingested_at_utc=ingested,
            quality_flags=chain_flags,
        )
        return ChainReconstructionResult(snapshot, assessments, rejected)
