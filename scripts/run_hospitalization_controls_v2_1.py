"""Thin CLI for the annual-v2.1 Bayesian negative-control extension."""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.hospitalization_controls_v2_1_runner import main  # noqa: E402


if __name__ == "__main__":
    import typer

    typer.run(main)
