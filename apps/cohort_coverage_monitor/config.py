import os
from pathlib import Path

# Base paths for the local snapshot builder
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_PARTICIPANTS_PATH = ROOT_DIR / "data" / "raw" / "zipcodes" / "2026-07" / "participant_locations.csv"
REGISTRY_PATH = ROOT_DIR / "config" / "operations" / "cohort_latam_report.yaml"
CATALOG_PATH = ROOT_DIR / "webapp" / "public" / "data" / "catalog.json"
MANIFESTS_BASE_PATH = ROOT_DIR / "webapp" / "public"

# Snapshot path
SNAPSHOT_PATH = Path(__file__).parent / "data" / "cohort_public_snapshot.json"

# UI Constants
APP_TITLE = "GEMMA BrainLat Cohort"
APP_SUBTITLE = "Monitor operativo independiente de GEMMA"
GEMMA_FULL_NAME = "Global Exposome Modeling, Mapping & Analytics"

# Colors and fonts taken verbatim from GEMMA's palette (webapp/public/palette.json),
# so this monitor stays a client of the same visual identity instead of a copy of it.
COLORS = {
    "bg_sky": "#1a1c2c",
    "bg_panel": "#29366f",
    "bg_panel_dark": "#0d0e1a",
    "ui_accent": "#ff77a8",
    "ui_accent_2": "#f4b41b",
    "ui_accent_3": "#94b0c2",
    "ui_text": "#f4f4f4",
    "ui_text_muted": "#94b0c2",
    "data_low": "#3b5dc9",
    "data_mid": "#41a6f6",
    "data_high": "#ff004d",
    "shadow": "#0d0e1a",
}

PIXEL_FONT = "'Press Start 2P', monospace"
BODY_FONT = "'VT323', monospace"

# Same operational-status vocabulary as notebooks/cohort/cohort_latam_status_report.ipynb,
# remapped onto the GEMMA palette hues instead of ad hoc Bootstrap colors.
STATUS_COLORS = {
    "published": COLORS["data_mid"],
    "running": COLORS["ui_accent"],
    "ready": COLORS["ui_accent_2"],
    "preparing": COLORS["ui_accent_3"],
    "blocked": COLORS["data_high"],
    "pending": COLORS["bg_panel"],
}

TIER_COLORS = {
    "production": COLORS["data_mid"],
    "preview": COLORS["ui_accent"],
    "none": COLORS["bg_panel"],
}
