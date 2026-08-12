"""Shared test helpers for the BrainLat exposome project."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import config as exposome_config  # noqa: E402

# Number of spatial units (communes for Santiago) expected by the
# master builder. Read from the city config so the same test suite
# works for any city (or for a future zip-code-level master: the
# helper can be overridden at test time by reloading the config).
EXPECTED_N_UNITS = int(
    exposome_config.load_config("santiago").get("expected_communes", 52)
)

# Aliases preserved for readability inside test assertions.
EXPECTED_COMMUNES = EXPECTED_N_UNITS
