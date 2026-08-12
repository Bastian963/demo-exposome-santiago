"""Write a point extraction as a verifiable, self-describing bundle.

Consumers read artifacts through a manifest with SHA-256 digests, never by
picking up whatever CSV happens to be in a directory (ADR 0006).  A downloaded
extraction therefore ships four things: the long table, an optional wide pivot,
the methodology that explains what the numbers mean, and a manifest that pins
every input and output.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

from .point_extraction import (
    DEFAULT_DATA_ROOT,
    BundleStudy,
    available_indicators,
    coverage_summary,
    extract_points,
    load_bundle_catalog,
    study_for_point,
)
from .point_support import DEFAULT_RADII, describe_radius, has_support

#: Bump when the estimator changes in a way that alters published values.
METHOD_VERSION = "1.0.0"

LONG_CSV = "point_exposome_long.csv"
WIDE_CSV = "point_exposome_wide.csv"
MANIFEST = "extraction_manifest.json"
METHODOLOGY = "METHODOLOGY.md"

_METHODOLOGY_SOURCE = Path("docs/point_extraction_methodology.md")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def extraction_plan(
    points: pd.DataFrame,
    indicators: Sequence[str],
    radii: Sequence[float] = DEFAULT_RADII,
    data_root: Path | str = DEFAULT_DATA_ROOT,
) -> pd.DataFrame:
    """What each (study, indicator, radius) would deliver -- before any I/O.

    This is the preflight: it reads manifests, never pixels, so a user can see
    that a 500 m NO2 buffer will come back ``sub_observation`` without waiting
    for a batch to run.
    """
    studies = load_bundle_catalog(data_root)
    matched: dict[str, BundleStudy] = {}
    for point in points.itertuples(index=False):
        study = study_for_point(studies, float(point.lon), float(point.lat))
        if study is not None:
            matched.setdefault(study.study_id, study)

    rows: list[dict[str, Any]] = []
    for study in matched.values():
        availability = available_indicators(study)
        _, south, _, north = study.bbox
        latitude = (south + north) / 2
        for indicator_id in indicators:
            status = availability.get(indicator_id, "not_published_by_study")
            if not has_support(indicator_id):
                rows.append({
                    "study_id": study.study_id, "exposome_id": indicator_id,
                    "availability": "undeclared_support", "radius_m": None,
                    "radius_status": None, "support_m": None,
                })
                continue
            for radius in radii:
                described = describe_radius(indicator_id, radius, latitude)
                rows.append({
                    "study_id": study.study_id,
                    "exposome_id": indicator_id,
                    "availability": status,
                    "estimand_kind": described["estimand_kind"],
                    "radius_m": described["radius_m"],
                    "radius_status": described["radius_status"],
                    "support_m": described["support_m"],
                })
                if described["estimand_kind"] != "raster_block":
                    break  # a non-raster estimand has one row, not one per radius
    return pd.DataFrame(rows)


def to_wide(frame: pd.DataFrame, *, radius_m: float | None = None,
            year: int | str | None = None) -> pd.DataFrame:
    """One row per point, one column per exposome -- for merging with a cohort.

    The long table is the honest shape because a value only means something
    alongside its radius and year.  Analysts still want a wide merge key, so the
    pivot is offered for **one** explicit (radius, year) slice rather than
    silently collapsing them.
    """
    subset = frame
    if radius_m is not None and "radius_m" in subset:
        subset = subset[(subset["radius_m"] == radius_m) | subset["radius_m"].isna()]
    if year is not None and "year" in subset:
        subset = subset[(subset["year"] == year) | subset["year"].isna()]
    if subset.empty:
        return pd.DataFrame()
    keys = [column for column in ("query_id", "lon", "lat", "study_id") if column in subset]
    wide = subset.pivot_table(
        index=keys, columns="exposome_id", values="value", aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    return wide


def _checkpoint_path(cache_dir: Path, query_id: Any, signature: str) -> Path:
    token = _sha256_bytes(f"{query_id}|{signature}".encode())[:16]
    return cache_dir / f"{token}.json"


def run_extraction(
    points: pd.DataFrame,
    indicators: Sequence[str],
    output_dir: Path,
    *,
    radii: Sequence[float] = DEFAULT_RADII,
    years: Sequence[int | str] | None = None,
    data_root: Path | str = DEFAULT_DATA_ROOT,
    cache_dir: Path | None = None,
    resume: bool = True,
    wide_radius: float | None = None,
    progress: Callable[[Iterable], Iterable] | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Extract every point, checkpointing each one, then write the bundle.

    Checkpointing is per point because that is the unit a user re-runs: a batch
    interrupted at address 380 of 500 resumes without re-reading 380 rasters.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    signature = _sha256_bytes(
        json.dumps({
            "indicators": list(indicators),
            "radii": [float(radius) for radius in radii],
            "years": [str(year) for year in (years or [])],
            "method": METHOD_VERSION,
        }, sort_keys=True).encode()
    )[:16]
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

    iterator: Iterable = list(points.itertuples(index=False))
    if progress is not None:
        iterator = progress(iterator)

    frames: list[pd.DataFrame] = []
    reused = 0
    for point in iterator:
        query_id = getattr(point, "query_id", None)
        checkpoint = (
            _checkpoint_path(cache_dir, query_id, signature) if cache_dir else None
        )
        if resume and checkpoint is not None and checkpoint.exists():
            frames.append(pd.DataFrame(json.loads(checkpoint.read_text())))
            reused += 1
            continue
        single = pd.DataFrame([point._asdict()])
        result = extract_points(
            single, indicators, radii=radii, years=years, data_root=data_root
        )
        if checkpoint is not None:
            checkpoint.write_text(result.to_json(orient="records"))
        frames.append(result)

    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    long_path = output_dir / LONG_CSV
    frame.to_csv(long_path, index=False)
    outputs = [long_path]

    if wide_radius is not None:
        wide = to_wide(frame, radius_m=wide_radius)
        if not wide.empty:
            wide_path = output_dir / WIDE_CSV
            wide.to_csv(wide_path, index=False)
            outputs.append(wide_path)

    methodology = _copy_methodology(output_dir, repo_root)
    if methodology is not None:
        outputs.append(methodology)

    manifest_path = write_extraction_manifest(
        output_dir,
        frame=frame,
        outputs=outputs,
        indicators=indicators,
        radii=radii,
        years=years,
        data_root=data_root,
    )
    return {
        "frame": frame,
        "long_csv": long_path,
        "manifest": manifest_path,
        "reused_checkpoints": reused,
        "summary": coverage_summary(frame),
    }


def _copy_methodology(output_dir: Path, repo_root: Path | None) -> Path | None:
    """Ship the methodology with the data so the numbers travel explained."""
    root = repo_root or Path(__file__).resolve().parents[2]
    source = root / _METHODOLOGY_SOURCE
    if not source.exists():
        return None
    destination = output_dir / METHODOLOGY
    destination.write_text(source.read_text())
    return destination


def _bundle_provenance(frame: pd.DataFrame, data_root: Path) -> list[dict[str, Any]]:
    """Pin the published bundle each value came from."""
    if frame.empty or "study_id" not in frame:
        return []
    studies = {study.study_id: study for study in load_bundle_catalog(data_root)}
    provenance = []
    for study_id in sorted(frame["study_id"].dropna().unique()):
        study = studies.get(study_id)
        if study is None:
            continue
        release = study.root / "release_manifest.json"
        provenance.append({
            "study_id": study_id,
            "bundle": study.bundle,
            "release_manifest_sha256": (
                sha256_file(release) if release.exists() else None
            ),
        })
    return provenance


def write_extraction_manifest(
    output_dir: Path,
    *,
    frame: pd.DataFrame,
    outputs: Sequence[Path],
    indicators: Sequence[str],
    radii: Sequence[float],
    years: Sequence[int | str] | None,
    data_root: Path | str,
) -> Path:
    """Record method, inputs, outputs and digests so a result is reproducible."""
    data_root = Path(data_root)
    payload = {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "estimand": (
            "Promedio del indicador sobre B(x, r): la celda contenedora cuando "
            "r = 0, o el disco de radio r. Sin interpolar."
        ),
        "request": {
            "indicators": list(indicators),
            "radii_m": [float(radius) for radius in radii],
            "years": [str(year) for year in (years or [])] or None,
        },
        "source": {
            "kind": "published_bundle",
            "data_root": str(data_root),
            "studies": _bundle_provenance(frame, data_root),
        },
        "coverage": coverage_summary(frame),
        "outputs": [
            {
                "path": Path(path).name,
                "bytes": Path(path).stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in outputs
            if Path(path).exists()
        ],
        "documentation": METHODOLOGY,
    }
    manifest_path = Path(output_dir) / MANIFEST
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return manifest_path
