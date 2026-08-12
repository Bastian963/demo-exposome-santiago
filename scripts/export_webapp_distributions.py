"""Export cross-city distribution comparisons for the webapp analytics panel.

Reads already-published bundles (``webapp/public/data/v1/<iso2>/<city>/<study>/
master.csv``) for the admin-unit sample and their manifest-verified detail
assets for the fine-grid sample, and writes a single precomputed artifact:

    webapp/public/data/v1/analytics/distributions.json

All statistics (robust median/MAD band, shared histogram, eCDF, KS, k-sample
Anderson-Darling) are computed here in Python via
``exposome.distributions`` -- the webapp only renders the resulting JSON, it
never recomputes inference client-side.

This is a local, fast, offline export (like the other ``export_webapp_*.py``
scripts): it never calls GEE/Open-Meteo/OSM/Esri, only reads data that a
previous ``exposome run``/``exposome publish`` already materialized on disk.

Usage
-----
    python scripts/export_webapp_distributions.py --dry-run
    python scripts/export_webapp_distributions.py
    python scripts/export_webapp_distributions.py --indicators pm25,no2
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.distributions import (  # noqa: E402
    FINE_SAMPLE_AUTOCORR_WARNING_N,
    ad_ksample,
    count_outliers,
    ecdf_points,
    ks_two_sample,
    robust_scale_double_mad,
    shared_histogram,
    shared_histogram_log,
)
from exposome.spatial_detail import NATIVE_RASTER_INDICATORS  # noqa: E402

app = typer.Typer(help="Export cross-city distribution comparisons for the analytics panel.")

DATA_ROOT = REPO_ROOT / "webapp" / "public" / "data"
CATALOG_PATH = DATA_ROOT / "catalog.json"
DEFAULT_OUTPUT = DATA_ROOT / "v1" / "analytics" / "distributions.json"

# Columns that describe geometry/identity, not an exposome indicator -- never
# compared as a "distribution".
ADMIN_COLUMN_DENYLIST = {"name", "slug", "spatial_id", "spatial_name", "area_km2"}

# Fine-grid indicators are NOT relabeled from palette.json.exposomes: the
# admin-level registry entry for "no2" describes a different physical
# quantity (mu g/m3 surface proxy) than the fine native raster (mol/m2
# tropospheric column) -- reusing it here would silently misrepresent the
# unit. Units below are read from each city's own native metadata.json at
# runtime and cross-checked against these as a sanity fallback only.
FINE_INDICATOR_LABELS = {
    "pm25": "PM2.5 (pixel nativo)",
    "no2": "NO2 columna troposferica (pixel nativo)",
    "alan": "Luminosidad nocturna (pixel nativo)",
    "wind": "Velocidad del viento (pixel nativo)",
    "green": "Cobertura verde (pixel nativo)",
}
FINE_INDICATOR_CATEGORY = "entorno"
FINE_INDICATOR_UNITS = {
    "pm25": "µg/m³",
    "no2": "mol/m²",
    "alan": "nW/cm²/sr",
    "wind": "m/s",
    "green": "%",
}


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def visible_studies(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Studies that are actually comparable today: published, not hidden.

    Hidden studies (``buenos_aires_comunas``, ``caba_native``) are either a
    subset of an already-included study or a native-only bundle without a
    ``master.csv`` -- including them would double count Buenos Aires or
    silently skip the admin sample.
    """
    return [
        s
        for s in catalog.get("studies", [])
        if s.get("available") and s.get("bundle") and not s.get("hidden")
    ]


def parse_bundle(bundle: str) -> tuple[str, str, str]:
    """``v1/<iso2>/<city>/<study>`` -> (iso2, city, study)."""
    iso2, city, study = bundle.strip("/").split("/")[1:4]
    return iso2, city, study


def load_palette() -> dict[str, Any]:
    path = REPO_ROOT / "webapp" / "public" / "palette.json"
    return json.loads(path.read_text(encoding="utf-8"))


def registry_by_column(palette: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Map ``master.csv`` column -> (exposome_id, catalog entry).

    This is the *single* place the fragile column->exposome join lives. The
    webapp panel never re-derives it: it builds its rail from the same
    ``palette.exposomes`` catalog and matches data by the ``exposome_id`` we
    stamp here (see docs/analytics_distribution_comparison.md).

    ``status: group`` entries are aggregation parents whose ``column`` merely
    duplicates one of their children (e.g. ``heat`` and its child
    ``heat_index`` share ``heat_exposure_index``). Skipping them lets the
    concrete child exposome own the column, so the analytics indicator keys the
    leaf the picker would drill into, not the parent.
    """
    exposomes = palette.get("exposomes", {})
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for indicator_id, entry in exposomes.items():
        if entry.get("status") == "group" or entry.get("analytics_exclude") is True:
            continue
        column = entry.get("column")
        if column and column not in out:
            out[column] = (indicator_id, entry)
    return out


def humanize_column(column: str) -> str:
    return column.replace("_", " ").strip().title()


def collect_admin_samples(
    studies: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, int]]]:
    """column -> {city_slug: array of non-null values}, plus column ->
    {city_slug: n_dropped_nan} so a city with many missing units for a given
    indicator is visible in the UI rather than silently shrinking ``n``."""
    by_column: dict[str, dict[str, np.ndarray]] = {}
    dropped_by_column: dict[str, dict[str, int]] = {}
    for study in studies:
        _, city, _ = parse_bundle(study["bundle"])
        master_path = DATA_ROOT / study["bundle"] / "master.csv"
        if not master_path.exists():
            continue
        df = pd.read_csv(master_path, low_memory=False)
        n_rows = len(df)
        for column in df.columns:
            if column in ADMIN_COLUMN_DENYLIST:
                continue
            if not pd.api.types.is_numeric_dtype(df[column]):
                continue
            values = df[column].dropna().to_numpy(dtype=float)
            if values.size == 0:
                continue
            by_column.setdefault(column, {})[city] = values
            dropped_by_column.setdefault(column, {})[city] = n_rows - values.size
    # Only keep columns shared by at least two cities -- a single-city
    # column isn't a "comparison", and would otherwise flood the index with
    # ~300 Santiago-only / Buenos-Aires-only columns.
    shared = {col: cities for col, cities in by_column.items() if len(cities) >= 2}
    dropped_shared = {col: dropped_by_column[col] for col in shared}
    return shared, dropped_shared


def _verified_published_detail(
    bundle_dir: Path,
    manifest: dict[str, Any],
    indicator_id: str,
    expected_type: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    """Return a published fine asset only when its manifest proves support.

    A native file merely existing under ``data/processed`` is insufficient:
    publication may deliberately hide a stale or non-canonical raster.  COGs
    therefore require the v3 canonical-resolution flag and a matching sidecar
    scale; the green GeoJSON requires the stable study-aligned grid contract.
    """
    if manifest.get("schema_version") != 3:
        return None
    records = manifest.get("spatial_indicators")
    record = records.get(indicator_id) if isinstance(records, dict) else None
    detail = record.get("detail") if isinstance(record, dict) else None
    if not isinstance(detail, dict) or detail.get("type") != expected_type:
        return None
    relative_path = detail.get("path")
    if not isinstance(relative_path, str):
        return None
    asset = bundle_dir / relative_path
    if not asset.is_file():
        return None

    if expected_type == "cog":
        descriptor_scale = detail.get("source_native_resolution_m")
        if detail.get("canonical_resolution_verified") is not True or not isinstance(
            descriptor_scale, (int, float)
        ):
            return None
        sidecar_path = asset.with_suffix(".metadata.json")
        if not sidecar_path.is_file():
            return None
        try:
            metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        sidecar_scale = metadata.get("source_native_resolution_m")
        if (
            metadata.get("source_support_preserved") is not True
            or not isinstance(sidecar_scale, (int, float))
            or not np.isclose(float(sidecar_scale), float(descriptor_scale), rtol=0, atol=0.01)
        ):
            return None
        return asset, metadata, record

    try:
        metadata = json.loads(asset.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if indicator_id == "green" and metadata.get("grid_alignment") != "study_aoi_metric_grid":
        return None
    return asset, metadata, record


def _resolution_value(record: dict[str, Any]) -> float | None:
    rendered = record.get("rendered")
    resolution = rendered.get("resolution") if isinstance(rendered, dict) else None
    value = resolution.get("value") if isinstance(resolution, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def collect_fine_samples(
    studies: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, Any]]]:
    """Collect manifest-verified fine samples shared by at least two cities."""
    import rasterio

    by_indicator: dict[str, dict[str, np.ndarray]] = {}
    meta_by_indicator: dict[str, dict[str, Any]] = {}
    for study in studies:
        iso2, city, study_id = parse_bundle(study["bundle"])
        bundle_dir = DATA_ROOT / study["bundle"]
        manifest_path = bundle_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for indicator_id in NATIVE_RASTER_INDICATORS:
            published = _verified_published_detail(
                bundle_dir, manifest, indicator_id, "cog"
            )
            if published is None:
                continue
            tif_path, metadata, record = published
            detail = record["detail"]
            band = int(detail.get("band", 1))
            try:
                with rasterio.open(tif_path) as dataset:
                    data = dataset.read(band, masked=True)
                    values = np.asarray(data.compressed(), dtype="float64")
            except Exception as exc:  # noqa: BLE001 - one bad raster shouldn't abort the export
                print(f"  ! Skipping {city}/{indicator_id}: failed to read {tif_path} ({exc})")
                continue
            if values.size == 0:
                continue
            by_indicator.setdefault(indicator_id, {})[city] = values
            meta_by_indicator.setdefault(
                indicator_id,
                {
                    "label": FINE_INDICATOR_LABELS.get(indicator_id, indicator_id),
                    "unit": detail.get("unit") or FINE_INDICATOR_UNITS.get(indicator_id),
                    "resolution": (
                        f"~{metadata.get('source_native_resolution_m')} m (nativo)"
                    ),
                    "category": FINE_INDICATOR_CATEGORY,
                },
            )

        # Green values live in a published stable-grid GeoJSON, not a raster.
        published_green = _verified_published_detail(bundle_dir, manifest, "green", "geojson")
        if published_green is not None:
            _, geojson, green_record = published_green
            values = np.array(
                [
                    f["properties"]["value"]
                    for f in geojson.get("features", [])
                    if f.get("properties", {}).get("value") is not None
                ],
                dtype="float64",
            )
            if values.size:
                by_indicator.setdefault("green", {})[city] = values
                meta_by_indicator.setdefault(
                    "green",
                    {
                        "label": FINE_INDICATOR_LABELS["green"],
                        "unit": FINE_INDICATOR_UNITS["green"],
                        "resolution": f"~{_resolution_value(green_record)} m (grilla de análisis)",
                        "category": FINE_INDICATOR_CATEGORY,
                    },
                )
    # A single-city fine layer is not a cross-city comparison.  In that case
    # the caller falls back to the shared administrative headline column.
    shared = {key: cities for key, cities in by_indicator.items() if len(cities) >= 2}
    shared_meta = {key: meta_by_indicator[key] for key in shared}
    return shared, shared_meta


def _physical_floor(values_by_city: dict[str, np.ndarray]) -> float | None:
    """Only clip the lower band to 0 when every observed value across every
    city is already non-negative -- a data-driven proxy for "this is a
    concentration/count/percentage", without a hand-maintained per-column
    sign registry that would drift out of sync."""
    if all(np.min(vals) >= 0 for vals in values_by_city.values()):
        return 0.0
    return None


def build_indicator_entry(
    indicator_id: str,
    values_by_city: dict[str, np.ndarray],
    *,
    label: str,
    unit: str | None,
    unit_long: str | None,
    category: str,
    column: str | None,
    resolution: str | None,
    sample_level: str,
    max_bins: int,
    dropped_by_city: dict[str, int] | None = None,
) -> dict[str, Any]:
    floor = _physical_floor(values_by_city)
    hist = shared_histogram(values_by_city, max_bins=max_bins)
    dropped_by_city = dropped_by_city or {}

    # Log view only when every value is strictly positive (log10 undefined at
    # 0): a data-driven eligibility check, same spirit as _physical_floor.
    log_json: dict[str, Any] | None = None
    if all(np.min(vals) > 0 for vals in values_by_city.values()):
        log_hist = shared_histogram_log(values_by_city, max_bins=max_bins)
        if log_hist.bins:
            log_json = {
                "bins": log_hist.bins,
                "cities": {
                    city: {"hist_density": density}
                    for city, density in log_hist.density_by_city.items()
                },
            }

    cities_json: dict[str, Any] = {}
    for city, values in values_by_city.items():
        scale = robust_scale_double_mad(values, physical_floor=floor)
        ecdf = ecdf_points(values)
        n_dropped = dropped_by_city.get(city, 0)
        cities_json[city] = {
            "n": int(values.size),
            "n_valid": int(values.size),
            "n_dropped_nan": int(n_dropped),
            "median": scale.median,
            **scale.to_json(),
            "n_outliers": count_outliers(values, scale),
            "hist_density": hist.density_by_city.get(city, []),
            "overflow_low": hist.overflow_low_by_city.get(city, 0),
            "overflow_high": hist.overflow_high_by_city.get(city, 0),
            "ecdf": ecdf.to_json(),
        }

    tests: dict[str, Any] = {}
    city_slugs = sorted(values_by_city)
    if len(city_slugs) >= 2:
        ks_pairs = []
        for i, a in enumerate(city_slugs):
            for b in city_slugs[i + 1 :]:
                result = ks_two_sample(values_by_city[a], values_by_city[b])
                ks_pairs.append({"a": a, "b": b, **result.to_json()})
        tests["ks"] = ks_pairs
        ad_result = ad_ksample([values_by_city[c] for c in city_slugs])
        if ad_result is not None:
            tests["ad"] = {**ad_result.to_json(), "cities": city_slugs}

    warnings_list: list[str] = []
    if sample_level == "fine" and any(
        v.size >= FINE_SAMPLE_AUTOCORR_WARNING_N for v in values_by_city.values()
    ):
        warnings_list.append("spatial_autocorrelation")

    return {
        "exposome_id": indicator_id,
        "label": label,
        "unit": unit,
        "unit_long": unit_long,
        "category": category,
        "column": column,
        "sample_level": sample_level,
        "resolution": resolution,
        "warnings": warnings_list,
        "display_range": list(hist.display_range),
        "bins": hist.bins,
        "cities": cities_json,
        **({"log": log_json} if log_json else {}),
        **({"tests": tests} if tests else {}),
    }


@app.command()
def main(
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
    bins: int = typer.Option(60, "--bins", help="Max histogram bins (Freedman-Diaconis capped)."),
    indicators: str | None = typer.Option(
        None, "--indicators", help="Comma-separated indicator ids to restrict to (debugging)."
    ),
    include_fine: bool = typer.Option(True, "--include-fine/--no-fine"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    catalog = load_catalog()
    studies = visible_studies(catalog)
    if not studies:
        raise typer.BadParameter("No visible (available, non-hidden) studies with a bundle found.")

    only = set(i.strip() for i in indicators.split(",")) if indicators else None

    admin_samples, admin_dropped = collect_admin_samples(studies)
    fine_samples: dict[str, dict[str, np.ndarray]] = {}
    fine_meta: dict[str, dict[str, Any]] = {}
    if include_fine:
        fine_samples, fine_meta = collect_fine_samples(studies)

    if only:
        admin_samples = {k: v for k, v in admin_samples.items() if k in only}
        admin_dropped = {k: v for k, v in admin_dropped.items() if k in only}
        fine_samples = {k: v for k, v in fine_samples.items() if k in only}

    palette = load_palette()
    by_column = registry_by_column(palette)

    headline_cols = {
        col for col in admin_samples if (hit := by_column.get(col)) and hit[0] not in fine_samples
    }
    print(f"Studies: {[parse_bundle(s['bundle'])[1] for s in studies]}")
    print(f"Fine indicators: {sorted(fine_samples)} ({len(fine_samples)})")
    print(
        f"Admin columns shared by >=2 cities: {len(admin_samples)} "
        f"-> catalog headline columns kept: {len(headline_cols)} "
        f"(dropped {len(admin_samples) - len(headline_cols)} detail columns)"
    )

    if dry_run:
        for indicator_id, values_by_city in sorted(fine_samples.items()):
            counts = {c: v.size for c, v in values_by_city.items()}
            print(f"  [fine]  {indicator_id}: {counts}")
        for column, values_by_city in sorted(admin_samples.items()):
            counts = {c: v.size for c, v in values_by_city.items()}
            print(f"  [admin] {column}: {counts}")
        return

    indicators_json: dict[str, Any] = {}

    # Fine grids win only when at least two cities publish a manifest-verified
    # detail asset.  Otherwise the shared administrative headline remains the
    # honest cross-city comparison.
    for indicator_id, values_by_city in fine_samples.items():
        meta = fine_meta[indicator_id]
        indicators_json[indicator_id] = build_indicator_entry(
            indicator_id,
            values_by_city,
            label=meta["label"],
            unit=meta["unit"],
            unit_long=meta.get("unit_long"),
            category=meta["category"],
            column=None,
            resolution=meta["resolution"],
            sample_level="fine",
            max_bins=bins,
        )

    # Admin sample: keep only columns that are an exposome's *headline* column
    # in the catalog -- the same ~40 the picker shows, keyed by exposome_id.
    # The ~160 derived/detail columns (pm25_who_ratio, ndvi_mean vs evi_mean,
    # precip_rx1day, spi_3_mean, tmax_p95_c...) the picker deliberately hides
    # are dropped, not surfaced as pseudo-indicators. master.csv stays the full
    # source of truth for anyone who needs them.
    for column, values_by_city in admin_samples.items():
        registry_hit = by_column.get(column)
        if registry_hit is None:
            continue
        reg_id, entry = registry_hit
        if reg_id in fine_samples:
            continue  # already exported at fine (max) resolution
        indicators_json[reg_id] = build_indicator_entry(
            reg_id,
            values_by_city,
            label=entry.get("label", humanize_column(column)),
            unit=entry.get("unit"),
            unit_long=entry.get("unit_long"),
            category=entry.get("category", "otros"),
            column=column,
            resolution="por unidad administrativa",
            sample_level="admin",
            max_bins=bins,
            dropped_by_city=admin_dropped.get(column, {}),
        )

    city_slugs = sorted({parse_bundle(s["bundle"])[1] for s in studies})
    cities_meta = []
    for study in studies:
        iso2, city, _ = parse_bundle(study["bundle"])
        if city in city_slugs:
            cities_meta.append(
                {
                    "slug": city,
                    "name": study.get("name") or city,
                    "country_code": study.get("country_code") or iso2.upper(),
                }
            )
            city_slugs.remove(city)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "1",
        "cities": cities_meta,
        "indicators": indicators_json,
    }

    for indicator_id, entry in indicators_json.items():
        assert entry["bins"], f"{indicator_id}: empty bins"
        assert entry["cities"], f"{indicator_id}: empty cities"

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(output)
    print(f"  Wrote: {output} ({len(indicators_json)} indicators, {output.stat().st_size} bytes)")


if __name__ == "__main__":
    app()
