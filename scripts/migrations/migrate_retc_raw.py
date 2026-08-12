"""Copy verified RETC provider payloads from legacy caches into data/raw.

Dry-run is the default. Pass ``--write`` only after reviewing the inventory.
This migration never downloads, moves, or deletes a source file.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import re
import shutil
import sys
from typing import Iterable
from uuid import uuid4

import typer


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from exposome.heavy_metals import RETC_URLS  # noqa: E402
from exposome.raw_sources import build_raw_source_asset, write_source_manifest  # noqa: E402


DEFAULT_VERSION = "ckan-2026-06"
DEFAULT_DESTINATION = ROOT / "data" / "raw" / "mma" / "retc-air-point-sources" / DEFAULT_VERSION
DEFAULT_SOURCES = (
    ROOT / "cache",
    ROOT
    / "cache"
    / "cl"
    / "santiago"
    / "santiago_communes"
    / "temporal_exposomes"
    / "heavy_metals",
)
_RESOURCE_ID = re.compile(r"/resource/([^/]+)/")


def inventory_retc(
    source_dirs: Iterable[Path],
    years: Iterable[int],
) -> dict[int, Path]:
    """Choose one source per year and reject byte disagreements."""
    selected: dict[int, Path] = {}
    for year in sorted(set(years)):
        candidates = sorted(
            path
            for root in map(Path, source_dirs)
            for path in (root / f"retc_efp_{year}.csv", root / f"retc_efp_{year}.xlsx")
            if path.is_file()
        )
        if not candidates:
            raise FileNotFoundError(f"No cached RETC source found for {year}")
        hashes = {_sha256_file(path) for path in candidates}
        if len(hashes) != 1:
            detail = ", ".join(f"{path}={_sha256_file(path)}" for path in candidates)
            raise ValueError(f"RETC {year} cache copies disagree: {detail}")
        selected[year] = candidates[0]
    return selected


def migrate_retc(
    selected: dict[int, Path],
    destination: Path,
    *,
    version: str,
    write: bool,
) -> list[str]:
    """Copy and verify selected files, then publish one immutable manifest."""
    messages: list[str] = []
    assets = []
    if write:
        destination.mkdir(parents=True, exist_ok=True)
    for year, source in sorted(selected.items()):
        target = destination / source.name
        source_hash = _sha256_file(source)
        if target.exists():
            target_hash = _sha256_file(target)
            if target_hash != source_hash:
                raise ValueError(
                    f"Destination conflict for {year}: {target}. "
                    "Choose a new provider snapshot version."
                )
            action = "KEEP"
        elif write:
            staged = target.with_name(f".{target.name}.{uuid4().hex}.partial")
            shutil.copyfile(source, staged)
            if _sha256_file(staged) != source_hash:
                staged.unlink(missing_ok=True)
                raise ValueError(f"Copy checksum mismatch for RETC {year}")
            os.replace(staged, target)
            action = "COPY"
        else:
            action = "WOULD COPY"
        messages.append(f"{action} {year}: {source} -> {target} [{source_hash}]")
        if write:
            url = RETC_URLS[year]
            match = _RESOURCE_ID.search(url)
            assets.append(
                build_raw_source_asset(
                    destination,
                    target,
                    url=url,
                    year=year,
                    resource_id=match.group(1) if match else None,
                )
            )
    if write:
        manifest = write_source_manifest(
            destination,
            provider="mma",
            dataset="retc-air-point-sources",
            version=version,
            license_name="CC-BY",
            assets=assets,
        )
        messages.append(f"WRITE manifest: {manifest}")
    else:
        messages.append(f"WOULD WRITE manifest: {destination / 'source_manifest.json'}")
    return messages


def main(
    years: str = typer.Option("2015-2022", help="Inclusive range, e.g. 2015-2022"),
    source_dir: list[Path] | None = typer.Option(
        None,
        "--source-dir",
        help="Repeat to replace the default legacy cache roots",
    ),
    destination: Path = typer.Option(DEFAULT_DESTINATION),
    version: str = typer.Option(DEFAULT_VERSION),
    write: bool = typer.Option(False, "--write", help="Perform verified copies"),
) -> None:
    requested_years = _parse_years(years)
    selected = inventory_retc(source_dir or list(DEFAULT_SOURCES), requested_years)
    for message in migrate_retc(selected, destination, version=version, write=write):
        typer.echo(message)
    if not write:
        typer.echo("Dry-run only; pass --write after reviewing this inventory.")


def _parse_years(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"(\d{4})-(\d{4})", value.strip())
    if not match:
        raise typer.BadParameter("years must be an inclusive YYYY-YYYY range")
    first, last = map(int, match.groups())
    if first > last:
        raise typer.BadParameter("years start must be <= end")
    unknown = sorted(set(range(first, last + 1)) - set(RETC_URLS))
    if unknown:
        raise typer.BadParameter(f"No configured RETC URLs for years: {unknown}")
    return tuple(range(first, last + 1))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    typer.run(main)
