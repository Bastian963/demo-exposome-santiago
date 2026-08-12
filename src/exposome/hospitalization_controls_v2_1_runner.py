"""Resumable runner for the annual-v2.1 Bayesian negative-control extension."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import typer
from tqdm.auto import tqdm

from exposome.hospitalization_annual_v2 import load_analysis_config, resolve_repo_path
from exposome.hospitalization_annual_v2_runner import _graph, _sample_task
from exposome.hospitalization_controls_v2_1 import (
    extension_fingerprint,
    extension_tasks,
    load_extension_config,
)
from exposome.inference_run_state import (
    InferenceRunStore,
    InferenceStateError,
    atomic_write_csv,
    atomic_write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path("config/analyses/hospitalization_annual_v2_1_controls.yaml")
VALID_PHASES = {"prepare", "run", "finalize", "status"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _output(repo_root: Path, config: dict[str, Any], output_dir: Path | None) -> Path:
    return output_dir or resolve_repo_path(repo_root, config["paths"]["output_dir"])


def prepare_extension(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> dict[str, Any]:
    config = load_extension_config(config_path)
    output = _output(repo_root, config, output_dir)
    fingerprint, input_hashes, baseline_state = extension_fingerprint(
        repo_root, config_path, config
    )
    state_path = output / "prepared_state.json"
    if state_path.is_file():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        downstream = (output / "bayesian" / "run_state" / "models").is_dir()
        if downstream and previous.get("scientific_fingerprint") != fingerprint:
            raise InferenceStateError(
                "The v2.1 output contains another fingerprint; use a new output directory"
            )
    state = {
        "schema_version": 1,
        "study": config["study"],
        "protocol_version": config["protocol_version"],
        "scientific_fingerprint": fingerprint,
        "baseline_fingerprint": baseline_state["scientific_fingerprint"],
        "input_hashes": input_hashes,
        "registered_models": len(extension_tasks(config)),
    }
    atomic_write_json(state_path, state)
    return state


def require_prepared_extension(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    config = load_extension_config(config_path)
    output = _output(repo_root, config, output_dir)
    state_path = output / "prepared_state.json"
    if not state_path.is_file():
        raise FileNotFoundError("Run the v2.1 prepare phase first")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    current, _, _ = extension_fingerprint(repo_root, config_path, config)
    if state.get("scientific_fingerprint") != current:
        raise InferenceStateError(
            "Prepared v2.1 inputs or implementation changed; use a new output directory"
        )
    baseline_config = load_analysis_config(
        resolve_repo_path(repo_root, config["baseline"]["config"])
    )
    baseline_config = dict(baseline_config)
    baseline_config["seed"] = int(config["seed"])
    baseline_config["evidence"] = {
        **baseline_config["evidence"],
        **config["evidence"],
    }
    return config, state, output, baseline_config


def _baseline_tables(
    repo_root: Path, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline = resolve_repo_path(repo_root, config["baseline"]["output_dir"])
    return (
        pd.read_csv(baseline / "annual_exposures.csv", dtype={"spatial_id": str}),
        pd.read_csv(baseline / "annual_outcomes.csv", dtype={"spatial_id": str}),
    )


def run_extension(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
    resume: bool,
    rerun_failed: bool,
    dry_run: bool,
    progressbar: bool,
) -> dict[str, Any]:
    config, state, output, model_config = require_prepared_extension(
        repo_root, config_path, output_dir=output_dir
    )
    tasks = extension_tasks(config)
    store = InferenceRunStore(output / "bayesian", state["scientific_fingerprint"])
    rows = store.status_rows(tasks, resume=resume, rerun_failed=rerun_failed)
    pending = [
        task for task, row in zip(tasks, rows, strict=True) if row["state"] == "pending"
    ]
    result = {
        "tasks": len(tasks),
        "complete": len(tasks) - len(pending),
        "pending": len(pending),
        "states": pd.DataFrame(rows)["state"].value_counts().to_dict(),
    }
    if dry_run:
        return result
    store.preflight(
        tasks,
        resume=resume,
        rerun_failed=rerun_failed,
        minimum_free_gib=5.0,
    )
    exposures, outcomes = _baseline_tables(repo_root, config)
    graph = _graph(repo_root, model_config)
    for task in tqdm(pending, desc="annual-v2.1 negative controls", unit="model"):
        idata, diagnostics, effect, loo = _sample_task(
            task,
            exposures=exposures,
            outcomes=outcomes,
            graph=graph,
            config=model_config,
            exact_reloo=bool(model_config["bym2"].get("exact_reloo", True)),
            progressbar=progressbar,
        )
        required = [
            name
            for name in (
                "intercept",
                "beta_within",
                "beta_between",
                "beta_deprivation",
                "beta_interaction",
                "alpha",
                "sigma",
                "rho",
                "theta",
                "phi",
                "mu",
            )
            if name in idata.posterior
        ]
        store.save_record(
            task,
            idata,
            diagnostics=diagnostics,
            effect=effect,
            extras={"loo": loo},
            required_variables=required,
        )
    final_rows = store.status_rows(tasks, resume=True, rerun_failed=False)
    result = {
        "tasks": len(tasks),
        "complete": sum(row["state"] in {"ok", "failed_diagnostics"} for row in final_rows),
        "pending": sum(row["state"] == "pending" for row in final_rows),
        "states": pd.DataFrame(final_rows)["state"].value_counts().to_dict(),
    }
    atomic_write_json(output / "bayesian" / "bayesian_status.json", result)
    return result


def _control_clear(record: dict[str, Any], minimum_probability: float) -> bool:
    diagnostics_ok = bool(record.get("diagnostics", {}).get("diagnostics_passed"))
    effect = record.get("effect") or {}
    probability = effect.get("probability_within_direction")
    low = effect.get("rr_within_hdi_low")
    high = effect.get("rr_within_hdi_high")
    directional = (
        probability is not None
        and float(probability) >= minimum_probability
        and low is not None
        and high is not None
        and (float(low) > 1.0 or float(high) < 1.0)
    )
    return diagnostics_ok and not directional


def finalize_extension(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> dict[str, Any]:
    config, state, output, _ = require_prepared_extension(
        repo_root, config_path, output_dir=output_dir
    )
    tasks = extension_tasks(config)
    store = InferenceRunStore(output / "bayesian", state["scientific_fingerprint"])
    actual = list(store.models_dir.glob("*.json")) if store.models_dir.is_dir() else []
    if {path.stem for path in actual} != {task.model_id for task in tasks}:
        raise InferenceStateError(
            f"v2.1 registry mismatch: expected 16 sidecars, found {len(actual)}"
        )
    states = store.status_rows(tasks, resume=True, rerun_failed=False)
    if any(row["state"] != "ok" for row in states):
        counts = pd.DataFrame(states)["state"].value_counts().to_dict()
        raise InferenceStateError(f"v2.1 finalization gate failed: {counts}")
    records = store.records(tasks)
    rows: list[dict[str, Any]] = []
    threshold = float(config["evidence"]["minimum_direction_probability"])
    for task, record in zip(tasks, records, strict=True):
        trace = store.trace_path(task)
        if _sha256(trace) != str(record.get("trace", {}).get("sha256", "")):
            raise InferenceStateError(f"v2.1 trace hash mismatch: {trace}")
        window, timing = str(task.variant).split("__", 1)
        rows.append(
            {
                "outcome": task.outcome,
                "exposure": task.exposure,
                "window": window,
                "timing": timing,
                "bayesian_negative_control_clear": _control_clear(record, threshold),
                "status": record["status"],
                **record["diagnostics"],
                **(record.get("effect") or {}),
                **{
                    f"loo_{key}": value
                    for key, value in record.get("extras", {}).get("loo", {}).items()
                },
                "model_id": task.model_id,
                "trace_sha256": record["trace"]["sha256"],
            }
        )
    table = pd.DataFrame(rows).sort_values(["timing", "exposure"])
    atomic_write_csv(table, output / "negative_control_evidence.csv")
    acceptance = {
        "schema_version": 1,
        "status": "complete",
        "scientific_fingerprint": state["scientific_fingerprint"],
        "baseline_fingerprint": state["baseline_fingerprint"],
        "models_expected": 16,
        "models_saved": 16,
        "models_failed_diagnostics": 0,
        "controls_clear": int(table["bayesian_negative_control_clear"].sum()),
        "controls_directional": int((~table["bayesian_negative_control_clear"]).sum()),
        "accepted_for_causal_interpretation": False,
    }
    atomic_write_json(output / "publication_acceptance.json", acceptance)
    return acceptance


def extension_status(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> dict[str, Any]:
    config = load_extension_config(config_path)
    output = _output(repo_root, config, output_dir)
    result: dict[str, Any] = {
        "output_dir": str(output),
        "prepared": (output / "prepared_state.json").is_file(),
        "finalized": (output / "publication_acceptance.json").is_file(),
    }
    if not result["prepared"]:
        result["prepared_valid"] = False
        result["bayesian"] = None
        return result
    try:
        config, state, _, _ = require_prepared_extension(
            repo_root, config_path, output_dir=output
        )
        result["prepared_valid"] = True
        store = InferenceRunStore(output / "bayesian", state["scientific_fingerprint"])
        rows = store.status_rows(
            extension_tasks(config), resume=True, rerun_failed=False
        )
        result["bayesian"] = {
            "tasks": len(rows),
            "complete": sum(row["state"] in {"ok", "failed_diagnostics"} for row in rows),
            "pending": sum(row["state"] == "pending" for row in rows),
            "states": pd.DataFrame(rows)["state"].value_counts().to_dict(),
            "reconstructed_from_sidecars": True,
        }
    except Exception as exc:
        result["prepared_valid"] = False
        result["prepared_reason"] = f"{type(exc).__name__}: {exc}"
        result["bayesian"] = None
    return result


def main(
    phase: str = typer.Option(..., help="prepare, run, finalize, or status"),
    config: Path = typer.Option(DEFAULT_CONFIG, exists=True, dir_okay=False),
    output_dir: Optional[Path] = typer.Option(None),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    rerun_failed: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
    progressbar: bool = typer.Option(True, "--progressbar/--no-progressbar"),
) -> None:
    phase = phase.strip().lower()
    if phase not in VALID_PHASES:
        raise typer.BadParameter(f"phase must be one of {sorted(VALID_PHASES)}")
    config_path = resolve_repo_path(REPO_ROOT, config)
    resolved_output = (
        resolve_repo_path(REPO_ROOT, output_dir) if output_dir is not None else None
    )
    if phase == "prepare":
        result = prepare_extension(REPO_ROOT, config_path, output_dir=resolved_output)
    elif phase == "run":
        result = run_extension(
            REPO_ROOT,
            config_path,
            output_dir=resolved_output,
            resume=resume,
            rerun_failed=rerun_failed,
            dry_run=dry_run,
            progressbar=progressbar,
        )
    elif phase == "finalize":
        result = finalize_extension(REPO_ROOT, config_path, output_dir=resolved_output)
    else:
        result = extension_status(REPO_ROOT, config_path, output_dir=resolved_output)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
