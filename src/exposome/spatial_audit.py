"""Offline verifier for the browser spatial-support contract."""
from __future__ import annotations

import json
import hashlib
import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .spatial_support import (
    SPATIAL_SCHEMA_VERSION,
    administrative_unit_label,
    canonical_detail_source_grid,
    indicators_for_bundle,
    validate_vector_contour_descriptor,
    validate_indicator_records,
    validate_palette_coverage,
)


@dataclass(frozen=True)
class SpatialAudit:
    """Machine-readable result for a palette and optional published bundle."""

    palette: Path
    bundle: Path | None
    checked_indicators: int
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "palette": str(self.palette),
            "bundle": str(self.bundle) if self.bundle else None,
            "checked_indicators": self.checked_indicators,
            "issues": list(self.issues),
        }


def audit_spatial_contract(
    palette_path: str | Path,
    *,
    bundle_path: str | Path | None = None,
    strict: bool = False,
) -> SpatialAudit:
    """Validate source-support coverage and, when supplied, a web bundle.

    The check is intentionally local: it confirms publication truthfulness but
    never contacts a data provider.  A missing detail asset is valid; an
    advertised asset that is absent or unsupported is not.
    """
    palette = Path(palette_path)
    bundle = Path(bundle_path) if bundle_path is not None else None
    issues: list[str] = []
    palette_payload = _read_object(palette, "palette", issues)
    exposomes = palette_payload.get("exposomes") if palette_payload else None
    if not isinstance(exposomes, Mapping):
        issues.append("palette has no exposomes mapping")
        return SpatialAudit(palette, bundle, 0, tuple(issues))
    issues.extend(validate_palette_coverage(exposomes))

    if bundle is None:
        return SpatialAudit(palette, None, len(exposomes), tuple(issues))

    manifest = _read_object(bundle / "manifest.json", "web manifest", issues)
    if not manifest:
        return SpatialAudit(palette, bundle, 0, tuple(issues))
    if manifest.get("schema_version") != SPATIAL_SCHEMA_VERSION:
        issues.append(f"web manifest must use spatial schema_version {SPATIAL_SCHEMA_VERSION}")
    records = manifest.get("spatial_indicators")
    if not isinstance(records, Mapping):
        issues.append("web manifest has no spatial_indicators mapping")
        return SpatialAudit(palette, bundle, 0, tuple(issues))
    missing = sorted(set(exposomes) - set(records))
    extra = sorted(set(records) - set(exposomes))
    if missing:
        issues.append("manifest lacks palette indicators: " + ", ".join(missing))
    if extra:
        issues.append("manifest has undeclared indicators: " + ", ".join(extra))
    issues.extend(validate_indicator_records(records, require_publication_target=strict))

    for indicator_id, record in records.items():
        if not isinstance(record, Mapping):
            continue
        detail = record.get("detail")
        if not isinstance(detail, Mapping):
            continue
        path = detail.get("path")
        if not isinstance(path, str) or not (bundle / path).is_file():
            issues.append(f"{indicator_id}: advertised detail asset is missing")
            continue
        if detail.get("type") == "cog":
            if detail.get("canonical_resolution_verified") is not True:
                issues.append(f"{indicator_id}: COG scale was not canonically verified")
            if not isinstance(detail.get("source_native_resolution_m"), (int, float)):
                issues.append(f"{indicator_id}: COG descriptor lacks native source resolution")
            sidecar = bundle / path.replace(".tif", ".metadata.json")
            if not sidecar.is_file():
                issues.append(f"{indicator_id}: COG sidecar metadata is missing")
            else:
                metadata = _read_object(sidecar, f"{indicator_id} COG metadata", issues)
                required = {"source_native_study", "source_path", "source_support_preserved"}
                missing_provenance = sorted(key for key in required if not metadata.get(key))
                if missing_provenance:
                    issues.append(
                        f"{indicator_id}: COG lacks provenance ({', '.join(missing_provenance)})"
                    )
                if metadata.get("source_support_preserved") is not True:
                    issues.append(f"{indicator_id}: COG does not preserve source support")
                if metadata.get("source_native_resolution_m") != detail.get("source_native_resolution_m"):
                    issues.append(f"{indicator_id}: COG descriptor and sidecar scales differ")
                if strict:
                    source_grid = metadata.get("source_grid")
                    storage_grid = metadata.get("storage_grid")
                    source_hash = metadata.get("source_sha256")
                    if not isinstance(source_hash, str) or len(source_hash) != 64:
                        issues.append(f"{indicator_id}: COG lacks source content hash")
                    if not isinstance(source_grid, Mapping):
                        issues.append(f"{indicator_id}: COG lacks inspected source grid")
                    elif not canonical_detail_source_grid(str(indicator_id), metadata):
                        issues.append(
                            f"{indicator_id}: COG source grid does not meet the canonical provider grid"
                        )
                    if not isinstance(storage_grid, Mapping):
                        issues.append(f"{indicator_id}: COG lacks inspected storage grid")
                    if isinstance(storage_grid, Mapping):
                        try:
                            from .spatial_detail import raster_grid_signature

                            actual_grid = raster_grid_signature(bundle / path)
                        except (ImportError, OSError, ValueError) as exc:
                            issues.append(f"{indicator_id}: cannot inspect COG grid ({exc})")
                        else:
                            if not _grid_matches(storage_grid, actual_grid):
                                issues.append(f"{indicator_id}: COG storage grid differs from inspected TIFF")
        elif detail.get("type") == "geojson":
            payload = _read_object(bundle / path, f"{indicator_id} detail GeoJSON", issues)
            if payload.get("grid_alignment") != "study_aoi_metric_grid":
                issues.append(f"{indicator_id}: detail grid is not aligned to the study AOI")
            if payload.get("is_synthetic") is not False:
                issues.append(f"{indicator_id}: detail GeoJSON is not proven real")
        elif detail.get("type") == "vector_contours":
            _audit_vector_contours(
                str(indicator_id), detail, bundle, issues, strict=strict
            )
    _audit_temporal_details(manifest, bundle, issues, strict=strict)
    return SpatialAudit(palette, bundle, len(records), tuple(issues))


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gzip_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))


def _audit_vector_contours(
    indicator_id: str,
    detail: Mapping[str, Any],
    bundle: Path,
    issues: list[str],
    *,
    strict: bool,
) -> None:
    """Verify a local MVT tree and the evidence that binds it to its source."""
    descriptor_path = bundle / str(detail.get("path") or "")
    descriptor = _read_object(
        descriptor_path,
        f"{indicator_id} vector-contour descriptor",
        issues,
    )
    if not descriptor:
        return
    contract_issues = validate_vector_contour_descriptor(indicator_id, descriptor)
    issues.extend(f"{indicator_id}: {issue}" for issue in contract_issues)
    for key in (
        "schema_version",
        "type",
        "tiles",
        "minzoom",
        "maxzoom",
        "bounds",
        "source_layer",
        "bands",
        "source_manifest_sha256",
        "source_assets",
        "source_sha256",
        "source_support_preserved",
        "validation",
    ):
        if detail.get(key) != descriptor.get(key):
            issues.append(f"{indicator_id}: manifest and vector descriptor differ at {key}")

    tile_root = bundle / "detail" / indicator_id
    tile_paths = (
        sorted(
            path
            for path in tile_root.rglob("*.pbf")
            if not any(part.startswith(".") for part in path.relative_to(tile_root).parts)
        )
        if tile_root.is_dir()
        else []
    )
    if not tile_paths:
        issues.append(f"{indicator_id}: vector-contour tile tree is missing")
        return
    zoom_counts = {zoom: 0 for zoom in range(11, 16)}
    relative_tiles: dict[str, Path] = {}
    for tile_path in tile_paths:
        try:
            relative = tile_path.relative_to(bundle).as_posix()
            parts = tile_path.relative_to(tile_root).parts
            if len(parts) != 3 or not parts[2].endswith(".pbf"):
                raise ValueError
            zoom = int(parts[0])
            x = int(parts[1])
            y = int(Path(parts[2]).stem)
        except (ValueError, TypeError):
            issues.append(f"{indicator_id}: invalid tile path {tile_path}")
            continue
        if zoom not in zoom_counts or not (0 <= x < 2**zoom) or not (0 <= y < 2**zoom):
            issues.append(f"{indicator_id}: tile coordinates are outside zoom contract ({relative})")
            continue
        if tile_path.stat().st_size <= 0:
            issues.append(f"{indicator_id}: empty tile {relative}")
        zoom_counts[zoom] += 1
        relative_tiles[relative] = tile_path
    missing_zooms = [str(zoom) for zoom, count in zoom_counts.items() if count == 0]
    if missing_zooms:
        issues.append(f"{indicator_id}: vector tiles missing zooms {', '.join(missing_zooms)}")
    if not strict:
        return

    validation_ref = descriptor.get("validation")
    if not isinstance(validation_ref, Mapping):
        return
    report_path = bundle / str(validation_ref.get("path") or "")
    if not report_path.is_file():
        issues.append(f"{indicator_id}: vector validation report is missing")
        return
    if _sha256_path(report_path) != validation_ref.get("sha256"):
        issues.append(f"{indicator_id}: vector validation report hash differs")
        return
    report = _read_object(report_path, f"{indicator_id} vector validation report", issues)
    if not report:
        return
    if report.get("source_manifest_sha256") != descriptor.get("source_manifest_sha256"):
        issues.append(f"{indicator_id}: validation report source manifest differs")
    if report.get("source_assets") != descriptor.get("source_assets"):
        issues.append(f"{indicator_id}: validation report source assets differ")
    if report.get("source_support_preserved") is not True:
        issues.append(f"{indicator_id}: validation report does not preserve source support")
    if report.get("minzoom") != 11 or report.get("maxzoom") != 15:
        issues.append(f"{indicator_id}: validation report zoom contract differs")
    if report.get("quantization_invalid_geometry") != "polygonal_make_valid_or_drop":
        issues.append(f"{indicator_id}: MVT quantization policy is missing")
    geometry_hash = report.get("geometry_sha256")
    if not isinstance(geometry_hash, str) or len(geometry_hash) != 64:
        issues.append(f"{indicator_id}: final vector geometry hash is missing")

    topology = report.get("topology")
    required_topology = ("resolved_valid", "simplified_valid", "bands_disjoint", "within_aoi")
    if not isinstance(topology, Mapping) or any(topology.get(key) is not True for key in required_topology):
        issues.append(f"{indicator_id}: vector topology proof is incomplete")
    area_checks = report.get("area_checks")
    if not isinstance(area_checks, Mapping):
        issues.append(f"{indicator_id}: vector area proof is missing")
    else:
        expected_bands = {band["value"] for band in descriptor.get("bands", []) if isinstance(band, Mapping)}
        if set(area_checks) != expected_bands:
            issues.append(f"{indicator_id}: vector area proof does not cover every band")
        for band, check in area_checks.items():
            if not isinstance(check, Mapping):
                issues.append(f"{indicator_id}: invalid area proof for {band}")
                continue
            try:
                float(check["source_to_resolved_fraction"])
            except (KeyError, TypeError, ValueError):
                issues.append(f"{indicator_id}: area proof {band} lacks source overlap evidence")
            for field in ("resolved_to_simplified_fraction", "simplified_to_tiled_fraction"):
                try:
                    delta = abs(float(check[field]))
                except (KeyError, TypeError, ValueError):
                    issues.append(f"{indicator_id}: area proof {band} lacks {field}")
                    continue
                if delta > 0.005:
                    issues.append(
                        f"{indicator_id}: area drift for {band} exceeds 0.5% ({field}={delta:.6f})"
                    )

    inventory = report.get("tiles")
    inventory_by_path = {
        str(entry.get("path")): entry
        for entry in inventory or []
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }
    if set(inventory_by_path) != set(relative_tiles):
        issues.append(f"{indicator_id}: tile inventory has missing or extra PBFs")
    try:
        from mapbox_vector_tile import decode
    except ImportError as exc:
        issues.append(f"{indicator_id}: cannot decode MVT tiles ({exc})")
        decode = None
    for relative, tile_path in relative_tiles.items():
        entry = inventory_by_path.get(relative)
        if not isinstance(entry, Mapping):
            continue
        actual_raw = tile_path.stat().st_size
        actual_gzip = _gzip_size(tile_path)
        if entry.get("sha256") != _sha256_path(tile_path):
            issues.append(f"{indicator_id}: tile hash differs for {relative}")
        if entry.get("raw_bytes") != actual_raw or entry.get("gzip_bytes") != actual_gzip:
            issues.append(f"{indicator_id}: tile size evidence differs for {relative}")
        if actual_gzip > 500_000:
            issues.append(f"{indicator_id}: compressed tile exceeds 500 kB ({relative})")
        if decode is not None:
            try:
                payload = decode(tile_path.read_bytes())
                layer = payload.get(descriptor.get("source_layer"))
                features = layer.get("features") if isinstance(layer, Mapping) else None
                if not isinstance(features, list) or not features:
                    raise ValueError("source layer is empty")
                if any(
                    feature.get("properties", {}).get("lden_band") is None
                    or not isinstance(
                        feature.get("properties", {}).get("band_priority"), int
                    )
                    for feature in features
                    if isinstance(feature, Mapping)
                ):
                    raise ValueError("feature lacks categorical Lden properties")
            except Exception as exc:
                issues.append(f"{indicator_id}: cannot decode {relative} ({exc})")
    initial = report.get("initial_visible_gzip_bytes")
    if not isinstance(initial, Mapping) or any(
        not isinstance(initial.get(view), int) or initial[view] > 2_000_000
        for view in ("desktop_4x4", "mobile_3x5")
    ):
        issues.append(f"{indicator_id}: initial visible MVT load exceeds 2 MB or is unproven")


def _valid_color_domain(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        low = float(value["min"])
        high = float(value["max"])
    except (KeyError, TypeError, ValueError):
        return False
    return low == low and high == high and high > low


def _audit_temporal_details(
    manifest: Mapping[str, Any],
    bundle: Path,
    issues: list[str],
    *,
    strict: bool,
) -> None:
    """Verify that annual rasters are year-specific and comparable.

    A static period-average COG can be scientifically valid while still being
    invalid for an annual slider.  The temporal contract therefore verifies
    every harvest independently and requires one shared numeric color domain.
    """
    temporal = manifest.get("temporal_indicators")
    if temporal is None:
        return
    if not isinstance(temporal, Mapping):
        issues.append("web manifest temporal_indicators must be a mapping")
        return

    spatial_records = manifest.get("spatial_indicators")
    if not isinstance(spatial_records, Mapping):
        spatial_records = {}
    for indicator_id, record in temporal.items():
        if not isinstance(record, Mapping):
            issues.append(f"{indicator_id}: temporal indicator must be an object")
            continue
        years = record.get("years")
        if not isinstance(years, Mapping):
            issues.append(f"{indicator_id}: temporal indicator has no years mapping")
            continue
        target = record.get("spatial_target")
        expected_years = record.get("expected_years")
        base_record = spatial_records.get(indicator_id)
        base_target = (
            base_record.get("publication_target")
            if isinstance(base_record, Mapping)
            else None
        )
        required = (
            isinstance(target, Mapping)
            and target.get("required_for_production") is True
        ) or (
            not isinstance(target, Mapping)
            and isinstance(base_target, Mapping)
            and base_target.get("required_for_production") is True
        )
        if required:
            if expected_years is None and not isinstance(target, Mapping):
                expected_years = [str(value) for value in years]
            if not isinstance(expected_years, list) or not all(
                isinstance(value, str) and len(value) == 4 and value.isdigit()
                for value in expected_years
            ):
                issues.append(f"{indicator_id}: required temporal series has no expected_years")
                expected_years = []
            # Documented, permanent per-year gaps (ADR 0008) waive presence/detail
            # checks for exactly the declared years -- an exception can only
            # subtract from expected_years, never add an undeclared year, and
            # each excepted year must carry its own documented reason.
            raw_excepted_years = record.get("excepted_years") or []
            if not isinstance(raw_excepted_years, list) or not all(
                isinstance(value, str) and len(value) == 4 and value.isdigit()
                for value in raw_excepted_years
            ):
                issues.append(f"{indicator_id}: excepted_years must be a list of 4-digit years")
                raw_excepted_years = []
            excepted_years = set(raw_excepted_years)
            undeclared_exceptions = sorted(excepted_years - set(expected_years))
            if undeclared_exceptions:
                issues.append(
                    f"{indicator_id}: excepted_years {undeclared_exceptions} are not in "
                    "expected_years"
                )
            exception_reasons = {
                str(entry.get("year")): entry.get("reason")
                for entry in (record.get("exceptions") or [])
                if isinstance(entry, Mapping)
            }
            unexplained_exceptions = sorted(
                year for year in excepted_years if not exception_reasons.get(year)
            )
            if unexplained_exceptions:
                issues.append(
                    f"{indicator_id}: excepted_years {unexplained_exceptions} have no "
                    "documented reason"
                )
            required_years = [year for year in expected_years if year not in excepted_years]
            actual_years = {str(value) for value in years}
            missing_years = sorted(set(required_years) - actual_years)
            extra_years = sorted(actual_years - set(expected_years))
            if missing_years:
                issues.append(
                    f"{indicator_id}: required temporal series is missing years {missing_years}"
                )
            if extra_years:
                issues.append(
                    f"{indicator_id}: temporal series has undeclared years {extra_years}"
                )
            missing_detail = sorted(
                year
                for year in required_years
                if not isinstance(years.get(year), Mapping)
                or not isinstance(years[year].get("detail"), Mapping)
            )
            if missing_detail:
                issues.append(
                    f"{indicator_id}: required temporal detail is missing for {missing_detail}"
                )
        details = {
            str(year): year_record.get("detail")
            for year, year_record in years.items()
            if isinstance(year_record, Mapping) and isinstance(year_record.get("detail"), Mapping)
        }
        if not details:
            continue
        series_domain = record.get("color_domain")
        if not _valid_color_domain(series_domain):
            issues.append(f"{indicator_id}: annual raster series lacks a valid shared color domain")
        source_hashes: dict[str, str] = {}

        for year, detail in details.items():
            assert isinstance(detail, Mapping)
            prefix = f"{indicator_id} {year}"
            detail_type = detail.get("type")
            if detail_type not in {"cog", "geojson"}:
                issues.append(f"{prefix}: annual detail must be a COG or GeoJSON grid")
                continue
            path_value = detail.get("path")
            if not isinstance(path_value, str):
                issues.append(f"{prefix}: annual detail path is missing")
                continue
            path = bundle / path_value
            if not path.is_file():
                issues.append(f"{prefix}: advertised annual detail is missing")
                continue
            support = detail.get("temporal_support")
            if not (
                isinstance(support, Mapping)
                and support.get("kind") == "year"
                and str(support.get("year")) == year
                and isinstance(support.get("source_label"), str)
                and bool(str(support.get("source_label")).strip())
            ):
                issues.append(f"{prefix}: detail temporal support does not match its harvest")
            if detail.get("source_support_preserved") is not True:
                issues.append(f"{prefix}: detail does not preserve source support")
            source_hash = detail.get("source_sha256")
            if not isinstance(source_hash, str) or len(source_hash) != 64:
                issues.append(f"{prefix}: detail lacks source content hash")
            else:
                source_hashes[year] = source_hash
            if series_domain != detail.get("color_domain"):
                issues.append(f"{prefix}: detail does not use the series color domain")

            sidecar = path.with_suffix(".metadata.json")
            if not sidecar.is_file():
                issues.append(f"{prefix}: detail sidecar metadata is missing")
                continue
            metadata = _read_object(sidecar, f"{prefix} detail metadata", issues)
            if metadata.get("temporal_support") != support:
                issues.append(f"{prefix}: descriptor and sidecar temporal support differ")
            if metadata.get("source_sha256") != source_hash:
                issues.append(f"{prefix}: descriptor and sidecar source hashes differ")
            if metadata.get("source_support_preserved") is not True:
                issues.append(f"{prefix}: sidecar does not preserve source support")
            if metadata.get("series_color_domain") != series_domain:
                issues.append(f"{prefix}: sidecar does not use the series color domain")
            if detail_type == "cog":
                if detail.get("canonical_resolution_verified") is not True:
                    issues.append(f"{prefix}: COG scale was not canonically verified")
                if metadata.get("source_native_resolution_m") != detail.get(
                    "source_native_resolution_m"
                ):
                    issues.append(f"{prefix}: descriptor and sidecar scales differ")
            else:
                payload = _read_object(path, f"{prefix} analysis grid", issues)
                if (
                    detail.get("analysis_grid_verified") is not True
                    or detail.get("grid_alignment") != "study_aoi_metric_grid"
                    or payload.get("grid_alignment") != "study_aoi_metric_grid"
                    or payload.get("is_synthetic") is not False
                    or payload.get("temporal_support") != support
                    or metadata.get("analysis_resolution_m")
                    != detail.get("analysis_resolution_m")
                ):
                    issues.append(f"{prefix}: annual analysis grid is not canonical")
                if strict and isinstance(source_hash, str):
                    from .spatial_detail import _file_sha256

                    if _file_sha256(path) != source_hash:
                        issues.append(f"{prefix}: GeoJSON content hash differs from descriptor")

            if strict and detail_type == "cog":
                if not canonical_detail_source_grid(str(indicator_id), metadata):
                    issues.append(
                        f"{prefix}: COG source grid does not meet the canonical provider grid"
                    )
                storage_grid = metadata.get("storage_grid")
                if not isinstance(storage_grid, Mapping):
                    issues.append(f"{prefix}: COG lacks inspected storage grid")
                else:
                    try:
                        from .spatial_detail import raster_grid_signature

                        actual_grid = raster_grid_signature(path)
                    except (ImportError, OSError, ValueError) as exc:
                        issues.append(f"{prefix}: cannot inspect COG grid ({exc})")
                    else:
                        if not _grid_matches(storage_grid, actual_grid):
                            issues.append(f"{prefix}: COG storage grid differs from inspected TIFF")

        if len(source_hashes) > 1 and len(set(source_hashes.values())) != len(source_hashes):
            issues.append(f"{indicator_id}: annual details reuse identical source content")


def _grid_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """Compare inspected grids with a small tolerance for serialized floats."""
    if str(expected.get("crs")) != str(actual.get("crs")):
        return False
    expected_resolution = expected.get("resolution")
    actual_resolution = actual.get("resolution")
    if not isinstance(expected_resolution, Mapping) or not isinstance(actual_resolution, Mapping):
        return False
    if expected_resolution.get("unit") != actual_resolution.get("unit"):
        return False
    try:
        return all(
            abs(float(expected_resolution[axis]) / float(actual_resolution[axis]) - 1.0) <= 1e-9
            for axis in ("x", "y")
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def published_bundle_paths(root: str | Path) -> list[Path]:
    """Return bundle manifests, excluding per-layer manifests nested within them."""
    base = Path(root)
    return sorted(
        path
        for path in base.rglob("manifest.json")
        if "layers" not in path.relative_to(base).parts
    )


def migrate_bundle_to_v3(bundle_path: str | Path, palette_path: str | Path) -> Path:
    """Regenerate a bundle's spatial records from its local, real assets.

    This migration never fabricates raster data.  It only moves a web manifest
    to v3, preserving the bundle's other fields and advertising a detail asset
    only when its on-disk metadata proves its provenance.
    """
    bundle = Path(bundle_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    palette = json.loads(Path(palette_path).read_text(encoding="utf-8"))
    exposomes = palette.get("exposomes")
    if not isinstance(exposomes, Mapping):
        raise ValueError("palette has no exposomes mapping")
    files = [
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and not path.name.startswith("._")
    ]
    detail_metadata: dict[str, Mapping[str, Any]] = {}
    for path in bundle.glob("detail/*.metadata.json"):
        if path.name.startswith("._"):
            continue  # macOS AppleDouble sidecar (NFS/SMB mounts), never real content
        try:
            detail_metadata[path.name.removesuffix(".metadata.json")] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid COG metadata: {path}") from exc
    geojson_metadata: dict[str, Mapping[str, Any]] = {}
    for path in bundle.glob("subcomuna/*.geojson"):
        if path.name.startswith("._"):
            continue  # macOS AppleDouble sidecar (NFS/SMB mounts), never real content
        try:
            geojson_metadata[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid detail GeoJSON: {path}") from exc
    unit_label = str(manifest.get("spatial", {}).get("unit_type") or "unidad administrativa")
    records = indicators_for_bundle(
        files,
        detail_metadata=detail_metadata,
        geojson_detail_metadata=geojson_metadata,
        administrative_unit_label=administrative_unit_label(unit_label),
        is_native=manifest.get("mode") == "native",
    )
    errors = validate_palette_coverage(exposomes) + validate_indicator_records(records)
    if errors:
        raise ValueError("invalid v3 spatial contract: " + "; ".join(errors))
    manifest["schema_version"] = SPATIAL_SCHEMA_VERSION
    manifest["spatial_indicators"] = records
    manifest.pop("manifest_payload_sha256", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_payload_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _read_object(path: Path, label: str, issues: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"invalid {label}: {path} ({exc})")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{label} must be a JSON object: {path}")
        return {}
    return payload
