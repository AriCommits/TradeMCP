"""Smoke tests for the Options Desk PNG viz CLI (paper only, no Slack)."""

from __future__ import annotations

import glob
import os
import sys

import pytest

import options_desk_slack_viz as viz_cli
from options_desk import viz_data, viz_figure

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.join(_SCRIPTS_DIR, "options_desk", "fixtures")


def test_viz_requires_out_dir():
    with pytest.raises(SystemExit) as exc:
        viz_cli.main(["--paper-trades-root", _ROOT])
    assert exc.value.code == 2


def test_viz_writes_three_panel_png(tmp_path):
    rc = viz_cli.main(["--paper-trades-root", _ROOT, "--out-dir", str(tmp_path)])
    assert rc == 0
    pngs = glob.glob(os.path.join(str(tmp_path), "*.png"))
    assert len(pngs) == 1
    assert os.path.getsize(pngs[0]) > 1000  # non-trivial PNG


def test_figure_has_three_panels_from_fixture_db():
    book = viz_data.load_book(_ROOT)
    assert book.present  # fixture DB has open legs
    fig = viz_figure.build_figure(book)
    assert len(fig.axes) == 3


def test_figure_three_panels_when_book_empty():
    empty = viz_data.build_book_from_rows([])
    fig = viz_figure.build_figure(empty)
    assert len(fig.axes) == 3  # degrades gracefully, still 3 panels


def test_no_slack_or_composio_module_imported():
    # After running the viz path, no third-party Slack/Composio SDK should be
    # loaded. (The CLI's own module name contains "slack" for desk continuity;
    # exclude our own package modules from the check.)
    third_party = [
        m
        for m in sys.modules
        if any(k in m.lower() for k in ("slack_sdk", "slackclient", "composio"))
    ]
    assert third_party == []


def test_viz_db_fence_rejected(tmp_path):
    from options_desk import config

    with pytest.raises(config.DBFenceError):
        viz_data.load_book(db_path="/tmp/not-options.db")
