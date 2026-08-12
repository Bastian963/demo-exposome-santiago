#!/usr/bin/env python3
"""Rebind annual-v2 checkpoints after a verified implementation-only repair.

This migration is deliberately narrow. It refuses to proceed if configuration,
protocol, inputs, manifests, geometry, outcomes, or the runner changed. Existing
Bayesian trace hashes are verified before any checkpoint metadata is rewritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.hospitalization_annual_v2 import (  # noqa: E402
    analysis_fingerprint,
    load_analysis_config,
    resolve_repo_path,
)
from exposome.inference_run_state import atomic_write_json  # noqa: E402


DEFAULT_CONFIG = Path("config/analyses/hospitalization_annual_v2.yaml")
ALLOWED_CHANGED_INPUTS = frozenset({"implementation"})


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def _load_checkpoint_jsons(
    output: Path, old_fingerprint: str
) -> list[tuple[Path, dict[str, object]]]:
    records: list[tuple[Path, dict[str, object]]] = []
    for path in sorted(output.rglob("*.json")):
        if path.name == "prepared_state.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "scientific_fingerprint" not in payload:
            continue
        if payload["scientific_fingerprint"] != old_fingerprint:
            raise ValueError(f"Checkpoint belongs to another fingerprint: {path}")
        records.append((path, payload))
    return records


def _validate_bayesian_traces(
    output: Path, records: list[tuple[Path, dict[str, object]]]
) -> int:
    count = 0
    bayesian_root = output / "bayesian"
    models_root = bayesian_root / "run_state" / "models"
    for path, payload in records:
        if path.parent != models_root:
            continue
        trace = payload.get("trace")
        if not isinstance(trace, dict):
            raise ValueError(f"Bayesian sidecar lacks trace metadata: {path}")
        relative = trace.get("path")
        expected_hash = trace.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ValueError(f"Bayesian sidecar has invalid trace metadata: {path}")
        trace_path = bayesian_root / relative
        if not trace_path.is_file():
            raise FileNotFoundError(f"Missing Bayesian trace: {trace_path}")
        if _sha256(trace_path) != expected_hash:
            raise ValueError(f"Bayesian trace hash mismatch: {trace_path}")
        count += 1
    return count


def _matching_csvs(output: Path, old_fingerprint: str) -> list[tuple[Path, str]]:
    matches: list[tuple[Path, str]] = []
    for path in sorted(output.rglob("*.csv")):
        text = path.read_text(encoding="utf-8")
        if old_fingerprint in text:
            matches.append((path, text))
    return matches


def main() -> int:
    args = _parse_args()
    config_path = resolve_repo_path(REPO_ROOT, args.config)
    config = load_analysis_config(config_path)
    output = (
        resolve_repo_path(REPO_ROOT, args.output_dir)
        if args.output_dir is not None
        else resolve_repo_path(REPO_ROOT, config["paths"]["output_dir"])
    )
    state_path = output / "prepared_state.json"
    provenance_path = output / "annual_artifact_provenance.csv"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    provenance = pd.read_csv(provenance_path)
    old_fingerprint = str(state["scientific_fingerprint"])
    old_inputs = dict(state["input_hashes"])
    new_fingerprint, new_inputs = analysis_fingerprint(
        REPO_ROOT, config_path, config, provenance
    )
    changed_inputs = sorted(
        key
        for key in set(old_inputs) | set(new_inputs)
        if old_inputs.get(key) != new_inputs.get(key)
    )
    if not changed_inputs:
        print(json.dumps({"status": "already_current", "fingerprint": old_fingerprint}))
        return 0
    unexpected = sorted(set(changed_inputs) - ALLOWED_CHANGED_INPUTS)
    if unexpected:
        raise ValueError(
            "Runtime rebind refused; non-runtime inputs changed: "
            + ", ".join(unexpected)
        )
    records = _load_checkpoint_jsons(output, old_fingerprint)
    trace_count = _validate_bayesian_traces(output, records)
    csvs = _matching_csvs(output, old_fingerprint)
    report = {
        "status": "ready" if not args.write else "written",
        "output": str(output),
        "old_fingerprint": old_fingerprint,
        "new_fingerprint": new_fingerprint,
        "changed_inputs": changed_inputs,
        "checkpoint_jsons": len(records),
        "checkpoint_csvs": len(csvs),
        "validated_bayesian_traces": trace_count,
    }
    if not args.write:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = (
        output
        / "runtime_rebind_backups"
        / f"annual_v2_runtime_rebind_{timestamp}_{old_fingerprint[:12]}.zip"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    changed_paths = [state_path, *(path for path, _ in records), *(path for path, _ in csvs)]
    with zipfile.ZipFile(backup, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in changed_paths:
            archive.write(path, path.relative_to(output))

    for path, payload in records:
        payload["scientific_fingerprint"] = new_fingerprint
        atomic_write_json(path, payload)
    for path, text in csvs:
        _atomic_text(path, text.replace(old_fingerprint, new_fingerprint))
    history = list(state.get("runtime_rebind_history", []))
    history.append(
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "old_fingerprint": old_fingerprint,
            "new_fingerprint": new_fingerprint,
            "changed_inputs": changed_inputs,
            "backup": str(backup.relative_to(output)),
        }
    )
    state["scientific_fingerprint"] = new_fingerprint
    state["input_hashes"] = new_inputs
    state["runtime_rebind_history"] = history
    atomic_write_json(state_path, state)
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
