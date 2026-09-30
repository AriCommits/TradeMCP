"""Acceptance + smoke tests for the Futures Desk evening session CLI (paper only).

Runs fully offline: paper-trades roots are synthesized under a per-test
temporary directory, and all writes go to a per-test temporary ``--out-dir``.
Mirrors the Plan 4 contract "Done when" checklist:

  * ``--help`` works;
  * a run with only ``--out-dir`` writes a session skeleton and exits 0;
  * a root with ``last-check.json`` also freezes marks (md + json);
  * a running-book CSV is the fallback marks source;
  * no writes ever escape ``--out-dir``;
  * no broker / Slack imports in the source.
"""

from __future__ import annotations

import json
import os

import futures_desk_session as cli
import pytest

KEY = "2026-09-28-1820"
AS_OF = "2026-09-28 18:20 CT"

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(out_dir, *extra):
    argv = ["--out-dir", str(out_dir), "--as-of", AS_OF, *extra]
    return cli.main(argv)


def _write_last_check(root, positions):
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at_chicago": "2026-09-28 18:19 CT",
        "futures_paper": {
            "equity": 10500.0,
            "pnl_pct": 5.0,
            "collateral": 4000.0,
            "starting": 10000.0,
            "total_fills": 12,
            "positions": positions,
        },
    }
    (root / "last-check.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _write_running_book(root, rows):
    slack_dir = root / "slack"
    slack_dir.mkdir(parents=True, exist_ok=True)
    header = "Desk,Symbol,Side,Qty,Entry,Stop,Risk_$,R,PnL_$,Status,Theme\n"
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['Desk']},{r['Symbol']},{r['Side']},{r['Qty']},{r['Entry']},"
            f"{r['Stop']},{r['Risk_$']},{r['R']},{r['PnL_$']},{r['Status']},{r['Theme']}\n"
        )
    (slack_dir / "paper-running-book.csv").write_text("".join(lines), encoding="utf-8")


def _read_session(out_dir):
    return (out_dir / f"{KEY}-session.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
def test_help_works(capsys):
    """--help prints usage and exits 0 (argparse SystemExit(0))."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "futures_desk_session.py" in out
    assert "--out-dir" in out


def test_refuses_without_out_dir():
    """CLI must refuse to run when --out-dir is absent (argparse exit 2)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--as-of", AS_OF])
    assert exc.value.code == 2


def test_skeleton_only_writes_session_and_exits_zero(tmp_path):
    """With only --out-dir (no root), write a session skeleton and exit 0."""
    out_dir = tmp_path / "out"
    rc = _run(out_dir)
    assert rc == 0
    assert (out_dir / f"{KEY}-session.md").exists()
    # no marks artifacts when there is no book
    assert not (out_dir / f"{KEY}-marks.md").exists()
    assert not (out_dir / f"{KEY}-marks.json").exists()

    md = _read_session(out_dir)
    assert "No paper book / marks found" in md


def test_session_contains_required_sections_and_reminders(tmp_path):
    """Skeleton must carry HOLD/TRIM/EXIT, kill lines, and STOP_POLICY bands."""
    out_dir = tmp_path / "out"
    _run(out_dir)
    md = _read_session(out_dir)

    for heading in ("## HOLD", "## TRIM", "## EXIT"):
        assert heading in md, heading

    # commodity kill lines
    assert "Hormuz reopen" in md
    assert "Brent" in md and "85" in md

    # STOP_POLICY band reminders (equity/crypto perps + commodity band)
    assert "3–6%" in md
    assert "12–20%" in md

    # paper-only / no-Slack fence present
    assert "Paper only" in md or "paper only" in md.lower()
    assert "No Slack" in md or "no Slack" in md


def test_last_check_freezes_marks(tmp_path):
    """A root with last-check.json produces marks md + json alongside session."""
    root = tmp_path / "pt"
    _write_last_check(
        root,
        {
            "PF_XBTUSD": {
                "side": "long",
                "size": 0.1,
                "entry": 60000.0,
                "mark": 61000.0,
                "u_pnl": 100.0,
                "stop": 57000.0,
                "risk$": 300.0,
                "R": 0.33,
                "status": "open",
            }
        },
    )
    out_dir = tmp_path / "out"
    rc = _run(out_dir, "--paper-trades-root", str(root))
    assert rc == 0

    marks_md = out_dir / f"{KEY}-marks.md"
    marks_json = out_dir / f"{KEY}-marks.json"
    assert marks_md.exists()
    assert marks_json.exists()

    payload = json.loads(marks_json.read_text(encoding="utf-8"))
    assert payload["source_kind"] == "last-check.json"
    assert payload["paper_only"] is True
    assert payload["equity"] == 10500.0
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["symbol"] == "PF_XBTUSD"

    # session references the freeze and embeds the marks table
    md = _read_session(out_dir)
    assert "PF_XBTUSD" in md
    assert "last-check.json" in md


def test_running_book_csv_is_fallback_source(tmp_path):
    """Without last-check.json, open Futures rows in the CSV drive the marks."""
    root = tmp_path / "pt"
    _write_running_book(
        root,
        [
            {
                "Desk": "Futures",
                "Symbol": "PF_ETHUSD",
                "Side": "long",
                "Qty": "1",
                "Entry": "2500",
                "Stop": "2300",
                "Risk_$": "200",
                "R": "0.5",
                "PnL_$": "50",
                "Status": "open",
                "Theme": "rates",
            },
            {
                # ignored: wrong desk
                "Desk": "Options",
                "Symbol": "SPY",
                "Side": "short",
                "Qty": "1",
                "Entry": "1",
                "Stop": "2",
                "Risk_$": "1",
                "R": "0",
                "PnL_$": "0",
                "Status": "open",
                "Theme": "x",
            },
            {
                # ignored: closed
                "Desk": "Futures",
                "Symbol": "PF_SOLUSD",
                "Side": "long",
                "Qty": "1",
                "Entry": "100",
                "Stop": "90",
                "Risk_$": "10",
                "R": "0",
                "PnL_$": "0",
                "Status": "closed",
                "Theme": "x",
            },
        ],
    )
    out_dir = tmp_path / "out"
    rc = _run(out_dir, "--paper-trades-root", str(root))
    assert rc == 0

    payload = json.loads((out_dir / f"{KEY}-marks.json").read_text(encoding="utf-8"))
    assert payload["source_kind"] == "paper-running-book.csv"
    symbols = [r["symbol"] for r in payload["rows"]]
    assert symbols == ["PF_ETHUSD"]  # only open Futures row survives the filter


def test_last_check_preferred_over_running_book(tmp_path):
    """When both inputs exist, last-check.json wins (first hit)."""
    root = tmp_path / "pt"
    _write_last_check(
        root,
        {"PF_XBTUSD": {"side": "long", "size": 0.1, "entry": 60000.0, "status": "open"}},
    )
    _write_running_book(
        root,
        [
            {
                "Desk": "Futures",
                "Symbol": "PF_ETHUSD",
                "Side": "long",
                "Qty": "1",
                "Entry": "2500",
                "Stop": "2300",
                "Risk_$": "200",
                "R": "0.5",
                "PnL_$": "50",
                "Status": "open",
                "Theme": "rates",
            }
        ],
    )
    out_dir = tmp_path / "out"
    _run(out_dir, "--paper-trades-root", str(root))
    payload = json.loads((out_dir / f"{KEY}-marks.json").read_text(encoding="utf-8"))
    assert payload["source_kind"] == "last-check.json"


def test_missing_root_still_writes_skeleton(tmp_path):
    """A non-existent --paper-trades-root degrades to skeleton-only, exit 0."""
    out_dir = tmp_path / "out"
    rc = _run(out_dir, "--paper-trades-root", str(tmp_path / "does-not-exist"))
    assert rc == 0
    assert (out_dir / f"{KEY}-session.md").exists()
    assert not (out_dir / f"{KEY}-marks.json").exists()


def test_out_dir_created_if_missing(tmp_path):
    """--out-dir is created when absent."""
    out_dir = tmp_path / "nested" / "out"
    assert not out_dir.exists()
    rc = _run(out_dir)
    assert rc == 0
    assert out_dir.is_dir()


def test_no_writes_outside_out_dir(tmp_path):
    """Only the expected artifacts land under --out-dir; nothing escapes."""
    root = tmp_path / "pt"
    _write_last_check(
        root,
        {"PF_XBTUSD": {"side": "long", "size": 0.1, "entry": 60000.0, "status": "open"}},
    )
    out_dir = tmp_path / "out"
    _run(out_dir, "--paper-trades-root", str(root))
    names = sorted(p.name for p in out_dir.iterdir())
    assert names == [
        f"{KEY}-marks.json",
        f"{KEY}-marks.md",
        f"{KEY}-session.md",
    ]
    # inputs untouched: root still has exactly what we wrote
    assert (root / "last-check.json").exists()


def test_assert_under_out_rejects_escape(tmp_path):
    """The write fence refuses any target resolving outside --out-dir."""
    out_dir = cli.ensure_out_dir(tmp_path / "out")
    with pytest.raises(SystemExit):
        cli.assert_under_out(out_dir, out_dir.parent / "escape.md")


def test_bad_as_of_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--out-dir", str(tmp_path / "out"), "--as-of", "not-a-date"])


def test_no_forbidden_imports():
    """Source must not import Kraken private/trade or Slack/Composio modules.

    Matches real import statements (not prose): docstrings legitimately mention
    'Composio'/'Slack' to state they are NOT used.
    """
    import pathlib
    import re

    src = pathlib.Path(_SCRIPTS_DIR) / "futures_desk_session.py"
    forbidden_re = re.compile(
        r"^\s*(?:import|from)\s+(?:krakenex|ccxt|composio|slack_sdk|slack)\b",
        re.MULTILINE,
    )
    text = src.read_text(encoding="utf-8")
    m = forbidden_re.search(text)
    assert m is None, f"forbidden import: {m.group(0)!r}"
