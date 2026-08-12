"""Spatial-support declarations for browser-facing exposome indicators.

The web application used to advertise a single global ``resolution`` string
from ``palette.json``.  That conflated three different things: source pixel
size, the unit used by the method, and whether a particular city actually
published an intra-unit asset.  This module is the small, versioned source of
truth used by the publisher to expose those concepts separately.

It deliberately contains no provider calls and no geometry processing.  A
detail asset is optional: an indicator is *not* considered fine merely because
its provider has a fine native product.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping


SPATIAL_SCHEMA_VERSION = 3

_ADMINISTRATIVE_UNIT_LABELS = {
    "commune": "comuna",
    "admin_unit": "unidad administrativa",
    "distrito": "distrito",
    "comuna_corregimiento": "comuna o corregimiento",
    "alcaldia": "alcaldía",
    "municipio": "municipio",
    "partido": "partido",
    "comarca": "comarca",
    "provincia": "provincia",
    "postal_code": "código postal",
}


def administrative_unit_label(unit_type: str | None) -> str:
    """Return the public Spanish label for a configured spatial unit type."""
    return _ADMINISTRATIVE_UNIT_LABELS.get(str(unit_type or ""), "unidad administrativa")


def _raster(
    *,
    source_label: str,
    source_resolution: Mapping[str, Any],
    analysis_label: str,
    analysis_resolution: Mapping[str, Any],
    layer_id: str,
    boundary_role: str = "mask_only",
    observation_label: str | None = None,
    observation_resolution: Mapping[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Describe all supports without treating storage pixels as observations.

    ``downloaded`` is the provider grid saved by the pipeline; ``observation``
    is the footprint that can actually support a measurement; ``analysis`` is
    the unit on which the indicator is calculated.  Keeping these objects
    separate makes a reprojected COG incapable of silently becoming a claim of
    finer scientific resolution.
    """
    record = {
        "layer_id": layer_id,
        "downloaded": {
            "kind": "raster_grid",
            "label": source_label,
            "resolution": dict(source_resolution),
        },
        "observation": {
            "kind": "raster_footprint",
            "label": observation_label or source_label,
            "resolution": dict(observation_resolution or source_resolution),
        },
        "analysis": {
            "kind": "regular_grid",
            "label": analysis_label,
            "resolution": dict(analysis_resolution),
        },
        "rendered": None,
        "boundary_role": boundary_role,
        "resampling": "none",
        "notes": notes,
    }
    # Compatibility alias for v2 consumers.  v3 readers must use
    # ``downloaded``/``observation`` explicitly; keeping this alias lets a
    # staged web deployment read a new manifest without falling back to the
    # palette resolution string.
    record["source"] = deepcopy(record["downloaded"])
    return record


def _admin(*, layer_id: str, label: str = "comuna / partido") -> dict[str, Any]:
    record = {
        "layer_id": layer_id,
        "downloaded": {"kind": "administrative_unit", "label": label, "resolution": None},
        "observation": {"kind": "administrative_unit", "label": label, "resolution": None},
        "analysis": {"kind": "administrative_unit", "label": label, "resolution": None},
        "rendered": {"kind": "administrative_polygon", "label": label, "resolution": None},
        "boundary_role": "source_unit",
        "resampling": "none",
        "notes": "La fuente publicada ya está agregada; no se infiere variación intraunidad.",
    }
    record["source"] = deepcopy(record["downloaded"])
    return record


def _vector(
    *,
    layer_id: str,
    source_label: str,
    analysis_label: str,
    analysis_kind: str,
    analysis_resolution: Mapping[str, Any] | None,
    boundary_role: str,
) -> dict[str, Any]:
    """Describe a vector inventory without pretending that it has pixels."""
    record = {
        "layer_id": layer_id,
        "downloaded": {
            "kind": "vector_features",
            "label": source_label,
            "resolution": {"value": None, "unit": "vector"},
        },
        "observation": {
            "kind": "vector_geometry",
            "label": source_label,
            "resolution": {"value": None, "unit": "vector"},
        },
        "analysis": {
            "kind": analysis_kind,
            "label": analysis_label,
            "resolution": dict(analysis_resolution) if analysis_resolution else None,
        },
        "rendered": {
            "kind": "administrative_polygon",
            "label": "solo resumen administrativo publicado",
            "resolution": None,
        },
        "boundary_role": boundary_role,
        "resampling": "none",
        "notes": "La geometría vectorial fuente no se convierte en una falsa grilla raster.",
    }
    record["source"] = deepcopy(record["downloaded"])
    return record


def _composite(*, layer_id: str, label: str) -> dict[str, Any]:
    """Declare a group/index whose components keep different supports."""
    record = {
        "layer_id": layer_id,
        "downloaded": {"kind": "component_specific", "label": label, "resolution": None},
        "observation": {"kind": "component_specific", "label": label, "resolution": None},
        "analysis": {"kind": "component_specific", "label": label, "resolution": None},
        "rendered": {
            "kind": "administrative_polygon",
            "label": "solo resumen compuesto publicado",
            "resolution": None,
        },
        "boundary_role": "component_specific",
        "resampling": "none",
        "notes": "Cada componente conserva su propio soporte espacial; el índice no hereda una resolución única.",
    }
    record["source"] = deepcopy(record["downloaded"])
    return record


_DEG_001 = {"x": 0.01, "y": 0.01, "unit": "degree"}
_DEG_005 = {"x": 0.05, "y": 0.05, "unit": "degree"}
_DEG_010 = {"x": 0.10, "y": 0.10, "unit": "degree"}


# Keys are public palette/exposome ids, not filenames.  They are intentionally
# explicit so a renamed pipeline layer cannot silently inherit a resolution.
INDICATOR_SUPPORT: dict[str, dict[str, Any]] = {
    "pm25": _raster(
        layer_id="air_quality_pm25",
        source_label="ACAG PM2.5, grilla 0,01°",
        source_resolution=_DEG_001,
        analysis_label="píxel ACAG nativo",
        analysis_resolution=_DEG_001,
    ),
    "no2": _raster(
        layer_id="air_quality_satellite",
        source_label="Sentinel-5P TROPOMI L3",
        source_resolution={"value": 1113.2, "unit": "m"},
        analysis_label="columna troposférica S5P",
        analysis_resolution={"value": 1113.2, "unit": "m"},
        observation_label="huella observacional TROPOMI (a través de pista)",
        observation_resolution={"x": 3500, "y": 5500, "y_max": 7000, "unit": "m"},
        notes=(
            "La grilla L3 descargada es de 1.113 m, pero una observación TROPOMI "
            "cubre aproximadamente 3,5 × 5,5–7 km. El detalle usa columna "
            "troposférica en mol/m²; no es una medición real a 1,1 km. "
            "Cualquier proxy de superficie debe declarar por separado el "
            "soporte de la BLH."
        ),
    ),
    "alan": _raster(
        layer_id="alan",
        source_label="VIIRS DNB monthly VCMSLCFG",
        source_resolution={"value": 463.83, "unit": "m"},
        analysis_label="radiancia VIIRS nativa",
        analysis_resolution={"value": 463.83, "unit": "m"},
    ),
    "green": _raster(
        layer_id="greenspace_multisource",
        source_label="Dynamic World V1, 10 m",
        source_resolution={"value": 10, "unit": "m"},
        analysis_label="porcentaje verde en celda estable; muestreo 30 m",
        analysis_resolution={"value": 1000, "unit": "m"},
        notes="La fuente no se declara como resolución del mapa cuando el indicador es un porcentaje por celda.",
    ),
    "canopy": _raster(
        layer_id="greenspace_multisource",
        source_label="Meta/WRI canopy height, 1 m",
        source_resolution={"value": 1, "unit": "m"},
        analysis_label="fracción de dosel agregada a 30 m",
        analysis_resolution={"value": 30, "unit": "m"},
    ),
    # The family and its index are not native ERA5-Land variables.  They are
    # city-relative combinations of several administrative summaries; showing
    # a raster here would falsely imply that the rank/z-score exists at every
    # ERA5 pixel.  Individual physical heat metrics below retain their own
    # raster contracts.
    "heat": _composite(
        layer_id="climate_heat",
        label="familia de métricas térmicas ERA5-Land con índice relativo por ciudad",
    ),
    "heat_index": _composite(
        layer_id="climate_heat",
        label="z-scores de métricas térmicas combinados dentro del estudio",
    ),
    "heat_summer_tmax": _raster(layer_id="climate_heat", source_label="ERA5-Land daily aggregates", source_resolution={"value": 11132, "unit": "m"}, analysis_label="Tmax por píxel ERA5-Land", analysis_resolution={"value": 11132, "unit": "m"}),
    "heat_hot_days": _raster(layer_id="climate_heat", source_label="ERA5-Land daily aggregates", source_resolution={"value": 11132, "unit": "m"}, analysis_label="días cálidos por píxel ERA5-Land", analysis_resolution={"value": 11132, "unit": "m"}),
    "heat_tropical_nights": _raster(layer_id="climate_heat", source_label="ERA5-Land daily aggregates", source_resolution={"value": 11132, "unit": "m"}, analysis_label="noches tropicales por píxel ERA5-Land", analysis_resolution={"value": 11132, "unit": "m"}),
    # ``precip_extremes_index`` is likewise a percentile composite evaluated
    # across the study.  CHIRPS can support its component maps, not a fictive
    # source-pixel version of that city-relative score.
    "rain": _composite(
        layer_id="precipitation",
        label="familia CHIRPS de volumen, sequía y lluvia intensa",
    ),
    "rain_index": _composite(
        layer_id="precipitation",
        label="percentiles de extremos hídricos combinados dentro del estudio",
    ),
    "rain_annual": _raster(layer_id="precipitation", source_label="CHIRPS Daily", source_resolution=_DEG_005, analysis_label="precipitación anual por píxel CHIRPS", analysis_resolution=_DEG_005),
    "rain_dry_spell": _raster(layer_id="precipitation", source_label="CHIRPS Daily", source_resolution=_DEG_005, analysis_label="racha seca por píxel CHIRPS", analysis_resolution=_DEG_005),
    "rain_heavy": _raster(layer_id="precipitation", source_label="CHIRPS Daily", source_resolution=_DEG_005, analysis_label="días intensos por píxel CHIRPS", analysis_resolution=_DEG_005),
    # The current SPI implementation fits distributions to the already
    # commune-aggregated CHIRPS series. A CHIRPS source grid alone is not
    # evidence that this derived, city-period-specific SPI exists per pixel.
    "precipitation_spi": _admin(
        layer_id="precipitation_spi",
        label="SPI calculado sobre la serie CHIRPS agregada por unidad",
    ),
    "wind": _raster(
        layer_id="wind",
        source_label="ERA5-Land hourly",
        source_resolution={"value": 11132, "unit": "m"},
        analysis_label="grilla ERA5-Land nativa",
        analysis_resolution={"value": 11132, "unit": "m"},
    ),
    "wildfire": {
        **_composite(layer_id="wildfire", label="MODIS área quemada (500 m) + FIRMS focos activos (1 km)"),
        "components": {
            "burned_area": {
                "downloaded": {"kind": "raster_grid", "label": "MODIS MCD64A1 área quemada", "resolution": {"value": 500, "unit": "m"}},
                "observation": {"kind": "raster_footprint", "label": "MODIS MCD64A1 área quemada", "resolution": {"value": 500, "unit": "m"}},
            },
            "active_fire": {
                "downloaded": {"kind": "raster_grid", "label": "FIRMS focos activos", "resolution": {"value": 1000, "unit": "m"}},
                "observation": {"kind": "raster_footprint", "label": "FIRMS focos activos", "resolution": {"value": 1000, "unit": "m"}},
            },
        },
    },
    "greenspace_access": _vector(
        layer_id="greenspace_access",
        source_label="geometrías OSM",
        analysis_label="métrica resumida por unidad administrativa",
        analysis_kind="administrative_unit",
        analysis_resolution=None,
        boundary_role="analysis_unit",
    ),
    "healthcare": _vector(layer_id="healthcare", source_label="inventario OSM/DEIS", analysis_label="acceso local evaluado en grilla estable", analysis_kind="regular_grid", analysis_resolution={"value": 1000, "unit": "m"}, boundary_role="mask_only"),
    # The underlying nearest-distance grid is real, but the browser card is a
    # city-relative composite of coverage, counts, population and z-scores.
    # It cannot honestly inherit a pixel value from that intermediate grid.
    "social_infrastructure": _composite(
        layer_id="social_infrastructure",
        label="índice social compuesto de inventario, población y acceso local",
    ),
    "food_environment": _vector(layer_id="food_environment", source_label="POI OSM", analysis_label="indicador resumido por unidad administrativa", analysis_kind="administrative_unit", analysis_resolution=None, boundary_role="analysis_unit"),
    "walkability": _vector(layer_id="walkability", source_label="red peatonal OSM", analysis_label="indicador resumido por unidad administrativa", analysis_kind="administrative_unit", analysis_resolution=None, boundary_role="analysis_unit"),
    "noise": _admin(layer_id="noise", label="comuna / modelo GSU"),
    "noise_lden": _vector(
        layer_id="noise_spain",
        source_label="polígonos vectoriales MER/SICA de bandas Lden",
        analysis_label="intersección por superficie con unidad administrativa",
        analysis_kind="administrative_unit",
        analysis_resolution=None,
        boundary_role="analysis_unit",
    ),
    "heavy_metals": _admin(layer_id="heavy_metals", label="comuna; fuentes RETC puntuales"),
    "nse": _admin(layer_id="socioeconomic"),
    "food_insecurity": _admin(layer_id="food_insecurity"),
    "poverty_income": _admin(layer_id="pobreza_sae"),
    "poverty_multi": _admin(layer_id="pobreza_sae"),
    "community_safety": _admin(layer_id="community_safety"),
    "community_safety_property": _admin(layer_id="community_safety"),
    "community_safety_robbery": _admin(layer_id="community_safety"),
    "community_safety_theft": _admin(layer_id="community_safety"),
    "community_safety_vehicle": _admin(layer_id="community_safety"),
    "community_safety_public_space": _admin(layer_id="community_safety"),
    "community_safety_firearm": _admin(layer_id="community_safety"),
    "community_violence": _admin(layer_id="community_violence"),
    "violence_homicide": _admin(layer_id="community_violence"),
    "violence_attempted_homicide": _admin(layer_id="community_violence"),
    "violence_injury": _admin(layer_id="community_violence"),
    "violence_sexual": _admin(layer_id="community_violence"),
    "violence_aggravated_robbery": _admin(layer_id="community_violence"),
    "suicide_mortality": _admin(layer_id="suicide_mortality"),
    "road_traffic_mortality": _admin(layer_id="road_traffic_mortality"),
    "poverty": _composite(layer_id="pobreza_sae", label="familia de estimaciones SAE por comuna"),
    "ebi": _composite(layer_id="ebi", label="índice compuesto de exposomas"),
}


# Most browser-detail products retain the card's unit.  NO2 is intentionally
# different: the fine map is the native tropospheric column, whereas the
# commune summary may expose a separately modelled surface proxy.
DETAIL_UNITS = {"no2": "mol/m²", "healthcare": "m"}
DETAIL_BANDS = {"wind": 3}
DETAIL_NATIVE_RESOLUTION_M = {
    "pm25": 1113.0,
    "no2": 1113.0,
    "alan": 463.83,
    "wind": 11132.0,
    "heat_summer_tmax": 11132.0,
    "heat_hot_days": 11132.0,
    "heat_tropical_nights": 11132.0,
    "rain_annual": 5566.0,
    "rain_dry_spell": 5566.0,
    "rain_heavy": 5566.0,
    "canopy": 1.0,
}

# These are the grids of the actual rasters consumed by ``exposome detail``.
# They deliberately distinguish provider/source support from an analysis
# product: canopy starts from a 1 m source but the publishable fraction raster
# is genuinely calculated at 30 m.  Nominal metre labels alone are not proof;
# Earth Engine's reducer fallback is a one-degree grid while it can still carry
# a manually declared ``source_native_resolution_m``.
DETAIL_SOURCE_GRID = {
    "pm25": {"crs": "EPSG:4326", "resolution": {"x": 0.01, "y": 0.01, "unit": "degree"}},
    "no2": {"crs": "EPSG:4326", "resolution": {"x": 0.01, "y": 0.01, "unit": "degree"}},
    "alan": {"crs": "EPSG:4326", "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"}},
    "wind": {"crs": "EPSG:4326", "resolution": {"x": 0.10, "y": 0.10, "unit": "degree"}},
    "heat_summer_tmax": {"crs": "EPSG:4326", "resolution": {"x": 0.10, "y": 0.10, "unit": "degree"}},
    "heat_hot_days": {"crs": "EPSG:4326", "resolution": {"x": 0.10, "y": 0.10, "unit": "degree"}},
    "heat_tropical_nights": {"crs": "EPSG:4326", "resolution": {"x": 0.10, "y": 0.10, "unit": "degree"}},
    "rain_annual": {"crs": "EPSG:4326", "resolution": {"x": 0.05, "y": 0.05, "unit": "degree"}},
    "rain_dry_spell": {"crs": "EPSG:4326", "resolution": {"x": 0.05, "y": 0.05, "unit": "degree"}},
    "rain_heavy": {"crs": "EPSG:4326", "resolution": {"x": 0.05, "y": 0.05, "unit": "degree"}},
    "canopy": {"crs": "EPSG:3857", "resolution": {"x": 30, "y": 30, "unit": "m"}},
}

DETAIL_METRIC_LABELS = {
    "no2": "NO₂ columna troposférica",
}

VECTOR_CONTOUR_INDICATORS = {"noise_lden"}
VECTOR_CONTOUR_TARGET_LAYERS = {"noise_spain"}
NOISE_LDEN_BANDS = (
    {"value": "55-59", "label": "55–59 dB(A)", "lower_dba": 55, "upper_dba": 59},
    {"value": "60-64", "label": "60–64 dB(A)", "lower_dba": 60, "upper_dba": 64},
    {"value": "65-69", "label": "65–69 dB(A)", "lower_dba": 65, "upper_dba": 69},
    {"value": "70-74", "label": "70–74 dB(A)", "lower_dba": 70, "upper_dba": 74},
    {"value": "gt75", "label": ">75 dB(A)", "lower_dba": 75, "upper_dba": None},
)

YEAR_SCOPED_DETAIL_INDICATORS = {
    "heat_summer_tmax",
    "heat_hot_days",
    "heat_tropical_nights",
}


def valid_year_temporal_support(value: Any) -> bool:
    """Return whether a detail declares one concrete source year and label."""
    if not isinstance(value, Mapping) or value.get("kind") != "year":
        return False
    year = str(value.get("year") or "")
    source_label = value.get("source_label")
    return (
        len(year) == 4
        and year.isdigit()
        and isinstance(source_label, str)
        and bool(source_label.strip())
    )


def valid_period_temporal_support(value: Any) -> bool:
    """Return whether a detail declares one aggregate source period."""
    if not isinstance(value, Mapping) or value.get("kind") != "period":
        return False
    start = str(value.get("start_year") or "")
    end = str(value.get("end_year") or "")
    source_label = value.get("source_label")
    return (
        len(start) == 4
        and start.isdigit()
        and len(end) == 4
        and end.isdigit()
        and int(start) <= int(end)
        and value.get("aggregation") in {"mean", "median", "sum"}
        and isinstance(source_label, str)
        and bool(source_label.strip())
    )


def valid_temporal_support(value: Any) -> bool:
    """Return whether detail provenance is a supported year or aggregate period."""
    return valid_year_temporal_support(value) or valid_period_temporal_support(value)


def canonical_detail_source_grid(indicator_id: str, metadata: Mapping[str, Any] | None) -> bool:
    """Return whether an inspected source grid meets an indicator's contract.

    Every COG-backed indicator requires its inspected raster grid.  This makes
    a one-degree reducer fallback, a rounded VIIRS export, or a false canopy
    source claim incapable of masquerading as canonical detail.
    """
    expected = DETAIL_SOURCE_GRID.get(indicator_id)
    if expected is None:
        return True
    grid = metadata.get("source_grid") if isinstance(metadata, Mapping) else None
    if not isinstance(grid, Mapping):
        return False
    if str(grid.get("crs") or "").upper() != expected["crs"]:
        return False
    actual = grid.get("resolution")
    if not isinstance(actual, Mapping) or actual.get("unit") != expected["resolution"]["unit"]:
        return False
    try:
        return all(
            abs(float(actual[axis]) / float(expected["resolution"][axis]) - 1.0) <= 0.001
            for axis in ("x", "y")
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def publication_target(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the maximum honest browser product expected for one indicator.

    This is deliberately a *target*, not a claim about the active study.  The
    per-study manifest's ``detail`` field remains the authority for what is
    actually rendered.  Keeping both concepts side by side lets a city be an
    honest preview while the coverage audit still reports that a native product
    supplied by its method has not yet been published.
    """
    downloaded = record.get("downloaded", {})
    analysis = record.get("analysis", {})
    source_kind = downloaded.get("kind") if isinstance(downloaded, Mapping) else None
    analysis_kind = analysis.get("kind") if isinstance(analysis, Mapping) else None
    if record.get("layer_id") in VECTOR_CONTOUR_TARGET_LAYERS:
        return {
            "kind": "native_vector",
            "required_for_production": True,
            "label": "contornos vectoriales fuente verificados",
        }
    if source_kind == "raster_grid" and analysis_kind == "regular_grid":
        return {
            "kind": "native_raster",
            "required_for_production": True,
            "label": "detalle raster con soporte fuente verificado",
        }
    if source_kind == "vector_features" and analysis_kind == "regular_grid":
        return {
            "kind": "analysis_grid",
            "required_for_production": True,
            "label": "grilla analítica realmente calculada",
        }
    return {
        "kind": "administrative_or_component_specific",
        "required_for_production": False,
        "label": "sin detalle raster exigible para este método",
    }


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_vector_contour_descriptor(
    indicator_id: str,
    descriptor: Mapping[str, Any],
) -> list[str]:
    """Return contract errors for one browser vector-contour descriptor."""
    issues: list[str] = []
    expected_path = f"detail/{indicator_id}/{{z}}/{{x}}/{{y}}.pbf"
    if indicator_id not in VECTOR_CONTOUR_INDICATORS:
        issues.append("indicator does not support vector contours")
    if descriptor.get("schema_version") != 1:
        issues.append("descriptor schema_version must be 1")
    if descriptor.get("type") != "vector_contours":
        issues.append("descriptor type must be vector_contours")
    if descriptor.get("tiles") != [expected_path]:
        issues.append(f"tiles must contain exactly {expected_path!r}")
    if descriptor.get("minzoom") != 11 or descriptor.get("maxzoom") != 15:
        issues.append("vector contours must declare zooms 11–15")
    if descriptor.get("source_layer") != indicator_id:
        issues.append(f"source_layer must be {indicator_id!r}")
    bounds = descriptor.get("bounds")
    if not (
        isinstance(bounds, list)
        and len(bounds) == 4
        and all(isinstance(value, (int, float)) for value in bounds)
        and -180 <= float(bounds[0]) < float(bounds[2]) <= 180
        and -90 <= float(bounds[1]) < float(bounds[3]) <= 90
    ):
        issues.append("bounds must be a valid WGS84 [west,south,east,north] extent")
    if descriptor.get("bands") != list(NOISE_LDEN_BANDS):
        issues.append("descriptor must declare the canonical five Lden bands")
    if descriptor.get("source_support_preserved") is not True:
        issues.append("descriptor does not preserve source support")
    if not _valid_sha256(descriptor.get("source_manifest_sha256")):
        issues.append("descriptor lacks source_manifest_sha256")
    source_assets = descriptor.get("source_assets")
    if not isinstance(source_assets, list) or not source_assets:
        issues.append("descriptor must list at least one contributing source asset")
        source_assets = []
    else:
        paths: set[str] = set()
        for asset in source_assets:
            if not isinstance(asset, Mapping):
                issues.append("source_assets entries must be objects")
                continue
            path = asset.get("path")
            if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
                issues.append("source asset paths must be safe relative paths")
            elif path in paths:
                issues.append(f"duplicate source asset path {path!r}")
            else:
                paths.add(path)
            if not _valid_sha256(asset.get("sha256")):
                issues.append(f"source asset {path!r} lacks a SHA-256")
    direct_hash = descriptor.get("source_sha256")
    if len(source_assets) == 1:
        only_hash = source_assets[0].get("sha256") if isinstance(source_assets[0], Mapping) else None
        if direct_hash != only_hash:
            issues.append("single-source descriptor must repeat its ZIP hash as source_sha256")
    elif direct_hash is not None:
        issues.append("multi-source descriptor must use source_assets instead of source_sha256")
    validation = descriptor.get("validation")
    expected_validation = f"detail/{indicator_id}.vector_contours.validation.json"
    if not isinstance(validation, Mapping):
        issues.append("descriptor lacks validation report reference")
    else:
        if validation.get("path") != expected_validation:
            issues.append(f"validation path must be {expected_validation!r}")
        if not _valid_sha256(validation.get("sha256")):
            issues.append("validation report reference lacks a SHA-256")
    return issues


def detail_asset_for_indicator(
    indicator_id: str,
    files: Iterable[str],
    metadata: Mapping[str, Any] | None = None,
    geojson_metadata: Mapping[str, Any] | None = None,
    vector_contour_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the browser asset actually published for an indicator.

    COG is preferred.  The GeoJSON branch is a temporary compatibility bridge
    for the pre-v2 ``subcomuna`` assets; it is only advertised when the exact
    file exists in this study bundle.
    """
    available = {str(path) for path in files}
    vector_descriptor = f"detail/{indicator_id}.vector_contours.json"
    if vector_descriptor in available:
        descriptor = (
            vector_contour_metadata
            if isinstance(vector_contour_metadata, Mapping)
            else {}
        )
        issues = validate_vector_contour_descriptor(indicator_id, descriptor)
        if issues:
            raise ValueError(
                f"Invalid vector-contour detail {indicator_id!r}: " + "; ".join(issues)
            )
        record = deepcopy(dict(descriptor))
        record["path"] = vector_descriptor
        return record
    cog = f"detail/{indicator_id}.tif"
    if cog in available:
        expected_resolution = DETAIL_NATIVE_RESOLUTION_M.get(indicator_id)
        actual_resolution = (
            metadata.get("source_native_resolution_m")
            if isinstance(metadata, Mapping)
            else None
        )
        if expected_resolution is not None:
            try:
                scale_matches = (
                    actual_resolution is not None
                    and abs(float(actual_resolution) / expected_resolution - 1.0) <= 0.01
                )
            except (TypeError, ValueError, ZeroDivisionError):
                scale_matches = False
            if not scale_matches:
                return None
        if not canonical_detail_source_grid(indicator_id, metadata):
            return None
        temporal_support = (
            metadata.get("temporal_support")
            if isinstance(metadata, Mapping)
            else None
        )
        if (
            indicator_id in YEAR_SCOPED_DETAIL_INDICATORS
            and not valid_year_temporal_support(temporal_support)
        ):
            raise ValueError(
                f"Year-scoped detail {indicator_id!r} lacks valid temporal_support"
            )
        band = DETAIL_BANDS.get(indicator_id, 1)
        record: dict[str, Any] = {
            "type": "cog",
            "path": cog,
            "band": band,
            "canonical_resolution_verified": True,
            "source_native_resolution_m": float(actual_resolution),
        }
        by_band = metadata.get("statistics_by_band", {}) if isinstance(metadata, Mapping) else {}
        stats = by_band.get(str(band), metadata.get("statistics", {})) if isinstance(by_band, Mapping) and isinstance(metadata, Mapping) else {}
        if isinstance(stats, Mapping) and stats.get("p02") is not None and stats.get("p98") is not None:
            record["color_domain"] = {"min": stats["p02"], "max": stats["p98"]}
        if indicator_id in DETAIL_UNITS:
            record["unit"] = DETAIL_UNITS[indicator_id]
        if indicator_id in DETAIL_METRIC_LABELS:
            record["metric_label"] = DETAIL_METRIC_LABELS[indicator_id]
        source_grid = metadata.get("source_grid") if isinstance(metadata, Mapping) else None
        if isinstance(source_grid, Mapping):
            record["source_grid"] = deepcopy(dict(source_grid))
        if valid_temporal_support(temporal_support):
            record["temporal_support"] = deepcopy(dict(temporal_support))
        return record
    legacy = f"subcomuna/{indicator_id}.geojson"
    legacy_meta = geojson_metadata if isinstance(geojson_metadata, Mapping) else {}
    # Historical vector detail must prove that it was generated from real
    # spatial support. Green formerly used a different grid phase per commune,
    # so it also needs the shared-AOI alignment marker.
    legacy_is_real = legacy_meta.get("is_synthetic") is False
    # Every browser GeoJSON detail must be a stable analysis grid.  This
    # makes the former green-only safeguard apply equally to vector-derived
    # access surfaces such as healthcare.
    legacy_grid_ok = legacy_meta.get("grid_alignment") == "study_aoi_metric_grid"
    if legacy in available and legacy_is_real and legacy_grid_ok:
        record = {"type": "geojson", "path": legacy}
        if indicator_id in DETAIL_UNITS:
            record["unit"] = DETAIL_UNITS[indicator_id]
        return record
    return None


def indicators_for_bundle(
    files: Iterable[str],
    *,
    detail_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    geojson_detail_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    vector_contour_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    administrative_unit_label: str = "unidad administrativa",
    is_native: bool = False,
) -> dict[str, dict[str, Any]]:
    """Materialize immutable public support declarations for a web bundle."""
    file_list = tuple(files)
    records: dict[str, dict[str, Any]] = {}
    for indicator_id, spec in INDICATOR_SUPPORT.items():
        record = deepcopy(spec)
        record["publication_target"] = publication_target(record)
        detail = detail_asset_for_indicator(
            indicator_id,
            file_list,
            (detail_metadata or {}).get(indicator_id),
            (geojson_detail_metadata or {}).get(indicator_id),
            (vector_contour_metadata or {}).get(indicator_id),
        )
        if detail is not None:
            if detail["type"] == "vector_contours":
                rendered = {
                    "kind": "vector_contours",
                    "label": "Contornos vectoriales MER/SICA",
                    "resolution": None,
                }
                record["boundary_role"] = "mask_only"
            else:
                rendered = deepcopy(record["analysis"])
                rendered["kind"] = detail["type"]
            record["rendered"] = rendered
            record["detail"] = detail
        elif is_native:
            record["detail"] = None
            record["rendered"] = {
                "kind": "unavailable",
                "label": "sin mapa web publicado",
                "resolution": None,
            }
        else:
            record["detail"] = None
            rendered = record.get("rendered") or {}
            if (
                record["boundary_role"] == "mask_only"
                or (
                    rendered.get("kind") == "administrative_polygon"
                    and record["boundary_role"] != "component_specific"
                )
            ):
                record["rendered"] = {
                    "kind": "administrative_polygon",
                    "label": administrative_unit_label,
                    "resolution": None,
                }
                # Once only a polygon summary is published, the polygon is no
                # longer merely an AOI mask: it defines the reported value.
                # ``mask_only`` is reserved for a real fine-detail asset.
                if record["boundary_role"] == "mask_only":
                    record["boundary_role"] = "analysis_unit"
        records[indicator_id] = record
    return records


def apply_indicator_availability(
    records: Mapping[str, Mapping[str, Any]],
    *,
    enabled_layers: Iterable[str],
    available_layers: Iterable[str],
    country_code: str,
    layer_countries: Mapping[str, Iterable[str]],
    palette_statuses: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Attach per-study availability without duplicating catalog policy in JS."""
    enabled = {str(layer_id) for layer_id in enabled_layers}
    available = {str(layer_id) for layer_id in available_layers}
    country = str(country_code).upper()
    annotated: dict[str, dict[str, Any]] = {}
    for indicator_id, source_record in records.items():
        record = deepcopy(dict(source_record))
        layer_id = str(record.get("layer_id") or "")
        supported = tuple(str(code).upper() for code in layer_countries.get(layer_id, ()))
        palette_status = palette_statuses.get(indicator_id)
        if palette_status == "coming_soon":
            availability = {"status": "unavailable", "reason": "coming_soon"}
        elif supported and country not in supported:
            availability = {
                "status": "unavailable",
                "reason": "country_not_supported",
                "supported_countries": list(supported),
            }
        elif layer_id in available:
            availability = {"status": "available", "reason": None}
        elif layer_id in enabled:
            availability = {
                "status": "unavailable",
                "reason": "not_published_by_study",
            }
        else:
            availability = {
                "status": "unavailable",
                "reason": "not_enabled_by_study",
            }
        record["availability"] = availability
        if availability["status"] == "unavailable":
            labels = {
                "coming_soon": "indicador en preparación",
                "country_not_supported": f"fuente no disponible para {country}",
                "not_published_by_study": "capa habilitada pero no publicada",
                "not_enabled_by_study": "capa no habilitada en el estudio",
            }
            record["detail"] = None
            record["rendered"] = {
                "kind": "unavailable",
                "label": labels[str(availability["reason"])],
                "resolution": None,
            }
        annotated[indicator_id] = record
    return annotated


def validate_indicator_records(
    records: Mapping[str, Any],
    *,
    require_publication_target: bool = False,
    require_availability: bool = False,
) -> list[str]:
    """Return publication errors without assuming any particular raster library.

    ``publication_target`` was added after schema-v3 bundles already existed.
    Older manifests remain auditable because coverage can derive the target
    from their support declarations. New publications require the explicit
    field, which freezes the decision made at release time.
    """
    issues: list[str] = []
    for indicator_id, record in records.items():
        if not isinstance(record, Mapping):
            issues.append(f"indicator {indicator_id!r} is not an object")
            continue
        role = record.get("boundary_role")
        if role not in {"mask_only", "analysis_unit", "source_unit", "component_specific"}:
            issues.append(f"indicator {indicator_id!r} has invalid boundary_role")
        target = record.get("publication_target")
        if not isinstance(target, Mapping):
            if require_publication_target:
                issues.append(f"indicator {indicator_id!r} lacks publication_target")
        elif target.get("kind") not in {
            "native_raster",
            "native_vector",
            "analysis_grid",
            "administrative_or_component_specific",
        } or not isinstance(target.get("required_for_production"), bool):
            issues.append(f"indicator {indicator_id!r} has invalid publication_target")
        availability = record.get("availability")
        if not isinstance(availability, Mapping):
            if require_availability:
                issues.append(f"indicator {indicator_id!r} lacks availability")
        else:
            status = availability.get("status")
            reason = availability.get("reason")
            valid_reasons = {
                "country_not_supported",
                "not_enabled_by_study",
                "not_published_by_study",
                "coming_soon",
            }
            if status not in {"available", "unavailable"}:
                issues.append(f"indicator {indicator_id!r} has invalid availability status")
            if status == "available" and reason is not None:
                issues.append(f"indicator {indicator_id!r} available status has a reason")
            if status == "unavailable" and reason not in valid_reasons:
                issues.append(f"indicator {indicator_id!r} has invalid unavailability reason")
            if reason == "country_not_supported" and not availability.get(
                "supported_countries"
            ):
                issues.append(
                    f"indicator {indicator_id!r} country restriction lacks supported_countries"
                )
        for field in ("downloaded", "observation", "analysis", "rendered"):
            value = record.get(field)
            if not isinstance(value, Mapping):
                issues.append(f"indicator {indicator_id!r} lacks {field} support")
                continue
            if "kind" not in value or "label" not in value or "resolution" not in value:
                issues.append(f"indicator {indicator_id!r} has invalid {field} support")
        if record.get("downloaded", {}).get("kind") == "raster_grid" and record.get("observation", {}).get("resolution") is None:
            issues.append(f"indicator {indicator_id!r} raster has no observational support")
        if indicator_id == "wildfire":
            components = record.get("components")
            if not isinstance(components, Mapping) or not components:
                issues.append("wildfire composite has no component supports")
        detail = record.get("detail")
        rendered = record.get("rendered")
        if (
            isinstance(availability, Mapping)
            and availability.get("status") == "unavailable"
            and (detail is not None or rendered.get("kind") != "unavailable")
        ):
            issues.append(f"indicator {indicator_id!r} unavailable status advertises a map")
        if detail is not None:
            if not isinstance(detail, Mapping) or detail.get("type") not in {
                "cog",
                "geojson",
                "vector_contours",
            }:
                issues.append(f"indicator {indicator_id!r} has invalid detail asset")
            if detail.get("type") == "cog" and not isinstance(detail.get("color_domain"), Mapping):
                issues.append(f"indicator {indicator_id!r} COG has no color domain")
            if (
                indicator_id in YEAR_SCOPED_DETAIL_INDICATORS
                and detail.get("type") == "cog"
                and not valid_year_temporal_support(detail.get("temporal_support"))
            ):
                issues.append(
                    f"indicator {indicator_id!r} COG lacks valid temporal_support"
                )
            if role != "mask_only":
                issues.append(f"indicator {indicator_id!r} advertises detail with source-unit boundaries")
            if (
                not isinstance(rendered, Mapping)
                or (
                    detail.get("type") != "vector_contours"
                    and rendered.get("resolution") is None
                )
            ):
                issues.append(f"indicator {indicator_id!r} detail has no rendered support")
            if (
                detail.get("type") == "vector_contours"
                and (
                    rendered.get("kind") != "vector_contours"
                    or rendered.get("resolution") is not None
                )
            ):
                issues.append(
                    f"indicator {indicator_id!r} vector contours invent rendered resolution"
                )
        elif (
            isinstance(rendered, Mapping)
            and rendered.get("kind") == "administrative_polygon"
            and role == "mask_only"
        ):
            issues.append(
                f"indicator {indicator_id!r} administrative rendering cannot use mask_only boundaries"
            )
    return issues


def validate_palette_coverage(exposomes: Mapping[str, Any]) -> list[str]:
    """Ensure every browser-facing card has an explicit support declaration."""
    unknown = sorted(set(exposomes) - set(INDICATOR_SUPPORT))
    return [f"palette exposome {indicator_id!r} lacks a spatial-support declaration" for indicator_id in unknown]
