"""Plan emitters (JSON + human Markdown) for the Options Desk MVP.

Stdlib only. Owns output-path construction under ``--out-dir`` (via the config
fence) and both serializers, so tests and other callers reuse one path.

Output name: ``<out-dir>/YYYY-MM-DD-HHMM-<underlying>.{json,md}``.
Every plan carries **Stop + Risk $**; CSP plans include collateral.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

MAX_THEMES = 8


def plan_key(underlying: str, *, now: datetime | None = None) -> str:
    ts = now or datetime.now(timezone.utc)
    return f"{ts:%Y-%m-%d-%H%M}-{underlying.upper()}"


def plan_to_dict(draft, *, themes: list[str] | None = None) -> dict[str, Any]:
    """Serialize a PlanDraft into the required machine dict."""
    c = draft.candidate
    themes = (themes or [])[:MAX_THEMES]  # respect max 8 themes
    return {
        "underlying": c.underlying,
        "structure": c.structure,
        "occ_symbols": c.occ_symbols,
        "qty": c.qty,
        "entry_mid": c.mid,
        "stop": draft.stop,
        "risk_usd": draft.risk_usd,
        "risk_formula": draft.risk_formula,
        "thesis": draft.thesis,
        "expiry": c.expiry,
        "strike": c.strike,
        "credit": c.credit,
        "collateral": draft.collateral,
        "themes": themes,
    }


def render_plan_md(data: dict[str, Any]) -> str:
    """Human-readable Markdown plan. Must surface Stop + Risk $ prominently."""
    lines: list[str] = []
    lines.append(f"# Options plan — {data['underlying']} {data['structure'].upper()}")
    lines.append("")
    lines.append(f"**Thesis:** {data['thesis']}")
    lines.append("")
    lines.append("## Position")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| OCC symbols | {', '.join(data['occ_symbols'])} |")
    lines.append(f"| Structure | {data['structure']} |")
    lines.append(f"| Qty | {data['qty']} |")
    lines.append(f"| Entry mid | {data['entry_mid']} |")
    lines.append(f"| Strike | {data['strike']} |")
    lines.append(f"| Expiry | {data['expiry']} |")
    lines.append(f"| Credit | {data['credit']} |")
    lines.append(f"| **Stop** | {data['stop']} |")
    lines.append(f"| **Risk $** | {data['risk_usd']}  _({data['risk_formula']})_ |")
    if data.get("collateral") is not None:
        lines.append(f"| Collateral (CSP) | {data['collateral']} |")
    lines.append("")
    if data.get("themes"):
        lines.append("## Themes")
        lines.append("")
        for t in data["themes"]:
            lines.append(f"- {t}")
        lines.append("")
    lines.append("_Paper research context — human reviews before any order._")
    return "\n".join(lines).rstrip() + "\n"


def write_plan(out_dir, draft, *, themes: list[str] | None = None) -> dict[str, Path]:
    """Write ``<key>.json`` + ``<key>.md`` under ``out_dir``. Returns paths."""
    data = plan_to_dict(draft, themes=themes)
    key = plan_key(draft.candidate.underlying)
    json_path = config.out_path(out_dir, f"{key}.json")
    md_path = config.out_path(out_dir, f"{key}.md")
    json_path.write_text(
        json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_plan_md(data), encoding="utf-8")
    return {"json": json_path, "md": md_path}
