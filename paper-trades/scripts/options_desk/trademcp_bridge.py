"""TradeMCP bridge for the Options Desk MVP.

Soft-imports a local TradeMCP checkout when one exposes the expected
operations; otherwise falls back to an inline, deterministic paper
implementation. Never calls live broker adapters.

Exposed operations (stable signatures — O2..O5 depend on them):
  * screen_option_candidates(underlying, structure, dte, ...) -> list[Candidate]
  * compare_option_strategies(underlying, structures, ...)    -> list[Comparison]
  * stress_option_candidate(candidate, shocks=...)            -> StressResult
  * build_option_trade_plan(candidate, ...)                   -> PlanDraft

The inline implementation is paper-only research scaffolding: it produces
liquid-looking candidates from simple, documented rules. It is NOT a live
pricer and never places orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import risk as risk_mod

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    underlying: str
    structure: str
    occ_symbols: list[str]
    strike: float
    expiry: str
    dte: int
    mid: float
    width: float | None
    credit: float | None
    qty: int = 1
    liquidity_note: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Comparison:
    candidate: Candidate
    risk_usd: float
    credit_quality: float  # credit / risk, higher is better
    rank: int = 0


@dataclass
class StressResult:
    candidate: Candidate
    scenarios: dict[str, float]
    stop: float
    risk_usd: float


@dataclass
class PlanDraft:
    candidate: Candidate
    thesis: str
    stop: float
    risk_usd: float
    risk_formula: str
    collateral: float | None


# --------------------------------------------------------------------------- #
# Soft-import detection
# --------------------------------------------------------------------------- #
def _load_external():
    """Return an external TradeMCP module exposing the ops, or ``None``."""
    try:
        import trademcp_paper as ext  # type: ignore
    except Exception:  # noqa: BLE001 - any failure => use inline fallback
        return None
    required = (
        "screen_option_candidates",
        "compare_option_strategies",
        "stress_option_candidate",
        "build_option_trade_plan",
    )
    if all(hasattr(ext, name) for name in required):
        return ext
    return None


_EXTERNAL = _load_external()


def using_external() -> bool:
    return _EXTERNAL is not None


# --------------------------------------------------------------------------- #
# Helpers for the inline paper implementation
# --------------------------------------------------------------------------- #
def _parse_dte_range(dte: str | tuple[int, int] | None) -> tuple[int, int]:
    if dte is None:
        return (7, 14)
    if isinstance(dte, tuple):
        return dte
    text = str(dte).strip()
    if "-" in text:
        lo, hi = text.split("-", 1)
        return int(lo), int(hi)
    v = int(text)
    return v, v


def _occ(underlying: str, expiry: str, right: str, strike: float) -> str:
    # OCC-style: SPY   260930P00450000  (compact deterministic form)
    ymd = expiry.replace("-", "")[2:]
    strike_int = int(round(strike * 1000))
    return f"{underlying.upper():<6}{ymd}{right}{strike_int:08d}".replace(" ", "")


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def screen_option_candidates(
    underlying: str,
    structure: str = "csp",
    dte: str | tuple[int, int] | None = None,
    *,
    spot: float = 450.0,
    n: int = 3,
) -> list[Candidate]:
    """Return >=1 liquid candidate for the underlying/structure/dte."""
    if _EXTERNAL is not None:
        return _EXTERNAL.screen_option_candidates(underlying, structure, dte, spot=spot, n=n)

    lo, hi = _parse_dte_range(dte)
    mid_dte = (lo + hi) // 2
    expiry = f"2026-10-{max(1, min(28, mid_dte)):02d}"
    s = (structure or "csp").lower()

    candidates: list[Candidate] = []
    for i in range(max(1, n)):
        # strikes stepped ~2% OTM apart, deterministic
        strike = round(spot * (0.95 - 0.01 * i), 2)
        credit = round(strike * 0.012, 2)
        bid = round(credit - 0.05, 2)
        ask = round(credit + 0.05, 2)
        width = 5.0 if s in risk_mod.PCS_STRUCTURES else None
        candidates.append(
            Candidate(
                underlying=underlying.upper(),
                structure=s,
                occ_symbols=[_occ(underlying, expiry, "P", strike)],
                strike=strike,
                expiry=expiry,
                dte=mid_dte,
                mid=round((bid + ask) / 2, 4),
                width=width,
                credit=credit,
                liquidity_note=f"spread {round(ask - bid, 2)} wide; OI ok (paper)",
                meta={"bid": bid, "ask": ask, "spot": spot},
            )
        )
    return candidates


def compare_option_strategies(
    underlying: str,
    structures: list[str],
    *,
    spot: float = 450.0,
) -> list[Comparison]:
    """Rank >=2 structures by credit quality (credit / Risk $)."""
    if _EXTERNAL is not None:
        return _EXTERNAL.compare_option_strategies(underlying, structures, spot=spot)

    comps: list[Comparison] = []
    for structure in structures:
        cand = screen_option_candidates(underlying, structure, spot=spot, n=1)[0]
        rr = _risk_for_candidate(cand)
        credit = cand.credit or 0.0
        quality = (credit / rr.risk_usd) if rr.risk_usd > 0 else 0.0
        comps.append(Comparison(cand, rr.risk_usd, round(quality, 6)))
    comps.sort(key=lambda c: (-c.credit_quality, c.risk_usd))
    for idx, c in enumerate(comps, start=1):
        c.rank = idx
    return comps


def stress_option_candidate(
    candidate: Candidate,
    *,
    shocks: dict[str, float] | None = None,
) -> StressResult:
    """Apply deterministic spot shocks; return per-scenario P&L + Stop/Risk."""
    if _EXTERNAL is not None:
        return _EXTERNAL.stress_option_candidate(candidate, shocks=shocks)

    shocks = shocks or {"down_5pct": -0.05, "flat": 0.0, "up_5pct": 0.05}
    spot = float(candidate.meta.get("spot", candidate.strike))
    scenarios: dict[str, float] = {}
    for name, pct in shocks.items():
        shocked_spot = spot * (1.0 + pct)
        # simple intrinsic-style P&L proxy for a short put (paper research only)
        intrinsic = max(0.0, candidate.strike - shocked_spot)
        pnl = (candidate.credit or 0.0) - intrinsic
        scenarios[name] = round(pnl * candidate.qty * risk_mod.CONTRACT_MULTIPLIER, 2)
    rr = _risk_for_candidate(candidate)
    return StressResult(candidate, scenarios, rr.stop or candidate.mid, rr.risk_usd)


def build_option_trade_plan(candidate: Candidate) -> PlanDraft:
    """Assemble a plan draft with Stop + Risk $ + thesis."""
    if _EXTERNAL is not None:
        return _EXTERNAL.build_option_trade_plan(candidate)

    rr = _risk_for_candidate(candidate)
    collateral = None
    if candidate.structure in risk_mod.CSP_STRUCTURES:
        collateral = round(candidate.strike * candidate.qty * risk_mod.CONTRACT_MULTIPLIER, 2)
    thesis = (
        f"{candidate.structure.upper()} on {candidate.underlying} "
        f"{candidate.strike} exp {candidate.expiry}: collect {candidate.credit} "
        f"credit; manage per policy."
    )
    return PlanDraft(
        candidate=candidate,
        thesis=thesis,
        stop=rr.stop if rr.stop is not None else candidate.mid,
        risk_usd=rr.risk_usd,
        risk_formula=rr.formula,
        collateral=collateral,
    )


def _risk_for_candidate(candidate: Candidate) -> risk_mod.RiskResult:
    s = candidate.structure
    if s in risk_mod.CSP_STRUCTURES:
        stop = risk_mod.stop_for(candidate.mid, structure=s)
        return risk_mod.compute_risk(
            s, strike=candidate.strike, credit=candidate.credit or 0.0,
            qty=candidate.qty, stop=stop,
        )
    if s in risk_mod.PCS_STRUCTURES:
        stop = risk_mod.stop_for(candidate.mid, structure=s)
        return risk_mod.compute_risk(
            s, width=candidate.width or 0.0, credit=candidate.credit or 0.0,
            qty=candidate.qty, stop=stop,
        )
    entry = candidate.mid
    stop = risk_mod.stop_for(entry, structure=s)
    return risk_mod.compute_risk(s, entry=entry, stop=stop, qty=candidate.qty)
