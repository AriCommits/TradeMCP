"""Read-only, fail-closed input loaders for Scout wake-context.

Stdlib only. Every loader returns typed, documented structures and *fails
closed*: missing or unreadable inputs surface as an explicit empty/absent result
carrying ``quality_flags`` rather than fabricated values. No network calls in
this module — OHLCV is read from fixture/cache files under the input root so the
CLI runs fully offline and deterministically.

No Kraken private / paper buy-sell API is imported anywhere; only public-style
OHLCV rows (from fixtures or cached files) are read.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Pairs tracked by the monitor (same universe the Scout ring uses).
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "LINK")
SQUEEZE_SYMBOLS = ("BTC", "ETH", "SOL")


@dataclass
class Bar:
    """A single 5-minute OHLCV bar. Timestamps are epoch seconds (UTC)."""

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OHLCVSeries:
    """5m OHLCV for one symbol, oldest-to-newest."""

    symbol: str
    bars: list[Bar] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.bars)

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self.bars]


@dataclass
class RingData:
    """Parsed ring.json (or the ring portion of a snapshot)."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.entries) or bool(self.raw)


@dataclass
class Snapshot:
    """Frozen wake snapshot: board + ring."""

    board: list[dict[str, Any]] = field(default_factory=list)
    ring: RingData = field(default_factory=RingData)
    ts: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.raw)


@dataclass
class SqueezeData:
    """Squeeze overlay data restricted to BTC/ETH/SOL tags."""

    tags: dict[str, Any] = field(default_factory=dict)
    present: bool = False
    quality_flags: list[str] = field(default_factory=list)


def _read_json(path: Path) -> tuple[Any, list[str]]:
    """Read JSON, returning ``(data_or_None, quality_flags)``. Fail closed."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh), []
    except FileNotFoundError:
        return None, [f"missing:{path.name}"]
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"unreadable:{path.name}:{type(exc).__name__}"]


def _resolve(root: Path | None, rel_or_abs: str | Path) -> Path:
    """Resolve an input path against the root when it is relative."""
    p = Path(rel_or_abs)
    if p.is_absolute() or root is None:
        return p
    return root / p


# --------------------------------------------------------------------------- #
# OHLCV
# --------------------------------------------------------------------------- #
def load_ohlcv_5m(
    root: Path | None,
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
    *,
    subdir: str = "feeds/ohlcv",
) -> dict[str, OHLCVSeries]:
    """Load 5m OHLCV per symbol from CSV fixtures under ``root/subdir``.

    Expected file: ``<subdir>/<SYMBOL>-5m.csv`` with a header row
    ``ts,open,high,low,close,volume`` (ts = epoch seconds, UTC). Missing files
    yield an empty series with a ``missing`` quality flag (fail closed).
    """
    out: dict[str, OHLCVSeries] = {}
    for sym in symbols:
        series = OHLCVSeries(symbol=sym)
        if root is None:
            series.quality_flags.append("no_input_root")
            out[sym] = series
            continue
        path = _resolve(root, f"{subdir}/{sym}-5m.csv")
        if not path.exists():
            series.quality_flags.append(f"missing:{path.name}")
            out[sym] = series
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        series.bars.append(
                            Bar(
                                ts=int(float(row["ts"])),
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=float(row["volume"]),
                            )
                        )
                    except (KeyError, ValueError, TypeError):
                        series.quality_flags.append("bad_row_skipped")
                        continue
        except OSError as exc:
            series.quality_flags.append(f"unreadable:{type(exc).__name__}")
        series.bars.sort(key=lambda b: b.ts)
        if not series.bars:
            series.quality_flags.append("empty")
        out[sym] = series
    return out


# --------------------------------------------------------------------------- #
# Ring / snapshot / latest
# --------------------------------------------------------------------------- #
def _parse_ring_obj(obj: Any) -> RingData:
    ring = RingData()
    if isinstance(obj, dict):
        ring.raw = obj
        entries = obj.get("ring") or obj.get("entries") or obj.get("names")
        if isinstance(entries, list):
            ring.entries = [e for e in entries if isinstance(e, dict)]
    elif isinstance(obj, list):
        ring.entries = [e for e in obj if isinstance(e, dict)]
    return ring


def load_ring(root: Path | None, path: str | Path = "feeds/signals/ring.json") -> RingData:
    resolved = _resolve(root, path)
    data, flags = _read_json(resolved)
    if data is None:
        return RingData(quality_flags=flags or ["absent"])
    ring = _parse_ring_obj(data)
    if not ring.present:
        ring.quality_flags.append("empty")
    return ring


def load_snapshot(root: Path | None, path: str | Path) -> Snapshot:
    """Load a frozen wake-snapshot-*.json (board + ring)."""
    resolved = _resolve(root, path)
    data, flags = _read_json(resolved)
    if data is None or not isinstance(data, dict):
        return Snapshot(quality_flags=flags or ["absent_or_malformed"])
    board = data.get("board")
    board_list = [b for b in board if isinstance(b, dict)] if isinstance(board, list) else []
    ring_obj = data.get("ring", {})
    ring = _parse_ring_obj(ring_obj)
    return Snapshot(
        board=board_list,
        ring=ring,
        ts=data.get("ts") or data.get("as_of") or data.get("timestamp"),
        raw=data,
    )


def load_latest(
    root: Path | None, path: str | Path = "feeds/signals/latest.json"
) -> dict[str, Any]:
    """Load latest.json (ts/alerts fallback). Returns ``{}`` when absent."""
    resolved = _resolve(root, path)
    data, flags = _read_json(resolved)
    if data is None or not isinstance(data, dict):
        return {"_quality_flags": flags or ["absent"]}
    return data


# --------------------------------------------------------------------------- #
# Squeeze
# --------------------------------------------------------------------------- #
def load_squeeze(
    root: Path | None,
    md_path: str | Path = "feeds/squeeze/latest.md",
    csv_path: str | Path = "feeds/squeeze/history.csv",
) -> SqueezeData:
    """Load squeeze overlay data (BTC/ETH/SOL tags only).

    Prefers a JSON-in-markdown or CSV history if present; returns an explicit
    ``present=False`` "absent" state otherwise. Never fabricates values.
    """
    if root is None:
        return SqueezeData(quality_flags=["no_input_root"])

    md = _resolve(root, md_path)
    if md.exists():
        try:
            text = md.read_text(encoding="utf-8")
        except OSError as exc:
            return SqueezeData(quality_flags=[f"unreadable:{type(exc).__name__}"])
        tags = _parse_squeeze_md(text)
        if tags:
            return SqueezeData(tags=tags, present=True)
        return SqueezeData(quality_flags=["md_no_tags"])

    csv_file = _resolve(root, csv_path)
    if csv_file.exists():
        tags = _parse_squeeze_csv(csv_file)
        if tags:
            return SqueezeData(tags=tags, present=True)
        return SqueezeData(quality_flags=["csv_no_tags"])

    return SqueezeData(quality_flags=["absent"])


def _parse_squeeze_md(text: str) -> dict[str, Any]:
    """Extract ``SYMBOL: state`` style tags for BTC/ETH/SOL from markdown."""
    tags: dict[str, Any] = {}
    for line in text.splitlines():
        for sym in SQUEEZE_SYMBOLS:
            # match lines like "- BTC: on" / "BTC squeeze: fired"
            lower = line.lower()
            if sym.lower() in lower and ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    tags.setdefault(sym, value)
    return tags


def _parse_squeeze_csv(path: Path) -> dict[str, Any]:
    """Take the most recent row per BTC/ETH/SOL symbol from a history CSV."""
    tags: dict[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return tags
    for row in rows:  # later rows win (most recent last)
        sym = (row.get("symbol") or row.get("sym") or "").upper()
        if sym in SQUEEZE_SYMBOLS:
            tags[sym] = {k: v for k, v in row.items() if k not in ("symbol", "sym")}
    return tags
