#!/usr/bin/env python3
"""Fetch and materialize DANE 2024 urban AOIs for three Colombia studies.

This is a human-run, restartable reference collector. It queries the official
DANE MGN 2024 ``Zona Urbana`` feature layer for the municipal capital
(``clas_ccdgo = '1'``) of Santa Marta, Cartagena and Pasto. Each city is
checkpointed as its own immutable raw snapshot before the normalized reference
is written, so an interrupted run resumes from the first missing city.

The aggregate studies deliberately contain one official urban unit each. They
do not claim neighborhood-level resolution; native companion studies retain
source-grid detail wherever a layer's publication contract permits it.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

import geopandas as gpd
import requests
from tqdm import tqdm

from exposome.raw_sources import (
    SOURCE_MANIFEST_NAME,
    build_raw_source_asset,
    load_source_manifest,
    write_source_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
SERVICE_URLS = (
    (
        "https://geoportal.dane.gov.co/mparcgis/rest/services/MGN2024/"
        "Serv_CapasMGN_2024/FeatureServer/305/query"
    ),
    (
        "https://portalgis.dane.gov.co/mparcgis/rest/services/MGN2024/"
        "Serv_CapasMGN_2024/MapServer/305/query"
    ),
)
SOURCE_VERSION = "2024"
SOURCE_LICENSE = (
    "CC BY 4.0; attribute Departamento Administrativo Nacional de Estadistica "
    "- DANE (www.dane.gov.co)"
)
OUT_FIELDS = (
    "dpto_ccdgo,mpio_ccdgo,mpio_cdpmp,clas_ccdgo,zu_ccdgo,zu_cdivi,"
    "zu_cnmbre,zu_ccnct,zu_narea,zu_naltd,zu_nano,Categoria"
)
REQUIRED_FIELDS = {
    "mpio_cdpmp",
    "clas_ccdgo",
    "zu_ccdgo",
    "zu_cdivi",
    "zu_cnmbre",
    "zu_ccnct",
    "zu_narea",
    "zu_nano",
    "Categoria",
}


@dataclass(frozen=True)
class CitySpec:
    slug: str
    name: str
    department: str
    dane_code: str
    aggregate_study: str
    bbox: tuple[float, float, float, float]


CITY_SPECS = (
    CitySpec(
        "santa_marta",
        "Santa Marta",
        "Magdalena",
        "47001",
        "santa_marta_urban",
        (-74.36, 11.06, -74.05, 11.39),
    ),
    CitySpec(
        "cartagena",
        "Cartagena de Indias",
        "Bolivar",
        "13001",
        "cartagena_urban",
        (-75.68, 10.20, -75.35, 10.58),
    ),
    CitySpec(
        "pasto",
        "Pasto",
        "Narino",
        "52001",
        "pasto_urban",
        (-77.43, 1.04, -77.14, 1.37),
    ),
)
CITY_BY_SLUG = {spec.slug: spec for spec in CITY_SPECS}


def _discovery_query_params(spec: CitySpec) -> dict[str, str]:
    west, south, east, north = spec.bbox
    return {
        # The alternate official host's WAF rejects quoted compound SQL filters.
        # Discover the cabecera OBJECTID spatially, then fetch only that feature.
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,mpio_cdpmp,clas_ccdgo,Categoria",
        "returnGeometry": "false",
        "resultRecordCount": "100",
        "f": "json",
    }


def _feature_query_params(object_id: str) -> dict[str, str]:
    return {
        "objectIds": object_id,
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }


def _prepared_url(
    spec: CitySpec,
    service_url: str = SERVICE_URLS[0],
    *,
    object_id: str | None = None,
) -> str:
    params = (
        _feature_query_params(object_id)
        if object_id is not None
        else _discovery_query_params(spec)
    )
    prepared = requests.Request("GET", service_url, params=params).prepare()
    if not prepared.url:
        raise RuntimeError(f"Could not prepare DANE request for {spec.slug}")
    return prepared.url


def _select_object_id(payload: Any, spec: CitySpec) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError(f"DANE discovery response for {spec.slug} is not an object")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"DANE discovery features for {spec.slug} are not a list")
    candidates: list[Any] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        attributes = feature.get("attributes")
        if not isinstance(attributes, Mapping):
            continue
        code = str(attributes.get("mpio_cdpmp", "")).strip()
        klass = str(attributes.get("clas_ccdgo", "")).strip()
        category = str(attributes.get("Categoria", "")).strip()
        if code == spec.dane_code and klass == "1" and category == "Cabecera Municipal":
            candidates.append(attributes.get("OBJECTID"))
    if len(candidates) != 1 or candidates[0] is None:
        raise ValueError(
            f"Expected exactly one DANE cabecera OBJECTID for {spec.slug} "
            f"({spec.dane_code}), found {len(candidates)}"
        )
    object_id = str(candidates[0]).strip()
    if not object_id.isdigit():
        raise ValueError(f"Invalid DANE OBJECTID for {spec.slug}: {candidates[0]!r}")
    return object_id


def _snapshot_root(root: Path, spec: CitySpec) -> Path:
    dataset = f"mgn-zona-urbana-{spec.dane_code}"
    return root / "data" / "raw" / "dane" / dataset / SOURCE_VERSION


def _reference_root(root: Path, spec: CitySpec) -> Path:
    return root / "data" / "reference" / "co" / spec.slug / spec.aggregate_study


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as tmp:
        staged = Path(tmp.name)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(staged, path)


def _atomic_text(path: Path, content: str) -> None:
    _atomic_bytes(path, content.encode("utf-8"))


def _validate_payload(payload: Any, spec: CitySpec) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"DANE response for {spec.slug} is not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"DANE features for {spec.slug} are not a list")
    candidates: list[Mapping[str, Any]] = []
    for feature in features:
        if not isinstance(feature, Mapping):
            raise ValueError(f"Invalid DANE feature for {spec.slug}")
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError(f"DANE feature for {spec.slug} has no properties")
        code = str(properties.get("mpio_cdpmp", "")).strip()
        klass = str(properties.get("clas_ccdgo", "")).strip()
        if code == spec.dane_code and klass == "1":
            candidates.append(feature)
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one DANE cabecera feature for {spec.slug} "
            f"({spec.dane_code}), found {len(candidates)}"
        )
    feature = candidates[0]
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    assert isinstance(properties, Mapping)
    missing = sorted(REQUIRED_FIELDS - set(properties))
    if missing:
        raise ValueError(f"DANE feature for {spec.slug} is missing fields: {missing}")
    if str(properties.get("Categoria", "")).strip() != "Cabecera Municipal":
        raise ValueError(f"Unexpected DANE Categoria for {spec.slug}: {properties.get('Categoria')!r}")
    if not isinstance(geometry, Mapping) or geometry.get("type") not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise ValueError(f"DANE feature for {spec.slug} is not polygonal")
    return feature


def _read_payload(path: Path, spec: CitySpec) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid cached DANE GeoJSON {path}: {exc}") from exc
    _validate_payload(payload, spec)
    return payload


def _download_source(
    spec: CitySpec,
    *,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
    attempts_per_service: int,
    retry_wait_seconds: float,
) -> requests.Response:
    if attempts_per_service < 1:
        raise ValueError("attempts_per_service must be at least 1")
    errors: list[str] = []
    for service_url in SERVICE_URLS:
        host = requests.utils.urlparse(service_url).hostname or service_url
        for attempt in range(1, attempts_per_service + 1):
            tqdm.write(
                f"{spec.name}: trying {host} "
                f"(attempt {attempt}/{attempts_per_service})"
            )
            try:
                discovery = requests.get(
                    service_url,
                    params=_discovery_query_params(spec),
                    headers={"User-Agent": "BrainLat-exposome-reference-builder/1.1"},
                    timeout=(connect_timeout_seconds, read_timeout_seconds),
                )
                discovery.raise_for_status()
                try:
                    discovery_payload = discovery.json()
                except requests.JSONDecodeError as exc:
                    raise ValueError(
                        f"DANE returned non-JSON discovery content for {spec.slug}"
                    ) from exc
                object_id = _select_object_id(discovery_payload, spec)
                response = requests.get(
                    service_url,
                    params=_feature_query_params(object_id),
                    headers={"User-Agent": "BrainLat-exposome-reference-builder/1.1"},
                    timeout=(connect_timeout_seconds, read_timeout_seconds),
                )
                response.raise_for_status()
                try:
                    payload = response.json()
                except requests.JSONDecodeError as exc:
                    raise ValueError(
                        f"DANE returned non-JSON content for {spec.slug}"
                    ) from exc
                _validate_payload(payload, spec)
                return response
            except (requests.RequestException, ValueError) as exc:
                errors.append(f"{host} attempt {attempt}: {exc}")
                tqdm.write(f"{spec.name}: {host} unavailable: {exc}")
                if attempt < attempts_per_service and retry_wait_seconds > 0:
                    time.sleep(retry_wait_seconds)
    detail = "\n  - ".join(errors)
    raise RuntimeError(
        f"All official DANE services failed for {spec.name}:\n  - {detail}"
    )


def _checkpoint_source(
    root: Path,
    spec: CitySpec,
    *,
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
    attempts_per_service: int,
    retry_wait_seconds: float,
) -> tuple[Path, Path]:
    snapshot_root = _snapshot_root(root, spec)
    source = snapshot_root / "zona_urbana.geojson"
    manifest = snapshot_root / SOURCE_MANIFEST_NAME
    source_url = _prepared_url(spec)

    if source.is_file():
        _read_payload(source, spec)
        if manifest.is_file():
            snapshot = load_source_manifest(snapshot_root, verify=True)
            if (
                snapshot.provider != "dane"
                or snapshot.dataset != f"mgn-zona-urbana-{spec.dane_code}"
                or snapshot.version != SOURCE_VERSION
            ):
                raise ValueError(f"Unexpected source manifest identity: {manifest}")
            print(f"{spec.name}: raw DANE snapshot verified; skipping download")
            return source, manifest
        print(f"{spec.name}: completing manifest for existing raw checkpoint")
    else:
        print(f"{spec.name}: downloading official DANE urban boundary")
        response = _download_source(
            spec,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
            attempts_per_service=attempts_per_service,
            retry_wait_seconds=retry_wait_seconds,
        )
        _atomic_bytes(source, response.content)
        # The durable checkpoint exists before moving to the next city.
        source_url = response.url

    asset = build_raw_source_asset(snapshot_root, source, url=source_url)
    manifest = write_source_manifest(
        snapshot_root,
        provider="dane",
        dataset=f"mgn-zona-urbana-{spec.dane_code}",
        version=SOURCE_VERSION,
        license_name=SOURCE_LICENSE,
        assets=[asset],
    )
    return source, manifest


def _reference_is_current(output: Path, metadata_path: Path, source_hash: str) -> bool:
    if not output.is_file() or not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return metadata.get("source_geometry_sha256") == source_hash
    except (OSError, json.JSONDecodeError):
        return False


def _build_reference(root: Path, spec: CitySpec, source: Path, manifest: Path) -> Path:
    target = _reference_root(root, spec)
    output = target / "spatial_units.geojson"
    metadata_path = target / "metadata.json"
    source_hash = _sha256(source)
    if _reference_is_current(output, metadata_path, source_hash):
        print(f"{spec.name}: normalized reference already current; skipping build")
        return output

    raw = gpd.read_file(source)
    missing = sorted(REQUIRED_FIELDS - set(raw.columns))
    if missing:
        raise ValueError(f"Cached DANE source for {spec.slug} is missing fields: {missing}")
    code = raw["mpio_cdpmp"].astype(str).str.strip()
    klass = raw["clas_ccdgo"].astype(str).str.strip()
    selected = raw.loc[(code == spec.dane_code) & (klass == "1")].copy()
    if len(selected) != 1:
        raise ValueError(f"Expected one normalized feature for {spec.slug}, found {len(selected)}")
    if selected.crs is None:
        selected = selected.set_crs("EPSG:4326")
    else:
        selected = selected.to_crs("EPSG:4326")
    if selected.geometry.isna().any() or selected.geometry.is_empty.any():
        raise ValueError(f"Null or empty DANE geometry for {spec.slug}")
    if not selected.geometry.is_valid.all():
        selected["geometry"] = selected.geometry.make_valid()
    if set(selected.geometry.geom_type) - {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Non-polygonal normalized DANE geometry for {spec.slug}")

    selected["unit_id"] = spec.dane_code
    selected["unit_name"] = spec.name
    selected["unit_type"] = "dane_cabecera_municipal"
    selected["unit_source"] = "DANE MGN 2024 Zona Urbana, cabecera municipal"
    selected["source_name"] = selected["zu_cnmbre"].astype(str).str.strip()
    selected["department"] = spec.department
    result = selected[
        [
            "unit_id",
            "unit_name",
            "unit_type",
            "unit_source",
            "department",
            "source_name",
            "mpio_cdpmp",
            "zu_ccdgo",
            "zu_cdivi",
            "zu_ccnct",
            "zu_narea",
            "zu_nano",
            "geometry",
        ]
    ].copy()
    result = gpd.GeoDataFrame(result, geometry="geometry", crs="EPSG:4326")

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=target, prefix=".spatial_units.", suffix=".geojson", delete=False
    ) as tmp:
        staged_output = Path(tmp.name)
    result.to_file(staged_output, driver="GeoJSON")
    os.replace(staged_output, output)

    bounds = [float(value) for value in result.total_bounds]
    snapshot = load_source_manifest(manifest.parent, verify=True)
    metadata = {
        "schema_version": 1,
        "study_id": spec.aggregate_study,
        "spatial_id": "unit_id (DANE mpio_cdpmp)",
        "source_geometry": source.relative_to(root).as_posix(),
        "source_geometry_sha256": source_hash,
        "source_manifest": manifest.relative_to(root).as_posix(),
        "source_url": snapshot.assets[0].url,
        "source_layer": "DANE MGN 2024 ArcGIS layer 305 Zona Urbana",
        "filter": f"mpio_cdpmp = '{spec.dane_code}' AND clas_ccdgo = '1'",
        "license": SOURCE_LICENSE,
        "unit_count": 1,
        "crs": "EPSG:4326",
        "total_bounds": bounds,
    }
    _atomic_text(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_text(
        target / "README.md",
        f"# {spec.name} — cabecera urbana DANE 2024\n\n"
        "`spatial_units.geojson` contiene una sola unidad: la cabecera municipal "
        f"DIVIPOLA `{spec.dane_code}` de {spec.name}. Proviene de la capa oficial "
        "`Zona Urbana` (ID 305) del Marco Geoestadístico Nacional 2024 del DANE, "
        "filtrada a `clas_ccdgo = '1'`. No representa todo el municipio rural ni "
        "afirma resolución por barrios. La atribución requerida es: Departamento "
        "Administrativo Nacional de Estadística - DANE: www.dane.gov.co.\n",
    )
    print(
        f"{spec.name}: wrote {output.relative_to(root)}; "
        f"bounds={bounds[0]:.5f},{bounds[1]:.5f},{bounds[2]:.5f},{bounds[3]:.5f}"
    )
    return output


def run(
    *,
    root: Path,
    city_slugs: list[str],
    connect_timeout_seconds: int,
    read_timeout_seconds: int,
    attempts_per_service: int,
    retry_wait_seconds: float,
) -> list[Path]:
    specs = [CITY_BY_SLUG[slug] for slug in city_slugs] if city_slugs else list(CITY_SPECS)
    outputs: list[Path] = []
    for spec in tqdm(specs, desc="DANE urban references", unit="city"):
        source, manifest = _checkpoint_source(
            root,
            spec,
            connect_timeout_seconds=connect_timeout_seconds,
            read_timeout_seconds=read_timeout_seconds,
            attempts_per_service=attempts_per_service,
            retry_wait_seconds=retry_wait_seconds,
        )
        outputs.append(_build_reference(root, spec, source, manifest))
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--city",
        action="append",
        choices=sorted(CITY_BY_SLUG),
        default=[],
        help="Build one city; repeat for several. Defaults to all three.",
    )
    parser.add_argument("--connect-timeout-seconds", type=int, default=15)
    parser.add_argument("--read-timeout-seconds", type=int, default=120)
    parser.add_argument("--attempts-per-service", type=int, default=2)
    parser.add_argument("--retry-wait-seconds", type=float, default=3)
    args = parser.parse_args()
    outputs = run(
        root=ROOT,
        city_slugs=args.city,
        connect_timeout_seconds=args.connect_timeout_seconds,
        read_timeout_seconds=args.read_timeout_seconds,
        attempts_per_service=args.attempts_per_service,
        retry_wait_seconds=args.retry_wait_seconds,
    )
    print("\nReady references:")
    for output in outputs:
        print(f"  - {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
