"""Risk $ and Stop math for the Options Desk MVP.

Stdlib only. Formulas per ``R_REPORTING.md`` / ``STOP_POLICY.md`` (source of
truth on the box). The canonical long-premium formula is fixed by the spec:

    risk_usd = abs(entry - stop) * qty * 100        # long premium (per contract x100)

For credit structures the risk is capital-at-risk rather than premium debit:

    CSP  (cash-secured put):        risk_usd = (strike - credit) * qty * 100
    PCS  (put credit spread):       risk_usd = (width - credit)  * qty * 100

``qty`` is the number of contracts; the 100 multiplier is the standard equity
option contract size. Every plan must carry a Stop and a Risk $.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTRACT_MULTIPLIER = 100

LONG_STRUCTURES = frozenset({"long", "debit", "long_call", "long_put", "debit_spread"})
CSP_STRUCTURES = frozenset({"csp", "cash_secured_put"})
PCS_STRUCTURES = frozenset({"pcs", "put_credit_spread", "credit_spread"})


class RiskInputError(ValueError):
    """Raised when required risk inputs are missing/invalid."""


@dataclass
class RiskResult:
    structure: str
    risk_usd: float
    stop: float | None
    formula: str


def long_premium_risk(entry: float, stop: float, qty: int) -> float:
    """Risk $ for a long-premium position: abs(entry-stop) * qty * 100."""
    return abs(float(entry) - float(stop)) * int(qty) * CONTRACT_MULTIPLIER


def csp_risk(strike: float, credit: float, qty: int) -> float:
    """Capital at risk for a cash-secured put: (strike - credit) * qty * 100."""
    return max(0.0, (float(strike) - float(credit))) * int(qty) * CONTRACT_MULTIPLIER


def pcs_risk(width: float, credit: float, qty: int) -> float:
    """Max loss for a put credit spread: (width - credit) * qty * 100."""
    return max(0.0, (float(width) - float(credit))) * int(qty) * CONTRACT_MULTIPLIER


def stop_for(entry: float, *, stop_mult: float = 1.0, structure: str = "long") -> float:
    """Derive a Stop per STOP_POLICY.md.

    Default policy (documented): stop at ``stop_mult`` R below entry for long
    premium (a 1R stop = 100% of debit by default). Structures without a premium
    stop (CSP/PCS held to management) return the entry as a placeholder Stop that
    the plan text explains; callers may override with a policy-specific value.
    """
    s = (structure or "").lower()
    if s in CSP_STRUCTURES or s in PCS_STRUCTURES:
        # credit structures manage by underlying/rules; Stop echoes entry mark.
        return round(float(entry), 6)
    return round(float(entry) * (1.0 - float(stop_mult)), 6)


def compute_risk(
    structure: str,
    *,
    entry: float | None = None,
    stop: float | None = None,
    qty: int = 1,
    strike: float | None = None,
    credit: float | None = None,
    width: float | None = None,
) -> RiskResult:
    """Dispatch to the correct Risk $ formula and return a RiskResult."""
    s = (structure or "").lower()
    if s in CSP_STRUCTURES:
        if strike is None or credit is None:
            raise RiskInputError("CSP risk needs strike and credit")
        risk = csp_risk(strike, credit, qty)
        return RiskResult(s, round(risk, 2), stop, "(strike-credit)*qty*100")
    if s in PCS_STRUCTURES:
        if width is None or credit is None:
            raise RiskInputError("PCS risk needs width and credit")
        risk = pcs_risk(width, credit, qty)
        return RiskResult(s, round(risk, 2), stop, "(width-credit)*qty*100")
    # default: long premium
    if entry is None or stop is None:
        raise RiskInputError("long-premium risk needs entry and stop")
    risk = long_premium_risk(entry, stop, qty)
    return RiskResult(s or "long", round(risk, 2), stop, "abs(entry-stop)*qty*100")
