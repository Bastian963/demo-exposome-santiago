"""Thin CLI for the offline hospitalization-inference workflow."""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.hospitalization_inference_runner import main  # noqa: E402


if __name__ == "__main__":
    main()
