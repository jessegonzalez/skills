"""Pytest configuration: put ``scripts/`` on sys.path.

This lets tests do ``from rollout_lib import ...`` without needing a package
install. The CLI scripts themselves live in ``scripts/`` next to
``rollout_lib.py`` so they import the same way at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
