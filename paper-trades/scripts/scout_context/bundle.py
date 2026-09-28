"""Context bundle assembly + byte-stable JSON serialization for Scout.

Stdlib only. Assembles regime + vol features + ring summary + squeeze overlay
into a single context structure and serializes it to
``<out_dir>/wake-context-<key>.json``.

Byte-stability contract: two runs over identical inputs produce byte-identical
JSON *except* for the single ``generated_at`` field. This is achieved by:
  * ``sort_keys=True`` and a fixed separator/indent;
  * fixed float formatting (rounded to ``FLOAT_NDIGITS`` at build time);
  * deterministic ordering of all symbol maps and lists.

No NaN/inf is ever written: the builder validates finiteness and raises
:class:`BundleError` before serialization.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import paths
from .regime import Regime
from .ring_summary import RingSummary
from .squeeze_overlay import SqueezeOverlay
from .vol_features import VolFeatures

SCHEMA_VERSION = "1.0"
FLOAT_NDIGITS = 10


class BundleError(RuntimeError):
    """Raised when a bundle contains non-finite numbers before serialization."""


@dataclass
class ContextBundle:
    key: str
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""  # the ONLY volatile field; excluded from stability
    caveat: str = "Offline research context only — not a trade signal."
    symbols: list[str] = field(default_factory=list)
    regime: dict[str, Any] = field(default_factory=dict)
    vol_features: dict[str, Any] = field(default_factory=dict)
    ring_summary: dict[str, Any] = field(default_factory=dict)
    squeeze_overlay: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


def _round(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), FLOAT_NDIGITS)


def _assert_finite(value: Any, where: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise BundleError(f"non-finite value at {where}: {value!r}")
    if isinstance(value, dict):
        for k, v in value.items():
            _assert_finite(v, f"{where}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _assert_finite(v, f"{where}[{i}]")


def build_bundle(
    key: str,
    regimes: dict[str, Regime],
    vol: dict[str, VolFeatures],
    ring: RingSummary,
    squeeze: SqueezeOverlay,
    *,
    provenance: dict[str, Any] | None = None,
) -> ContextBundle:
    """Assemble analysis outputs into a deterministic bundle (no serialization)."""
    symbols = sorted(set(regimes) | set(vol))

    regime_map = {
        sym: {
            "label": regimes[sym].label,
            "confidence": _round(regimes[sym].confidence),
            "quality_flags": list(regimes[sym].quality_flags),
        }
        for sym in sorted(regimes)
    }

    vol_map = {
        sym: {
            "realized_vol_20": _round(vol[sym].realized_vol_20),
            "vol_ratio_vs_ring": _round(vol[sym].vol_ratio_vs_ring),
            "vol_forecast_ratio": _round(vol[sym].vol_forecast_ratio),
            "expansion_flag": bool(vol[sym].expansion_flag),
            "quality_flags": list(vol[sym].quality_flags),
        }
        for sym in sorted(vol)
    }

    ring_dict = {
        "present": ring.present,
        "count": ring.count,
        "members": [
            {
                "symbol": m["symbol"],
                "z": _round(m.get("z")),
                "residual": _round(m.get("residual")),
            }
            for m in ring.members
        ],
        "top_by_abs_z": (
            {
                "symbol": ring.top_by_abs_z["symbol"],
                "z": _round(ring.top_by_abs_z.get("z")),
                "residual": _round(ring.top_by_abs_z.get("residual")),
            }
            if ring.top_by_abs_z
            else None
        ),
        "quality_flags": list(ring.quality_flags),
    }

    squeeze_dict = {
        "present": squeeze.present,
        "tags": {k: squeeze.tags[k] for k in sorted(squeeze.tags)},
        "quality_flags": list(squeeze.quality_flags),
    }

    bundle = ContextBundle(
        key=key,
        symbols=symbols,
        regime=regime_map,
        vol_features=vol_map,
        ring_summary=ring_dict,
        squeeze_overlay=squeeze_dict,
        provenance=dict(provenance or {}),
    )

    # Validate finiteness across everything except the (empty) generated_at.
    payload = asdict(bundle)
    payload.pop("generated_at", None)
    _assert_finite(payload, "bundle")
    return bundle


def to_json(bundle: ContextBundle, *, generated_at: str | None = None) -> str:
    """Serialize a bundle to a byte-stable JSON string.

    ``generated_at`` defaults to the current UTC time; pass a fixed value for
    reproducible output in tests.
    """
    data = asdict(bundle)
    data["generated_at"] = generated_at if generated_at is not None else _now_iso()
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def stable_payload(json_text: str) -> dict[str, Any]:
    """Parse JSON and drop ``generated_at`` for byte-stability comparisons."""
    data = json.loads(json_text)
    data.pop("generated_at", None)
    return data


def write_json(
    out_dir, bundle: ContextBundle, *, generated_at: str | None = None
) -> "paths.Path":
    """Write the bundle JSON under ``out_dir`` (fenced). Returns the path."""
    target = paths.context_json_path(out_dir, bundle.key)
    paths.assert_write_allowed(out_dir, target)
    text = to_json(bundle, generated_at=generated_at)
    target.write_text(text, encoding="utf-8")
    return target


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
