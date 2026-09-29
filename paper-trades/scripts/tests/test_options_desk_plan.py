"""Acceptance + smoke tests for the Options Desk plan CLI (paper only).

Offline: inputs from packaged fixtures via ``--paper-trades-root``; all writes
go to a per-test temporary ``--out-dir``.
"""

from __future__ import annotations

import glob
import json
import os

import pytest

import options_desk_plan as cli
from options_desk import config, risk

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.join(_SCRIPTS_DIR, "options_desk", "fixtures")


def _capture(capsys):
    return capsys.readouterr().out


# --------------------------------------------------------------------------- #
def test_screen_requires_out_dir():
    with pytest.raises(SystemExit) as exc:
        cli.main(["screen", "--underlying", "SPY"])
    assert exc.value.code == 2


def test_screen_returns_liquid_candidate(tmp_path, capsys):
    rc = cli.main(
        ["screen", "--underlying", "SPY", "--structure", "csp",
         "--dte", "7-14", "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    rows = json.loads(_capture(capsys))
    assert len(rows) >= 1
    top = rows[0]
    assert top["mid"] is not None
    assert top["liquidity_note"]  # width/liquidity note present


def test_compare_ranks_two_structures(tmp_path, capsys):
    rc = cli.main(
        ["compare", "--underlying", "SPY", "--structures", "csp,pcs",
         "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    rows = json.loads(_capture(capsys))
    assert len(rows) >= 2
    ranks = [r["rank"] for r in rows]
    assert ranks == sorted(ranks)  # ranked ascending
    # ranked by credit quality descending
    q = [r["credit_quality"] for r in rows]
    assert q == sorted(q, reverse=True)


def test_stress_emits_stop_and_risk(tmp_path, capsys):
    rc = cli.main(
        ["stress", "--underlying", "SPY", "--structure", "csp",
         "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    out = json.loads(_capture(capsys))
    assert out["stop"] is not None
    assert out["risk_usd"] is not None
    assert out["scenarios"]


def test_plan_writes_json_md_with_required_fields(tmp_path):
    rc = cli.main(
        ["plan", "--underlying", "SPY", "--structure", "csp",
         "--dte", "7-14", "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    jsons = glob.glob(os.path.join(str(tmp_path), "*.json"))
    mds = glob.glob(os.path.join(str(tmp_path), "*.md"))
    assert len(jsons) == 1 and len(mds) == 1

    data = json.load(open(jsons[0], encoding="utf-8"))
    for k in ("occ_symbols", "qty", "entry_mid", "stop", "risk_usd",
              "thesis", "structure", "expiry"):
        assert data.get(k) is not None, k
    assert data["collateral"] is not None  # CSP collateral
    assert len(data.get("themes", [])) <= 8

    md = open(mds[0], encoding="utf-8").read()
    assert "**Stop**" in md and "**Risk $**" in md


def test_risk_long_premium_formula():
    # abs(entry - stop) * qty * 100
    assert risk.long_premium_risk(2.00, 1.00, 3) == pytest.approx(300.0)
    rr = risk.compute_risk("long", entry=2.0, stop=1.0, qty=3)
    assert rr.risk_usd == pytest.approx(300.0)
    assert rr.formula == "abs(entry-stop)*qty*100"


def test_db_fence_rejects_non_options_path():
    with pytest.raises(config.DBFenceError):
        config.assert_db_fenced("/tmp/papertrade.db")
    with pytest.raises(config.DBFenceError):
        config.assert_db_fenced("/x/futures/papertrade.db")
    # allowed
    assert config.assert_db_fenced("/x/options/papertrade.db")
