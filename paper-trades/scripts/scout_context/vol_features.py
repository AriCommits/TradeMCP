"""Short-horizon volatility features for Scout wake-context.

Stdlib only (``math``, ``statistics``). All outputs are finite floats or an
explicit ``None`` with a documented sentinel flag — never NaN/inf.

Features (per symbol) documented for citation in wake-reviews and the README:
  * ``realized_vol_20`` — annualization-free realized volatility over the last
    20 log returns (sample stdev of 5m log returns). Bar-scaled, not annualized.
  * ``vol_ratio_vs_ring`` — the symbol's ``realized_vol_20`` divided by the
    cross-ring median of the same measure. > 1 means the name is more volatile
    than the ring's typical member; ~1 is in-line; < 1 is calmer.
  * ``vol_forecast_ratio`` — recent (last 6 returns) realized vol divided by the
    prior 6, a 3–12-bar-ahead expansion proxy. > 1 => expanding.
  * ``expansion_flag`` — True when ``vol_forecast_ratio`` exceeds
    ``EXPANSION_THRESHOLD``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .loaders import OHLCVSeries

REALIZED_WINDOW = 20
FORECAST_WINDOW = 6
EXPANSION_THRESHOLD = 1.25
MIN_BARS = REALIZED_WINDOW + 1  # need N+1 closes for N log returns


@dataclass
class VolFeatures:
    symbol: str
    realized_vol_20: float | None = None
    vol_ratio_vs_ring: float | None = None
    vol_forecast_ratio: float | None = None
    expansion_flag: bool = False
    quality_flags: list[str] = field(default_factory=list)


def _log_returns(closes: list[float]) -> list[float]:
    rets: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            rets.append(math.log(cur / prev))
    return rets


def _finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)


def _realized_vol(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    try:
        val = statistics.stdev(returns)
    except statistics.StatisticsError:
        return None
    return val if math.isfinite(val) else None


def compute_symbol(series: OHLCVSeries) -> VolFeatures:
    """Compute vol features for one symbol (ratio-vs-ring filled in later)."""
    vf = VolFeatures(symbol=series.symbol)
    closes = series.closes
    if len(closes) < MIN_BARS:
        vf.quality_flags.append(f"insufficient_bars:{len(closes)}<{MIN_BARS}")
        return vf

    rets = _log_returns(closes)
    window = rets[-REALIZED_WINDOW:]
    rv = _realized_vol(window)
    if not _finite(rv):
        vf.quality_flags.append("realized_vol_undefined")
        return vf
    vf.realized_vol_20 = round(rv, 10)

    # forecast: last FORECAST_WINDOW vs prior FORECAST_WINDOW
    if len(rets) >= 2 * FORECAST_WINDOW:
        recent = _realized_vol(rets[-FORECAST_WINDOW:])
        prior = _realized_vol(rets[-2 * FORECAST_WINDOW : -FORECAST_WINDOW])
        if _finite(recent) and _finite(prior) and prior > 0:
            ratio = recent / prior
            if math.isfinite(ratio):
                vf.vol_forecast_ratio = round(ratio, 10)
                vf.expansion_flag = ratio >= EXPANSION_THRESHOLD
        else:
            vf.quality_flags.append("forecast_undefined")
    else:
        vf.quality_flags.append("insufficient_bars_for_forecast")
    return vf


def compute_all(series_by_symbol: dict[str, OHLCVSeries]) -> dict[str, VolFeatures]:
    """Compute vol features for every symbol, then fill ``vol_ratio_vs_ring``.

    The ring reference is the median of finite ``realized_vol_20`` across all
    symbols with a defined value.
    """
    feats = {sym: compute_symbol(s) for sym, s in series_by_symbol.items()}

    rvs = [f.realized_vol_20 for f in feats.values() if _finite(f.realized_vol_20)]
    ring_ref = statistics.median(rvs) if rvs else None

    for f in feats.values():
        if _finite(f.realized_vol_20) and _finite(ring_ref) and ring_ref > 0:
            ratio = f.realized_vol_20 / ring_ref
            f.vol_ratio_vs_ring = round(ratio, 10) if math.isfinite(ratio) else None
            if f.vol_ratio_vs_ring is None:
                f.quality_flags.append("vol_ratio_undefined")
        else:
            f.quality_flags.append("vol_ratio_unavailable")
    return feats
