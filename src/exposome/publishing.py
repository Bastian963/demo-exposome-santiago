"""Publish study outputs as versioned, self-describing web bundles.

The web application must never infer a city from a filename such as
``santiago_exposome_master.csv``.  This module is the single Python-side
translation from a :class:`~exposome.config.StudyContext` to a bundle with a
stable manifest and study-local asset paths.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .layer_info import (
    build_methodology_json,
    build_sources_entry,
    expand_aliases,
    load_layer_info_registry,
    resolve_layer_info,
)
from .native import NATIVE_LAYER_SPECS
from .artifact_contract import StudyRelease, load_release
from .releases import canonical_enabled_layers
from .spatial_support import (
    SPATIAL_SCHEMA_VERSION,
    apply_indicator_availability,
    indicators_for_bundle,
    administrative_unit_label,
    validate_indicator_records,
    validate_palette_coverage,
)
from .spatial_coverage import coverage_for_manifest
from .studies import StudyContext, load_study


# Web manifests are v3 because spatial support is now a first-class,
# per-study contract.  Layer/release manifests intentionally remain v1; their
# checksum protocol is unchanged.
SCHEMA_VERSION = SPATIAL_SCHEMA_VERSION
DEFAULT_WEB_VERSION = "v1"

# Catalogued studies are grouped by the country of their configured location,
# not by the historical LATAM-first default. Keep the mapping deliberately
# small and explicit for the countries currently supported by this repository;
# unknown legacy/test locations retain the original South America fallback.
_CONTINENT_BY_COUNTRY_CODE = {
    "AR": "south_america",
    "BR": "south_america",
    "CL": "south_america",
    "CO": "south_america",
    "ES": "europe",
    "MX": "north_america",
    "PE": "south_america",
}


def _continent_for_country_code(country_code: str) -> str:
    return _CONTINENT_BY_COUNTRY_CODE.get(str(country_code).upper(), "south_america")


@dataclass(frozen=True)
class PublishedBundle:
    """Result of publishing one study."""

    study_id: str
    path: Path
    manifest: Mapping[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _copy_file(source: Path, destination: Path) -> dict[str, Any] | None:
    if not source.exists() or not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"source": str(source), "destination": destination}


def _primary_layer_metadata(
    context: StudyContext,
    layer_id: str,
) -> Mapping[str, Any] | None:
    from .artifact_contract import load_layer_bundle
    from .layers import load_layer_catalog

    catalog = load_layer_catalog()
    bundle = load_layer_bundle(
        context,
        layer_id,
        verify=True,
        spec=catalog.get(layer_id),
    )
    candidates = list(bundle.assets_with_role("metadata"))
    # Legacy directories can retain an older city-level sidecar beside output
    # rebuilt for the current Study. Prefer the Study-specific name first;
    # then the declared primary-table basename. Manifest order is not
    # provenance.
    expected_name = (
        f"{bundle.primary_table.stem}_metadata.json"
        if bundle.primary_table is not None
        else ""
    )
    study_prefix = f"{context.study.id}_"
    candidates.sort(
        key=lambda candidate: (
            not candidate.name.startswith(study_prefix),
            candidate.name != expected_name,
        )
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            return payload
    return None


def aggregate_provenance_issues(context: StudyContext) -> list[str]:
    """Reject stale sidecars that contradict the resolved provider settings."""
    if context.is_native:
        return []
    cfg = context.config
    issues: list[str] = []
    if "alan" in context.enabled_layers:
        try:
            metadata = _primary_layer_metadata(context, "alan")
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            issues.append(f"alan bundle is invalid: {exc}")
            metadata = None
        if metadata is not None:
            expected = cfg.get("alan", {}).get("collection", {}).get("scale_meters")
            actual = metadata.get("resolution_m")
            if expected is not None:
                try:
                    scale_matches = (
                        actual is not None
                        and abs(float(actual) / float(expected) - 1.0) <= 0.01
                    )
                except (TypeError, ValueError, ZeroDivisionError):
                    scale_matches = False
                if not scale_matches:
                    issues.append(
                        f"alan resolution is {actual or '<missing>'} m, expected {expected} m"
                    )
    if "climate_heat" in context.enabled_layers:
        try:
            metadata = _primary_layer_metadata(context, "climate_heat")
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            issues.append(f"climate_heat bundle is invalid: {exc}")
            metadata = None
        if metadata is not None:
            expected = str(cfg.get("climate_heat", {}).get("source") or "").lower()
            actual = str(metadata.get("source") or "").lower()
            if expected and actual != expected:
                issues.append(
                    f"climate_heat source is {actual or '<missing>'}, expected {expected}"
                )
    if "wind" in context.enabled_layers:
        try:
            metadata = _primary_layer_metadata(context, "wind")
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            issues.append(f"wind bundle is invalid: {exc}")
            metadata = None
        if metadata is not None:
            expected = str(cfg.get("wind", {}).get("id") or "")
            actual = str(metadata.get("source") or "")
            if expected and expected not in actual:
                issues.append(
                    f"wind source is {actual or '<missing>'}, expected {expected}"
                )
    return issues


def slugify(value: str) -> str:
    """Web-identity slug ("Ñuñoa" -> "nunoa").

    Must match the slugs baked into legacy profile filenames
    (scripts/export_webapp_master.py), since aggregate studies without a
    native ``spatial_id`` fall back to this to key their web identity.
    """
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = value.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in value if c.isalnum() or c == "_").strip("_") or "unknown"


def _copy_aggregate_assets(
    context: StudyContext,
    bundle: Path,
    release: StudyRelease,
) -> dict[str, Any]:
    source_root = context.paths.processed
    assets: dict[str, Any] = {}
    master_geo = release.asset("master_geojson")
    master_csv = release.asset("master_csv")
    if master_geo:
        destination = bundle / "master.geojson"
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(master_geo.read_text(encoding="utf-8"))
        columns: set[str] = set()
        for feature in data.get("features", []):
            props = feature.setdefault("properties", {})
            if "slug" not in props:
                props["slug"] = slugify(
                    str(props.get("name") or props.get("spatial_name") or props.get("spatial_id") or "")
                )
            if "name" not in props:
                props["name"] = props.get("spatial_name") or props["slug"]
            columns.update(props.keys())
        destination.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assets["master_geojson"] = destination
        assets["columns"] = sorted(columns)
    if master_csv:
        destination = bundle / "master.csv"
        _copy_file(master_csv, destination)
        assets["master_csv"] = destination
    if _copy_file(release.manifest_path, bundle / "release_manifest.json"):
        assets["release_manifest"] = bundle / "release_manifest.json"

    publication_roots: set[str] = set()
    for release_asset in release.assets:
        if not release_asset.role.startswith("publication/"):
            continue
        relative = Path(release_asset.path)
        source = release.manifest_path.parent / relative
        destination = bundle / relative
        _copy_file(source, destination)
        root_name = relative.parts[0]
        publication_roots.add(root_name)
        if len(relative.parts) == 1:
            assets[relative.stem] = destination
    for root_name in sorted(publication_roots):
        root = bundle / root_name
        if root.is_dir():
            assets[root_name] = root

    # Detail grids produced by a Layer live inside its verified bundle until
    # publication. Promote them into the shared browser ``subcomuna`` root so
    # the spatial-support manifest can advertise their real analysis grid.
    for layer_bundle in release.layers.values():
        for asset in layer_bundle.assets:
            relative = Path(asset.path)
            if not relative.parts or relative.parts[0] != "subcomuna":
                continue
            source = layer_bundle.manifest_path.parent / relative
            destination = bundle / relative
            _copy_file(source, destination)
            assets["subcomuna"] = bundle / "subcomuna"
    # Palette is a global UI contract. Explanatory assets are study-local;
    # only Santiago may fall back to the legacy root copies.
    palette_source = context.repo_root / "webapp" / "public" / "palette.json"
    if _copy_file(palette_source, bundle / "palette.json"):
        assets["palette"] = bundle / "palette.json"

    registry = load_layer_info_registry(context.repo_root)
    generated_sources = _write_aggregate_sources(
        context, source_root, bundle, registry, columns=assets.get("columns")
    )
    if generated_sources:
        assets["sources"] = generated_sources
    methodology_dir = _write_aggregate_methodologies(
        context, source_root, bundle, registry, columns=assets.get("columns")
    )
    if methodology_dir:
        assets["methodology"] = methodology_dir
    if "location_profile_axes" not in assets:
        axes = bundle / "location_profile_axes.json"
        axes.write_text(
            json.dumps(
                {
                    "study_id": context.study.id,
                    "method_note": (
                        f"Relative within {context.location.name}; axes are derived from the "
                        "published study master and are not comparable across cities."
                    ),
                    "axes": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assets["location_profile_axes"] = axes

    outcome_entries: list[dict[str, Any]] = []
    outcome_dir = bundle / "outcomes"
    from .layers import load_layer_catalog

    catalog = load_layer_catalog()
    for raw_layer_id in context.enabled_layers:
        layer_id = catalog.resolve_id(raw_layer_id)
        layer_bundle = release.layers[layer_id]
        declared_web = {
            path.resolve() for path in layer_bundle.assets_with_role("web")
        }
        web_dir = source_root / layer_id / "web"
        entry_path = web_dir / "catalog_entry.json"
        if not entry_path.exists():
            continue
        if entry_path.resolve() not in declared_web:
            raise ValueError(
                f"Outcome catalog entry is not a declared web asset: {entry_path}"
            )
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        source_geojson = web_dir / f"{layer_id}.geojson"
        if not source_geojson.exists():
            raise FileNotFoundError(
                f"Outcome catalog entry has no sanitized GeoJSON: {source_geojson}"
            )
        if source_geojson.resolve() not in declared_web:
            raise ValueError(
                f"Outcome GeoJSON is not a declared web asset: {source_geojson}"
            )
        destination_geojson = outcome_dir / source_geojson.name
        _copy_file(source_geojson, destination_geojson)
        outcome_entries.append(entry)
        methodology_dir = bundle / "methodology"
        methodology_dir.mkdir(parents=True, exist_ok=True)
        if (methodology_dir / f"{layer_id}.json").exists():
            # The registry already published the full methodology for this
            # outcome; the generic stub below is only a fallback.
            assets["methodology"] = methodology_dir
            continue
        (methodology_dir / f"{layer_id}.json").write_text(
            json.dumps(
                {
                    "id": layer_id,
                    "sections": [
                        {
                            "title": entry.get("title", layer_id),
                            "level": 1,
                            "body": [
                                "Resultado ecológico agregado, separado del exposoma y excluido del EBI.",
                                "Las ventanas de tres años con menos de cinco eventos se publican como datos suprimidos.",
                                "Las asociaciones permanecen cerradas hasta aprobar ajuste censal, colinealidad y diagnóstico espacial.",
                            ],
                        }
                    ],
                    "raw": "Ecological outcome; not causal and not an individual-risk estimate.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assets["methodology"] = methodology_dir
    if outcome_entries:
        outcome_dir.mkdir(parents=True, exist_ok=True)
        catalog_path = outcome_dir / "catalog.json"
        catalog_path.write_text(
            json.dumps(
                {"schema_version": 1, "study_id": context.study.id, "outcomes": outcome_entries},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        assets["outcomes_catalog"] = catalog_path
        assets["outcome_layers"] = outcome_dir

    associations_source = source_root / "analysis" / "web" / "associations.json"
    if associations_source.exists():
        declared_publication = {
            (release.manifest_path.parent / asset.path).resolve()
            for asset in release.assets
            if asset.role.startswith("publication/")
        }
        if associations_source.resolve() not in declared_publication:
            raise ValueError(
                f"Associations file is not declared by the Study release: {associations_source}"
            )
        destination = bundle / "associations" / "results.json"
        _copy_file(associations_source, destination)
        assets["associations"] = destination

    return assets


def _pooled_raster_color_domain(paths: list[Path], *, band: int = 1) -> dict[str, float]:
    """Return one robust domain shared by every harvest in a raster series."""
    import rasterio

    samples: list[np.ndarray] = []
    for path in paths:
        with rasterio.open(path) as dataset:
            values = np.asarray(dataset.read(band, masked=True).compressed(), dtype="float64")
        values = values[np.isfinite(values)]
        if values.size > 250_000:
            stride = int(np.ceil(values.size / 250_000))
            values = values[::stride]
        if values.size:
            samples.append(values)
    if not samples:
        raise ValueError("Annual raster series has no finite values")
    pooled = np.concatenate(samples)
    low = float(np.nanpercentile(pooled, 2))
    high = float(np.nanpercentile(pooled, 98))
    if not np.isfinite([low, high]).all() or not high > low:
        raise ValueError("Annual raster series has no usable shared color domain")
    return {"min": low, "max": high}


def _pooled_geojson_color_domain(paths: list[Path]) -> dict[str, float]:
    samples: list[np.ndarray] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = np.asarray(
            [
                feature.get("properties", {}).get("value")
                for feature in payload.get("features", [])
            ],
            dtype="float64",
        )
        values = values[np.isfinite(values)]
        if values.size:
            samples.append(values)
    if not samples:
        raise ValueError("Annual analysis-grid series has no finite values")
    pooled = np.concatenate(samples)
    low = float(np.nanpercentile(pooled, 2))
    high = float(np.nanpercentile(pooled, 98))
    if not np.isfinite([low, high]).all() or not high > low:
        raise ValueError("Annual analysis-grid series has no usable shared color domain")
    return {"min": low, "max": high}


def _publish_annual_detail(
    *,
    context: StudyContext,
    bundle: Path,
    annual_dir: Path,
    indicator: Any,
    year: int,
    source_manifest: Mapping[str, Any],
    source_root: Path,
) -> tuple[dict[str, Any], Path, Path]:
    """Convert one validated annual source raster into a browser COG."""
    from .spatial_detail import _file_sha256, build_cog, raster_grid_signature
    from .spatial_support import canonical_detail_source_grid

    source_record = (source_manifest.get("details") or {}).get(indicator.exposome_id)
    if not isinstance(source_record, Mapping):
        raise ValueError(
            f"Annual product {context.study.id}/{year} lacks {indicator.exposome_id!r} detail"
        )
    source = source_root / str(source_record["path"])
    source_metadata_path = source_root / str(source_record["metadata"])
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    source_grid = raster_grid_signature(source)
    if not canonical_detail_source_grid(indicator.exposome_id, {"source_grid": source_grid}):
        raise ValueError(
            f"Annual {indicator.exposome_id} {year} does not preserve its canonical source grid"
        )
    expected_support = {
        "kind": "year",
        "year": str(year),
        "source_label": indicator.detail_source_label or source_manifest.get("source"),
    }
    if source_metadata.get("temporal_support") != expected_support:
        raise ValueError(
            f"Annual {indicator.exposome_id} detail does not identify source year {year}"
        )
    destination = annual_dir / "detail" / f"{indicator.exposome_id}_{year}.tif"
    metadata_path = destination.with_suffix(".metadata.json")
    cog_metadata = build_cog(
        source,
        destination,
        source_bands=(int(indicator.detail_band),),
    )
    cog_metadata.update(
        {
            "indicator_id": indicator.exposome_id,
            "source_study_id": context.study.id,
            "source_path": source.relative_to(context.paths.processed).as_posix(),
            "source_band": int(indicator.detail_band),
            "source_sha256": _file_sha256(source),
            "source_native_resolution_m": float(indicator.detail_native_resolution_m),
            "source_grid": source_grid,
            "source_support_preserved": True,
            "temporal_support": expected_support,
        }
    )
    metadata_path.write_text(
        json.dumps(cog_metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    descriptor = {
        "type": "cog",
        "path": destination.relative_to(bundle).as_posix(),
        "band": 1,
        "canonical_resolution_verified": True,
        "source_native_resolution_m": float(indicator.detail_native_resolution_m),
        "source_support_preserved": True,
        "source_sha256": cog_metadata["source_sha256"],
        "source_grid": source_grid,
        "storage_grid": cog_metadata["storage_grid"],
        "unit": indicator.detail_unit or indicator.unit,
        "metric_label": indicator.detail_metric_label or indicator.label,
        "temporal_support": expected_support,
    }
    return descriptor, source, metadata_path


def _publish_annual_analysis_grid(
    *,
    context: StudyContext,
    bundle: Path,
    annual_dir: Path,
    indicator: Any,
    year: int,
    source_manifest: Mapping[str, Any],
    source_root: Path,
) -> tuple[dict[str, Any], Path, Path]:
    """Copy one verified year-specific analysis grid into the web bundle."""
    from .spatial_detail import _file_sha256

    source_record = (source_manifest.get("details") or {}).get(indicator.exposome_id)
    if not isinstance(source_record, Mapping):
        raise ValueError(
            f"Annual product {context.study.id}/{year} lacks {indicator.exposome_id!r} detail"
        )
    source = source_root / str(source_record["path"])
    source_metadata_path = source_root / str(source_record["metadata"])
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    expected_support = {
        "kind": "year",
        "year": str(year),
        "source_label": indicator.detail_source_label or source_manifest.get("source"),
    }
    if (
        source_payload.get("temporal_support") != expected_support
        or source_metadata.get("temporal_support") != expected_support
        or source_payload.get("grid_alignment") != "study_aoi_metric_grid"
        or source_payload.get("is_synthetic") is not False
        or float(source_payload.get("analysis_resolution_m", 0))
        != float(indicator.detail_analysis_resolution_m or 0)
    ):
        raise ValueError(
            f"Annual {indicator.exposome_id} {year} analysis grid is not canonical"
        )
    destination = annual_dir / "detail" / f"{indicator.exposome_id}_{year}.geojson"
    metadata_path = destination.with_suffix(".metadata.json")
    _copy_file(source, destination)
    metadata = {
        **source_metadata,
        "indicator_id": indicator.exposome_id,
        "source_study_id": context.study.id,
        "source_path": source.relative_to(context.paths.processed).as_posix(),
        "source_sha256": _file_sha256(source),
        "source_support_preserved": True,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    descriptor = {
        "type": "geojson",
        "path": destination.relative_to(bundle).as_posix(),
        "analysis_grid_verified": True,
        "analysis_resolution_m": float(indicator.detail_analysis_resolution_m),
        "source_native_resolution_m": float(indicator.detail_source_resolution_m),
        "source_support_preserved": True,
        "source_sha256": metadata["source_sha256"],
        "grid_alignment": "study_aoi_metric_grid",
        "value_property": "value",
        "unit": indicator.detail_unit or indicator.unit,
        "metric_label": indicator.detail_metric_label or indicator.label,
        "temporal_support": expected_support,
    }
    return descriptor, source, metadata_path


def _write_temporal_assets(
    context: StudyContext,
    bundle: Path,
) -> tuple[Path | None, dict[str, Any]]:
    """Publish validated annual tables and optional year-matched native COGs."""
    from .temporal_exposomes import completed_annual_products, discover_temporal_specs

    products = completed_annual_products(context)
    specs = discover_temporal_specs(context)
    start_year = int(str(context.study.period["start_date"])[:4])
    end_year = int(str(context.study.period["end_date"])[:4])
    completed_keys = {(spec.layer_id, int(year)) for spec, year, _, _ in products}
    # Documented, permanent per-layer/year gaps (see studies.TemporalException /
    # ADR 0008) skip the publish-blocking check below without touching
    # `expected_years`, so the app still reports the series as incomplete and
    # hides its annual selector -- only an undeclared gap aborts publication.
    excepted_years_by_layer: dict[str, set[int]] = {}
    exceptions_by_layer: dict[str, list[dict[str, str]]] = {}
    for exception in getattr(context.study, "temporal_exceptions", ()):
        excepted_years_by_layer.setdefault(exception.layer_id, set()).update(exception.years)
        exceptions_by_layer.setdefault(exception.layer_id, []).extend(
            {"year": str(year), "reason": exception.reason, "doc": exception.doc}
            for year in exception.years
        )
    missing_required: list[str] = []
    for spec in specs:
        required_indicators = [
            indicator
            for indicator in spec.indicators
            if indicator.detail_required_for_production
        ]
        if not required_indicators:
            continue
        excepted_years = excepted_years_by_layer.get(spec.layer_id, set())
        missing_years = [
            year
            for year in spec.years(start_year, end_year)
            if (spec.layer_id, year) not in completed_keys and year not in excepted_years
        ]
        if missing_years:
            missing_required.append(
                f"{spec.layer_id} ({','.join(map(str, missing_years))})"
            )
    if missing_required:
        raise ValueError(
            "Annual spatial publication is incomplete for required series: "
            + "; ".join(missing_required)
            + ". Run scripts/run_missing_annual_exposomes.py --study "
            + context.study.id
            + " --resume --require-complete before publishing."
        )
    if not products:
        return None, {}
    annual_dir = bundle / "annual"
    annual_dir.mkdir(parents=True, exist_ok=True)
    temporal: dict[str, dict[str, Any]] = {}
    detail_sources: dict[str, list[Path]] = {}
    detail_sidecars: dict[str, list[Path]] = {}
    detail_hashes: dict[str, dict[str, str]] = {}
    detail_kinds: dict[str, str] = {}
    for spec, year, source_manifest, table_path in products:
        frame = pd.read_csv(table_path, dtype={"spatial_id": str})
        indicator_columns = [indicator.value_column for indicator in spec.indicators]
        missing = sorted(set(indicator_columns) - set(frame.columns))
        if missing:
            raise ValueError(
                f"Annual product {context.study.id}/{spec.layer_id}/{year} "
                f"is missing configured value columns: {missing}"
            )
        for column in indicator_columns:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(
                    f"Annual product {context.study.id}/{spec.layer_id}/{year} "
                    f"contains non-finite {column} values"
                )

        identity = ["spatial_id", "spatial_name", "year"]
        public_columns = identity + [
            column for column in indicator_columns if column not in identity
        ]
        public = frame[public_columns]
        destination = annual_dir / f"{spec.layer_id}_{year}.json"
        payload = {
            "schema_version": 1,
            "study_id": context.study.id,
            "layer_id": spec.layer_id,
            "year": year,
            "source": spec.source,
            "spatial_id_column": "spatial_id",
            "n_rows": len(public),
            "value_columns": indicator_columns,
            "records": json.loads(public.to_json(orient="records")),
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        common_year_record = {
            "year": year,
            "asset": _asset(destination, bundle),
            "n_rows": len(public),
            "source": spec.source,
            "source_table_sha256": source_manifest["sha256"],
            "source_manifest_sha256": _sha256(table_path.parent / "manifest.json"),
        }
        for indicator in spec.indicators:
            record = temporal.setdefault(
                indicator.exposome_id,
                {
                    "layer_id": spec.layer_id,
                    "value_column": indicator.value_column,
                    "label": indicator.label,
                    "unit": indicator.unit,
                    "expected_years": [
                        str(value) for value in spec.years(start_year, end_year)
                    ],
                    "excepted_years": sorted(
                        str(year)
                        for year in excepted_years_by_layer.get(spec.layer_id, set())
                    ),
                    "exceptions": sorted(
                        exceptions_by_layer.get(spec.layer_id, []),
                        key=lambda item: item["year"],
                    ),
                    "spatial_target": {
                        "kind": indicator.detail_kind
                        or "administrative_or_component_specific",
                        "required_for_production": indicator.detail_required_for_production,
                    },
                    "years": {},
                },
            )
            if (
                record["layer_id"] != spec.layer_id
                or record["value_column"] != indicator.value_column
            ):
                raise ValueError(
                    f"Conflicting temporal declaration for {indicator.exposome_id!r}"
                )
            year_record = dict(common_year_record)
            if indicator.detail_kind == "native_raster":
                descriptor, source, sidecar = _publish_annual_detail(
                    context=context,
                    bundle=bundle,
                    annual_dir=annual_dir,
                    indicator=indicator,
                    year=year,
                    source_manifest=source_manifest,
                    source_root=table_path.parent,
                )
                year_record["detail"] = descriptor
                detail_sources.setdefault(indicator.exposome_id, []).append(source)
                detail_sidecars.setdefault(indicator.exposome_id, []).append(sidecar)
                detail_hashes.setdefault(indicator.exposome_id, {})[str(year)] = descriptor[
                    "source_sha256"
                ]
                detail_kinds[indicator.exposome_id] = "native_raster"
            elif indicator.detail_kind == "analysis_grid":
                descriptor, source, sidecar = _publish_annual_analysis_grid(
                    context=context,
                    bundle=bundle,
                    annual_dir=annual_dir,
                    indicator=indicator,
                    year=year,
                    source_manifest=source_manifest,
                    source_root=table_path.parent,
                )
                year_record["detail"] = descriptor
                detail_sources.setdefault(indicator.exposome_id, []).append(source)
                detail_sidecars.setdefault(indicator.exposome_id, []).append(sidecar)
                detail_hashes.setdefault(indicator.exposome_id, {})[str(year)] = descriptor[
                    "source_sha256"
                ]
                detail_kinds[indicator.exposome_id] = "analysis_grid"
            record["years"][str(year)] = year_record

    for indicator_id, sources in detail_sources.items():
        hashes = detail_hashes[indicator_id]
        if len(hashes) > 1 and len(set(hashes.values())) != len(hashes):
            raise ValueError(
                f"Annual {indicator_id} details reuse identical raster content across years"
            )
        domain = (
            _pooled_geojson_color_domain(sources)
            if detail_kinds.get(indicator_id) == "analysis_grid"
            else _pooled_raster_color_domain(sources)
        )
        temporal[indicator_id]["color_domain"] = domain
        for year_record in temporal[indicator_id]["years"].values():
            if isinstance(year_record.get("detail"), dict):
                year_record["detail"]["color_domain"] = domain
        for sidecar in detail_sidecars[indicator_id]:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata["series_color_domain"] = domain
            sidecar.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return annual_dir, temporal


# Derived master indicators (no layer directory) that still deserve a full
# info panel.  Emitted only when the master actually carries their column.
_DERIVED_INFO_LAYERS = {"ebi": "ebi_score"}


def _info_layer_ids(context: StudyContext, columns: list[str] | None) -> list[tuple[str, str]]:
    """Yield (canonical_layer_id, raw_enabled_id) pairs for the info panel.

    Study configs may enable a layer under a catalog alias (``pm25``); the
    registry and the published info assets are keyed by the canonical id.
    """
    from .layers import load_layer_catalog

    catalog = load_layer_catalog()
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_id in context.enabled_layers:
        canonical = catalog.resolve_id(raw_id)
        if canonical not in seen:
            pairs.append((canonical, raw_id))
            seen.add(canonical)
    for layer_id, column in _DERIVED_INFO_LAYERS.items():
        if columns and column in columns and layer_id not in seen:
            pairs.append((layer_id, layer_id))
            seen.add(layer_id)
    return pairs


def _sidecar_facts(layer_dir: Path) -> dict[str, Any]:
    """Collect measured facts from a layer's processed metadata sidecars.

    A layer directory may hold both a minimal ``<layer>_metadata.json`` and a
    richer named sidecar; the first sidecar carrying each fact wins.
    """
    facts: dict[str, Any] = {}
    if not layer_dir.exists():
        return facts
    for candidate in sorted(layer_dir.glob("*_metadata.json")):
        try:
            metadata = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(metadata, Mapping):
            continue
        for key in ("years", "resolution_m", "native_resolution_m", "period",
                    "limitations", "methodology_doc", "units", "method"):
            if key not in facts and metadata.get(key) not in (None, "", []):
                facts[key] = metadata[key]
    return facts


def _flatten_source_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        names: list[str] = []
        for item in value.values():
            names.extend(_flatten_source_names(item))
        return names
    if isinstance(value, list):
        names = []
        for item in value:
            names.extend(_flatten_source_names(item))
        return names
    return []


def _fallback_sources_entry(layer_id: str, sidecar: Mapping[str, Any]) -> dict[str, Any]:
    """Minimal canonical-shaped entry for a layer missing from the registry."""
    names = _flatten_source_names(
        sidecar.get("source") or sidecar.get("sources") or sidecar.get("provider") or layer_id
    )
    return {
        "name": "; ".join(names) if names else layer_id,
        "url": "",
        "license": "",
        "spatial_resolution": (
            f"~{sidecar['resolution_m']} m" if sidecar.get("resolution_m") else ""
        ),
        "temporal_coverage": str(sidecar.get("period", "")),
        "validation": str(sidecar.get("method", "")),
        "layer_id": layer_id,
    }


def _write_aggregate_sources(
    context: StudyContext,
    source_root: Path,
    bundle: Path,
    registry: Mapping[str, Mapping[str, Any]],
    *,
    columns: list[str] | None = None,
) -> Path | None:
    """Build the study source register from the curated layer-info registry.

    Measured per-study facts (years, resolution) come from the processed
    sidecars; identity and prose come from ``config/layer_info``.  A layer
    missing from the registry degrades to a minimal entry with a warning —
    the publish-time validator, not this writer, is the hard gate.
    """
    records: dict[str, dict[str, Any]] = {}
    for layer_id, raw_id in _info_layer_ids(context, columns):
        layer_dir = source_root / layer_id
        if not layer_dir.exists() and raw_id != layer_id:
            layer_dir = source_root / raw_id
        sidecar = _sidecar_facts(layer_dir)
        entry = registry.get(layer_id)
        if entry is None:
            if not sidecar:
                continue
            print(f"WARNING: no config/layer_info entry for layer {layer_id!r}; "
                  "emitting minimal sources fallback")
            records[layer_id] = _fallback_sources_entry(layer_id, sidecar)
            continue
        info = resolve_layer_info(
            entry, country_code=context.location.country_code, study_id=context.study.id
        )
        records[layer_id] = build_sources_entry(info, sidecar)
    if not records:
        return None
    destination = bundle / "sources.json"
    destination.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "study_id": context.study.id,
                "location": context.location.name,
                "sources": expand_aliases(records, registry),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def _write_methodology_files(
    destination_dir: Path,
    layer_id: str,
    payload: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
) -> None:
    """Write one methodology JSON under the layer_id and its webapp aliases."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    aliases = [layer_id] + [
        alias
        for alias in (registry.get(layer_id) or {}).get("webapp_keys", [])
        if alias != layer_id
    ]
    for name in aliases:
        (destination_dir / f"{name}.json").write_text(text, encoding="utf-8")


def _write_aggregate_methodologies(
    context: StudyContext,
    source_root: Path,
    bundle: Path,
    registry: Mapping[str, Mapping[str, Any]],
    *,
    columns: list[str] | None = None,
) -> Path | None:
    """Publish registry-declared Markdown methodologies as browser JSON assets.

    The registry's ``methodology_doc`` is the source of truth; a processed
    sidecar may override it.  Sidecar ``limitations`` are appended to the
    registry ones as the final "Limitaciones" section.
    """
    destination_dir = bundle / "methodology"
    written = False
    for layer_id, raw_id in _info_layer_ids(context, columns):
        layer_dir = source_root / layer_id
        if not layer_dir.exists() and raw_id != layer_id:
            layer_dir = source_root / raw_id
        sidecar = _sidecar_facts(layer_dir)
        entry = registry.get(layer_id)
        info = (
            resolve_layer_info(
                entry, country_code=context.location.country_code, study_id=context.study.id
            )
            if entry is not None
            else {}
        )
        if sidecar.get("methodology_doc"):
            info = dict(info)
            info["methodology_doc"] = sidecar["methodology_doc"]
        extra_limitations = sidecar.get("limitations") or []
        payload = build_methodology_json(
            layer_id,
            info,
            context.repo_root,
            extra_limitations=[str(item) for item in extra_limitations],
        )
        if payload is None:
            continue
        _write_methodology_files(destination_dir, layer_id, payload, registry)
        written = True
    return destination_dir if written or destination_dir.exists() else None


def _copy_native_assets(
    context: StudyContext,
    bundle: Path,
    release: StudyRelease,
) -> dict[str, Any]:
    assets: dict[str, Any] = {}
    # Palette is the same global UI contract the aggregate path ships; the
    # post-publish spatial validation reads it from the bundle.
    palette_source = context.repo_root / "webapp" / "public" / "palette.json"
    if _copy_file(palette_source, bundle / "palette.json"):
        assets["palette"] = bundle / "palette.json"
    if context.aoi_path:
        destination = bundle / "aoi.geojson"
        if _copy_file(Path(context.aoi_path), destination):
            assets["aoi"] = destination
    if _copy_file(release.manifest_path, bundle / "release_manifest.json"):
        assets["release_manifest"] = bundle / "release_manifest.json"
    layers: dict[str, Any] = {}
    for layer_id, layer_bundle in release.layers.items():
        source_dir = layer_bundle.manifest_path.parent
        destination_dir = bundle / "layers" / layer_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        destination_by_source: dict[Path, Path] = {}
        for bundle_asset in layer_bundle.assets:
            source = source_dir / bundle_asset.path
            destination = destination_dir / bundle_asset.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(destination)
            destination_by_source[source.resolve()] = destination
        preview = _build_native_preview(destination_dir, destination_dir, layer_id)
        if preview is not None:
            copied.append(preview)
        if not copied:
            continue
        metadata: dict[str, Any] = {}
        metadata_sources = layer_bundle.assets_with_role("metadata")
        metadata_path = (
            destination_by_source.get(metadata_sources[0].resolve())
            if len(metadata_sources) == 1
            else None
        )
        if metadata_path is not None and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid native metadata: {metadata_path}") from exc
        spec = NATIVE_LAYER_SPECS.get(layer_id)
        layers[layer_id] = {
            "title": spec.description if spec else layer_id,
            "kind": metadata.get("product_kind", spec.kind if spec else "unknown"),
            "units": metadata.get("units", spec.units if spec else ""),
            "native_resolution_m": metadata.get(
                "native_resolution_m", spec.native_resolution_m if spec else None
            ),
            "assets": [destination for destination in copied],
            "metadata": metadata,
        }
    if layers:
        registry = load_layer_info_registry(context.repo_root)
        sources: dict[str, dict[str, Any]] = {}
        methodology_dir = bundle / "methodology"
        methodology_dir.mkdir(parents=True, exist_ok=True)
        for layer_id, entry in layers.items():
            metadata = dict(entry.get("metadata", {}))
            if entry.get("native_resolution_m") and "native_resolution_m" not in metadata:
                metadata["native_resolution_m"] = entry["native_resolution_m"]
            registry_entry = registry.get(layer_id)
            if registry_entry is not None:
                info = resolve_layer_info(
                    registry_entry,
                    country_code=context.location.country_code,
                    study_id=context.study.id,
                )
                sources[layer_id] = build_sources_entry(info, metadata)
            else:
                print(
                    f"WARNING: no config/layer_info entry for native layer {layer_id!r}; "
                    "emitting minimal sources fallback"
                )
                info = {}
                sources[layer_id] = _fallback_sources_entry(layer_id, metadata)
            payload = build_methodology_json(
                layer_id,
                info,
                context.repo_root,
                extra_limitations=[str(item) for item in metadata.get("limitations", [])],
                fallback_markdown=str(
                    metadata.get("method") or entry.get("title") or layer_id
                ),
            )
            if payload is not None:
                _write_methodology_files(methodology_dir, layer_id, payload, registry)
        sources_path = bundle / "sources.json"
        sources_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "study_id": context.study.id,
                    "location": context.location.name,
                    "sources": expand_aliases(sources, registry),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        assets["sources"] = sources_path
        assets["methodology"] = methodology_dir
    assets["layers"] = layers
    return assets


def _build_native_preview(source_dir: Path, destination_dir: Path, layer_id: str) -> Path | None:
    """Create a small browser-readable preview beside native source assets.

    The original GeoTIFF/GeoPackage remains downloadable and authoritative.
    The preview is deliberately bounded so the app can render a native study
    without loading a 30 m raster or a complete street network up front.
    """
    preview = destination_dir / "native_preview.geojson"
    # ``._*`` AppleDouble sidecars (NFS/SMB-mounted native studies) sort before
    # the real file and are not valid rasters/packages -- exclude explicitly
    # rather than let GDAL silently swallow the study's actual asset.
    tif = next(
        iter(sorted(p for p in source_dir.glob("*.tif") if not p.name.startswith("._"))), None
    )
    if tif is not None:
        try:
            import rasterio
            from rasterio.transform import xy
            from shapely.geometry import mapping, Point

            with rasterio.open(tif) as dataset:
                max_dim = 100
                scale = max(1, max(dataset.width, dataset.height) // max_dim)
                rows = range(0, dataset.height, scale)
                cols = range(0, dataset.width, scale)
                band = dataset.read(1)
                features = []
                for row in rows:
                    for col in cols:
                        value = band[row, col]
                        if value != value:
                            continue
                        lon, lat = xy(dataset.transform, row, col, offset="center")
                        features.append({
                            "type": "Feature",
                            "geometry": mapping(Point(lon, lat)),
                            "properties": {"value": float(value), "layer": layer_id},
                        })
            preview.write_text(
                json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
                encoding="utf-8",
            )
            return preview
        except (ImportError, OSError, ValueError):
            return None

    gpkg = next(
        iter(sorted(p for p in source_dir.glob("*.gpkg") if not p.name.startswith("._"))), None
    )
    if gpkg is not None:
        try:
            import geopandas as gpd

            layers = list(gpd.list_layers(gpkg)["name"])
            preferred = "edges" if "edges" in layers else (layers[0] if layers else None)
            if preferred is None:
                return None
            frame = gpd.read_file(gpkg, layer=preferred)
            if frame.empty:
                return None
            frame = frame.to_crs("EPSG:4326")
            frame["geometry"] = frame.geometry.simplify(0.00005, preserve_topology=True)
            frame = frame.head(5000)
            preview.write_text(frame.to_json(drop_id=True), encoding="utf-8")
            return preview
        except (ImportError, OSError, ValueError):
            return None
    return None


# Directory assets whose individual files the webapp needs to know about
# up front (see data-repository.js studyHasFineLayer/studyAnnualYears) to
# gate per-exposome UI (fine layer, time slider) without a per-file probe
# request. Other directories (profiles, methodology, ...) are addressed by
# a known naming convention instead, so listing them would only bloat the
# manifest.
_FILE_LISTED_DIRECTORIES = {"subcomuna", "annual", "detail"}


def _directory_files(path: Path) -> list[str]:
    """List web-addressable files in a declared directory asset.

    ``subcomuna`` and ``annual`` historically contained flat GeoJSON files.
    ``detail`` may contain COGs and metadata sidecars, hence the recursive
    list.  The manifest is the only file listing the browser is allowed to
    trust; it must never infer a city's detail availability from the palette.
    """
    return sorted(
        candidate.relative_to(path).as_posix()
        for candidate in path.rglob("*")
        if candidate.is_file() and not candidate.name.startswith(".")
    )


def _detail_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read optional COG sidecars without letting malformed metadata pass."""
    if path is None or not path.is_dir():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for sidecar in path.glob("*.metadata.json"):
        if sidecar.name.startswith("._"):
            continue  # macOS AppleDouble sidecar (NFS/SMB mounts), never real metadata
        indicator_id = sidecar.name.removesuffix(".metadata.json")
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid detail metadata: {sidecar}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Detail metadata must be an object: {sidecar}")
        records[indicator_id] = payload
    return records


def _vector_contour_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read the authoritative TileJSON-like vector-contour descriptors."""
    if path is None or not path.is_dir():
        return {}
    records: dict[str, dict[str, Any]] = {}
    suffix = ".vector_contours.json"
    for descriptor in path.glob(f"*{suffix}"):
        if descriptor.name.startswith("._"):
            continue
        indicator_id = descriptor.name.removesuffix(suffix)
        try:
            payload = json.loads(descriptor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid vector-contour descriptor: {descriptor}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Vector-contour descriptor must be an object: {descriptor}")
        records[indicator_id] = payload
    return records


def _geojson_detail_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read FeatureCollection-level provenance for legacy detail bridges."""
    if path is None or not path.is_dir():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for candidate in path.glob("*.geojson"):
        if candidate.name.startswith("._"):
            continue  # macOS AppleDouble sidecar (NFS/SMB mounts), never real content
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid subcomuna detail GeoJSON: {candidate}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Subcomuna detail GeoJSON root must be an object: {candidate}")
        records[candidate.stem] = payload
    return records


def _relative_assets(value: Any, bundle: Path, key: str | None = None) -> Any:
    if isinstance(value, Path):
        if value.is_dir():
            entry: dict[str, Any] = {
                "path": value.relative_to(bundle).as_posix(),
                "type": "directory",
            }
            if key in _FILE_LISTED_DIRECTORIES:
                files = _directory_files(value)
                # MVT trees are discovered through their verified descriptor.
                # Listing every PBF here would inflate the browser manifest by
                # megabytes; the strict release manifest and validation report
                # still retain a checksum for every individual tile.
                if key == "detail":
                    files = [path for path in files if not path.endswith(".pbf")]
                entry["files"] = files
            return entry
        return _asset(value, bundle)
    if isinstance(value, list):
        return [_relative_assets(item, bundle, key) for item in value]
    if isinstance(value, dict):
        return {k: _relative_assets(item, bundle, k) for k, item in value.items()}
    return value


def _location_manifest(context: StudyContext) -> dict[str, Any]:
    bbox = context.location.bbox
    return {
        "id": context.location.id,
        "name": context.location.name,
        "country": context.location.country,
        "country_code": context.location.country_code,
        "timezone": context.location.timezone,
        "bbox": [bbox.west, bbox.south, bbox.east, bbox.north],
    }


def publish_study(
    study: str | StudyContext,
    *,
    output_root: str | Path,
    version: str = DEFAULT_WEB_VERSION,
    clean: bool = False,
) -> PublishedBundle:
    """Publish one study into ``output_root/version/country/city/study``.

    The function writes to a temporary sibling directory and atomically
    replaces the old bundle only after the manifest can be validated.  The
    source data is never modified.
    """
    context = load_study(study) if isinstance(study, str) else study
    from .layers import load_layer_catalog

    catalog = load_layer_catalog()
    expected_layers = canonical_enabled_layers(context)
    release = load_release(
        context,
        verify=True,
        expected_layer_ids=expected_layers,
        specs=catalog.layers,
    )
    provenance_issues = aggregate_provenance_issues(context)
    if provenance_issues:
        raise ValueError(
            f"Study {context.study.id!r} has stale provider provenance: "
            + "; ".join(provenance_issues)
            + ". Reprocess the affected layers before publishing."
        )
    country = context.location.country_code.lower()
    bundle = Path(output_root) / version / country / context.city / context.study.id
    staging = bundle.with_name(f".{bundle.name}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    copied = (
        _copy_native_assets(context, staging, release)
        if context.is_native
        else _copy_aggregate_assets(context, staging, release)
    )
    if not context.is_native and "master_geojson" not in copied:
        raise FileNotFoundError(
            f"Aggregate study {context.study.id!r} has no master GeoJSON in "
            f"verified Study release {release.manifest_path}"
        )

    columns = copied.pop("columns", None)
    temporal_indicators: dict[str, Any] = {}
    if not context.is_native:
        annual_dir, temporal_indicators = _write_temporal_assets(context, staging)
        if annual_dir is not None:
            copied["annual"] = annual_dir
    layer_records: dict[str, Any] = {}
    if context.is_native:
        for layer_id, entry in copied.get("layers", {}).items():
            layer_records[layer_id] = {
                key: _relative_assets(value, staging)
                for key, value in entry.items()
            }
    else:
        for canonical_id in expected_layers:
            layer_records[canonical_id] = {
                "available": canonical_id in release.layers,
                "bundle_manifest_sha256": _sha256(
                    release.layers[canonical_id].manifest_path
                ),
            }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": context.study.id,
        "location": _location_manifest(context),
        "mode": "native" if context.is_native else "aggregate",
        "spatial": {
            "unit_type": context.study.unit_type,
            "id_column": context.study.id_column,
            "name_column": context.study.name_column,
            "expected_units": context.study.expected_units,
        },
        "period": dict(context.study.period),
        "layers": layer_records,
        "assets": _relative_assets(
            {key: value for key, value in copied.items() if key != "layers"},
            staging,
        ),
    }
    if columns is not None:
        manifest["columns"] = columns
    manifest["temporal_indicators"] = temporal_indicators
    detail_files: list[str] = []
    for directory in ("detail", "subcomuna"):
        value = copied.get(directory)
        if isinstance(value, Path) and value.is_dir():
            detail_files.extend(f"{directory}/{path}" for path in _directory_files(value))
    detail_dir = copied.get("detail")
    subcomuna_dir = copied.get("subcomuna")
    palette_path = staging / "palette.json"
    try:
        palette_payload = json.loads(palette_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid browser palette: {palette_path}") from exc
    palette_exposomes = palette_payload.get("exposomes")
    if not isinstance(palette_exposomes, Mapping):
        raise ValueError(f"Browser palette has no exposomes mapping: {palette_path}")
    coverage_issues = validate_palette_coverage(palette_exposomes)
    if coverage_issues:
        raise ValueError("Invalid spatial-support coverage: " + "; ".join(coverage_issues))
    spatial_indicators = indicators_for_bundle(
        detail_files,
        detail_metadata=_detail_metadata(detail_dir if isinstance(detail_dir, Path) else None),
        geojson_detail_metadata=_geojson_detail_metadata(
            subcomuna_dir if isinstance(subcomuna_dir, Path) else None
        ),
        vector_contour_metadata=_vector_contour_metadata(
            detail_dir if isinstance(detail_dir, Path) else None
        ),
        administrative_unit_label=administrative_unit_label(context.study.unit_type),
        is_native=context.is_native,
    )
    spatial_indicators = apply_indicator_availability(
        spatial_indicators,
        enabled_layers=expected_layers,
        available_layers=(
            layer_id
            for layer_id, record in layer_records.items()
            if record.get("available", True)
        ),
        country_code=context.location.country_code,
        layer_countries={
            layer_id: spec.countries for layer_id, spec in catalog.layers.items()
        },
        palette_statuses={
            str(indicator_id): str(entry.get("status") or "")
            for indicator_id, entry in palette_exposomes.items()
            if isinstance(entry, Mapping)
        },
    )
    spatial_issues = validate_indicator_records(
        spatial_indicators,
        require_publication_target=True,
        require_availability=True,
    )
    if spatial_issues:
        raise ValueError("Invalid spatial indicator contract: " + "; ".join(spatial_issues))
    manifest["spatial_indicators"] = spatial_indicators
    coverage = coverage_for_manifest(manifest)
    manifest["spatial_completion"] = coverage.as_dict()
    manifest["publication_tier"] = coverage.publication_tier
    manifest_path = staging / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    # Record the manifest itself as a checksum-bearing asset for consumers and
    # deployment tooling; its content is intentionally deterministic except for
    # the creation timestamp.
    manifest["manifest_payload_sha256"] = _sha256(manifest_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    bundle.parent.mkdir(parents=True, exist_ok=True)
    backup = bundle.with_name(f".{bundle.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if bundle.exists():
        bundle.rename(backup)
    try:
        staging.replace(bundle)
    except Exception:
        if bundle.exists():
            shutil.rmtree(bundle)
        if backup.exists():
            backup.rename(bundle)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)
    return PublishedBundle(context.study.id, bundle, manifest)


def build_catalog(
    *,
    repo_root: str | Path,
    output_root: str | Path,
    version: str = DEFAULT_WEB_VERSION,
) -> dict[str, Any]:
    """Build a catalog from configured studies and already-published bundles."""
    root = Path(repo_root)
    studies_dir = root / "config" / "studies"
    records: list[dict[str, Any]] = []
    for path in sorted(studies_dir.glob("*.yaml")):
        context = load_study(path, repo_root_path=root)
        bundle = (
            Path(output_root)
            / version
            / context.location.country_code.lower()
            / context.city
            / context.study.id
        )
        manifest_path = bundle / "manifest.json"
        manifest = None
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records.append(
            {
                "study_id": context.study.id,
                "city": context.city,
                "name": context.location.name,
                "country": context.location.country,
                "country_code": context.location.country_code,
                "mode": "native" if context.is_native else "aggregate",
                "available": manifest is not None,
                "hidden": context.study.hidden,
                "bundle": (
                    f"{version}/{context.location.country_code.lower()}/"
                    f"{context.city}/{context.study.id}"
                    if manifest is not None
                    else None
                ),
                "layers": sorted(
                    layer_id
                    for layer_id, layer_record in (manifest or {}).get("layers", {}).items()
                    if not isinstance(layer_record, Mapping)
                    or layer_record.get("available", True)
                ),
                "bbox": list(context.location.bbox.as_tuple()),
                "center": [
                    (context.location.bbox.west + context.location.bbox.east) / 2,
                    (context.location.bbox.south + context.location.bbox.north) / 2,
                ],
                "continent": _continent_for_country_code(context.location.country_code),
                "n_units": context.study.expected_units,
                "unit_type": context.study.unit_type,
                "publication_tier": (manifest or {}).get("publication_tier", "preview"),
                "spatial_completion": (manifest or {}).get("spatial_completion"),
            }
        )
    cities: list[dict[str, Any]] = []
    seen_cities: set[str] = set()
    for record in records:
        if not record["available"] or record["hidden"]:
            continue
        # A city may publish more than one study (e.g. an aggregate communal
        # study alongside a native-resolution one). The first available study
        # keeps the plain city slug so existing single-study cities are
        # unaffected; later studies for the same city get their own slug
        # (suffixed with study_id) so they stay reachable in the picker
        # instead of being silently displaced.
        is_primary = record["city"] not in seen_cities
        seen_cities.add(record["city"])
        slug = record["city"] if is_primary else f"{record['city']}_{record['study_id']}"
        name = record["name"] if is_primary else f"{record['name']} · {record['study_id']}"
        cities.append(
            {
                "slug": slug,
                "name": name,
                "country": record["country"],
                "country_code": record["country_code"],
                "continent": record["continent"],
                "marker_icon": None,
                "center": record["center"],
                "default_zoom": 9 if record["mode"] == "aggregate" else 11,
                "study_id": record["study_id"],
                "mode": record["mode"],
                "available": True,
                "n_communes": record["n_units"],
                "unit_type": record["unit_type"],
                "n_layers": len(record["layers"]),
                "n_indicators": None,
                "publication_tier": record["publication_tier"],
                "layers": record["layers"],
                "data_url": (
                    f"/data/{record['bundle']}/manifest.json"
                    if record["bundle"]
                    else None
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "default_study": "santiago_communes",
        "global_center": [-65, -25],
        "global_zoom": 3,
        "continents": {
            "south_america": {"label": "Sudamérica"},
            "north_america": {"label": "Norteamérica"},
            "europe": {"label": "Europa"},
            "africa": {"label": "África"},
            "asia": {"label": "Asia"},
            "oceania": {"label": "Oceanía"},
        },
        "cities": cities,
        "studies": records,
    }


def write_catalog(catalog: Mapping[str, Any], output_root: str | Path) -> Path:
    destination = Path(output_root) / "catalog.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(catalog), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destination
