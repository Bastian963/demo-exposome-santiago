#!/usr/bin/env python3
"""Materialize canonical Santiago outputs from validated flat legacy products.

This is a non-computational migration: it copies every catalogued master product,
attaches CUT identifiers through the shared output normalizer, then builds a
canonical master and release manifest.  Original flat files are never changed.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from exposome.layers import (  # noqa: E402
    build_study_master_from_catalog,
    load_layer_catalog,
    normalize_layer_outputs,
)
from exposome.releases import write_release_manifest  # noqa: E402
from exposome.studies import load_study  # noqa: E402
from build_master_exposome import LAYER_SPECS  # noqa: E402


# These catalogued products are review/validation artifacts rather than master
# inputs. They still receive normalised IDs and manifests so their provenance is
# contained in the same Santiago release.
_AUXILIARY_SOURCES = {
    "greenspace_cv": "santiago_greenspace_cv_commune",
    "neuro_mortality": "santiago_neuro_mortality_2018_2022",
    "neuro_hospitalizations": "santiago_neuro_hospitalizations_2006_2006",
}

_FIGURES = {
    "socioeconomic": "socioeconomic_santiago_4panel.png",
    "air_quality": "air_quality_before_after_satellite.png",
    "air_quality_pm25": "pm25_santiago_4panel.png",
    "heavy_metals": "heavy_metals_santiago_4panel.png",
    "air_quality_satellite": "air_quality_satellite_santiago_4panel.png",
    "wind": "wind_santiago_4panel.png",
    "alan": "alan_santiago_4panel.png",
    "sleep_context": "sleep_context_santiago.png",
    "greenspace_access": "greenspace_access_santiago_2panel.png",
    "greenspace_coverage": "greenspace_coverage_santiago_2panel.png",
    "greenspace_cv": "greenspace_cv_santiago.png",
    "healthcare": "healthcare_access_santiago.png",
    "demography": "demography_santiago_2panel.png",
    "climate_heat": "climate_heat_santiago_pub.png",
    "precipitation": "precipitation_santiago_4panel.png",
    "precipitation_spi": "precipitation_spi_santiago_4panel.png",
    "climate_openmeteo": "climate_metrics_santiago.png",
    "wildfire": "wildfire_santiago_4panel.png",
    "noise": "noise_santiago_4panel.png",
    "walkability": "walkability_santiago_4panel.png",
    "public_transport": "public_transport_santiago_4panel.png",
    "social_infrastructure": "social_infrastructure_santiago_4panel.png",
    "food_environment": "food_environment_santiago_4panel.png",
    "neuro_mortality": "neuro_outcomes_santiago_4panel.png",
    "neuro_hospitalizations": "neuro_outcomes_santiago_4panel.png",
}


def _sources(catalog) -> dict[str, str]:
    """Use the historical master inventory as the migration source of truth."""
    sources: dict[str, str] = {}
    for spec in LAYER_SPECS:
        layer_id = str(spec["name"])
        if layer_id not in catalog.layers:
            # Internal annual series are not standalone catalog layers.
            continue
        sources[layer_id] = str(spec["csv"]).removesuffix(".csv")
    for layer_id, stem in _AUXILIARY_SOURCES.items():
        if layer_id in catalog.layers:
            sources[layer_id] = stem
    return sources


def _copy_source_products(
    source_root: Path, stem: str, destination: Path, *, figure: Path | None = None
) -> None:
    copied = []
    for suffix in (".csv", ".geojson", ".json", "_metadata.json"):
        source = source_root / f"{stem}{suffix}"
        if source.exists():
            shutil.copy2(source, destination / source.name)
            copied.append(source.name)
    if not any(name.endswith(".csv") for name in copied):
        raise FileNotFoundError(f"Legacy source has no CSV: {source_root / (stem + '.csv')}")
    if figure is not None and figure.is_file():
        shutil.copy2(figure, destination / figure.name)


def _copy_declared_intermediate_inputs(context: object, source_root: Path) -> None:
    """Move historical derived-layer inputs to the canonical interim namespace."""
    paths = getattr(context, "paths")
    target = Path(paths.interim) / "climate_openmeteo_daily_2024_2024.csv"
    source = source_root / "santiago_climate_openmeteo_daily_2024_2024.csv"
    if not source.is_file():
        raise FileNotFoundError(f"Missing validated climate intermediate: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_precipitation_daily_input(context: object, source_root: Path) -> None:
    """Keep the CHIRPS daily dependency beside its canonical producer layer."""
    source = source_root / "santiago_precipitation_chirps_daily_2015_2024.csv"
    if not source.is_file():
        raise FileNotFoundError(f"Missing validated CHIRPS daily input: {source}")
    target = (
        Path(getattr(context, "paths").layer_processed("precipitation"))
        / "santiago_communes_precipitation_chirps_daily_2015_2024.csv"
    )
    shutil.copy2(source, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace existing canonical layer directories")
    args = parser.parse_args()
    context = load_study("santiago_communes")
    catalog = load_layer_catalog()
    sources = _sources(catalog)
    source_root = ROOT / "data" / "processed"

    _copy_declared_intermediate_inputs(context, source_root)

    for layer_id, stem in sources.items():
        destination = context.paths.layer_processed(layer_id)
        if destination.exists():
            if not args.force:
                raise FileExistsError(f"Canonical layer exists: {destination}; pass --force")
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        figure_name = _FIGURES.get(layer_id)
        _copy_source_products(
            source_root,
            stem,
            destination,
            figure=(ROOT / "figures" / figure_name) if figure_name else None,
        )
        if layer_id == "precipitation":
            _copy_precipitation_daily_input(context, source_root)
        normalize_layer_outputs(context, catalog.get(layer_id), destination)
        print(destination.relative_to(ROOT))

    master_layer_ids = tuple(
        layer_id
        for layer_id in sources
        if bool((catalog.get(layer_id).master or {}).get("include", False))
    )
    master = build_study_master_from_catalog(
        context,
        catalog=catalog,
        layer_ids=master_layer_ids,
        strict_required=True,
        write=True,
    )
    release = write_release_manifest(context, master)
    print(release.relative_to(ROOT))


if __name__ == "__main__":
    main()
