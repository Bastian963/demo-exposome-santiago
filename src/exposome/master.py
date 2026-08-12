"""Build a study-level exposome master table.

This module contains the multi-study builder.  The Santiago-specific builder in
``scripts/build_master_exposome.py`` remains available for legacy outputs.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

import geopandas as gpd
import pandas as pd

if TYPE_CHECKING:
    from exposome.studies import StudyContext


__all__ = [
    "LayerOutputSpec",
    "StudyMasterResult",
    "build_study_master",
    "discover_layer_outputs",
]


CANONICAL_ID = "spatial_id"
CANONICAL_NAME = "spatial_name"
_GENERATED_CSVS = {"master.csv", "master_coverage.csv"}


@dataclass(frozen=True)
class LayerOutputSpec:
    """Description of one processed layer consumed by the master builder."""

    layer_id: str
    path: Path | None
    required: bool = True
    id_column: str = CANONICAL_ID
    required_columns: tuple[str, ...] | None = None
    optional_columns: tuple[str, ...] = ()
    optional_prefixes: tuple[str, ...] = ()
    rename: Mapping[str, str] = field(default_factory=dict)
    metadata_path: Path | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass
class StudyMasterResult:
    """In-memory outputs and paths produced by :func:`build_study_master`."""

    master: pd.DataFrame
    geodata: gpd.GeoDataFrame
    coverage: pd.DataFrame
    metadata: dict[str, Any]
    paths: dict[str, Path]

    @property
    def csv_path(self) -> Path | None:
        return self.paths.get("csv")

    @property
    def geojson_path(self) -> Path | None:
        return self.paths.get("geojson")

    @property
    def coverage_path(self) -> Path | None:
        return self.paths.get("coverage")

    @property
    def metadata_path(self) -> Path | None:
        return self.paths.get("metadata")


@dataclass(frozen=True)
class _StudySettings:
    study_id: str
    country_code: str | None
    city: str | None
    unit_type: str | None
    period: Mapping[str, Any]
    config_path: Path | None
    boundaries: Path | gpd.GeoDataFrame
    id_column: str
    name_column: str | None
    expected_units: int | None
    layers_dir: Path | None
    output_dir: Path | None
    enabled_layers: tuple[str, ...]
    repo_root: Path | None


def build_study_master(
    study: str | Mapping[str, Any] | StudyContext,
    *,
    boundaries: str | Path | gpd.GeoDataFrame | None = None,
    layer_outputs: (
        Sequence[LayerOutputSpec | Mapping[str, Any] | str | Path]
        | Mapping[str, Any]
        | str
        | Path
        | None
    ) = None,
    layers_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    id_column: str | None = None,
    name_column: str | None = None,
    expected_units: int | None = None,
    strict_required: bool = True,
    write: bool = True,
) -> StudyMasterResult:
    """Build and optionally write a master for an arbitrary spatial study.

    ``study`` may be a study ID, a mapping with the study YAML shape, or a
    ``StudyContext`` from :mod:`exposome.studies`.  When a plain ID is passed,
    ``boundaries`` and either ``layer_outputs`` or ``layers_dir`` must supply
    the remaining inputs.

    Boundary source columns are normalized to ``spatial_id`` and
    ``spatial_name``.  Layer outputs must use ``spatial_id`` unless their
    manifest entry declares another ``id_column``.  Every merge is validated
    one-to-one, while missing or extra spatial IDs are retained in the coverage
    report rather than silently treated as complete coverage.

    A layer manifest entry accepts ``layer_id``, ``path``, ``required``,
    ``required_columns`` (or ``columns``), ``optional_columns``, ``rename``,
    ``id_column`` and optional source metadata.  A JSON/YAML manifest path or a
    mapping keyed by layer ID is also accepted. Canonical execution always
    supplies paths resolved from verified Artifact bundle manifests.
    """
    settings = _resolve_study_settings(
        study,
        boundaries=boundaries,
        layers_dir=layers_dir,
        output_dir=output_dir,
        id_column=id_column,
        name_column=name_column,
        expected_units=expected_units,
        require_output=write,
    )
    boundary_gdf, area_crs = _load_boundaries(settings)

    if layer_outputs is None:
        raise ValueError(
            "layer_outputs is required; master construction does not discover CSVs. "
            "Resolve verified Artifact bundles first."
        )
    else:
        specs = _normalise_layer_manifest(
            layer_outputs,
            base_dir=settings.layers_dir or settings.repo_root,
        )

    _validate_layer_ids(specs)
    base_columns = [CANONICAL_ID, CANONICAL_NAME, "area_km2"]
    master = pd.DataFrame(boundary_gdf.drop(columns="geometry"))[base_columns]
    # ``spatial_id`` is the sole join key and ``spatial_name`` is the canonical
    # display field.  Retaining ``name`` as a derived alias keeps historical
    # analytical scripts readable during migration without reintroducing a
    # name-based identity contract.
    master["name"] = master[CANONICAL_NAME]
    coverage_records: list[dict[str, Any]] = []
    layer_metadata: list[dict[str, Any]] = []

    for declared_spec in specs:
        declared_path = declared_spec.path
        spec = _resolve_layer_directory(declared_spec)
        if spec.path is None or not spec.path.exists():
            record = _missing_output_record(spec, master[CANONICAL_ID])
            coverage_records.append(record)
            layer_metadata.append(_layer_metadata_record(spec, record))
            if spec.required and strict_required:
                expected_path = (
                    str(declared_path) if declared_path else "<not discovered>"
                )
                raise FileNotFoundError(
                    f"Required layer {spec.layer_id!r} has no output: {expected_path}"
                )
            continue

        layer, source_metadata = _load_layer_output(spec)
        payload_columns = [column for column in layer.columns if column != CANONICAL_ID]
        collisions = sorted(set(payload_columns).intersection(master.columns))
        if collisions:
            raise ValueError(
                f"Layer {spec.layer_id!r} would overwrite master columns: {collisions}. "
                "Declare a rename in the layer manifest."
            )

        record = _coverage_record(
            spec.layer_id,
            boundary_ids=master[CANONICAL_ID],
            layer=layer,
            payload_columns=payload_columns,
        )
        coverage_records.append(record)
        master = master.merge(layer, on=CANONICAL_ID, how="left", validate="one_to_one")
        layer_metadata.append(
            _layer_metadata_record(spec, record, source_metadata=source_metadata)
        )

    master = master.sort_values(CANONICAL_ID, kind="stable").reset_index(drop=True)
    geodata = boundary_gdf[[CANONICAL_ID, "geometry"]].merge(
        master,
        on=CANONICAL_ID,
        how="right",
        validate="one_to_one",
    )
    geodata = gpd.GeoDataFrame(geodata, geometry="geometry", crs=boundary_gdf.crs)
    geodata = geodata.sort_values(CANONICAL_ID, kind="stable").reset_index(drop=True)

    coverage = _coverage_dataframe(coverage_records)
    paths = _output_paths(settings.output_dir) if write else {}
    metadata = _master_metadata(
        settings=settings,
        master=master,
        boundary_gdf=boundary_gdf,
        area_crs=area_crs,
        layers=layer_metadata,
        paths=paths,
    )

    if write:
        if settings.output_dir is None:  # guarded by _resolve_study_settings
            raise ValueError("output_dir is required when write=True")
        _write_outputs(master, geodata, coverage, metadata, paths)

    return StudyMasterResult(
        master=master,
        geodata=geodata,
        coverage=coverage,
        metadata=metadata,
        paths=paths,
    )


def discover_layer_outputs(
    layers_dir: str | Path,
    *,
    layer_ids: Iterable[str] | None = None,
    id_column: str = CANONICAL_ID,
) -> list[LayerOutputSpec]:
    """Discover one primary CSV per layer below a study processed directory.

    With ``layer_ids``, the expected convention is ``<root>/<layer_id>/*.csv``;
    each enabled layer is considered required. Callers may pass
    ``strict_required=False`` to :func:`build_study_master` when they need a
    diagnostic master with missing outputs retained in the coverage report.
    Without ``layer_ids``, layer
    IDs are inferred from the first relative directory component, or from the
    file stem for flat layouts.  Generated master CSVs and CSVs without the
    canonical spatial key are ignored.
    """
    root = Path(layers_dir).expanduser().resolve()
    if not root.exists():
        if layer_ids:
            return [
                LayerOutputSpec(layer_id=str(layer_id), path=None, required=True)
                for layer_id in layer_ids
            ]
        raise FileNotFoundError(f"Layer output directory not found: {root}")

    if layer_ids is not None:
        discovered: list[LayerOutputSpec] = []
        for raw_layer_id in layer_ids:
            layer_id = str(raw_layer_id)
            candidates = _spatial_csv_candidates(root / layer_id, id_column)
            if not candidates:
                candidates = [
                    path
                    for path in _spatial_csv_candidates(root, id_column, recursive=False)
                    if path.stem == layer_id or path.stem.startswith(f"{layer_id}_")
                ]
            selected = _select_layer_candidate(layer_id, candidates)
            discovered.append(
                LayerOutputSpec(layer_id=layer_id, path=selected, required=True)
            )
        return discovered

    grouped: dict[str, list[Path]] = {}
    for path in _spatial_csv_candidates(root, id_column):
        relative = path.relative_to(root)
        layer_id = relative.parts[0] if len(relative.parts) > 1 else path.stem
        grouped.setdefault(layer_id, []).append(path)

    return [
        LayerOutputSpec(
            layer_id=layer_id,
            path=_select_layer_candidate(layer_id, candidates),
            required=False,
        )
        for layer_id, candidates in sorted(grouped.items())
    ]


def _resolve_study_settings(
    study: str | Mapping[str, Any] | StudyContext,
    *,
    boundaries: str | Path | gpd.GeoDataFrame | None,
    layers_dir: str | Path | None,
    output_dir: str | Path | None,
    id_column: str | None,
    name_column: str | None,
    expected_units: int | None,
    require_output: bool,
) -> _StudySettings:
    repo_root: Path | None = None
    enabled_layers: Sequence[str] = ()
    country_code: str | None = None
    city: str | None = None
    unit_type: str | None = None
    period: Mapping[str, Any] = {}
    config_path: Path | None = None

    if isinstance(study, str):
        study_id = study
    elif isinstance(study, Mapping):
        raw_study = study.get("study", study)
        if not isinstance(raw_study, Mapping):
            raw_study = _object_values(raw_study)
        spatial = raw_study.get("spatial", {})
        paths = study.get("paths", {})
        location = study.get("location", {})
        study_id = str(raw_study.get("id") or study.get("study_id") or "")
        repo_value = study.get("repo_root")
        repo_root = Path(repo_value).expanduser().resolve() if repo_value else None
        if boundaries is None:
            boundaries = spatial.get("path") or raw_study.get("spatial_path")
        id_column = id_column or spatial.get("id_column") or raw_study.get("id_column")
        if name_column is None:
            name_column = spatial.get("name_column", raw_study.get("name_column"))
        if expected_units is None:
            expected_units = spatial.get("expected_units", raw_study.get("expected_units"))
        enabled_layers = tuple(raw_study.get("layers", raw_study.get("enabled_layers", ())))
        unit_type = spatial.get("unit_type", raw_study.get("unit_type"))
        period = raw_study.get("period", {})
        config_value = raw_study.get("config_path")
        config_path = _resolve_path(config_value, repo_root) if config_value else None
        if isinstance(location, Mapping):
            country_code = location.get("country_code")
            city = location.get("id") or location.get("city")
        layers_dir = layers_dir or _mapping_path(paths, "processed")
        output_dir = output_dir or _mapping_path(paths, "processed")
    else:
        context_study = getattr(study, "study", study)
        study_id = str(
            getattr(context_study, "id", None)
            or getattr(study, "study_id", None)
            or ""
        )
        repo_value = getattr(study, "repo_root", None)
        repo_root = Path(repo_value).expanduser().resolve() if repo_value else None
        if boundaries is None:
            spatial_loader = getattr(study, "load_spatial_units", None)
            boundaries = (
                spatial_loader()
                if callable(spatial_loader)
                else getattr(study, "spatial_path", None)
            )
        id_column = id_column or getattr(context_study, "id_column", None)
        if name_column is None:
            name_column = getattr(context_study, "name_column", None)
        if expected_units is None:
            expected_units = getattr(study, "expected_units", None)
        enabled_layers = tuple(getattr(study, "enabled_layers", ()) or ())
        country_code = getattr(study, "country_code", None)
        city = getattr(study, "city", None)
        unit_type = getattr(context_study, "unit_type", None)
        period = getattr(context_study, "period", {}) or {}
        config_value = getattr(context_study, "config_path", None)
        config_path = Path(config_value).resolve() if config_value else None
        context_paths = getattr(study, "paths", None)
        processed = getattr(context_paths, "processed", None)
        layers_dir = layers_dir or processed
        output_dir = output_dir or processed

    if not study_id.strip():
        raise ValueError("study must provide a non-empty study ID")
    if boundaries is None:
        raise ValueError("study must provide a spatial boundary path")

    resolved_boundaries: Path | gpd.GeoDataFrame
    if isinstance(boundaries, gpd.GeoDataFrame):
        resolved_boundaries = boundaries
    else:
        resolved_boundaries = _resolve_path(boundaries, repo_root)

    resolved_layers = _resolve_path(layers_dir, repo_root) if layers_dir else None
    resolved_output = _resolve_path(output_dir, repo_root) if output_dir else None
    if resolved_output is None and resolved_layers is not None:
        resolved_output = resolved_layers
    if resolved_output is None and require_output:
        raise ValueError("output_dir is required for a study master")

    resolved_expected = int(expected_units) if expected_units is not None else None
    if resolved_expected is not None and resolved_expected <= 0:
        raise ValueError("expected_units must be greater than zero")

    return _StudySettings(
        study_id=study_id.strip(),
        country_code=str(country_code) if country_code else None,
        city=str(city) if city else None,
        unit_type=str(unit_type) if unit_type else None,
        period=dict(period) if isinstance(period, Mapping) else {},
        config_path=config_path,
        boundaries=resolved_boundaries,
        id_column=id_column or CANONICAL_ID,
        name_column=name_column,
        expected_units=resolved_expected,
        layers_dir=resolved_layers,
        output_dir=resolved_output,
        enabled_layers=tuple(str(layer_id) for layer_id in enabled_layers),
        repo_root=repo_root,
    )


def _load_boundaries(settings: _StudySettings) -> tuple[gpd.GeoDataFrame, str]:
    if isinstance(settings.boundaries, gpd.GeoDataFrame):
        source = settings.boundaries.copy()
    else:
        if not settings.boundaries.exists():
            raise FileNotFoundError(f"Spatial boundary file not found: {settings.boundaries}")
        source = gpd.read_file(settings.boundaries)

    if source.empty:
        raise ValueError("Spatial boundary dataset is empty")
    if source.crs is None:
        raise ValueError("Spatial boundary dataset must declare a CRS")
    if CANONICAL_ID in source.columns:
        source_id = CANONICAL_ID
    elif settings.id_column in source.columns:
        source_id = settings.id_column
    else:
        raise ValueError(
            f"Spatial boundaries are missing ID column {settings.id_column!r}"
        )

    source_name = CANONICAL_NAME if CANONICAL_NAME in source.columns else settings.name_column
    if source_name and source_name not in source.columns:
        raise ValueError(
            f"Spatial boundaries are missing name column {settings.name_column!r}"
        )

    if source.geometry.isna().any() or source.geometry.is_empty.any():
        raise ValueError("Spatial boundaries contain null or empty geometries")
    invalid = ~source.geometry.is_valid
    if invalid.any():
        invalid_ids = source.loc[invalid, source_id].astype(str).tolist()
        raise ValueError(f"Spatial boundaries contain invalid geometries: {invalid_ids}")

    out = gpd.GeoDataFrame(geometry=source.geometry, crs=source.crs)
    out[CANONICAL_ID] = _normalise_ids(source[source_id], label="boundary")
    if source_name:
        names = source[source_name].astype("string").str.strip()
        if names.isna().any() or names.eq("").any():
            raise ValueError("Spatial boundaries contain missing spatial names")
        out[CANONICAL_NAME] = names
    elif CANONICAL_NAME in source.columns:
        out[CANONICAL_NAME] = source[CANONICAL_NAME].astype("string").str.strip()
    else:
        out[CANONICAL_NAME] = out[CANONICAL_ID]

    _raise_duplicate_ids(out[CANONICAL_ID], "Spatial boundaries")
    if settings.expected_units is not None and len(out) != settings.expected_units:
        raise ValueError(
            f"Study {settings.study_id!r} expected {settings.expected_units} spatial "
            f"units, got {len(out)}"
        )

    if "area_km2" in source.columns:
        area = pd.to_numeric(source["area_km2"], errors="coerce")
        if area.isna().any() or area.le(0).any():
            raise ValueError("Boundary area_km2 values must be positive numbers")
        out["area_km2"] = area.round(4)
        area_crs = str(source.attrs.get("metric_crs") or "provided")
    else:
        area_projection = source.estimate_utm_crs()
        if area_projection is None:
            area_projection = "EPSG:6933"
        out["area_km2"] = (source.to_crs(area_projection).geometry.area / 1e6).round(4)
        area_crs = str(area_projection)

    return out[[CANONICAL_ID, CANONICAL_NAME, "area_km2", "geometry"]], area_crs


def _normalise_layer_manifest(
    manifest: (
        Sequence[LayerOutputSpec | Mapping[str, Any] | str | Path]
        | Mapping[str, Any]
        | str
        | Path
    ),
    *,
    base_dir: Path | None,
) -> list[LayerOutputSpec]:
    if isinstance(manifest, (str, Path)):
        manifest_path = _resolve_path(manifest, base_dir)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Layer manifest not found: {manifest_path}")
        manifest = _read_manifest(manifest_path)
        base_dir = manifest_path.parent

    if isinstance(manifest, Mapping):
        if "layers" in manifest:
            return _normalise_layer_manifest(manifest["layers"], base_dir=base_dir)
        entries: list[LayerOutputSpec] = []
        for layer_id, value in manifest.items():
            if isinstance(value, LayerOutputSpec):
                entries.append(_resolve_layer_spec(value, base_dir))
            elif isinstance(value, Mapping):
                master = value.get("master", {})
                if isinstance(master, Mapping) and master.get("include", True) is False:
                    continue
                item = dict(value)
                item.setdefault("layer_id", str(layer_id))
                entries.append(_layer_spec_from_mapping(item, base_dir))
            else:
                entries.append(
                    _layer_spec_from_mapping(
                        {"layer_id": str(layer_id), "path": value}, base_dir
                    )
                )
        return entries

    entries = []
    for value in manifest:
        if isinstance(value, LayerOutputSpec):
            entries.append(_resolve_layer_spec(value, base_dir))
        elif isinstance(value, Mapping):
            master = value.get("master", {})
            if isinstance(master, Mapping) and master.get("include", True) is False:
                continue
            entries.append(_layer_spec_from_mapping(value, base_dir))
        else:
            path = _resolve_path(value, base_dir)
            entries.append(LayerOutputSpec(layer_id=path.stem, path=path))
    return entries


def _layer_spec_from_mapping(
    value: Mapping[str, Any], base_dir: Path | None
) -> LayerOutputSpec:
    master = value.get("master", {})
    if master and not isinstance(master, Mapping):
        raise TypeError("layer master settings must be a mapping")
    layer_id = value.get("layer_id") or value.get("id") or value.get("name")
    if not layer_id:
        raise ValueError("Every layer manifest entry needs layer_id")
    raw_path = (
        value.get("path")
        or value.get("csv")
        or value.get("output_path")
        or value.get("output")
    )
    path = _resolve_path(raw_path, base_dir) if raw_path else None
    metadata_path_value = value.get("metadata_path")
    metadata_path = (
        _resolve_path(metadata_path_value, base_dir) if metadata_path_value else None
    )
    required_columns = value.get(
        "required_columns", value.get("columns", master.get("required_columns"))
    )
    optional_columns = value.get(
        "optional_columns", master.get("optional_columns", ())
    )
    optional_prefixes = value.get(
        "optional_prefixes", master.get("optional_prefixes", ())
    )
    rename = value.get("rename", master.get("rename", {}))
    explicit_required = value.get("required")
    if explicit_required is None:
        explicit_required = master.get("required")
    if explicit_required is None:
        explicit_required = not bool(
            value.get("optional_layer", master.get("optional_layer", False))
        )
    return LayerOutputSpec(
        layer_id=str(layer_id),
        path=path,
        required=bool(explicit_required),
        id_column=str(value.get("id_column", CANONICAL_ID)),
        required_columns=(
            tuple(str(column) for column in required_columns)
            if required_columns is not None
            else None
        ),
        optional_columns=tuple(str(column) for column in optional_columns),
        optional_prefixes=tuple(str(prefix) for prefix in optional_prefixes),
        rename={str(key): str(target) for key, target in dict(rename).items()},
        metadata_path=metadata_path,
        metadata=value.get("metadata"),
    )


def _load_layer_output(
    spec: LayerOutputSpec,
) -> tuple[pd.DataFrame, Mapping[str, Any] | None]:
    if spec.path is None:
        raise ValueError(f"Layer {spec.layer_id!r} has no path")
    path = spec.path
    suffix = path.suffix.lower()
    if suffix == ".csv":
        header = pd.read_csv(path, nrows=0)
        if spec.id_column not in header.columns:
            raise ValueError(
                f"Layer {spec.layer_id!r} is missing ID column {spec.id_column!r}: {path}"
            )
        source = pd.read_csv(path, dtype={spec.id_column: "string"})
    elif suffix in {".geojson", ".gpkg"}:
        source = pd.DataFrame(gpd.read_file(path).drop(columns="geometry"))
    elif suffix == ".parquet":
        source = pd.read_parquet(path)
    else:
        raise ValueError(
            f"Unsupported output type for layer {spec.layer_id!r}: {path.suffix}"
        )

    if spec.id_column not in source.columns:
        raise ValueError(
            f"Layer {spec.layer_id!r} is missing ID column {spec.id_column!r}: {path}"
        )
    ids = _normalise_ids(source[spec.id_column], label=f"layer {spec.layer_id}")
    _raise_duplicate_ids(ids, f"Layer {spec.layer_id!r}")

    excluded = {
        spec.id_column,
        CANONICAL_ID,
        CANONICAL_NAME,
        "geometry",
        "area_km2",
    }
    if spec.required_columns is None:
        selected = [column for column in source.columns if column not in excluded]
    else:
        missing = [
            column for column in spec.required_columns if column not in source.columns
        ]
        if missing:
            raise ValueError(
                f"Layer {spec.layer_id!r} is missing required columns: {missing}"
            )
        selected = list(spec.required_columns)
        selected.extend(
            column
            for column in spec.optional_columns
            if column in source.columns and column not in selected
        )
        selected.extend(
            column
            for column in source.columns
            if any(column.startswith(prefix) for prefix in spec.optional_prefixes)
            and column not in selected
            and column not in excluded
        )
    if not selected:
        raise ValueError(f"Layer {spec.layer_id!r} has no master value columns")
    if any(column in excluded for column in selected):
        invalid = [column for column in selected if column in excluded]
        raise ValueError(
            f"Layer {spec.layer_id!r} cannot select identifier columns as values: {invalid}"
        )

    out = source[selected].copy()
    out.insert(0, CANONICAL_ID, ids)
    out = out.rename(columns=spec.rename)
    if out.columns.duplicated().any():
        duplicate_columns = out.columns[out.columns.duplicated()].tolist()
        raise ValueError(
            f"Layer {spec.layer_id!r} has duplicate columns after rename: "
            f"{duplicate_columns}"
        )

    metadata = spec.metadata
    metadata_path = spec.metadata_path
    if metadata is None and metadata_path is not None:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return out, metadata


def _coverage_record(
    layer_id: str,
    *,
    boundary_ids: pd.Series,
    layer: pd.DataFrame,
    payload_columns: Sequence[str],
) -> dict[str, Any]:
    boundary_values = set(boundary_ids.astype(str))
    layer_values = set(layer[CANONICAL_ID].astype(str))
    matched = boundary_values.intersection(layer_values)
    missing = sorted(boundary_values - layer_values)
    extra = sorted(layer_values - boundary_values)
    values = layer.loc[layer[CANONICAL_ID].isin(matched), list(payload_columns)]
    any_data = int(values.notna().any(axis=1).sum())
    complete_data = int(values.notna().all(axis=1).sum())
    expected = len(boundary_values)
    status = "complete"
    if not matched:
        status = "no_matches"
    elif missing or complete_data < expected:
        status = "partial"
    if extra:
        status = f"{status}_with_extra_ids"
    return {
        "layer_id": layer_id,
        "status": status,
        "expected_units": expected,
        "source_rows": int(len(layer)),
        "matched_units": len(matched),
        "units_with_any_data": any_data,
        "units_with_complete_data": complete_data,
        "coverage_pct": round(100.0 * len(matched) / expected, 2) if expected else 0.0,
        "complete_data_pct": (
            round(100.0 * complete_data / expected, 2) if expected else 0.0
        ),
        "missing_spatial_ids": missing,
        "extra_spatial_ids": extra,
        "columns": list(payload_columns),
    }


def _missing_output_record(
    spec: LayerOutputSpec, boundary_ids: pd.Series
) -> dict[str, Any]:
    missing = sorted(boundary_ids.astype(str).tolist())
    expected = len(missing)
    return {
        "layer_id": spec.layer_id,
        "status": "missing_output",
        "expected_units": expected,
        "source_rows": 0,
        "matched_units": 0,
        "units_with_any_data": 0,
        "units_with_complete_data": 0,
        "coverage_pct": 0.0,
        "complete_data_pct": 0.0,
        "missing_spatial_ids": missing,
        "extra_spatial_ids": [],
        "columns": [],
    }


def _layer_metadata_record(
    spec: LayerOutputSpec,
    coverage: Mapping[str, Any],
    *,
    source_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "layer_id": spec.layer_id,
        "required": spec.required,
        "source_output": str(spec.path) if spec.path else None,
        "manifest": {
            "id_column": spec.id_column,
            "required_columns": (
                list(spec.required_columns)
                if spec.required_columns is not None
                else None
            ),
            "optional_columns": list(spec.optional_columns),
            "optional_prefixes": list(spec.optional_prefixes),
            "rename": dict(spec.rename),
        },
        "coverage": dict(coverage),
    }
    if spec.path is not None and spec.path.exists():
        record["source_sha256"] = _sha256(spec.path)
        metadata_path = spec.metadata_path
        record["source_metadata_path"] = str(metadata_path) if metadata_path else None
    if source_metadata is not None:
        record["source_metadata"] = dict(source_metadata)
    return record


def _master_metadata(
    *,
    settings: _StudySettings,
    master: pd.DataFrame,
    boundary_gdf: gpd.GeoDataFrame,
    area_crs: str,
    layers: Sequence[Mapping[str, Any]],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    if isinstance(settings.boundaries, gpd.GeoDataFrame):
        boundary_source = settings.boundaries.attrs.get("source_path")
        boundary_source = str(boundary_source) if boundary_source else "in_memory_geodataframe"
    else:
        boundary_source = str(settings.boundaries)
    boundary_path = Path(boundary_source)
    boundary_sha256 = (
        _sha256(boundary_path)
        if boundary_source != "in_memory_geodataframe" and boundary_path.is_file()
        else None
    )
    return {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": settings.study_id,
        "study": {
            "id": settings.study_id,
            "country_code": settings.country_code,
            "city": settings.city,
            "unit_type": settings.unit_type,
            "expected_units": settings.expected_units,
            "period": dict(settings.period),
            "config_path": str(settings.config_path) if settings.config_path else None,
        },
        "spatial_key": CANONICAL_ID,
        "spatial_name": CANONICAL_NAME,
        "n_spatial_units": int(len(master)),
        "n_variables_including_identifiers_area": int(master.shape[1]),
        "boundary_source": boundary_source,
        "boundary_source_sha256": boundary_sha256,
        "boundary_crs": str(boundary_gdf.crs),
        "area_crs": area_crs,
        "layers": list(layers),
        "coverage_summary": {
            "complete_layers": sum(
                layer["coverage"]["status"] == "complete" for layer in layers
            ),
            "partial_layers": sum(
                str(layer["coverage"]["status"]).startswith("partial")
                for layer in layers
            ),
            "missing_layers": sum(
                layer["coverage"]["status"] == "missing_output" for layer in layers
            ),
        },
        "outputs": {key: str(path) for key, path in paths.items()},
    }


def _coverage_dataframe(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    columns = [
        "layer_id",
        "status",
        "expected_units",
        "source_rows",
        "matched_units",
        "units_with_any_data",
        "units_with_complete_data",
        "coverage_pct",
        "complete_data_pct",
        "missing_spatial_ids",
        "extra_spatial_ids",
        "columns",
    ]
    rows = []
    for record in records:
        row = dict(record)
        for column in ("missing_spatial_ids", "extra_spatial_ids", "columns"):
            row[column] = json.dumps(row[column], ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _write_outputs(
    master: pd.DataFrame,
    geodata: gpd.GeoDataFrame,
    coverage: pd.DataFrame,
    metadata: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> None:
    output_dir = paths["csv"].parent
    output_dir.mkdir(parents=True, exist_ok=True)
    master.to_csv(paths["csv"], index=False)
    geodata.to_file(paths["geojson"], driver="GeoJSON")
    coverage.to_csv(paths["coverage"], index=False)
    paths["metadata"].write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def _output_paths(output_dir: Path | None) -> dict[str, Path]:
    if output_dir is None:
        return {}
    return {
        "csv": output_dir / "master.csv",
        "geojson": output_dir / "master.geojson",
        "coverage": output_dir / "master_coverage.csv",
        "metadata": output_dir / "master_metadata.json",
    }


def _spatial_csv_candidates(
    directory: Path,
    id_column: str,
    *,
    required_columns: Sequence[str] = (),
    recursive: bool = True,
) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    iterator = directory.rglob("*.csv") if recursive else directory.glob("*.csv")
    candidates = []
    for path in sorted(iterator):
        if path.name in _GENERATED_CSVS:
            continue
        try:
            columns = pd.read_csv(path, nrows=0).columns
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            continue
        if id_column in columns and set(required_columns).issubset(columns):
            candidates.append(path.resolve())
    return candidates


def _select_layer_candidate(layer_id: str, candidates: Sequence[Path]) -> Path | None:
    unique = sorted(set(candidates))
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    exact = [path for path in unique if path.stem == layer_id]
    if len(exact) == 1:
        return exact[0]
    rendered = ", ".join(str(path) for path in unique)
    raise ValueError(
        f"Multiple spatial CSV outputs found for layer {layer_id!r}: {rendered}. "
        "Pass an explicit layer manifest."
    )


def _normalise_ids(values: pd.Series, *, label: str) -> pd.Series:
    ids = values.astype("string").str.strip()
    if ids.isna().any() or ids.eq("").any():
        raise ValueError(f"{label.capitalize()} contains missing spatial IDs")
    return ids


def _raise_duplicate_ids(ids: pd.Series, label: str) -> None:
    duplicate = ids.duplicated(keep=False)
    if duplicate.any():
        values = sorted(ids.loc[duplicate].astype(str).unique().tolist())
        raise ValueError(f"{label} contains duplicate spatial IDs: {values}")


def _validate_layer_ids(specs: Sequence[LayerOutputSpec]) -> None:
    ids = pd.Series([spec.layer_id for spec in specs], dtype="string")
    if ids.empty:
        return
    if ids.isna().any() or ids.str.strip().eq("").any():
        raise ValueError("Layer IDs must be non-empty")
    _raise_duplicate_ids(ids, "Layer manifest")


def _read_manifest(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise ValueError(f"Layer manifest must be JSON or YAML: {path}")


def _mapping_path(mapping: Any, key: str) -> Any:
    if isinstance(mapping, Mapping):
        return mapping.get(key)
    return getattr(mapping, key, None)


def _resolve_layer_spec(spec: LayerOutputSpec, base_dir: Path | None) -> LayerOutputSpec:
    path = _resolve_path(spec.path, base_dir) if spec.path is not None else None
    metadata_path = (
        _resolve_path(spec.metadata_path, base_dir)
        if spec.metadata_path is not None
        else None
    )
    return LayerOutputSpec(
        layer_id=spec.layer_id,
        path=path,
        required=spec.required,
        id_column=spec.id_column,
        required_columns=spec.required_columns,
        optional_columns=spec.optional_columns,
        optional_prefixes=spec.optional_prefixes,
        rename=spec.rename,
        metadata_path=metadata_path,
        metadata=spec.metadata,
    )


def _resolve_layer_directory(spec: LayerOutputSpec) -> LayerOutputSpec:
    if spec.path is None or not spec.path.is_dir():
        return spec
    raise ValueError(
        f"Layer {spec.layer_id!r} path is a directory ({spec.path}); "
        "master requires the primary_table declared by a verified bundle manifest"
    )


def _object_values(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dict__"):
        return vars(value)
    return {}


def _resolve_path(value: str | Path, base_dir: Path | None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
