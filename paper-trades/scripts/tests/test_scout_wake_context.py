"""Acceptance + smoke tests for the Scout wake-context CLI.

Runs fully offline: inputs come from the packaged fixtures via
``--paper-trades-root``; all writes go to a per-test temporary ``--out-dir``.
"""

from __future__ import annotations

import json
import os

import pytest

import scout_wake_context as cli
from scout_context import bundle as bundle_mod
from scout_context import inject as inject_mod
from scout_context import regime as regime_mod
from scout_context.render_md import HEADINGS

KEY = "2026-09-28-1500"

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG_FIXTURES = os.path.join(_SCRIPTS_DIR, "scout_context", "fixtures")
_TEST_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "wake-snapshot-2026-09-28-1500.json",
)


def _run(out_dir, *extra):
    argv = [
        "--snapshot", _TEST_SNAPSHOT,
        "--paper-trades-root", _PKG_FIXTURES,
        "--out-dir", str(out_dir),
        *extra,
    ]
    return cli.main(argv)


def _read_json(out_dir):
    p = os.path.join(str(out_dir), f"wake-context-{KEY}.json")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _read_md(out_dir):
    p = os.path.join(str(out_dir), f"wake-context-{KEY}.md")
    with open(p, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
def test_refuses_without_out_dir():
    """CLI must refuse to run when --out-dir is absent (argparse exit 2)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--snapshot", _TEST_SNAPSHOT, "--paper-trades-root", _PKG_FIXTURES])
    assert exc.value.code == 2


def test_writes_json_and_md_with_five_headings(tmp_path):
    rc = _run(tmp_path)
    assert rc == 0
    assert (tmp_path / f"wake-context-{KEY}.json").exists()
    assert (tmp_path / f"wake-context-{KEY}.md").exists()

    md = _read_md(tmp_path)
    positions = [md.index(f"### {h}") for h in HEADINGS]
    assert positions == sorted(positions), "headings out of order"
    assert len(positions) == len(HEADINGS) == 5


def test_regime_enum_and_confidence(tmp_path):
    _run(tmp_path)
    data = _read_json(tmp_path)
    assert data["regime"], "regime map empty"
    for sym, r in data["regime"].items():
        assert r["label"] in regime_mod.REGIME_ENUM, (sym, r["label"])
        assert 0.0 <= r["confidence"] <= 1.0, (sym, r["confidence"])


def test_vol_features_present_and_finite(tmp_path):
    _run(tmp_path)
    data = _read_json(tmp_path)
    assert data["vol_features"], "vol_features empty"
    for sym, v in data["vol_features"].items():
        # required feature keys exist
        for k in ("realized_vol_20", "vol_ratio_vs_ring", "vol_forecast_ratio"):
            assert k in v, (sym, k)
            val = v[k]
            # finite float or explicit None sentinel — never NaN string
            assert val is None or isinstance(val, (int, float))
        # at least one symbol should have a real realized vol
    assert any(
        v["realized_vol_20"] is not None for v in data["vol_features"].values()
    )
    # no NaN token anywhere in the serialized json
    raw = (tmp_path / f"wake-context-{KEY}.json").read_text(encoding="utf-8")
    assert "NaN" not in raw and "Infinity" not in raw


def test_inject_review_single_section_and_preserves_decision(tmp_path):
    review = tmp_path / "wake-review-2026-09-28-1500.md"
    review.write_text(
        "# Review\n\nDecision: PASS\nJudgment: hold\n", encoding="utf-8"
    )
    _run(tmp_path, "--inject-review", str(review))
    _run(tmp_path, "--inject-review", str(review))  # second run: idempotent

    text = review.read_text(encoding="utf-8")
    assert text.count(inject_mod.SECTION_HEADING) == 1
    assert "Decision: PASS" in text
    assert "Judgment: hold" in text


def test_json_byte_stable_excluding_generated_at(tmp_path):
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    _run(out1)
    _run(out2)
    t1 = (out1 / f"wake-context-{KEY}.json").read_text(encoding="utf-8")
    t2 = (out2 / f"wake-context-{KEY}.json").read_text(encoding="utf-8")
    assert bundle_mod.stable_payload(t1) == bundle_mod.stable_payload(t2)


def test_no_writes_outside_out_dir(tmp_path):
    """Only the two expected artifacts land under --out-dir; nothing else."""
    _run(tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [f"wake-context-{KEY}.json", f"wake-context-{KEY}.md"]


def test_no_forbidden_imports():
    """Source must not import Kraken private/trade or Slack/Composio modules."""
    import pathlib

    pkg = pathlib.Path(_SCRIPTS_DIR)
    forbidden = ("krakenex", "ccxt", "import slack", "composio", "slack_sdk")
    for py in pkg.rglob("*.py"):
        if "tests" in py.parts:
            continue
        text = py.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"{py} references {token!r}"
