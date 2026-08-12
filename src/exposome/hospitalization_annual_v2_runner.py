"""Resumable command runner for hospitalization annual-v2 inference."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import pandas as pd
import typer
from tqdm.auto import tqdm

from exposome.hospitalization_annual_v2 import (
    apply_screening_multiplicity,
    bayesian_tasks,
    build_panel_bym2_model,
    classify_evidence,
    fit_joint_elastic_net,
    load_analysis_config,
    panel_bayesian_diagnostics,
    panel_psis_loo,
    parse_task_variant,
    prepare_analysis,
    require_prepared_state,
    resolve_repo_path,
    screen_one_pair,
    screening_tasks,
    summarize_panel_effect,
    task_panel_data,
    task_slug,
)
from exposome.hospitalization_inference import (
    build_queen_graph,
    sample_pymc_model,
    stable_seed,
)
from exposome.inference_run_state import (
    InferenceStateError,
    InferenceRunStore,
    ModelTask,
    atomic_write_csv,
    atomic_write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path("config/analyses/hospitalization_annual_v2.yaml")
VALID_PHASES = {"prepare", "screen", "joint", "bayesian", "finalize", "status"}


def _filter_rows(
    rows: list[Any],
    *,
    outcomes: tuple[str, ...],
    exposures: tuple[str, ...],
    timings: tuple[str, ...],
    windows: tuple[str, ...],
) -> list[Any]:
    selected = []
    for row in rows:
        if isinstance(row, ModelTask):
            window, timing = parse_task_variant(row)
            outcome = row.outcome
            exposure = row.exposure
        else:
            window, timing = str(row["window"]), str(row["timing"])
            outcome, exposure = str(row["outcome"]), str(row["exposure"])
        if outcomes and outcome not in outcomes:
            continue
        if exposures and exposure not in exposures:
            continue
        if timings and timing not in timings:
            continue
        if windows and window not in windows:
            continue
        selected.append(row)
    return selected


def _load_prepared(output: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(output / "annual_exposures.csv", dtype={"spatial_id": str}),
        pd.read_csv(output / "annual_outcomes.csv", dtype={"spatial_id": str}),
    )


def _graph(repo_root: Path, config: dict[str, Any]):
    geometry = gpd.read_file(resolve_repo_path(repo_root, config["paths"]["geometry"]))
    return build_queen_graph(geometry)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalization_preflight(
    output: Path,
    config: dict[str, Any],
    scientific_fingerprint: str,
    *,
    verify_trace_hashes: bool = True,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Refuse finalization unless every registered artifact is valid and complete."""
    screening_path = output / "screening" / "screening_results.csv"
    if not screening_path.is_file():
        raise InferenceStateError("Missing screening_results.csv")
    screening = pd.read_csv(screening_path)
    expected_screening_tasks = screening_tasks(config)
    expected_screening_ids = {task_slug(task) for task in expected_screening_tasks}
    screening_dir = output / "screening" / "tasks"
    actual_screening_paths = list(screening_dir.glob("*.json")) if screening_dir.is_dir() else []
    actual_screening_ids = {path.stem for path in actual_screening_paths}
    if actual_screening_ids != expected_screening_ids:
        raise InferenceStateError(
            "Screening registry mismatch: "
            f"expected {len(expected_screening_ids)}, found {len(actual_screening_ids)}"
        )
    if len(screening) != len(expected_screening_tasks):
        raise InferenceStateError(
            f"Screening table has {len(screening)} rows, expected {len(expected_screening_tasks)}"
        )
    if "status" not in screening or screening["status"].eq("error").any():
        raise InferenceStateError("Screening contains errors or lacks a status column")
    for path in actual_screening_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("scientific_fingerprint") != scientific_fingerprint:
            raise InferenceStateError(f"Screening fingerprint mismatch: {path}")
        if record.get("status") == "error":
            raise InferenceStateError(f"Screening task failed: {path}")

    expected_joint_ids = {
        f"{outcome}__{timing}"
        for outcome in config["outcomes"]["primary"]
        for timing in config["windows"]["timings"]
    }
    joint_dir = output / "joint" / "tasks"
    actual_joint_paths = (
        [path for path in joint_dir.glob("*.json")]
        if joint_dir.is_dir()
        else []
    )
    if {path.stem for path in actual_joint_paths} != expected_joint_ids:
        raise InferenceStateError(
            f"Joint registry mismatch: expected {len(expected_joint_ids)}, "
            f"found {len(actual_joint_paths)}"
        )
    for path in actual_joint_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("scientific_fingerprint") != scientific_fingerprint:
            raise InferenceStateError(f"Joint fingerprint mismatch: {path}")
        if record.get("status") != "ok":
            raise InferenceStateError(f"Joint model is not successful: {path}")

    tasks = bayesian_tasks(config)
    expected_model_ids = {task.model_id for task in tasks}
    store = InferenceRunStore(output / "bayesian", scientific_fingerprint)
    model_dir = store.models_dir
    actual_model_paths = list(model_dir.glob("*.json")) if model_dir.is_dir() else []
    if {path.stem for path in actual_model_paths} != expected_model_ids:
        raise InferenceStateError(
            f"Bayesian registry mismatch: expected {len(expected_model_ids)}, "
            f"found {len(actual_model_paths)}"
        )
    status_rows = store.status_rows(tasks, resume=True, rerun_failed=False)
    invalid = [row for row in status_rows if row["state"] != "ok"]
    if invalid:
        states = pd.DataFrame(invalid)["state"].value_counts().to_dict()
        raise InferenceStateError(f"Bayesian finalization gate failed: {states}")
    records = store.records(tasks)
    if len(records) != len(tasks):
        raise InferenceStateError(
            f"Loaded {len(records)} Bayesian records, expected {len(tasks)}"
        )
    if verify_trace_hashes:
        for task, record in zip(tasks, records, strict=True):
            trace_path = store.trace_path(task)
            expected_hash = str(record.get("trace", {}).get("sha256", ""))
            if not expected_hash or _sha256(trace_path) != expected_hash:
                raise InferenceStateError(f"Bayesian trace hash mismatch: {trace_path}")
    return screening, records


def run_screening_phase(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
    resume: bool,
    dry_run: bool,
    outcomes_filter: tuple[str, ...],
    exposures_filter: tuple[str, ...],
    timings_filter: tuple[str, ...],
    windows_filter: tuple[str, ...],
    bootstrap_samples: int | None,
    moran_permutations: int | None,
) -> dict[str, Any]:
    config, state, output = require_prepared_state(
        repo_root, config_path, output_dir=output_dir
    )
    tasks = _filter_rows(
        screening_tasks(config),
        outcomes=outcomes_filter,
        exposures=exposures_filter,
        timings=timings_filter,
        windows=windows_filter,
    )
    task_dir = output / "screening" / "tasks"
    pending = []
    complete = 0
    for task in tasks:
        path = task_dir / f"{task_slug(task)}.json"
        if resume and path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("scientific_fingerprint") != state["scientific_fingerprint"]:
                raise ValueError(f"Stale screening checkpoint: {path}")
            complete += 1
        else:
            pending.append(task)
    status = {"tasks": len(tasks), "complete": complete, "pending": len(pending)}
    if dry_run:
        return status
    exposures, outcomes = _load_prepared(output)
    graph = _graph(repo_root, config)
    errors = 0
    for task in tqdm(pending, desc="annual-v2 screening", unit="pair"):
        path = task_dir / f"{task_slug(task)}.json"
        try:
            result = screen_one_pair(
                exposures,
                outcomes,
                graph,
                config,
                exposure=str(task["exposure"]),
                outcome=str(task["outcome"]),
                timing=str(task["timing"]),
                window=str(task["window"]),
                bootstrap_samples=bootstrap_samples,
                moran_permutations=moran_permutations,
            )
            record = {
                **result,
                "outcome_family": task["outcome_family"],
                "scientific_fingerprint": state["scientific_fingerprint"],
            }
        except Exception as exc:
            errors += 1
            record = {
                **task,
                "status": "error",
                "reason": f"{type(exc).__name__}: {exc}",
                "scientific_fingerprint": state["scientific_fingerprint"],
            }
        atomic_write_json(path, record)
    records = []
    strata_records: list[dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("scientific_fingerprint") == state["scientific_fingerprint"]:
            for stratum in record.pop("socioeconomic_strata", []) or []:
                strata_records.append(
                    {
                        "exposure": record.get("exposure"),
                        "outcome": record.get("outcome"),
                        "timing": record.get("timing"),
                        "window": record.get("window"),
                        **stratum,
                    }
                )
            records.append(record)
    table = pd.json_normalize(records)
    if not table.empty:
        if "ppml_p_value" not in table:
            table["ppml_p_value"] = pd.NA
        table = apply_screening_multiplicity(table, config)
        atomic_write_csv(table, output / "screening" / "screening_results.csv")
    if strata_records:
        atomic_write_csv(
            pd.DataFrame(strata_records),
            output / "screening" / "socioeconomic_strata_results.csv",
        )
    status.update(
        {
            "complete": len(tasks) - len(pending) + len(pending),
            "pending": 0,
            "errors_this_run": errors,
        }
    )
    atomic_write_json(output / "screening" / "screening_status.json", status)
    return status


def run_joint_phase(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
    resume: bool,
    dry_run: bool,
    outcomes_filter: tuple[str, ...],
    timings_filter: tuple[str, ...],
    stability_resamples: int | None,
) -> dict[str, Any]:
    config, state, output = require_prepared_state(
        repo_root, config_path, output_dir=output_dir
    )
    tasks = [
        {"outcome": outcome, "timing": timing}
        for outcome in config["outcomes"]["primary"]
        for timing in config["windows"]["timings"]
        if (not outcomes_filter or outcome in outcomes_filter)
        and (not timings_filter or timing in timings_filter)
    ]
    task_dir = output / "joint" / "tasks"
    pending = []
    complete = 0
    for task in tasks:
        slug = f"{task['outcome']}__{task['timing']}"
        state_path = task_dir / f"{slug}.json"
        if resume and state_path.is_file():
            record = json.loads(state_path.read_text(encoding="utf-8"))
            if record.get("scientific_fingerprint") != state["scientific_fingerprint"]:
                raise ValueError(f"Stale joint checkpoint: {state_path}")
            complete += 1
        else:
            pending.append(task)
    status = {"tasks": len(tasks), "complete": complete, "pending": len(pending)}
    if dry_run:
        return status
    exposures, outcomes = _load_prepared(output)
    for task in tqdm(pending, desc="annual-v2 elastic net", unit="model"):
        slug = f"{task['outcome']}__{task['timing']}"
        tuning, coefficients = fit_joint_elastic_net(
            exposures,
            outcomes,
            config,
            outcome=task["outcome"],
            timing=task["timing"],
            stability_resamples=stability_resamples,
        )
        atomic_write_csv(tuning, task_dir / f"{slug}__tuning.csv")
        atomic_write_csv(coefficients, task_dir / f"{slug}__coefficients.csv")
        atomic_write_json(
            task_dir / f"{slug}.json",
            {
                **task,
                "status": "ok",
                "scientific_fingerprint": state["scientific_fingerprint"],
            },
        )
    tuning_files = sorted(task_dir.glob("*__tuning.csv"))
    coefficient_files = sorted(task_dir.glob("*__coefficients.csv"))
    if tuning_files:
        atomic_write_csv(
            pd.concat([pd.read_csv(path) for path in tuning_files], ignore_index=True),
            output / "joint" / "elastic_net_tuning.csv",
        )
    if coefficient_files:
        atomic_write_csv(
            pd.concat([pd.read_csv(path) for path in coefficient_files], ignore_index=True),
            output / "joint" / "elastic_net_coefficients.csv",
        )
    status.update({"complete": len(tasks), "pending": 0})
    atomic_write_json(output / "joint" / "joint_status.json", status)
    return status


def _sample_task(
    task: ModelTask,
    *,
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    graph: Any,
    config: dict[str, Any],
    exact_reloo: bool,
    progressbar: bool,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = task_panel_data(task, exposures, outcomes, config, graph)
    include_exposure = task.model_name != "nb_bym2_panel_null"
    bym2 = config["bym2"]
    rho_prior = (
        bym2["rho_prior_sensitivity"]
        if task.model_name == "nb_bym2_panel_rho_prior_sensitivity"
        else None
    )
    seed = stable_seed(int(config["seed"]), task.model_id)
    attempts = [
        {
            "draws": int(bym2["draws"]),
            "tune": int(bym2["tune"]),
            "target_accept": float(bym2["target_accept"]),
        },
        {
            "draws": int(bym2["retry_draws"]),
            "tune": int(bym2["retry_tune"]),
            "target_accept": float(bym2["retry_target_accept"]),
        },
    ]
    idata = None
    diagnostics: dict[str, Any] = {}
    selected: dict[str, Any] = {}
    for number, sampling in enumerate(attempts, start=1):
        model = build_panel_bym2_model(
            data,
            graph,
            bym2,
            include_exposure=include_exposure,
            rho_prior=rho_prior,
        )
        idata = sample_pymc_model(
            model,
            draws=sampling["draws"],
            tune=sampling["tune"],
            chains=int(bym2["chains"]),
            target_accept=sampling["target_accept"],
            seed=stable_seed(seed, "attempt", number),
            progressbar=progressbar,
        )
        diagnostics = panel_bayesian_diagnostics(idata, bym2["diagnostics"])
        selected = {
            **sampling,
            "chains": int(bym2["chains"]),
            "attempt": number,
        }
        if diagnostics["diagnostics_passed"]:
            break
    if idata is None:
        raise RuntimeError("Bayesian sampler returned no inference data")
    diagnostics.update(selected)
    effect = (
        summarize_panel_effect(idata, data, rope_rr=config["evidence"]["rope_rr"])
        if include_exposure
        else {}
    )
    loo = panel_psis_loo(
        idata,
        data,
        graph,
        bym2,
        include_exposure=include_exposure,
        rho_prior=rho_prior,
        seed=seed,
        exact_reloo=exact_reloo,
        progressbar=progressbar,
    )
    return idata, diagnostics, effect, loo


def run_bayesian_phase(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
    resume: bool,
    rerun_failed: bool,
    dry_run: bool,
    outcomes_filter: tuple[str, ...],
    exposures_filter: tuple[str, ...],
    timings_filter: tuple[str, ...],
    windows_filter: tuple[str, ...],
    progressbar: bool,
) -> dict[str, Any]:
    config, state, output = require_prepared_state(
        repo_root, config_path, output_dir=output_dir
    )
    exact_reloo = bool(config["bym2"].get("exact_reloo", True))
    tasks = _filter_rows(
        bayesian_tasks(config),
        outcomes=outcomes_filter,
        exposures=exposures_filter,
        timings=timings_filter,
        windows=windows_filter,
    )
    store = InferenceRunStore(output / "bayesian", state["scientific_fingerprint"])
    status_rows = store.status_rows(tasks, resume=resume, rerun_failed=rerun_failed)
    pending = [
        task for task, row in zip(tasks, status_rows, strict=True) if row["state"] == "pending"
    ]
    status = {
        "tasks": len(tasks),
        "complete": len(tasks) - len(pending),
        "pending": len(pending),
        "states": pd.DataFrame(status_rows)["state"].value_counts().to_dict(),
    }
    if dry_run:
        return status
    store.preflight(
        tasks,
        resume=resume,
        rerun_failed=rerun_failed,
        minimum_free_gib=5.0,
    )
    exposures, outcomes = _load_prepared(output)
    graph = _graph(repo_root, config)
    for task in tqdm(pending, desc="annual-v2 BYM2", unit="model"):
        idata, diagnostics, effect, loo = _sample_task(
            task,
            exposures=exposures,
            outcomes=outcomes,
            graph=graph,
            config=config,
            exact_reloo=exact_reloo,
            progressbar=progressbar,
        )
        required = [
            value
            for value in (
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
            if value in idata.posterior
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
    status.update(
        {
            "complete": sum(row["state"] in {"ok", "failed_diagnostics"} for row in final_rows),
            "pending": sum(row["state"] == "pending" for row in final_rows),
            "states": pd.DataFrame(final_rows)["state"].value_counts().to_dict(),
        }
    )
    atomic_write_json(output / "bayesian" / "bayesian_status.json", status)
    return status


def run_finalize_phase(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> dict[str, Any]:
    config, state, output = require_prepared_state(
        repo_root, config_path, output_dir=output_dir
    )
    screening, bayesian_records = _finalization_preflight(
        output,
        config,
        state["scientific_fingerprint"],
    )
    bayesian_rows: list[dict[str, Any]] = []
    for record in bayesian_records:
        if not record.get("effect"):
            continue
        window, timing = str(record["variant"]).split("__", 1)
        bayesian_rows.append(
            {
                "outcome": record["outcome"],
                "exposure": record["exposure"],
                "window": window,
                "timing": timing,
                "bayesian_status": record["status"],
                "bayesian_model_name": record["model_name"],
                **record["diagnostics"],
                **record["effect"],
                **{
                    f"loo_{key}": value
                    for key, value in record.get("extras", {}).get("loo", {}).items()
                },
            }
        )
    bayesian = pd.DataFrame(bayesian_rows)
    evidence = screening.copy()
    if not bayesian.empty:
        sensitivity = bayesian[
            bayesian["bayesian_model_name"]
            == "nb_bym2_panel_rho_prior_sensitivity"
        ].copy()
        if not sensitivity.empty:
            atomic_write_csv(
                sensitivity,
                output / "bayesian" / "rho_prior_sensitivity_results.csv",
            )
        bayesian = bayesian[
            bayesian["bayesian_model_name"]
            != "nb_bym2_panel_rho_prior_sensitivity"
        ].copy()
        evidence = evidence.merge(
            bayesian,
            on=["outcome", "exposure", "window", "timing"],
            how="left",
            validate="one_to_one",
            suffixes=("", "_bayesian"),
        )
    negative_outcome = str(config["outcomes"]["negative_control"][0])
    controls = evidence[evidence["outcome"] == negative_outcome].copy()
    control_clear = {
        (str(row.exposure), str(row.window), str(row.timing)): bool(
            row.status == "ok"
            and pd.notna(row.ppml_q_value)
            and float(row.ppml_q_value) >= float(config["evidence"]["alpha"])
        )
        for row in controls.itertuples(index=False)
    }
    evidence["negative_control_clear"] = [
        control_clear.get((str(row.exposure), str(row.window), str(row.timing)), False)
        for row in evidence.itertuples(index=False)
    ]
    evidence["evidence_label"] = [
        classify_evidence(row, config) for row in evidence.to_dict(orient="records")
    ]
    atomic_write_csv(evidence, output / "evidence_table.csv")
    expected_bayesian = len(bayesian_tasks(config))
    saved_bayesian = len(bayesian_records)
    bayesian_failed = 0
    screening_errors = 0
    expected_screening = len(screening_tasks(config))
    completed_screening = int(len(screening))
    expected_joint = len(config["outcomes"]["primary"]) * len(
        config["windows"]["timings"]
    )
    completed_joint = expected_joint
    acceptance = {
        "schema_version": 1,
        "scientific_fingerprint": state["scientific_fingerprint"],
        "status": "complete",
        "accepted_for_causal_interpretation": False,
        "screening_errors": screening_errors,
        "screening_tasks_expected": expected_screening,
        "screening_tasks_completed": completed_screening,
        "joint_models_expected": expected_joint,
        "joint_models_completed": completed_joint,
        "bayesian_models_expected": expected_bayesian,
        "bayesian_models_saved": saved_bayesian,
        "bayesian_models_failed_diagnostics": bayesian_failed,
        "evidence_counts": evidence["evidence_label"].value_counts().to_dict(),
        "scope": EXPECTED_OFFLINE_SCOPE,
    }
    atomic_write_json(output / "publication_acceptance.json", acceptance)
    report = "\n".join(
        [
            "# Annual exposome–hospitalization analysis v2",
            "",
            f"- Status: **{acceptance['status']}**",
            f"- Fingerprint: `{state['scientific_fingerprint']}`",
            f"- Screening errors: {screening_errors}",
            f"- Bayesian models: {saved_bayesian}/{expected_bayesian}",
            "- Interpretation: ecological association only; not causal or individual-level.",
            "",
            "## Evidence labels",
            "",
            *[
                f"- {label}: {count}"
                for label, count in acceptance["evidence_counts"].items()
            ],
            "",
            "The full machine-readable results are in `evidence_table.csv`.",
        ]
    )
    _atomic_text(output / "analysis_report.md", report + "\n")
    return acceptance


# Keep the finalizer independent from private module constants.
EXPECTED_OFFLINE_SCOPE = {
    "product": "offline_data_analysis",
    "webapp": False,
    "exposome_master": False,
    "automated_publish": False,
}


def status_phase(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None,
) -> dict[str, Any]:
    config = load_analysis_config(config_path)
    output = output_dir or resolve_repo_path(repo_root, config["paths"]["output_dir"])
    result: dict[str, Any] = {
        "output_dir": str(output),
        "prepared": (output / "prepared_state.json").is_file(),
    }
    prepared_state: dict[str, Any] | None = None
    if result["prepared"]:
        try:
            _, prepared_state, _ = require_prepared_state(
                repo_root, config_path, output_dir=output
            )
            result["prepared_valid"] = True
            result["prepared_reason"] = None
        except Exception as exc:
            result["prepared_valid"] = False
            result["prepared_reason"] = f"{type(exc).__name__}: {exc}"
    for name in ("screening", "joint", "bayesian"):
        path = output / name / f"{name}_status.json"
        result[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    if result.get("prepared_valid") and result["bayesian"] is None:
        assert prepared_state is not None
        tasks = bayesian_tasks(config)
        store = InferenceRunStore(
            output / "bayesian", prepared_state["scientific_fingerprint"]
        )
        rows = store.status_rows(tasks, resume=True, rerun_failed=False)
        state_counts = pd.DataFrame(rows)["state"].value_counts().to_dict()
        result["bayesian"] = {
            "tasks": len(tasks),
            "complete": sum(row["state"] in {"ok", "failed_diagnostics"} for row in rows),
            "pending": sum(row["state"] == "pending" for row in rows),
            "states": state_counts,
            "reconstructed_from_sidecars": True,
        }
    result["finalized"] = (output / "publication_acceptance.json").is_file()
    return result


def main(
    phase: str = typer.Option(..., help="prepare, screen, joint, bayesian, finalize, or status"),
    config: Path = typer.Option(DEFAULT_CONFIG, exists=True, dir_okay=False),
    output_dir: Optional[Path] = typer.Option(None),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    rerun_failed: bool = typer.Option(False),
    dry_run: bool = typer.Option(False),
    outcome: Optional[list[str]] = typer.Option(None),
    exposure: Optional[list[str]] = typer.Option(None),
    timing: Optional[list[str]] = typer.Option(None),
    window: Optional[list[str]] = typer.Option(None),
    bootstrap_samples: Optional[int] = typer.Option(None, min=1),
    moran_permutations: Optional[int] = typer.Option(None, min=1),
    stability_resamples: Optional[int] = typer.Option(None, min=0),
    progressbar: bool = typer.Option(True, "--progressbar/--no-progressbar"),
) -> None:
    phase = phase.strip().lower()
    if phase not in VALID_PHASES:
        raise typer.BadParameter(f"phase must be one of {sorted(VALID_PHASES)}")
    config_path = resolve_repo_path(REPO_ROOT, config)
    selected_outcomes = tuple(outcome or ())
    selected_exposures = tuple(exposure or ())
    selected_timings = tuple(timing or ())
    selected_windows = tuple(window or ())
    resolved_output = (
        resolve_repo_path(REPO_ROOT, output_dir) if output_dir is not None else None
    )
    if phase == "prepare":
        result = prepare_analysis(
            REPO_ROOT, config_path, output_dir=resolved_output
        )
    elif phase == "screen":
        result = run_screening_phase(
            REPO_ROOT,
            config_path,
            output_dir=resolved_output,
            resume=resume,
            dry_run=dry_run,
            outcomes_filter=selected_outcomes,
            exposures_filter=selected_exposures,
            timings_filter=selected_timings,
            windows_filter=selected_windows,
            bootstrap_samples=bootstrap_samples,
            moran_permutations=moran_permutations,
        )
    elif phase == "joint":
        result = run_joint_phase(
            REPO_ROOT,
            config_path,
            output_dir=resolved_output,
            resume=resume,
            dry_run=dry_run,
            outcomes_filter=selected_outcomes,
            timings_filter=selected_timings,
            stability_resamples=stability_resamples,
        )
    elif phase == "bayesian":
        result = run_bayesian_phase(
            REPO_ROOT,
            config_path,
            output_dir=resolved_output,
            resume=resume,
            rerun_failed=rerun_failed,
            dry_run=dry_run,
            outcomes_filter=selected_outcomes,
            exposures_filter=selected_exposures,
            timings_filter=selected_timings,
            windows_filter=selected_windows,
            progressbar=progressbar,
        )
    elif phase == "finalize":
        result = run_finalize_phase(
            REPO_ROOT, config_path, output_dir=resolved_output
        )
    else:
        result = status_phase(REPO_ROOT, config_path, output_dir=resolved_output)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    typer.run(main)
