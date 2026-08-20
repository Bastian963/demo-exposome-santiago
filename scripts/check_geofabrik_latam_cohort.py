#!/usr/bin/env python3
"""Report and verify the frozen Geofabrik snapshots for the LATAM cohort.

This is intentionally an inventory/checker, not a downloader.  It prints
restartable human commands for absent snapshots; the operator performs the
network transfer and then freezes the PBF with the existing migration script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("config/operations/geofabrik_latam_cohort.yaml")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _fail(message: str) -> None:
    raise ValueError(message)


def load_inventory(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("schema_version") != 1:
        _fail(f"Unsupported Geofabrik inventory schema: {path}")
    if raw.get("provider") != "geofabrik" or raw.get("dataset") != "osm-regional-extract":
        _fail("Inventory must declare the canonical Geofabrik OSM dataset")
    version = raw.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d{6}", version):
        _fail("Inventory version must be a six-digit Geofabrik cutoff")
    layers = raw.get("supported_layers")
    expected_layers = {"greenspace_access", "food_environment", "healthcare", "social_infrastructure"}
    if not isinstance(layers, list) or set(layers) != expected_layers or len(layers) != len(expected_layers):
        _fail("supported_layers must be exactly the four tag-based local-extract layers")
    snapshots = raw.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        _fail("snapshots must be a non-empty list")
    ids: set[str] = set()
    urls: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            _fail("every snapshot must be a mapping")
        snapshot_id = snapshot.get("id")
        if not isinstance(snapshot_id, str) or not _SLUG.fullmatch(snapshot_id):
            _fail(f"invalid snapshot id: {snapshot_id!r}")
        if snapshot_id in ids:
            _fail(f"duplicate snapshot id: {snapshot_id}")
        ids.add(snapshot_id)
        for field in ("label", "source_path", "page_url", "pbf_url", "filename"):
            if not isinstance(snapshot.get(field), str) or not snapshot[field]:
                _fail(f"{snapshot_id}: missing {field}")
        if not snapshot["page_url"].endswith(".html") or not snapshot["pbf_url"].endswith(f"-{version}.osm.pbf"):
            _fail(f"{snapshot_id}: URL/version mismatch")
        if snapshot["pbf_url"] in urls:
            _fail(f"duplicate PBF URL: {snapshot['pbf_url']}")
        urls.add(snapshot["pbf_url"])
        if Path(snapshot["filename"]).name != snapshot["filename"] or not snapshot["filename"].endswith(".osm.pbf"):
            _fail(f"{snapshot_id}: filename must be a plain .osm.pbf name")
        countries = snapshot.get("countries")
        covers = snapshot.get("covers")
        if not isinstance(countries, list) or not countries or not all(isinstance(code, str) and _COUNTRY.fullmatch(code) for code in countries):
            _fail(f"{snapshot_id}: countries must be ISO-3166 alpha-2 codes")
        if not isinstance(covers, list) or not covers or not all(isinstance(city, str) and _SLUG.fullmatch(city) for city in covers):
            _fail(f"{snapshot_id}: covers must be non-empty city slugs")
    return raw


def snapshot_paths(root: Path, inventory: dict[str, Any], snapshot: dict[str, Any]) -> tuple[Path, Path]:
    base = root / "data" / "raw" / "geofabrik" / snapshot["id"] / inventory["version"]
    return base / snapshot["filename"], base / "source_manifest.json"


def read_manifest(path: Path, *, inventory: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid manifest ({exc})"
    if payload.get("schema_version") != 1 or payload.get("provider") != inventory["provider"]:
        return False, "wrong manifest schema/provider"
    if payload.get("dataset") != inventory["dataset"] or payload.get("version") != inventory["version"]:
        return False, "wrong manifest dataset/version"
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return False, "manifest assets missing"
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("path") == snapshot["filename"]]
    if len(matches) != 1:
        return False, "manifest does not describe the expected PBF"
    asset = matches[0]
    if asset.get("resource_id") != snapshot["id"] or asset.get("url") != snapshot["page_url"]:
        return False, "manifest source identity differs from inventory"
    if not isinstance(asset.get("bytes"), int) or asset["bytes"] <= 0 or not isinstance(asset.get("sha256"), str) or not _SHA256.fullmatch(asset["sha256"]):
        return False, "manifest asset hash/size invalid"
    return True, None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def status_for(root: Path, inventory: dict[str, Any], snapshot: dict[str, Any], *, verify_hash: bool) -> tuple[str, str]:
    pbf, manifest = snapshot_paths(root, inventory, snapshot)
    if not pbf.is_file() and not manifest.is_file():
        return "missing", "PBF and manifest absent"
    if pbf.is_file() and not manifest.is_file():
        return "unfrozen", "PBF exists; run ingest to create source_manifest.json"
    if not pbf.is_file():
        valid, detail = read_manifest(manifest, inventory=inventory, snapshot=snapshot)
        return ("payload_missing", "manifest is valid; copy the matching PBF locally" if valid else detail or "invalid manifest")
    valid, detail = read_manifest(manifest, inventory=inventory, snapshot=snapshot)
    if not valid:
        return "invalid", detail or "invalid manifest"
    if verify_hash:
        asset = next(asset for asset in json.loads(manifest.read_text(encoding="utf-8"))["assets"] if asset["path"] == snapshot["filename"])
        if pbf.stat().st_size != asset["bytes"]:
            return "invalid", f"size {pbf.stat().st_size} differs from manifest {asset['bytes']}"
        if sha256(pbf) != asset["sha256"]:
            return "invalid", "SHA-256 differs from manifest"
    return "ready", "payload and frozen manifest match" if verify_hash else "payload and frozen manifest present"


def print_commands(inventory: dict[str, Any], snapshot: dict[str, Any]) -> None:
    region = snapshot["id"]
    version = inventory["version"]
    pbf = f"data/raw/geofabrik/{region}/{version}/{snapshot['filename']}"
    print(f"\n# {snapshot['label']} ({', '.join(snapshot['covers'])})")
    print(f"mkdir -p data/raw/geofabrik/{region}/{version}")
    print(f"curl -fL -C - -o {pbf} {snapshot['pbf_url']}")
    print(f"sha256sum {pbf}")
    print("PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/migrations/ingest_geofabrik_extract.py \\")
    print(f"  --source {pbf} --region {region} --version {version} --source-path {snapshot['source_path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--require-payload", action="store_true", help="Fail when a snapshot PBF is absent locally.")
    parser.add_argument("--verify-hash", action="store_true", help="Recompute local SHA-256 values (implies --require-payload).")
    parser.add_argument("--commands", action="store_true", help="Print manual, resumable commands only for missing/unfrozen snapshots.")
    args = parser.parse_args()
    root = args.root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    inventory = load_inventory(config)
    if args.verify_hash:
        args.require_payload = True
    failures: list[str] = []
    for snapshot in inventory["snapshots"]:
        state, detail = status_for(root, inventory, snapshot, verify_hash=args.verify_hash)
        print(f"{snapshot['id']:<10} {state:<16} {detail}")
        if args.commands and state in {"missing", "unfrozen"}:
            print_commands(inventory, snapshot)
        if state == "invalid" or (args.require_payload and state != "ready"):
            failures.append(f"{snapshot['id']}: {state}")
    if failures:
        print(f"\nInventory check failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
