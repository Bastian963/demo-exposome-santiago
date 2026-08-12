"""Load and validate city YAML configs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator, Mapping
from copy import deepcopy
from datetime import date
import os

import yaml


_CONFIG_OVERRIDE: ContextVar[tuple[str, Mapping[str, Any]] | None] = ContextVar(
    "exposome_config_override",
    default=None,
)


@contextmanager
def resolved_config_scope(
    study_id: str,
    resolved: Mapping[str, Any],
) -> Iterator[None]:
    """Inject one centrally resolved Study mapping into legacy Layer code."""
    token = _CONFIG_OVERRIDE.set((str(study_id), resolved))
    try:
        yield
    finally:
        _CONFIG_OVERRIDE.reset(token)


def load_config(city: str = "santiago") -> dict[str, Any]:
    """Load a legacy city config or resolve a new multi-location study."""
    override = _CONFIG_OVERRIDE.get()
    if override is not None:
        study_id, resolved = override
        if city != study_id:
            raise ValueError(f"Injected Study config is for {study_id!r}, not {city!r}")
        return deepcopy(dict(resolved))
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "config" / "cities" / f"{city}.yaml"
    study_override = os.environ.get("EXPOSOME_STUDY_CONFIG")
    if path.exists() and not study_override:
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        # Preserve the exact legacy contract for current Santiago workflows.
        assert "name" in cfg, "Config must have 'name'"
        assert "crs" in cfg, "Config must have 'crs'"
        assert "expected_communes" in cfg, "Config must have 'expected_communes'"
        cfg.setdefault("expected_units", cfg["expected_communes"])
        cfg.setdefault("country_code", "CL" if cfg.get("country") == "Chile" else None)
        cfg.setdefault("country_code3", "CHL" if cfg.get("country") == "Chile" else None)
        cfg.setdefault("spatial_unit_type", "commune")
        return cfg

    from .spatial import load_spatial_units
    from .settings import resolve_settings
    from .studies import load_study

    study_ref = study_override or city
    context = load_study(study_ref, repo_root_path=repo_root)
    if context.study.id != city:
        raise ValueError(
            "EXPOSOME_STUDY_CONFIG id does not match the requested study: "
            f"{context.study.id!r} != {city!r}"
        )
    # New studies never inherit settings from another city.  The resolver
    # composes per-layer defaults, country settings, location overrides and
    # study overrides in a fixed order.  ``config/cities/santiago.yaml`` is
    # still supported only by the branch above for legacy direct callers.
    cfg = resolve_settings(context).legacy_mapping()

    _apply_study_period(
        cfg,
        context.study.period,
        enabled_layers=context.study.enabled_layers,
    )

    if context.is_native:
        # Native studies have an AOI but deliberately no analysis-unit polygons.
        # Keep the legacy mapping useful for native adapters without inventing a
        # unit count or forcing a zonal-statistics contract.
        cfg.update(
            {
                "name": context.study.id,
                "location_id": context.location.id,
                "study_id": context.study.id,
                "mode": "native",
                "country": context.location.country,
                "country_code": context.location.country_code,
                "country_code3": context.location.country_code3,
                "timezone": context.location.timezone,
                "region_query": context.location.raw.get(
                    "region_query",
                    f"{context.location.name}, {context.location.country}",
                ),
                # Legacy schema (config/cities/<city>.yaml) used lat_min/lat_max/
                # lon_min/lon_max; every location has a west/south/east/north
                # bbox, so this is always available for new cities too.
                "bbox": {
                    "lat_min": context.location.bbox.south,
                    "lat_max": context.location.bbox.north,
                    "lon_min": context.location.bbox.west,
                    "lon_max": context.location.bbox.east,
                },
                "expected_units": None,
                "expected_communes": None,
                "spatial_unit_type": "native_product",
                "aoi_path": str(context.aoi_path or context.spatial_path),
                "spatial_units": None,
                "outputs": {
                    "base_dir": str(context.paths.processed),
                    "figures_dir": str(context.paths.processed / "figures"),
                    "maps_dir": str(context.paths.processed / "maps"),
                    "cache_dir": str(context.paths.cache),
                },
            }
        )
        # Country-specific portable defaults still need the study country.
        if context.location.country_code3 and cfg.get("alan", {}).get("population"):
            cfg["alan"]["population"]["country"] = context.location.country_code3
        if cfg.get("pm25", {}).get("population") and context.location.country_code3:
            cfg["pm25"]["population"]["country"] = context.location.country_code3
        _apply_location_summer_convention(cfg)
        return cfg

    units = load_spatial_units(context)
    metric_crs = str(units.attrs["metric_crs"])
    cfg.update(
        {
            "name": context.study.id,
            "location_id": context.location.id,
            "study_id": context.study.id,
            "country": context.location.country,
            "country_code": context.location.country_code,
            "country_code3": context.location.country_code3,
            "timezone": context.location.timezone,
            "region_query": context.location.raw.get(
                "region_query",
                f"{context.location.name}, {context.location.country}",
            ),
            "expected_units": len(units),
            "expected_communes": len(units),
            "spatial_unit_type": context.study.unit_type,
            "crs": {
                "geographic": context.location.geographic_crs,
                "metric": metric_crs,
            },
            # Legacy schema (config/cities/<city>.yaml) used lat_min/lat_max/
            # lon_min/lon_max; every location has a west/south/east/north
            # bbox, so this is always available for new cities too.
            "bbox": {
                "lat_min": context.location.bbox.south,
                "lat_max": context.location.bbox.north,
                "lon_min": context.location.bbox.west,
                "lon_max": context.location.bbox.east,
            },
            "spatial_units": {
                "path": str(context.spatial_path),
                "layer": context.study.spatial_layer,
                "id_column": context.study.id_column,
                "name_column": context.study.name_column,
                "unit_type": context.study.unit_type,
                "expected_units": len(units),
                "source": context.study.spatial_source,
            },
            "outputs": {
                "base_dir": str(context.paths.processed),
                "figures_dir": str(context.paths.processed / "figures"),
                "maps_dir": str(context.paths.processed / "maps"),
                "cache_dir": str(context.paths.cache),
            },
        }
    )

    # Portable population layers follow the study country.
    if context.location.country_code3 and cfg.get("alan", {}).get("population"):
        cfg["alan"]["population"]["country"] = context.location.country_code3
    if cfg.get("pm25", {}).get("population") and context.location.country_code3:
        cfg["pm25"]["population"]["country"] = context.location.country_code3

    healthcare = cfg.get("healthcare")
    if isinstance(healthcare, dict):
        healthcare["output_base"] = f"{context.study.id}_healthcare_access"
        healthcare.setdefault("network", {})["graph_cache"] = str(
            context.paths.cache / f"{context.study.id}_walk_graph.graphml"
        )

    _apply_location_summer_convention(cfg)

    # minimal validation
    assert "name" in cfg, "Config must have 'name'"
    assert "crs" in cfg, "Config must have 'crs'"
    assert "expected_communes" in cfg, "Config must have 'expected_communes'"
    return cfg


def _apply_location_summer_convention(cfg: dict[str, Any]) -> None:
    """Set meteorological summer from study latitude when configured.

    Legacy Santiago settings keep their explicit Dec--Feb definition. New
    config-driven studies choose Dec--Feb south of the equator and Jun--Aug to
    the north. Tropical/local-climatology studies can set
    ``summer_convention: explicit`` and supply their own months.
    """
    climate = cfg.get("climate")
    bbox = cfg.get("bbox")
    if not isinstance(climate, dict) or not isinstance(bbox, dict):
        return
    if climate.get("summer_convention") != "hemisphere_meteorological":
        return
    try:
        latitude = (float(bbox["lat_min"]) + float(bbox["lat_max"])) / 2
    except (KeyError, TypeError, ValueError):
        return
    climate.setdefault("seasons", {})["summer"] = [12, 1, 2] if latitude < 0 else [6, 7, 8]


def _deep_merge(target: dict[str, Any], updates: dict[str, Any]) -> None:
    """Recursively merge configuration mappings in place."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _apply_study_period(
    cfg: dict[str, Any],
    period: Any,
    *,
    enabled_layers: Any = (),
) -> None:
    """Map a study window onto portable layer-specific date conventions."""
    if not isinstance(period, dict) or not period:
        return
    try:
        start = date.fromisoformat(str(period["start_date"]))
        end = date.fromisoformat(str(period["end_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Study period requires valid inclusive start_date and end_date"
        ) from exc
    if end < start:
        raise ValueError("Study period end_date must not precede start_date")
    if (start.month, start.day) != (1, 1) or (end.month, end.day) != (12, 31):
        raise ValueError(
            "Portable study periods currently require complete calendar years "
            "(January 1 through December 31)"
        )

    years = list(range(start.year, end.year + 1))
    enabled = {str(layer_id) for layer_id in enabled_layers}

    def uses(*layer_ids: str) -> bool:
        return not enabled or bool(enabled.intersection(layer_ids))

    reference_year = int(period.get("reference_year", years[-1]))
    if reference_year not in years:
        raise ValueError("Study period reference_year must fall inside the study window")
    cfg["study_period"] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "reference_year": reference_year,
    }

    for layer_id in ("precipitation", "wildfire", "climate"):
        if not uses(layer_id, "climate_heat" if layer_id == "climate" else layer_id):
            continue
        layer = cfg.get(layer_id)
        if isinstance(layer, dict):
            layer["years"] = years
            layer["start_date"] = start.isoformat()
            layer["end_date"] = end.isoformat()

    for layer_id in ("alan", "wind", "air_quality"):
        if not uses(layer_id):
            continue
        layer = cfg.get(layer_id)
        if isinstance(layer, dict):
            layer["year"] = reference_year
            layer["start_date"] = f"{reference_year}-01-01"
            layer["end_date"] = f"{reference_year + 1}-01-01"

    climate_heat = cfg.get("climate_heat")
    if uses("climate_heat") and isinstance(climate_heat, dict):
        climate_heat["year"] = reference_year

    satellite = cfg.get("greenspace", {}).get("satellite")
    if uses("greenspace_coverage") and isinstance(satellite, dict):
        satellite["years"] = [reference_year]

    pm25 = cfg.get("pm25")
    if uses("pm25", "air_quality_pm25") and isinstance(pm25, dict):
        available = [year for year in years if 2000 <= year <= 2022]
        if not available:
            raise ValueError(
                "The configured ACAG PM2.5 source is available only for 2000-2022"
            )
        pm25["years"] = available
        pm25["start_date"] = f"{available[0]}-01-01"
        pm25["end_date"] = f"{available[-1] + 1}-01-01"
