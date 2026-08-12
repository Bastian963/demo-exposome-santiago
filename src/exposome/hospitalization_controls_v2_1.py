"""Registered Bayesian negative-control extension for annual hospitalization v2."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from exposome.hospitalization_annual_v2 import (
    canonical_hash,
    load_analysis_config,
    resolve_repo_path,
    sha256_file,
    task_slug,
)
from exposome.inference_run_state import ModelTask


EXPECTED_EXPOSURES = (
    "pm25",
    "alan",
    "heat",
    "green",
    "precipitation",
    "wind",
    "wildfire",
    "heavy_metals",
)
EXPECTED_TIMINGS = ("same_year", "lag1")


def load_extension_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Extension config must be a mapping: {path}")
    control = config.get("negative_control", {})
    if tuple(control.get("exposures", ())) != EXPECTED_EXPOSURES:
        raise ValueError("The v2.1 exposure registry must contain the eight primaries")
    if tuple(control.get("timings", ())) != EXPECTED_TIMINGS:
        raise ValueError("The v2.1 timing registry must be same_year and lag1")
    if control.get("outcome") != "injury_poisoning":
        raise ValueError("The v2.1 negative-control outcome must be injury_poisoning")
    if config.get("protocol_version") != "2.1-control-extension":
        raise ValueError("Unexpected v2.1 protocol version")
    return config


def extension_tasks(config: Mapping[str, Any]) -> list[ModelTask]:
    control = config["negative_control"]
    tasks = [
        ModelTask(
            phase="annual-v2.1-negative-control",
            model_id=task_slug(
                {
                    "window": control["window"],
                    "timing": timing,
                    "outcome": control["outcome"],
                    "exposure": exposure,
                }
            ),
            outcome=str(control["outcome"]),
            exposure=str(exposure),
            model_name="nb_bym2_panel_negative_control",
            variant=f"{control['window']}__{timing}",
        )
        for timing in control["timings"]
        for exposure in control["exposures"]
    ]
    if len(tasks) != 16 or len({task.model_id for task in tasks}) != 16:
        raise AssertionError("The v2.1 registry must contain exactly 16 unique models")
    return tasks


def extension_fingerprint(
    repo_root: Path,
    config_path: Path,
    config: Mapping[str, Any],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    baseline_dir = resolve_repo_path(repo_root, config["baseline"]["output_dir"])
    baseline_state_path = baseline_dir / "prepared_state.json"
    acceptance_path = baseline_dir / "publication_acceptance.json"
    if not baseline_state_path.is_file() or not acceptance_path.is_file():
        raise FileNotFoundError("The frozen annual-v2.0 baseline is not finalized")
    baseline_state = json.loads(baseline_state_path.read_text(encoding="utf-8"))
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    expected = str(config["baseline"]["expected_fingerprint"])
    if baseline_state.get("scientific_fingerprint") != expected:
        raise ValueError("Prepared annual-v2.0 fingerprint does not match the extension")
    if acceptance.get("scientific_fingerprint") != expected:
        raise ValueError("Final annual-v2.0 fingerprint does not match the extension")
    if acceptance.get("status") != "complete":
        raise ValueError("The annual-v2.0 baseline is not complete")

    baseline_config_path = resolve_repo_path(repo_root, config["baseline"]["config"])
    load_analysis_config(baseline_config_path)
    inputs = {
        "extension_config": sha256_file(config_path),
        "extension_protocol": sha256_file(
            resolve_repo_path(repo_root, config["protocol"])
        ),
        "extension_implementation": sha256_file(Path(__file__)),
        "extension_runner": sha256_file(
            Path(__file__).with_name("hospitalization_controls_v2_1_runner.py")
        ),
        "annual_implementation": sha256_file(
            Path(__file__).with_name("hospitalization_annual_v2.py")
        ),
        "annual_runner": sha256_file(
            Path(__file__).with_name("hospitalization_annual_v2_runner.py")
        ),
        "inference_implementation": sha256_file(
            Path(__file__).with_name("hospitalization_inference.py")
        ),
        "run_state_implementation": sha256_file(
            Path(__file__).with_name("inference_run_state.py")
        ),
        "baseline_config": sha256_file(baseline_config_path),
        "baseline_prepared_state": sha256_file(baseline_state_path),
        "baseline_acceptance": sha256_file(acceptance_path),
        "annual_exposures": sha256_file(baseline_dir / "annual_exposures.csv"),
        "annual_outcomes": sha256_file(baseline_dir / "annual_outcomes.csv"),
    }
    payload = {
        "study": config["study"],
        "protocol_version": config["protocol_version"],
        "seed": config["seed"],
        "baseline_fingerprint": expected,
        "negative_control": config["negative_control"],
        "evidence": config["evidence"],
        "inputs": inputs,
    }
    return canonical_hash(payload), inputs, baseline_state

