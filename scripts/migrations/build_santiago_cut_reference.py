#!/usr/bin/env python3
"""Build the versioned Santiago spatial contract from validated legacy inputs.

The source geometry remains untouched in ``data/processed`` during migration.
This command produces a small reference dataset with stable CUT identifiers,
display names, legacy names and web slugs.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import unicodedata

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
LEGACY_BOUNDARIES = ROOT / "data" / "processed" / "socioeconomic_exposome_rm_santiago.geojson"
TARGET_DIR = ROOT / "data" / "reference" / "cl" / "santiago" / "santiago_communes"


def _normalise_name(values: pd.Series) -> pd.Series:
    return (
        values.astype(str)
        .str.title()
        .str.replace(" De ", " de ", regex=False)
        .str.replace(" Del ", " del ", regex=False)
        .str.replace(" La ", " la ", regex=False)
        .str.replace(" El ", " el ", regex=False)
        .str.replace(" Y ", " y ", regex=False)
        .str.strip()
    )


def _slug(value: str) -> str:
    text = unicodedata.normalize("NFD", value)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return "".join(char if char.isalnum() else "_" for char in text.lower()).strip("_")


def _find_census_table() -> Path:
    matches = sorted(ROOT.glob("cache/**/Microdato_Censo2017-Comunas.csv"))
    if not matches:
        raise FileNotFoundError(
            "Censo 2017 commune code table is absent from cache; run the demography downloader first."
        )
    return matches[0]


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    census_path = _find_census_table()
    boundaries = gpd.read_file(LEGACY_BOUNDARIES)
    if len(boundaries) != 52 or "name" not in boundaries:
        raise ValueError("Legacy Santiago boundaries must contain exactly 52 named communes")
    census = pd.read_csv(census_path, sep=";", encoding="utf-8", low_memory=False)
    census = census[census["COMUNA"].astype(str).str.startswith("13")].copy()
    census["legacy_name"] = _normalise_name(census["NOM_COMUNA"])
    census["spatial_id"] = census["COMUNA"].astype(int).astype(str).str.zfill(5)
    if len(census) != 52 or census["spatial_id"].duplicated().any():
        raise ValueError("Censo 2017 Region Metropolitana CUT table is not a 52-code mapping")

    frame = boundaries[["name", "geometry"]].rename(columns={"name": "legacy_name"})
    frame = frame.merge(census[["legacy_name", "spatial_id"]], on="legacy_name", how="left")
    if frame["spatial_id"].isna().any():
        missing = frame.loc[frame["spatial_id"].isna(), "legacy_name"].tolist()
        raise ValueError(f"Legacy communes have no CUT match: {missing}")
    if frame["spatial_id"].duplicated().any():
        raise ValueError("CUT mapping produced duplicate spatial IDs")
    frame.insert(1, "spatial_name", frame["legacy_name"])
    frame.insert(2, "slug", frame["legacy_name"].map(_slug))
    frame = gpd.GeoDataFrame(frame[["spatial_id", "spatial_name", "legacy_name", "slug", "geometry"]], crs=boundaries.crs)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_file(output, driver="GeoJSON")
    frame.drop(columns="geometry").to_csv(TARGET_DIR / "cut_crosswalk.csv", index=False)
    metadata = {
        "schema_version": 1,
        "study_id": "santiago_communes",
        "spatial_id": "CUT comuna, 5-digit string",
        "source_geometry": str(LEGACY_BOUNDARIES.relative_to(ROOT)),
        "source_geometry_sha256": _checksum(LEGACY_BOUNDARIES),
        "source_cut_table": str(census_path.relative_to(ROOT)),
        "source_cut_table_sha256": _checksum(census_path),
        "unit_count": len(frame),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Santiago communes spatial reference\n\n"
        "`spatial_units.geojson` is the canonical study support for Santiago. "
        "Its `spatial_id` is the five-digit CUT commune code; `legacy_name` and "
        "`slug` preserve compatibility with existing outputs and web profiles.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
