import json
from pathlib import Path
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot
from apps.cohort_coverage_monitor.config import SNAPSHOT_PATH

def load_snapshot() -> PublicSnapshot:
    """Loads the public snapshot from disk."""
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(f"Snapshot not found at {SNAPSHOT_PATH}. Please run snapshot_builder.py first.")
    
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return PublicSnapshot.from_dict(data)
