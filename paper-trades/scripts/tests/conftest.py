"""Pytest bootstrap: make the sibling ``scripts/`` dir importable.

Lets tests import ``scout_wake_context`` and the ``scout_context`` package the
same way the CLI does, regardless of the working directory.
"""

import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
