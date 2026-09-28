"""Human Markdown embed renderer for Scout wake-context.

Stdlib only. Renders the five fixed headings, in order:
  1. Regime
  2. Vol features
  3. Ring summary
  4. Squeeze overlay (BTC/ETH/SOL)
  5. Caveats  (one line: not a trade signal)

``render_block(bundle)`` returns the exact string that is both written to
``<out_dir>/wake-context-<key>.md`` and injected by the S8 review injector, so
the two paths never diverge.
"""

from __future__ import annotations

from . import paths
from .bundle import ContextBundle

HEADINGS = (
    "Regime",
    "Vol features",
    "Ring summary",
    "Squeeze overlay (BTC/ETH/SOL)",
    "Caveats",
)


def _fmt(x: float | None, ndigits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{ndigits}f}"


def _flags(flags: list) -> str:
    return f" _(flags: {', '.join(flags)})_" if flags else ""


def _regime_section(bundle: ContextBundle) -> list[str]:
    lines = ["### Regime", ""]
    if not bundle.regime:
        lines.append("_No regime data._")
        return lines
    lines.append("| Symbol | Label | Confidence |")
    lines.append("| --- | --- | --- |")
    for sym in sorted(bundle.regime):
        r = bundle.regime[sym]
        lines.append(f"| {sym} | {r['label']} | {_fmt(r.get('confidence'), 3)} |")
    return lines


def _vol_section(bundle: ContextBundle) -> list[str]:
    lines = ["### Vol features", ""]
    if not bundle.vol_features:
        lines.append("_No volatility data._")
        return lines
    lines.append("| Symbol | RV(20) | Ratio vs ring | Forecast ratio | Expanding |")
    lines.append("| --- | --- | --- | --- | --- |")
    for sym in sorted(bundle.vol_features):
        v = bundle.vol_features[sym]
        expanding = "yes" if v.get("expansion_flag") else "no"
        lines.append(
            f"| {sym} | {_fmt(v.get('realized_vol_20'), 6)} "
            f"| {_fmt(v.get('vol_ratio_vs_ring'), 3)} "
            f"| {_fmt(v.get('vol_forecast_ratio'), 3)} | {expanding} |"
        )
    return lines


def _ring_section(bundle: ContextBundle) -> list[str]:
    lines = ["### Ring summary", ""]
    rs = bundle.ring_summary
    if not rs or not rs.get("present"):
        lines.append("_No ring data._")
        return lines
    top = rs.get("top_by_abs_z")
    if top:
        lines.append(
            f"Top by |z|: **{top['symbol']}** "
            f"(z={_fmt(top.get('z'), 2)}, residual={_fmt(top.get('residual'), 4)})"
        )
        lines.append("")
    lines.append("| Symbol | z | Residual |")
    lines.append("| --- | --- | --- |")
    for m in rs.get("members", []):
        lines.append(
            f"| {m['symbol']} | {_fmt(m.get('z'), 2)} | {_fmt(m.get('residual'), 4)} |"
        )
    return lines


def _squeeze_section(bundle: ContextBundle) -> list[str]:
    lines = ["### Squeeze overlay (BTC/ETH/SOL)", ""]
    so = bundle.squeeze_overlay
    if not so or not so.get("present") or not so.get("tags"):
        lines.append("_No squeeze data._")
        return lines
    lines.append("| Symbol | Status |")
    lines.append("| --- | --- |")
    for sym in sorted(so["tags"]):
        lines.append(f"| {sym} | {so['tags'][sym]} |")
    return lines


def _caveats_section(bundle: ContextBundle) -> list[str]:
    caveat = bundle.caveat or "Offline research context only — not a trade signal."
    return ["### Caveats", "", caveat]


def render_block(bundle: ContextBundle) -> str:
    """Return the full embed block as a single string (no file write)."""
    parts: list[list[str]] = [
        _regime_section(bundle),
        _vol_section(bundle),
        _ring_section(bundle),
        _squeeze_section(bundle),
        _caveats_section(bundle),
    ]
    body: list[str] = []
    for section in parts:
        body.extend(section)
        body.append("")  # blank line between sections
    return "\n".join(body).rstrip() + "\n"


def write_md(out_dir, bundle: ContextBundle) -> "paths.Path":
    """Write the rendered block to ``<out_dir>/wake-context-<key>.md`` (fenced)."""
    target = paths.context_md_path(out_dir, bundle.key)
    paths.assert_write_allowed(out_dir, target)
    target.write_text(render_block(bundle), encoding="utf-8")
    return target
