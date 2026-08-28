"""Load and validate city YAML configs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(city: str = "santiago") -> dict[str, Any]:
    """Load a city config from config/cities/<city>.yaml."""
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "config" / "cities" / f"{city}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"City config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # minimal validation
    assert "name" in cfg, "Config must have 'name'"
    assert "crs" in cfg, "Config must have 'crs'"
    assert "expected_communes" in cfg, "Config must have 'expected_communes'"
    return cfg
