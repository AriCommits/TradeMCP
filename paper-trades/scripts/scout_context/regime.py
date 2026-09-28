"""Regime classification for Scout wake-context.

Stdlib only. Frozen, offline, deterministic heuristic over the loaded 5m bars.
Produces one label from a documented enum plus a confidence in ``[0, 1]``.

Enum (documented for the README and wake-review citation):
  * ``trend_up``       — persistent positive drift dominating noise.
  * ``trend_down``     — persistent negative drift dominating noise.
  * ``mean_revert``    — returns negatively autocorrelated (reversion) with
                         low net drift.
  * ``high_vol_chop``  — no clear drift, elevated realized volatility.
  * ``low_vol_chop``   — no clear drift, subdued realized volatility.
  * ``unknown``        — insufficient/degenerate data (never guesses; low conf).

Decision rule (in order):
  1. Insufficient bars -> ``unknown`` (confidence 0.0).
  2. |trend_strength| >= TREND_T where trend_strength = mean(ret)/stdev(ret):
     -> ``trend_up`` / ``trend_down``.
  3. lag-1 autocorrelation <= -REVERT_T and low drift -> ``mean_revert``.
  4. else compare realized vol to the cross-symbol median band:
     high -> ``high_vol_chop``, else ``low_vol_chop``.
Confidence scales with how decisively the winning rule cleared its threshold.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .loaders import OHLCVSeries
from .vol_features import _log_returns, _realized_vol

REGIME_ENUM = (
    "trend_up",
    "trend_down",
    "mean_revert",
    "high_vol_chop",
    "low_vol_chop",
    "unknown",
)

MIN_BARS = 21
TREND_T = 0.15  # mean/stdev of returns to call a trend
REVERT_T = 0.20  # magnitude of negative lag-1 autocorrelation to call reversion


@dataclass
class Regime:
    symbol: str
    label: str = "unknown"
    confidence: float = 0.0
    quality_flags: list[str] = field(default_factory=list)


def _clamp01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    return max(0.0, min(1.0, x))


def _autocorr_lag1(returns: list[float]) -> float | None:
    n = len(returns)
    if n < 3:
        return None
    mean = statistics.fmean(returns)
    num = sum((returns[i] - mean) * (returns[i - 1] - mean) for i in range(1, n))
    den = sum((r - mean) ** 2 for r in returns)
    if den <= 0:
        return None
    ac = num / den
    return ac if math.isfinite(ac) else None


def classify_symbol(
    series: OHLCVSeries, *, vol_high_band: float | None = None
) -> Regime:
    """Classify one symbol. ``vol_high_band`` is the cross-symbol median RV."""
    reg = Regime(symbol=series.symbol)
    closes = series.closes
    if len(closes) < MIN_BARS:
        reg.quality_flags.append(f"insufficient_bars:{len(closes)}<{MIN_BARS}")
        return reg

    rets = _log_returns(closes)[-20:]
    if len(rets) < 3:
        reg.quality_flags.append("insufficient_returns")
        return reg

    mean = statistics.fmean(rets)
    sd = _realized_vol(rets)
    if not sd or sd <= 0:
        reg.quality_flags.append("degenerate_zero_vol")
        reg.label = "low_vol_chop"
        reg.confidence = 0.2
        return reg

    trend_strength = mean / sd  # signal-to-noise of drift
    ac1 = _autocorr_lag1(rets)

    # 2. Trend
    if abs(trend_strength) >= TREND_T:
        reg.label = "trend_up" if trend_strength > 0 else "trend_down"
        # confidence grows as trend_strength clears the threshold
        reg.confidence = _clamp01((abs(trend_strength) - TREND_T) / (0.6 - TREND_T) * 0.7 + 0.3)
        return reg

    # 3. Mean reversion (low drift + negative autocorrelation)
    if ac1 is not None and ac1 <= -REVERT_T:
        reg.label = "mean_revert"
        reg.confidence = _clamp01((abs(ac1) - REVERT_T) / (0.8 - REVERT_T) * 0.6 + 0.3)
        return reg

    # 4. Chop: split by realized-vol band
    if vol_high_band is not None and math.isfinite(vol_high_band) and vol_high_band > 0:
        if sd >= vol_high_band:
            reg.label = "high_vol_chop"
            reg.confidence = _clamp01(min(sd / vol_high_band - 1.0, 1.0) * 0.5 + 0.3)
        else:
            reg.label = "low_vol_chop"
            reg.confidence = _clamp01((1.0 - sd / vol_high_band) * 0.5 + 0.3)
    else:
        # No cross-symbol band available; still avoid unknown when we have vol.
        reg.label = "low_vol_chop"
        reg.confidence = 0.25
        reg.quality_flags.append("no_vol_band")
    return reg


def classify_all(series_by_symbol: dict[str, OHLCVSeries]) -> dict[str, Regime]:
    """Classify every symbol, using the cross-symbol median RV as the band."""
    rvs: list[float] = []
    for s in series_by_symbol.values():
        rets = _log_returns(s.closes)[-20:]
        rv = _realized_vol(rets)
        if rv and math.isfinite(rv):
            rvs.append(rv)
    band = statistics.median(rvs) if rvs else None
    return {
        sym: classify_symbol(s, vol_high_band=band)
        for sym, s in series_by_symbol.items()
    }
