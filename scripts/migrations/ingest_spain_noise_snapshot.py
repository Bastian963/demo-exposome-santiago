"""Validate and freeze Spanish SICA MER phase-4 ZIP files as a raw snapshot.

The input directory is a human-provided local download.  This command never
downloads from SICA: large provider transfers remain a human operation.  It
does validate every byte before copying into the immutable ``data/raw`` store.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import typer
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "src"))

from exposome.noise_spain import LDEN_LAYER  # noqa: E402
from exposome.raw_sources import build_raw_source_asset, write_source_manifest  # noqa: E402


APP = typer.Typer(help="Freeze validated SICA strategic-noise ZIPs as a raw snapshot.")
RAW_ROOT = ROOT / "data/raw/miteco/sica-mer-agglomerations/4f-2022"
SOURCE_PAGE = "https://sicaweb.cedex.es/datos-geoespaciales/4a-fase/"
EXPECTED_COUNTS = {"cataluna": 12, "pais_vasco": 4}
PILOT_VERSION_SUFFIX = "-barcelones-pilot"


def _ascii_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")


def _region_for_directory(path: Path) -> str | None:
    token = _ascii_token(path.name)
    if token == "cataluna":
        return "cataluna"
    if token in {"pais_vasco", "paisvasco"}:
        return "pais_vasco"
    return None


def discover_archives(
    source_root: Path,
    *,
    require_expected_counts: bool = True,
) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for directory in sorted(source_root.iterdir()):
        if not directory.is_dir():
            continue
        region = _region_for_directory(directory)
        if region is None:
            continue
        for archive in sorted(directory.glob("*.zip")):
            if not archive.name.startswith("._"):
                found.append((region, archive))
    counts = {region: sum(item[0] == region for item in found) for region in EXPECTED_COUNTS}
    if require_expected_counts and counts != EXPECTED_COUNTS:
        raise ValueError(f"Expected SICA ZIP counts {EXPECTED_COUNTS}, found {counts}")
    return found


def validate_archive(path: Path, *, deep: bool = True) -> str:
    """Return the GPKG member after CRC and schema validation."""
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"CRC failure in {path.name}: {bad_member}")
            names = [name for name in archive.namelist() if not Path(name).name.startswith("._")]
            gpkg = [name for name in names if name.lower().endswith(".gpkg")]
            xml = [name for name in names if name.lower().endswith(".xml")]
            if len(gpkg) != 1 or not xml:
                raise ValueError(
                    f"{path.name} must contain one GPKG and XML metadata; "
                    f"got gpkg={gpkg}, xml={xml}"
                )
            member = gpkg[0]
            if not deep:
                return member
            with tempfile.TemporaryDirectory(prefix="gemma-sica-noise-") as tmp:
                gpkg_path = Path(tmp) / "source.gpkg"
                with archive.open(member) as source, gpkg_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                with sqlite3.connect(gpkg_path) as connection:
                    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    if integrity != "ok":
                        raise ValueError(f"GeoPackage integrity failure in {path.name}: {integrity}")
                    layers = {
                        row[0]
                        for row in connection.execute(
                            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
                        )
                    }
                    required = "NoiseContours_allSourcesInAgglomeration_Lden"
                    if required not in layers:
                        raise ValueError(f"{path.name} lacks required layer {required}")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError(f"Invalid ZIP {path}: {exc}") from exc
    return member


def _destination_name(path: Path) -> str:
    return f"{_ascii_token(path.stem)}.zip"


def _copy_archive_immutably(source: Path, target: Path) -> None:
    """Atomically copy a validated archive, refusing any divergent prior copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source_asset = build_raw_source_asset(source.parent, source, url=SOURCE_PAGE)
        target_asset = build_raw_source_asset(target.parent, target, url=SOURCE_PAGE)
        if (
            target_asset.bytes != source_asset.bytes
            or target_asset.sha256 != source_asset.sha256
        ):
            raise ValueError(
                f"Existing snapshot asset differs: {target}. Choose a new snapshot version."
            )
        return
    with tempfile.NamedTemporaryFile(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".partial",
        delete=False,
    ) as staged_handle:
        staged = Path(staged_handle.name)
    try:
        shutil.copy2(source, staged)
        staged.replace(target)
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def _validate_archives(
    archives: Iterable[tuple[str, Path]],
    *,
    deep: bool,
    allow_failures: bool,
) -> list[tuple[str, Path, str]]:
    verified: list[tuple[str, Path, str]] = []
    failures: list[str] = []
    for region, archive in tqdm(list(archives), desc="Validando ZIP MER", unit="archivo"):
        try:
            member = validate_archive(archive, deep=deep)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        verified.append((region, archive, member))
    if failures and not allow_failures:
        raise ValueError("SICA snapshot validation failed:\n- " + "\n- ".join(failures))
    return verified


def _freeze_verified_archives(
    verified: list[tuple[str, Path, str]],
    *,
    destination: Path,
    payload_root: Path,
    version: str,
) -> list[Path]:
    if not verified:
        raise ValueError("SICA snapshot needs at least one validated archive")
    copied: list[Path] = []
    for region, source, _ in tqdm(verified, desc="Copiando snapshot SICA", unit="archivo"):
        target = payload_root / region / _destination_name(source)
        _copy_archive_immutably(source, target)
        copied.append(target)
    assets = [
        build_raw_source_asset(
            payload_root,
            target,
            url=SOURCE_PAGE,
            resource_id=source.stem,
        )
        for (_, source, _), target in zip(verified, copied, strict=True)
    ]
    write_source_manifest(
        destination,
        provider="miteco",
        dataset="sica-mer-agglomerations",
        version=version,
        license_name="SICA XML metadata: no access limitations; no conditions apply",
        assets=assets,
        payload_root=payload_root,
    )
    return copied


def _archive_intersects_target(path: Path, member: str, target: object) -> bool:
    with tempfile.TemporaryDirectory(prefix="gemma-sica-pilot-") as tmp:
        gpkg_path = Path(tmp) / "source.gpkg"
        with zipfile.ZipFile(path) as archive:
            with archive.open(member) as source, gpkg_path.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        contours = gpd.read_file(gpkg_path, layer=LDEN_LAYER).to_crs("EPSG:3035")
    return bool(contours.geometry.intersects(target).any())


def freeze_barcelones_pilot_snapshot(
    source_root: Path,
    *,
    spatial_units: Path,
    spatial_id: str,
    destination: Path,
    payload_root: Path | None = None,
    verify_only: bool = False,
    deep: bool = True,
) -> list[Path]:
    """Freeze the validated SICA archives that spatially cover Barcelonès.

    Damaged archives are deliberately skipped only for this explicitly partial
    pilot. The full Cataluña snapshot continues to reject every failed archive.
    """
    units = gpd.read_file(spatial_units)
    target_rows = units.loc[units["unit_id"].astype(str) == str(spatial_id)]
    if len(target_rows) != 1:
        raise ValueError(f"Expected exactly one unit_id={spatial_id!r} in {spatial_units}")
    target = target_rows.to_crs("EPSG:3035").geometry.iloc[0]
    archives = [
        item
        for item in discover_archives(source_root)
        if item[0] == "cataluna"
    ]
    verified = _validate_archives(archives, deep=deep, allow_failures=True)
    selected = [
        item
        for item in tqdm(verified, desc="Seleccionando cobertura Barcelonès", unit="archivo")
        if _archive_intersects_target(item[1], item[2], target)
    ]
    if verify_only:
        return [path for _, path, _ in selected]
    payload_root = destination if payload_root is None else payload_root
    return _freeze_verified_archives(
        selected,
        destination=destination,
        payload_root=payload_root,
        version=f"4f-2022{PILOT_VERSION_SUFFIX}",
    )


def freeze_snapshot(
    source_root: Path,
    *,
    destination: Path = RAW_ROOT,
    payload_root: Path | None = None,
    verify_only: bool = False,
    deep: bool = True,
    version: str = "4f-2022",
) -> list[Path]:
    archives = discover_archives(source_root)
    verified = _validate_archives(archives, deep=deep, allow_failures=False)

    if verify_only:
        return [path for _, path, _ in verified]
    payload_root = destination if payload_root is None else payload_root
    copied = _freeze_verified_archives(
        verified,
        destination=destination,
        payload_root=payload_root,
        version=version,
    )
    readme = destination / "README.md"
    if not readme.exists():
        readme.write_text(
            "# SICA/MITECO — Mapas Estratégicos de Ruido\n\n"
            "Snapshot local de los GeoPackage de aglomeraciones, cuarta fase (2022). "
            f"Fuente: {SOURCE_PAGE}\n\n"
            "Los ZIP se validan con CRC y `PRAGMA integrity_check` antes de crear "
            "`source_manifest.json`. Los archivos binarios están ignorados por Git; "
            "el manifest es la referencia reproducible.\n",
            encoding="utf-8",
        )
    return copied


@APP.command()
def run(
    source_root: Path = typer.Option(..., exists=True, file_okay=False, readable=True),
    destination: Path = typer.Option(RAW_ROOT),
    payload_root: Path | None = typer.Option(
        None,
        help="Snapshot payload directory; defaults to destination. Use the external volume here.",
    ),
    verify_only: bool = typer.Option(False),
    skip_sqlite_check: bool = typer.Option(False, help="Skip expensive extracted-GPKG integrity checks."),
    barcelones_spatial_units: Path | None = typer.Option(
        None,
        help="Enable the explicit partial Barcelonès pilot using this spatial-units GeoJSON.",
    ),
    barcelones_spatial_id: str = typer.Option("cat_13"),
) -> None:
    """Validate the 16 source ZIPs and optionally freeze an immutable snapshot."""
    if barcelones_spatial_units is not None:
        paths = freeze_barcelones_pilot_snapshot(
            source_root,
            spatial_units=barcelones_spatial_units,
            spatial_id=barcelones_spatial_id,
            destination=destination,
            payload_root=payload_root,
            verify_only=verify_only,
            deep=not skip_sqlite_check,
        )
    else:
        paths = freeze_snapshot(
            source_root,
            destination=destination,
            payload_root=payload_root,
            verify_only=verify_only,
            deep=not skip_sqlite_check,
        )
    verb = "Validated" if verify_only else "Frozen"
    typer.echo(f"{verb} {len(paths)} SICA MER archives")


if __name__ == "__main__":
    APP()
