#!/usr/bin/env python3
"""Freeze a manually downloaded Geofabrik `.osm.pbf` as a raw snapshot.

This command deliberately does NOT download anything. Geofabrik extracts are
fetched by hand from the region page (see data/raw/geofabrik/README.md); this
script validates what a human already downloaded and freezes it with an
immutable SHA-256 manifest, the same contract as
``ingest_spain_noise_snapshot.py`` for the SICA noise GeoPackages.

Validation before freezing is the point: a truncated `.pbf` does not raise when
opened, it silently yields fewer features. So the file is opened and required
to expose GDAL's five OSM layers plus the promoted attributes that the tag
filtering in ``osm_fetch.fetch_features_from_local_extract`` relies on. The
"free" shapefile/GeoPackage variants fail this check by construction, which is
intended -- they collapse original tags into Geofabrik's own ``fclass``.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unicodedata

import typer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from exposome.raw_sources import build_raw_source_asset, write_source_manifest  # noqa: E402

APP = typer.Typer(help="Validate and freeze a Geofabrik OSM extract.")

RAW_ROOT = ROOT / "data/raw/geofabrik"
# The continent/country path a region lives under on download.geofabrik.de. The
# provenance URL written into source_manifest.json is the only record of where a
# payload came from, so it has to be the real page: hardcoding `europe/spain`
# made every non-Spanish extract claim a Spanish origin.
SOURCE_PAGE_TEMPLATE = "https://download.geofabrik.de/{path}/{region}.html"
DEFAULT_SOURCE_PATH = "europe/spain"

# GDAL's OSM driver always exposes these five layers. A file that lacks any of
# them is not a `.osm.pbf` we can filter against.
REQUIRED_LAYERS = ("points", "lines", "multilinestrings", "multipolygons", "other_relations")

# Promoted attributes the four tag-based layers query directly on
# `multipolygons`. `other_tags` carries everything else and must be present
# too, because POI keys (shop/amenity/healthcare) live there on `points`.
REQUIRED_MULTIPOLYGON_FIELDS = (
    "osm_id", "osm_way_id", "name", "leisure", "landuse", "natural",
    "amenity", "shop", "tourism", "other_tags",
)


def _ascii_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")


def validate_extract(path: Path) -> dict[str, int]:
    """Open the extract and assert it can answer the queries the layers make."""
    import pyogrio

    if not path.is_file():
        raise ValueError(f"Extract not found: {path}")
    if path.suffix != ".pbf":
        raise ValueError(f"Expected a .osm.pbf file, got {path.name}")
    if path.stat().st_size == 0:
        # iCloud eviction leaves a zero-byte stub that still stats as a file.
        raise ValueError(f"{path.name} is empty -- truncated or evicted by a sync client")

    try:
        layers = {name for name, _ in pyogrio.list_layers(path)}
    except Exception as exc:  # pragma: no cover - driver/IO specific
        raise ValueError(f"{path.name} is not readable as an OSM extract: {exc}") from exc

    missing = [name for name in REQUIRED_LAYERS if name not in layers]
    if missing:
        raise ValueError(
            f"{path.name} lacks OSM layer(s) {missing}. The '-free' shapefile and "
            "GeoPackage variants fail here by design: they collapse original tags "
            "into an fclass classification the pipeline cannot filter on."
        )

    info = pyogrio.read_info(path, layer="multipolygons")
    fields = set(info["fields"])
    missing_fields = [name for name in REQUIRED_MULTIPOLYGON_FIELDS if name not in fields]
    if missing_fields:
        raise ValueError(f"{path.name} multipolygons layer lacks field(s) {missing_fields}")

    return {"layers": len(layers), "multipolygon_fields": len(fields)}


def _copy_immutably(source: Path, target: Path, *, url: str) -> None:
    """Atomically copy the extract, refusing any divergent prior copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source_asset = build_raw_source_asset(source.parent, source, url=url)
        target_asset = build_raw_source_asset(target.parent, target, url=url)
        if (
            target_asset.bytes != source_asset.bytes
            or target_asset.sha256 != source_asset.sha256
        ):
            raise ValueError(
                f"Existing snapshot asset differs: {target}. Choose a new --version."
            )
        return
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", suffix=".partial", delete=False
    ) as handle:
        staged = Path(handle.name)
    try:
        shutil.copy2(source, staged)
        staged.replace(target)
    except Exception:
        staged.unlink(missing_ok=True)
        raise


@APP.command()
def run(
    source: Path = typer.Option(..., exists=True, dir_okay=False, readable=True),
    region: str = typer.Option(..., help="Geofabrik region id, e.g. cataluna or pais-vasco."),
    version: str = typer.Option(..., help="Cut date from the file name, e.g. 260809."),
    source_path: str = typer.Option(
        DEFAULT_SOURCE_PATH,
        help=(
            "Geofabrik continent/country path the region page lives under, e.g. "
            "europe/spain or south-america. Recorded as the payload's provenance URL."
        ),
    ),
    destination: Path = typer.Option(RAW_ROOT),
    payload_root: Path | None = typer.Option(
        None, help="Where the .pbf lives; defaults to destination. Keep it off Dropbox/iCloud."
    ),
    verify_only: bool = typer.Option(False, help="Validate without writing anything."),
) -> None:
    """Validate a downloaded Geofabrik extract and freeze it with a manifest."""
    token = _ascii_token(region)
    try:
        stats = validate_extract(source)
    except ValueError as exc:
        typer.echo(f"Extract rejected: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        f"Validated {source.name}: {stats['layers']} OSM layers, "
        f"{stats['multipolygon_fields']} multipolygon fields, "
        f"{source.stat().st_size:,} bytes"
    )
    if verify_only:
        return

    url = SOURCE_PAGE_TEMPLATE.format(path=source_path.strip("/"), region=region)
    snapshot = Path(destination) / token / version
    payload_dir = snapshot if payload_root is None else Path(payload_root) / token / version
    target = payload_dir / f"{token}.osm.pbf"

    _copy_immutably(source, target, url=url)
    asset = build_raw_source_asset(payload_dir, target, url=url, resource_id=region)
    write_source_manifest(
        snapshot,
        provider="geofabrik",
        dataset="osm-regional-extract",
        version=version,
        license_name="ODbL 1.0 (OpenStreetMap contributors)",
        assets=[asset],
        payload_root=payload_dir,
    )
    typer.echo(f"Frozen {target}")
    typer.echo(f"Manifest {snapshot / 'source_manifest.json'}")
    # layer_overrides, NOT layer_inputs: these four layers run through the
    # legacy runner path that takes --city, so they only ever see the resolved
    # cfg. A key placed under layer_inputs would be silently ignored.
    declared = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    typer.echo(
        "\nDeclare it in the study with:\n"
        "  layer_overrides:\n"
        "    greenspace:\n"
        "      access:\n"
        f"        osm_extract: {declared}\n"
        "    food_environment:\n"
        f"      osm_extract: {declared}\n"
        "    healthcare:\n"
        f"      osm_extract: {declared}\n"
        "    social_infrastructure:\n"
        f"      osm_extract: {declared}"
    )


if __name__ == "__main__":
    APP()
