"""Resumable annual-exposome collection for any configured aggregate study.

This module only materializes provider-backed annual exposure tables.  It does
not rebuild the master, publish web assets, or run any health-outcome analysis.
Network-heavy collection is deliberately exposed through a human-run CLI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
from tqdm import tqdm

from .studies import StudyContext, load_study


SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, SCHEMA_VERSION})
DEFAULT_STUDY = "santiago_communes"

DERIVED_LAYERS = frozenset({"precipitation_spi", "sleep_context"})
OUTCOME_LAYERS = frozenset({"neuro_mortality", "neuro_hospitalizations"})
STATIC_REASONS: dict[str, str] = {
    "air_quality": "Legacy CAMS/Open-Meteo snapshot; no validated annual historical contract.",
    "socioeconomic": "Administrative/survey harvests, not a homogeneous annual provider series.",
    "noise": "Official Gran Santiago noise map is a single 2023 product.",
    "greenspace_access": "Current OpenStreetMap snapshot has no equivalent historical archive.",
    "greenspace_cv": "Sampled imagery validation is not an annual production layer.",
    "walkability": "Current OpenStreetMap street-network snapshot.",
    "public_transport": "Current OpenStreetMap transport snapshot.",
    "social_infrastructure": "Current OpenStreetMap snapshot.",
    "food_environment": "Current OpenStreetMap snapshot.",
    "healthcare": "Current official/OSM facility inventory.",
    "demography": "Census/projection harvest, not an annually observed exposome.",
    "food_insecurity": "Selected CASEN harvests already represented as year columns.",
    "pobreza_sae": "Selected SAE harvests already represented as year columns.",
}


@dataclass(frozen=True)
class TemporalSpec:
    """One annual provider product declared by resolved layer settings."""

    layer_id: str
    adapter: str
    first_year: int
    last_year: int
    source: str
    indicators: tuple["TemporalIndicatorSpec", ...] = ()

    def years(self, project_start: int, project_end: int) -> tuple[int, ...]:
        first = max(self.first_year, project_start)
        last = min(self.last_year, project_end)
        return tuple(range(first, last + 1)) if first <= last else ()


@dataclass(frozen=True)
class TemporalIndicatorSpec:
    """Browser-facing indicator backed by one annual product table."""

    exposome_id: str
    value_column: str
    label: str | None = None
    unit: str | None = None
    detail_kind: str | None = None
    detail_band: int = 1
    detail_native_resolution_m: float | None = None
    detail_source_label: str | None = None
    detail_metric_label: str | None = None
    detail_unit: str | None = None
    detail_required_for_production: bool = False
    detail_analysis_resolution_m: float | None = None
    detail_source_resolution_m: float | None = None


@dataclass(frozen=True)
class AnnualRasterDetail:
    """One provider-backed annual raster checkpoint."""

    indicator_id: str
    raster_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class AnnualAnalysisGridDetail:
    """One provider-backed annual analysis-grid checkpoint."""

    indicator_id: str
    geojson_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class AnnualBuildResult:
    """Annual table plus any source rasters collected for the same year."""

    frame: pd.DataFrame
    details: tuple[AnnualRasterDetail | AnnualAnalysisGridDetail, ...] = ()


@dataclass(frozen=True)
class TemporalPaths:
    output_root: Path
    cache_root: Path

    def year_dir(self, layer_id: str, year: int) -> Path:
        return self.output_root / layer_id / str(year)

    def cache_dir(self, layer_id: str) -> Path:
        return self.cache_root / layer_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    frame.to_csv(partial, index=False)
    partial.replace(path)


def _project_years(context: StudyContext) -> tuple[int, int]:
    period = context.study.period
    try:
        start = int(str(period["start_date"])[:4])
        end = int(str(period["end_date"])[:4])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Study period must declare start_date and end_date") from exc
    return start, end


def discover_temporal_specs(context: StudyContext) -> tuple[TemporalSpec, ...]:
    """Resolve all configured annual products enabled by a study."""
    cfg = context.resolved_config()
    enabled = set(context.enabled_layers)
    records: list[Mapping[str, Any]] = []
    for layer_id, settings in cfg.items():
        if not isinstance(settings, Mapping):
            continue
        temporal = settings.get("temporal")
        if not isinstance(temporal, Mapping):
            continue
        products = temporal.get("products")
        if isinstance(products, list):
            records.extend(record for record in products if isinstance(record, Mapping))
        else:
            records.append({"layer_id": layer_id, **temporal})

    specs: list[TemporalSpec] = []
    for record in records:
        layer_id = str(record.get("layer_id") or "")
        if layer_id not in enabled or record.get("status") != "annual_downloadable":
            continue
        raw_indicators = record.get("indicators") or []
        if not isinstance(raw_indicators, list):
            raise ValueError(f"Temporal indicators for {layer_id!r} must be a list")
        indicators: list[TemporalIndicatorSpec] = []
        for raw_indicator in raw_indicators:
            if not isinstance(raw_indicator, Mapping):
                raise ValueError(f"Temporal indicator for {layer_id!r} must be a mapping")
            exposome_id = str(raw_indicator.get("exposome_id") or "").strip()
            value_column = str(raw_indicator.get("value_column") or "").strip()
            if not exposome_id or not value_column:
                raise ValueError(
                    f"Temporal indicator for {layer_id!r} requires exposome_id and value_column"
                )
            raw_detail = raw_indicator.get("detail")
            if raw_detail is not None and not isinstance(raw_detail, Mapping):
                raise ValueError(
                    f"Temporal detail for {layer_id!r}/{exposome_id!r} must be a mapping"
                )
            detail_kind = str(raw_detail.get("kind") or "") if raw_detail else None
            if detail_kind and detail_kind not in {"native_raster", "analysis_grid"}:
                raise ValueError(
                    f"Unsupported temporal detail kind {detail_kind!r} for {exposome_id!r}"
                )
            indicators.append(
                TemporalIndicatorSpec(
                    exposome_id=exposome_id,
                    value_column=value_column,
                    label=(str(raw_indicator["label"]) if raw_indicator.get("label") else None),
                    unit=(str(raw_indicator["unit"]) if raw_indicator.get("unit") else None),
                    detail_kind=detail_kind or None,
                    detail_band=int(raw_detail.get("band", 1)) if raw_detail else 1,
                    detail_native_resolution_m=(
                        float(raw_detail["native_resolution_m"])
                        if raw_detail and raw_detail.get("native_resolution_m") is not None
                        else None
                    ),
                    detail_source_label=(
                        str(raw_detail["source_label"])
                        if raw_detail and raw_detail.get("source_label")
                        else None
                    ),
                    detail_metric_label=(
                        str(raw_detail["metric_label"])
                        if raw_detail and raw_detail.get("metric_label")
                        else None
                    ),
                    detail_unit=(
                        str(raw_detail["unit"])
                        if raw_detail and raw_detail.get("unit")
                        else None
                    ),
                    detail_required_for_production=bool(
                        raw_detail and raw_detail.get("required_for_production", False)
                    ),
                    detail_analysis_resolution_m=(
                        float(raw_detail["analysis_resolution_m"])
                        if raw_detail and raw_detail.get("analysis_resolution_m") is not None
                        else None
                    ),
                    detail_source_resolution_m=(
                        float(raw_detail["source_resolution_m"])
                        if raw_detail and raw_detail.get("source_resolution_m") is not None
                        else None
                    ),
                )
            )
        specs.append(
            TemporalSpec(
                layer_id=layer_id,
                adapter=str(record["adapter"]),
                first_year=int(record["available_start_year"]),
                last_year=int(record["available_end_year"]),
                source=str(record["source"]),
                indicators=tuple(indicators),
            )
        )
    duplicated = pd.Series([spec.layer_id for spec in specs]).duplicated()
    if duplicated.any():
        raise ValueError("Temporal configuration contains duplicate layer_id values")
    return tuple(sorted(specs, key=lambda item: item.layer_id))


def default_paths(context: StudyContext) -> TemporalPaths:
    return TemporalPaths(
        output_root=context.paths.processed / "temporal_exposomes",
        cache_root=context.paths.cache / "temporal_exposomes",
    )


def _manifest_path(paths: TemporalPaths, spec: TemporalSpec, year: int) -> Path:
    return paths.year_dir(spec.layer_id, year) / "manifest.json"


def _validated_manifest(
    path: Path,
    *,
    study_id: str,
    layer_id: str,
    year: int,
    expected_units: int,
    expected_spatial_ids: Iterable[str],
    spec: TemporalSpec | None = None,
    require_details: bool = True,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        annual = path.parent / str(manifest["annual_table"])
        if (
            manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS
            or manifest.get("study_id", manifest.get("study")) != study_id
            or manifest.get("layer_id") != layer_id
            or int(manifest.get("year")) != year
            or int(manifest.get("n_rows")) != expected_units
            or not annual.is_file()
            or manifest.get("sha256") != _sha256(annual)
        ):
            return None
        frame = pd.read_csv(annual, dtype={"spatial_id": str})
        actual_ids = set(frame["spatial_id"].astype(str))
        if (
            len(frame) != expected_units
            or frame["spatial_id"].duplicated().any()
            or actual_ids != set(str(value) for value in expected_spatial_ids)
        ):
            return None
        required_details = tuple(
            indicator
            for indicator in (spec.indicators if spec else ())
            if indicator.detail_kind in {"native_raster", "analysis_grid"}
        )
        if require_details and required_details:
            if manifest.get("schema_version") != SCHEMA_VERSION:
                return None
            details = manifest.get("details")
            if not isinstance(details, Mapping):
                return None
            for indicator in required_details:
                detail = details.get(indicator.exposome_id)
                if not isinstance(detail, Mapping):
                    return None
                asset = path.parent / str(detail.get("path") or "")
                metadata_path = path.parent / str(detail.get("metadata") or "")
                if (
                    detail.get("kind") != indicator.detail_kind
                    or not asset.is_file()
                    or not metadata_path.is_file()
                    or detail.get("sha256") != _sha256(asset)
                    or detail.get("metadata_sha256") != _sha256(metadata_path)
                ):
                    return None
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                expected_support = {
                    "kind": "year",
                    "year": str(year),
                    "source_label": indicator.detail_source_label or spec.source,
                }
                if metadata.get("temporal_support") != expected_support:
                    return None
                if indicator.detail_kind == "analysis_grid":
                    payload = json.loads(asset.read_text(encoding="utf-8"))
                    if (
                        payload.get("grid_alignment") != "study_aoi_metric_grid"
                        or payload.get("is_synthetic") is not False
                        or payload.get("temporal_support") != expected_support
                        or float(payload.get("analysis_resolution_m", 0))
                        != float(indicator.detail_analysis_resolution_m or 0)
                    ):
                        return None
                    continue
                if indicator.detail_native_resolution_m is not None:
                    if abs(
                        float(metadata.get("source_native_resolution_m", 0))
                        / indicator.detail_native_resolution_m
                        - 1.0
                    ) > 0.01:
                        return None
                from .spatial_detail import raster_grid_signature
                from .spatial_support import canonical_detail_source_grid

                actual_grid = raster_grid_signature(asset)
                if metadata.get("export_grid") != actual_grid:
                    return None
                if not canonical_detail_source_grid(indicator.exposome_id, {
                    "source_grid": actual_grid,
                }):
                    return None
        return manifest
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _canonical_units(context: StudyContext) -> pd.DataFrame:
    units = context.load_spatial_units()
    return units[["spatial_id", "spatial_name", "area_km2"]].copy().assign(
        spatial_id=lambda frame: frame["spatial_id"].astype(str)
    )


def _normalize_annual_frame(
    frame: pd.DataFrame,
    *,
    units: pd.DataFrame,
    layer_id: str,
    year: int,
) -> pd.DataFrame:
    out = pd.DataFrame(frame.drop(columns="geometry", errors="ignore")).copy()
    if "spatial_id" in out.columns:
        out["spatial_id"] = out["spatial_id"].astype(str)
        out = out.drop(columns=["spatial_name"], errors="ignore").merge(
            units[["spatial_id", "spatial_name"]],
            on="spatial_id",
            how="left",
            validate="one_to_one",
        )
    else:
        name_column = "name" if "name" in out.columns else "spatial_name"
        if name_column not in out.columns:
            raise ValueError(f"{layer_id} {year} has no spatial identifier")
        lookup = units.rename(columns={"spatial_name": name_column})[
            ["spatial_id", name_column]
        ]
        out = lookup.merge(out, on=name_column, how="left", validate="one_to_one")
        if name_column != "spatial_name":
            out.insert(1, "spatial_name", out[name_column])

    expected = set(units["spatial_id"])
    actual = set(out["spatial_id"].dropna().astype(str))
    if len(out) != len(units) or expected != actual or out["spatial_id"].duplicated().any():
        raise ValueError(
            f"{layer_id} {year} coverage mismatch: rows={len(out)}, "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    out["year"] = int(year)
    front = ["spatial_id", "spatial_name", "year"]
    remaining = [column for column in out.columns if column not in front]
    out = out[front + remaining].sort_values("spatial_id").reset_index(drop=True)
    value_columns = [
        column
        for column in out.columns
        if column not in {"spatial_id", "spatial_name", "year", "name"}
    ]
    if not value_columns:
        raise ValueError(f"{layer_id} {year} has no exposure values")
    if out[value_columns].isna().any().any():
        missing = out[value_columns].columns[out[value_columns].isna().any()].tolist()
        raise ValueError(f"{layer_id} {year} contains missing values in {missing}")
    numeric = out[value_columns].select_dtypes(include=[np.number])
    if numeric.empty or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{layer_id} {year} has no finite numeric exposure values")
    return out


def _read_builder_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Annual builder did not write {path}")
    return pd.read_csv(path, dtype={"spatial_id": str})


def _attach_native_details(
    spec: TemporalSpec,
    year: int,
    frame: pd.DataFrame,
    *,
    context: StudyContext,
    paths: TemporalPaths,
) -> pd.DataFrame | AnnualBuildResult:
    """Materialize only the source rasters declared by the temporal contract."""
    indicators = tuple(
        indicator
        for indicator in spec.indicators
        if indicator.detail_kind == "native_raster"
    )
    if not indicators:
        return frame
    detail_dir = paths.year_dir(spec.layer_id, year) / "detail-source"
    if spec.adapter == "pm25":
        from .pm25 import export_annual_pm25_raster

        raster, metadata = export_annual_pm25_raster(context, year, detail_dir)
    else:
        from .annual_spatial_detail import export_annual_raster

        source_labels = {
            indicator.detail_source_label or spec.source for indicator in indicators
        }
        if len(source_labels) != 1:
            raise ValueError(
                f"Annual {spec.layer_id} indicators must share one source label"
            )
        raster, metadata = export_annual_raster(
            context,
            adapter=spec.adapter,
            year=year,
            output_dir=detail_dir,
            source_label=next(iter(source_labels)),
        )
    return AnnualBuildResult(
        frame,
        tuple(
            AnnualRasterDetail(indicator.exposome_id, raster, metadata)
            for indicator in indicators
        ),
    )


def _attach_analysis_grid_details(
    spec: TemporalSpec,
    year: int,
    frame: pd.DataFrame,
    *,
    context: StudyContext,
    paths: TemporalPaths,
) -> pd.DataFrame | AnnualBuildResult:
    indicators = tuple(
        indicator
        for indicator in spec.indicators
        if indicator.detail_kind == "analysis_grid"
    )
    if not indicators:
        return frame
    if spec.adapter != "greenspace_multisource" or {
        item.exposome_id for item in indicators
    } != {"green"}:
        raise ValueError(
            f"Adapter {spec.adapter!r} has no annual analysis-grid exporter"
        )
    from .annual_spatial_detail import export_annual_green_grid

    indicator = indicators[0]
    geojson, metadata = export_annual_green_grid(
        context,
        year=year,
        output_dir=paths.year_dir(spec.layer_id, year) / "detail-source",
        cache_dir=paths.cache_dir(spec.layer_id) / "green-detail",
        source_label=indicator.detail_source_label or spec.source,
    )
    return AnnualBuildResult(
        frame,
        (AnnualAnalysisGridDetail(indicator.exposome_id, geojson, metadata),),
    )


def _run_adapter(
    spec: TemporalSpec,
    year: int,
    *,
    context: StudyContext,
    paths: TemporalPaths,
    existing_frame: pd.DataFrame | None = None,
) -> pd.DataFrame | AnnualBuildResult:
    """Run one provider/year through existing tested layer functions."""
    city = context.study.id
    out_dir = paths.year_dir(spec.layer_id, year) / "builder"
    cache_dir = paths.cache_dir(spec.layer_id)
    figures_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if spec.adapter == "pm25":
        from .pm25 import build_pm25_layer

        frame = (
            existing_frame
            if existing_frame is not None
            else build_pm25_layer(city, cache_dir, out_dir, years=[year])[0]
        )
        return _attach_native_details(
            spec, year, frame, context=context, paths=paths
        )
    if spec.adapter == "air_quality_satellite":
        from .air_quality import build_air_quality_layer

        frame = existing_frame if existing_frame is not None else build_air_quality_layer(
            city, cache_dir, out_dir, year=year
        )[0]
        return _attach_native_details(spec, year, frame, context=context, paths=paths)
    if spec.adapter == "alan":
        from .alan import build_alan_layer

        frame = existing_frame if existing_frame is not None else build_alan_layer(
            city, cache_dir, out_dir, year=year
        )[0]
        return _attach_native_details(spec, year, frame, context=context, paths=paths)
    if spec.adapter == "greenspace_coverage":
        from .greenspace_satellite import build_greenspace_coverage_layer

        if existing_frame is not None:
            return existing_frame
        csv_path, _ = build_greenspace_coverage_layer(
            city, cache_dir, out_dir, figures_dir, years=[year]
        )
        return _read_builder_csv(csv_path)
    if spec.adapter == "greenspace_multisource":
        from .greenspace_multisource import build_greenspace_multisource_layer

        if existing_frame is not None:
            frame = existing_frame
        else:
            csv_path, _ = build_greenspace_multisource_layer(
                city, cache_dir, out_dir, figures_dir, years=[year]
            )
            frame = _read_builder_csv(csv_path)
        return _attach_analysis_grid_details(
            spec, year, frame, context=context, paths=paths
        )
    if spec.adapter == "climate_heat":
        from .climate.build_layer import build_climate_heat_layer
        from .climate.fetch_era5land import fetch_era5land_years

        if existing_frame is None:
            fetch_era5land_years(
                city=city,
                years=[year],
                cache_dir=cache_dir,
                out_dir=out_dir,
            )
            frame = build_climate_heat_layer(
                city=city,
                cache_dir=cache_dir,
                out_dir=out_dir,
                source="era5land",
                year=year,
                fallback_to_representative_point=False,
                base_name=f"{city}_climate_heat_era5land_{year}",
            )[0]
        else:
            frame = existing_frame
        return _attach_native_details(spec, year, frame, context=context, paths=paths)
    if spec.adapter == "climate_openmeteo":
        from .climate.fetch_openmeteo import fetch_openmeteo_years
        from .climate_metrics import build_climate_metrics_layer

        if existing_frame is not None:
            return existing_frame
        daily = fetch_openmeteo_years(
            city=city,
            years=[year],
            cache_dir=cache_dir,
            out_dir=out_dir,
        )
        daily_path = out_dir / f"{city}_climate_openmeteo_daily_{year}_{year}.csv"
        if not daily_path.is_file():
            _atomic_csv(daily_path, daily)
        return build_climate_metrics_layer(
            city=city,
            daily_csv=daily_path,
            out_dir=out_dir,
            cache_dir=cache_dir,
        )[0]
    if spec.adapter == "wind":
        from .wind import build_wind_layer

        frame = existing_frame if existing_frame is not None else build_wind_layer(
            city, cache_dir, out_dir, year=year
        )[0]
        return _attach_native_details(spec, year, frame, context=context, paths=paths)
    if spec.adapter == "precipitation":
        from .precipitation import build_precipitation_layer

        frame = existing_frame if existing_frame is not None else build_precipitation_layer(
            city, cache_dir, out_dir, years=[year]
        )[0]
        return _attach_native_details(spec, year, frame, context=context, paths=paths)
    if spec.adapter == "wildfire":
        # build_wildfire_layer collapses years into one summary row per unit;
        # the annual product needs the per-year frame, so ask for that instead.
        from .wildfire import build_wildfire_annual_frame

        if existing_frame is not None:
            return existing_frame
        frame = build_wildfire_annual_frame(city, cache_dir, years=[year])
        return frame.drop(columns="year", errors="ignore")
    if spec.adapter == "heavy_metals":
        from .heavy_metals import build_heavy_metals_layer

        if existing_frame is not None:
            return existing_frame
        return build_heavy_metals_layer(
            city=city, cache_dir=cache_dir, out_dir=out_dir, years=[year]
        )[0]
    raise ValueError(f"No annual adapter registered for {spec.adapter!r}")


def _study_period_token(context: StudyContext) -> str:
    start, end = _project_years(context)
    return f"{start}_{end}"


def _canonical_local_source(
    spec: TemporalSpec, context: StudyContext
) -> tuple[Path, str] | None:
    """Resolve a study-owned local source without crossing city namespaces.

    The Santiago wildfire cache predates canonical study paths, so it retains
    one explicit compatibility fallback. No other study may consult it.
    """
    study_id = context.study.id
    period = _study_period_token(context)
    if spec.adapter == "precipitation":
        return (
            context.paths.processed
            / "precipitation"
            / f"{study_id}_precipitation_chirps_daily_{period}.csv",
            "precipitation",
        )
    if spec.adapter == "wildfire":
        canonical = (
            context.paths.cache
            / "wildfire"
            / f"{study_id}_wildfire_annual_{period}.csv"
        )
        if canonical.is_file() or study_id != DEFAULT_STUDY:
            return canonical, "wildfire"
        return (
            context.repo_root / "cache" / "santiago_wildfire_annual_2015_2024.csv",
            "wildfire",
        )
    return None


def _legacy_precipitation_frame(context: StudyContext, year: int) -> pd.DataFrame | None:
    source = _canonical_local_source(
        TemporalSpec("precipitation", "precipitation", 0, 9999, ""), context
    )
    if source is None:
        return None
    daily_path, _ = source
    if not daily_path.is_file():
        return None
    from .precipitation import calculate_annual_precipitation_table

    daily = pd.read_csv(daily_path, usecols=["name", "date", "precipitation_mm"])
    dates = pd.to_datetime(daily["date"])
    annual = daily.loc[dates.dt.year == year].copy()
    if annual.empty:
        return None
    table = calculate_annual_precipitation_table(annual)
    rename = {
        "annual_total": "precip_annual_mm",
        "n_days": "precip_n_days",
        "wet_days": "precip_wet_days",
        "wet_day_pct": "precip_wet_day_pct",
        "heavy_days": "precip_heavy_days_10mm",
        "very_heavy_days": "precip_very_heavy_days_20mm",
        "rx1day": "precip_rx1day_mm",
        "rx5day": "precip_rx5day_mm",
        "cdd": "precip_cdd_days",
        "cwd": "precip_cwd_days",
    }
    return table.drop(columns="year").rename(columns=rename)


def _legacy_wildfire_frame(context: StudyContext, year: int) -> pd.DataFrame | None:
    source = _canonical_local_source(
        TemporalSpec("wildfire", "wildfire", 0, 9999, ""), context
    )
    if source is None or not source[0].is_file():
        return None
    path, _ = source
    annual = pd.read_csv(path)
    frame = annual.loc[pd.to_numeric(annual["year"], errors="coerce") == year].copy()
    if frame.empty:
        return None
    frame = frame.drop(columns="year")
    units = _canonical_units(context)
    area = units.rename(columns={"spatial_name": "name"})[["name", "area_km2"]]
    frame = frame.merge(area, on="name", how="left", validate="one_to_one")
    frame["fire_burned_pct"] = frame["burned_km2"] / frame["area_km2"] * 100.0
    frame["brightness_max_k"] = frame["brightness_max_k"].fillna(0.0)
    return frame


def _existing_source_frame(
    spec: TemporalSpec, context: StudyContext, year: int
) -> pd.DataFrame | None:
    if spec.adapter == "precipitation":
        return _legacy_precipitation_frame(context, year)
    if spec.adapter == "wildfire":
        return _legacy_wildfire_frame(context, year)
    return None


@lru_cache(maxsize=16)
def _years_in_file(path_text: str, modified_ns: int, kind: str) -> frozenset[int]:
    """Read coverage once per source-file version during repeated status refreshes."""
    del modified_ns  # included only to invalidate the cache when a file changes
    path = Path(path_text)
    if kind == "precipitation":
        dates = pd.read_csv(path, usecols=["date"])["date"]
        values = pd.to_datetime(dates, errors="coerce").dt.year.dropna()
    elif kind == "wildfire":
        values = pd.to_numeric(pd.read_csv(path, usecols=["year"])["year"], errors="coerce").dropna()
    else:
        return frozenset()
    return frozenset(int(value) for value in values.unique())


def _existing_source_has_year(spec: TemporalSpec, context: StudyContext, year: int) -> bool:
    source = _canonical_local_source(spec, context)
    if source is None:
        return False
    path, kind = source
    if not path.is_file():
        return False
    return year in _years_in_file(path.as_posix(), path.stat().st_mtime_ns, kind)


def inventory(
    context: StudyContext,
    *,
    paths: TemporalPaths | None = None,
    layers: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return one row per annual target plus explicit non-temporal layers."""
    paths = paths or default_paths(context)
    selected = set(layers or ())
    discovered = discover_temporal_specs(context)
    known = {spec.layer_id for spec in discovered}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"Unknown or non-temporal layer selections: {unknown}")
    specs = [spec for spec in discovered if not selected or spec.layer_id in selected]
    start, end = _project_years(context)
    units = _canonical_units(context)
    expected = len(units)
    expected_ids = units["spatial_id"].astype(str).tolist()
    rows: list[dict[str, Any]] = []
    temporal_ids = {spec.layer_id for spec in specs}
    for spec in specs:
        for year in spec.years(start, end):
            manifest = _validated_manifest(
                _manifest_path(paths, spec, year),
                study_id=context.study.id,
                layer_id=spec.layer_id,
                year=year,
                expected_units=expected,
                expected_spatial_ids=expected_ids,
                spec=spec,
            )
            source_cached = False
            if manifest is None and spec.adapter in {"precipitation", "wildfire"}:
                source_cached = _existing_source_has_year(spec, context, year)
            state = "complete" if manifest is not None else (
                "source_cached" if source_cached else "pending"
            )
            rows.append(
                {
                    "layer_id": spec.layer_id,
                    "year": year,
                    "classification": "annual_downloadable",
                    "state": state,
                    "source": spec.source,
                    "reason": "",
                }
            )

    if not selected:
        for layer_id in context.enabled_layers:
            if layer_id in temporal_ids:
                continue
            if layer_id in DERIVED_LAYERS:
                classification = "derived_from_downloaded_data"
                reason = "Derived locally; it has no independent provider download."
            elif layer_id in OUTCOME_LAYERS:
                classification = "not_an_exposure"
                reason = "Health outcome/comparator, not an exposome."
            else:
                classification = "static_snapshot"
                reason = STATIC_REASONS.get(
                    layer_id,
                    "No homogeneous annual download contract is declared for this layer.",
                )
            rows.append(
                {
                    "layer_id": layer_id,
                    "year": pd.NA,
                    "classification": classification,
                    "state": "not_applicable",
                    "source": "",
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["classification", "layer_id", "year"], na_position="last"
    ).reset_index(drop=True)


def _write_success(
    result: pd.DataFrame | AnnualBuildResult,
    *,
    context: StudyContext,
    paths: TemporalPaths,
    spec: TemporalSpec,
    year: int,
) -> dict[str, Any]:
    build = result if isinstance(result, AnnualBuildResult) else AnnualBuildResult(result)
    frame = build.frame
    units = _canonical_units(context)
    normalized = _normalize_annual_frame(
        frame, units=units, layer_id=spec.layer_id, year=year
    )
    year_dir = paths.year_dir(spec.layer_id, year)
    annual_path = year_dir / "annual.csv"
    _atomic_csv(annual_path, normalized)
    details: dict[str, Any] = {}
    for detail in build.details:
        if detail.indicator_id in details:
            raise ValueError(f"Duplicate annual detail {detail.indicator_id!r}")
        try:
            asset_path = (
                detail.raster_path
                if isinstance(detail, AnnualRasterDetail)
                else detail.geojson_path
            )
            asset_relative = asset_path.relative_to(year_dir).as_posix()
            metadata_relative = detail.metadata_path.relative_to(year_dir).as_posix()
        except ValueError as exc:
            raise ValueError("Annual detail assets must live inside their year directory") from exc
        details[detail.indicator_id] = {
            "kind": (
                "native_raster"
                if isinstance(detail, AnnualRasterDetail)
                else "analysis_grid"
            ),
            "path": asset_relative,
            "metadata": metadata_relative,
            "sha256": _sha256(asset_path),
            "metadata_sha256": _sha256(detail.metadata_path),
        }
    required_details = {
        indicator.exposome_id
        for indicator in spec.indicators
        if indicator.detail_kind in {"native_raster", "analysis_grid"}
    }
    missing_details = sorted(required_details - set(details))
    if missing_details:
        raise ValueError(
            f"Annual product {spec.layer_id} {year} lacks required details: {missing_details}"
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": _utc_now(),
        "study_id": context.study.id,
        # ``study`` is retained for readers of the first schema revision.
        "study": context.study.id,
        "layer_id": spec.layer_id,
        "adapter": spec.adapter,
        "source": spec.source,
        "year": year,
        "n_rows": len(normalized),
        "columns": normalized.columns.tolist(),
        "annual_table": annual_path.name,
        "sha256": _sha256(annual_path),
        "details": details,
        "scope": {
            "master": False,
            "webapp": False,
            "health_analysis": False,
        },
    }
    _atomic_json(year_dir / "manifest.json", manifest)
    failure = year_dir / "failure.json"
    failure.unlink(missing_ok=True)
    return manifest


def _write_failure(
    *, paths: TemporalPaths, spec: TemporalSpec, year: int, error: Exception
) -> None:
    _atomic_json(
        paths.year_dir(spec.layer_id, year) / "failure.json",
        {
            "schema_version": SCHEMA_VERSION,
            "failed_utc": _utc_now(),
            "layer_id": spec.layer_id,
            "year": year,
            "error_type": type(error).__name__,
            "error": str(error),
            "retry": "Run the same command with --resume.",
        },
    )


def _write_global_state(context: StudyContext, paths: TemporalPaths) -> pd.DataFrame:
    table = inventory(context, paths=paths)
    _atomic_csv(paths.output_root / "coverage.csv", table)
    completed = table[table["state"] == "complete"]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "updated_utc": _utc_now(),
        "study_id": context.study.id,
        # ``study`` is retained for readers of the first schema revision.
        "study": context.study.id,
        "period": list(_project_years(context)),
        "annual_targets": int((table["classification"] == "annual_downloadable").sum()),
        "completed": int(len(completed)),
        "pending": int((table["state"] == "pending").sum()),
        "source_cached": int((table["state"] == "source_cached").sum()),
        "coverage_table": "coverage.csv",
        "coverage_sha256": _sha256(paths.output_root / "coverage.csv"),
        "scope": {"master": False, "webapp": False, "health_analysis": False},
    }
    _atomic_json(paths.output_root / "manifest.json", manifest)
    return table


def collect_missing(
    study: str = DEFAULT_STUDY,
    *,
    layers: Iterable[str] | None = None,
    output_root: Path | None = None,
    cache_root: Path | None = None,
    resume: bool = True,
    local_only: bool = False,
) -> pd.DataFrame:
    """Collect every missing annual product and continue across provider failures."""
    context = load_study(study)
    paths = default_paths(context)
    if output_root is not None:
        paths = TemporalPaths(Path(output_root), paths.cache_root)
    if cache_root is not None:
        paths = TemporalPaths(paths.output_root, Path(cache_root))
    selected = set(layers or ())
    specs = [
        spec
        for spec in discover_temporal_specs(context)
        if not selected or spec.layer_id in selected
    ]
    known = {spec.layer_id for spec in discover_temporal_specs(context)}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"Unknown or non-temporal layer selections: {unknown}")

    units = _canonical_units(context)
    expected = len(units)
    start, end = _project_years(context)
    targets = [(spec, year) for spec in specs for year in spec.years(start, end)]
    failures: list[tuple[str, int, str]] = []
    progress = tqdm(targets, desc=f"temporal exposomes [{study}]", unit="year")
    for spec, year in progress:
        progress.set_postfix_str(f"{spec.layer_id} {year}")
        manifest_path = _manifest_path(paths, spec, year)
        if resume and _validated_manifest(
            manifest_path,
            study_id=context.study.id,
            layer_id=spec.layer_id,
            year=year,
            expected_units=expected,
            expected_spatial_ids=units["spatial_id"].astype(str).tolist(),
            spec=spec,
        ):
            tqdm.write(f"  SKIP {spec.layer_id} {year}: complete")
            continue
        try:
            frame = _existing_source_frame(spec, context, year)
            if frame is not None:
                tqdm.write(f"  LOCAL {spec.layer_id} {year}: materializing cached source")
                needs_provider_detail = any(
                    indicator.detail_kind in {"native_raster", "analysis_grid"}
                    for indicator in spec.indicators
                )
                if local_only and needs_provider_detail:
                    tqdm.write(
                        f"  SKIP {spec.layer_id} {year}: local table exists but "
                        "verified annual spatial detail still requires the provider"
                    )
                    continue
                if needs_provider_detail:
                    frame = _run_adapter(
                        spec,
                        year,
                        context=context,
                        paths=paths,
                        existing_frame=frame,
                    )
            elif local_only:
                tqdm.write(f"  SKIP {spec.layer_id} {year}: no canonical local source")
                continue
            else:
                tqdm.write(f"  FETCH {spec.layer_id} {year}: {spec.source}")
                table_manifest = _validated_manifest(
                    manifest_path,
                    study_id=context.study.id,
                    layer_id=spec.layer_id,
                    year=year,
                    expected_units=expected,
                    expected_spatial_ids=units["spatial_id"].astype(str).tolist(),
                    spec=spec,
                    require_details=False,
                )
                existing_frame = (
                    pd.read_csv(
                        manifest_path.parent / str(table_manifest["annual_table"]),
                        dtype={"spatial_id": str},
                    )
                    if table_manifest is not None
                    else None
                )
                frame = _run_adapter(
                    spec,
                    year,
                    context=context,
                    paths=paths,
                    existing_frame=existing_frame,
                )
            _write_success(
                frame,
                context=context,
                paths=paths,
                spec=spec,
                year=year,
            )
        except Exception as exc:  # keep the overnight batch moving
            _write_failure(paths=paths, spec=spec, year=year, error=exc)
            failures.append((spec.layer_id, year, str(exc)))
            tqdm.write(f"  FAILED {spec.layer_id} {year}: {exc}")
        _write_global_state(context, paths)
    table = _write_global_state(context, paths)
    if failures:
        summary = "; ".join(f"{layer} {year}: {error}" for layer, year, error in failures)
        raise RuntimeError(
            f"{len(failures)} annual targets failed; valid checkpoints were kept. {summary}"
        )
    if selected:
        return inventory(context, paths=paths, layers=selected)
    return table


def completed_annual_products(
    context: StudyContext,
    *,
    paths: TemporalPaths | None = None,
) -> tuple[tuple[TemporalSpec, int, dict[str, Any], Path], ...]:
    """Return checksum-validated annual tables available for publication."""
    paths = paths or default_paths(context)
    units = _canonical_units(context)
    expected_ids = units["spatial_id"].astype(str).tolist()
    start, end = _project_years(context)
    completed: list[tuple[TemporalSpec, int, dict[str, Any], Path]] = []
    for spec in discover_temporal_specs(context):
        for year in spec.years(start, end):
            manifest_path = _manifest_path(paths, spec, year)
            manifest = _validated_manifest(
                manifest_path,
                study_id=context.study.id,
                layer_id=spec.layer_id,
                year=year,
                expected_units=len(units),
                expected_spatial_ids=expected_ids,
                spec=spec,
            )
            if manifest is None:
                continue
            completed.append(
                (spec, year, manifest, manifest_path.parent / str(manifest["annual_table"]))
            )
    return tuple(completed)


def status_summary(table: pd.DataFrame) -> str:
    annual = table[table["classification"] == "annual_downloadable"]
    counts = annual.groupby(["layer_id", "state"]).size().unstack(fill_value=0)
    if counts.empty:
        return "No annual-downloadable exposomes are configured."
    return counts.to_string()


def estimate_target_count(context: StudyContext) -> int:
    start, end = _project_years(context)
    return sum(len(spec.years(start, end)) for spec in discover_temporal_specs(context))


def validate_no_analysis_side_effects(paths: TemporalPaths) -> None:
    """Assert the collector target is isolated from masters and web assets."""
    text = paths.output_root.as_posix()
    forbidden = ("webapp/public", "/analysis/hospitalizations/inference", "/master")
    if any(fragment in text for fragment in forbidden) or text.endswith("/master.csv"):
        raise ValueError(f"Temporal output root is not isolated: {paths.output_root}")


def duration_hint(targets: int) -> str:
    if targets <= 0:
        return "No pending downloads."
    hours = max(1, math.ceil(targets * 12 / 60))
    return f"Provider-dependent; budget at least ~{hours} h for {targets} uncached layer-years."
