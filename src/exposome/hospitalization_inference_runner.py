"""Orchestrate local, publication-oriented hospitalization inference.

This runner reads materialized commune-level SMR/count and exposure matrices.  It
does not read or reprocess individual DEIS microdata and makes no network calls.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome.config import load_config  # noqa: E402
from exposome.hospitalization_inference import (  # noqa: E402
    augment_exposure_matrix,
    bivariate_moran_analysis,
    build_inference_manifest,
    build_pymc_nb_model,
    build_queen_graph,
    classical_correlation_analysis,
    collinearity_diagnostics,
    deterministic_spatial_blocks,
    elastic_net_poisson_nested_cv,
    exposure_definitions,
    file_sha256,
    fit_with_diagnostic_retry,
    hospitalization_mortality_triangulation,
    horn_parallel_analysis,
    negative_control_availability,
    normalise_spatial_id,
    oriented_exposure_matrix,
    posterior_predictive_checks,
    prepare_bayesian_model_data,
    psis_loo_with_exact_refits,
    retained_pca_outputs,
    stable_seed,
    summarize_bayesian_effect,
    validate_analysis_inputs,
    validate_inference_config,
    write_json,
)
from exposome.inference_run_state import (  # noqa: E402
    InferenceRunStore,
    InferenceStateError,
    ModelTask,
    atomic_write_csv,
    atomic_write_json,
    publication_tasks,
    scientific_fingerprint,
)


app = typer.Typer(
    help=(
        "Offline ecological hospitalization analysis from existing commune-level "
        "matrices; never reprocesses DEIS microdata or publishes to the webapp."
    )
)


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"spatial_id": str})
    if "spatial_id" in frame:
        frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    return frame


def _write_csv(frame: pd.DataFrame, path: Path, products: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    products.append(path)


def _aggregate_annual_window(
    annual: pd.DataFrame,
    years: list[int],
    label: str,
) -> pd.DataFrame:
    frame = annual[annual["year"].isin(years)].copy()
    grouped = (
        frame.groupby(["spatial_id", "spatial_name", "outcome"], as_index=False)
        .agg(observed=("observed", "sum"), expected=("expected", "sum"))
    )
    grouped["smr"] = grouped["observed"] / grouped["expected"]
    grouped["window"] = label
    return grouped


def _one_exposure_config(
    config: dict[str, Any],
    exposure_ids: list[str],
    *,
    window: str | None = None,
) -> dict[str, Any]:
    subset = deepcopy(config)
    subset["exposures"] = [
        item for item in subset["exposures"] if str(item["id"]) in exposure_ids
    ]
    if window is not None:
        subset["windows"]["primary"] = window
    return subset


def _run_classical_sensitivities(
    smr: pd.DataFrame,
    annual: pd.DataFrame,
    exposures: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    loo_frames: list[pd.DataFrame] = []
    windows = [
        (
            "year_2018",
            _aggregate_annual_window(annual, [2018], "year_2018"),
        ),
        (
            "year_2019",
            _aggregate_annual_window(annual, [2019], "year_2019"),
        ),
        (
            str(config["windows"]["covid_sensitivity"]),
            smr,
        ),
    ]
    for label, data in windows:
        local = _one_exposure_config(config, ["pm25_hist"], window=label)
        result, loo, _ = classical_correlation_analysis(data, exposures, local)
        result["sensitivity"] = label
        loo["sensitivity"] = label
        frames.append(result)
        loo_frames.append(loo)
    return pd.concat(frames, ignore_index=True), pd.concat(loo_frames, ignore_index=True)


def _classical_products(
    smr: pd.DataFrame,
    annual: pd.DataFrame,
    exposures: pd.DataFrame,
    mortality: pd.DataFrame,
    geometry: gpd.GeoDataFrame,
    config: dict[str, Any],
    output_dir: Path,
    products: list[Path],
    *,
    include_exploratory_outcomes: bool,
    run_elastic_net: bool,
) -> dict[str, Any]:
    index = validate_analysis_inputs(smr, exposures, config)
    _write_csv(index, output_dir / "main_analysis_index.csv", products)

    correlations, influence, exclusions = classical_correlation_analysis(
        smr, exposures, config
    )
    _write_csv(correlations, output_dir / "classical_correlations.csv", products)
    _write_csv(influence, output_dir / "classical_leave_one_commune_out.csv", products)
    _write_csv(exclusions, output_dir / "exclusions.csv", products)

    sensitivity, sensitivity_loo = _run_classical_sensitivities(
        smr, annual, exposures, config
    )
    _write_csv(sensitivity, output_dir / "pm25_window_sensitivity.csv", products)
    _write_csv(
        sensitivity_loo,
        output_dir / "pm25_window_sensitivity_leave_one_out.csv",
        products,
    )

    if include_exploratory_outcomes:
        exploratory, exploratory_loo, exploratory_exclusions = (
            classical_correlation_analysis(
                smr,
                exposures,
                config,
                outcomes=config["outcomes"]["exploratory"],
                multiplicity_family="exploratory_outcomes",
            )
        )
        _write_csv(
            exploratory,
            output_dir / "appendix_exploratory_outcomes_correlations.csv",
            products,
        )
        _write_csv(
            exploratory_loo,
            output_dir / "appendix_exploratory_outcomes_leave_one_out.csv",
            products,
        )
        if not exploratory_exclusions.empty:
            _write_csv(
                exploratory_exclusions,
                output_dir / "appendix_exploratory_outcomes_exclusions.csv",
                products,
            )

    negative_status = negative_control_availability(smr, config)
    _write_csv(negative_status, output_dir / "negative_control_status.csv", products)
    if negative_status["available_in_materialized_smr"].all():
        control_config = _one_exposure_config(config, ["pm25_hist", "no2"])
        control, control_loo, _ = classical_correlation_analysis(
            smr,
            exposures,
            control_config,
            outcomes=config["outcomes"]["negative_control"],
            multiplicity_family="negative_control",
        )
        _write_csv(control, output_dir / "negative_control_correlations.csv", products)
        _write_csv(
            control_loo,
            output_dir / "negative_control_leave_one_out.csv",
            products,
        )

    graph = build_queen_graph(geometry)
    graph_table = pd.DataFrame(graph.adjacency, index=graph.spatial_ids, columns=graph.spatial_ids)
    graph_path = output_dir / "queen_adjacency.csv"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_table.to_csv(graph_path, index_label="spatial_id")
    products.append(graph_path)
    graph_metadata = {
        "n_nodes": len(graph.spatial_ids),
        "n_edges": int(graph.adjacency.sum() // 2),
        "connected": True,
        "symmetric": True,
        "islands": 0,
        "spatial_ids": list(graph.spatial_ids),
        "icar_scaling_factor": graph.scaling_factor,
    }
    graph_metadata_path = output_dir / "queen_graph_metadata.json"
    write_json(graph_metadata_path, graph_metadata)
    products.append(graph_metadata_path)

    moran = bivariate_moran_analysis(smr, exposures, graph, config)
    _write_csv(moran, output_dir / "bivariate_moran.csv", products)

    oriented, orientation = oriented_exposure_matrix(exposures, config)
    _write_csv(oriented, output_dir / "oriented_exposure_matrix.csv", products)
    _write_csv(orientation, output_dir / "exposure_orientation.csv", products)
    ids = list(exposure_definitions(config))
    joint = config["joint_exposome"]
    matrix, vif, clusters = collinearity_diagnostics(
        oriented,
        ids,
        rho_threshold=float(joint["collinearity_rho_threshold"]),
    )
    vif["above_threshold"] = vif["vif"] > float(joint["vif_threshold"])
    _write_csv(matrix, output_dir / "exposure_correlations_long.csv", products)
    _write_csv(vif, output_dir / "exposure_vif.csv", products)
    _write_csv(clusters, output_dir / "exposure_clusters.csv", products)
    horn = horn_parallel_analysis(
        oriented,
        ids,
        permutations=int(joint["horn_permutations"]),
        seed=stable_seed(int(config["seed"]), "horn"),
    )
    _write_csv(horn, output_dir / "pca_horn_parallel_analysis.csv", products)
    scores, loadings = retained_pca_outputs(oriented, ids, horn)
    _write_csv(scores, output_dir / "pca_scores.csv", products)
    _write_csv(loadings, output_dir / "pca_loadings.csv", products)

    blocks = deterministic_spatial_blocks(
        geometry,
        n_blocks=int(joint["spatial_blocks"]),
        seed=stable_seed(int(config["seed"]), "spatial_blocks"),
    )
    _write_csv(blocks, output_dir / "spatial_cv_blocks.csv", products)
    if run_elastic_net:
        primary = smr[
            (smr["window"] == config["windows"]["primary"])
            & smr["outcome"].isin(config["outcomes"]["confirmatory"])
        ]
        performance, coefficients, stability = elastic_net_poisson_nested_cv(
            primary, oriented, blocks, ids, config
        )
        _write_csv(
            performance, output_dir / "elastic_net_nested_cv_performance.csv", products
        )
        _write_csv(coefficients, output_dir / "elastic_net_coefficients.csv", products)
        _write_csv(stability, output_dir / "elastic_net_stability.csv", products)

    triangulation = hospitalization_mortality_triangulation(smr, mortality, config)
    _write_csv(
        triangulation,
        output_dir / "hospitalization_mortality_triangulation.csv",
        products,
    )
    return {
        "graph": graph,
        "oriented": oriented,
        "blocks": blocks,
        "negative_control_status": negative_status,
        "main_correlations": correlations,
    }


def _publication_acceptance(
    bayesian: dict[str, pd.DataFrame],
    sensitivities: dict[str, pd.DataFrame],
    negative_controls: dict[str, pd.DataFrame],
    classical: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    effects = bayesian["effects"]
    negative = classical["negative_control_status"]
    outcomes = [str(value) for value in config["outcomes"]["confirmatory"]]
    sensitivity_effects = sensitivities["effects"]
    commune_loo = sensitivities["commune_loo_effects"]
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        spatial = effects[
            (effects["outcome"] == outcome)
            & (effects["exposure"] == "pm25_hist")
            & (effects["model"] == "nb_bym2_exposure")
        ]
        nonspatial = effects[
            (effects["outcome"] == outcome)
            & (effects["exposure"] == "pm25_hist")
            & (effects["model"] == "nb_nonspatial_exposure")
        ]
        converged = bool(
            not spatial.empty
            and spatial.iloc[0]["diagnostics_passed"]
            and not nonspatial.empty
            and nonspatial.iloc[0]["diagnostics_passed"]
        )
        if spatial.empty or nonspatial.empty:
            direction_stable = False
            hdi_excludes = False
            probability = False
        else:
            direction_stable = bool(
                (float(spatial.iloc[0]["rr_per_sd"]) - 1)
                * (float(nonspatial.iloc[0]["rr_per_sd"]) - 1)
                > 0
            )
            hdi_excludes = bool(
                float(spatial.iloc[0]["hdi_95_low"]) > 1
                or float(spatial.iloc[0]["hdi_95_high"]) < 1
            )
            probability = bool(
                float(spatial.iloc[0]["probability_direction"])
                >= float(config["evidence"]["minimum_direction_probability"])
            )
        classical_row = classical["main_correlations"]
        classical_row = classical_row[
            (classical_row["outcome"] == outcome)
            & (classical_row["exposure"] == "pm25_hist")
            & (classical_row["method"] == "partial_spearman_core")
        ]
        not_influential = bool(
            not classical_row.empty and not classical_row.iloc[0]["loo_sign_change"]
        )
        sensitivity_rows = sensitivity_effects[sensitivity_effects["outcome"] == outcome]
        loo_rows = commune_loo[commune_loo["outcome"] == outcome]
        main_direction = (
            0 if spatial.empty else int(np.sign(float(spatial.iloc[0]["rr_per_sd"]) - 1))
        )
        sensitivity_complete = bool(
            len(sensitivity_rows) == 5
            and sensitivity_rows["diagnostics_passed"].all()
            and len(loo_rows) == 52
            and loo_rows["diagnostics_passed"].all()
        )
        sensitivity_direction_stable = bool(
            sensitivity_complete
            and (np.sign(sensitivity_rows["rr_per_sd"].astype(float) - 1) == main_direction).all()
            and (np.sign(loo_rows["rr_per_sd"].astype(float) - 1) == main_direction).all()
        )
        row = {
            "outcome": outcome,
            "converged": converged,
            "nb_bym2_direction_stable": direction_stable,
            "hdi_excludes_one": hdi_excludes,
            "direction_probability_passed": probability,
            "not_dominated_by_classical_loo_sign_change": not_influential,
            "sensitivity_models_complete": sensitivity_complete,
            "year_access_prior_and_commune_direction_stable": sensitivity_direction_stable,
        }
        row["accepted"] = all(row.values())
        rows.append(row)
    control_effects = negative_controls["effects"]
    control_ready = bool(
        negative["available_in_materialized_smr"].all()
        and len(control_effects) == 2
        and control_effects["diagnostics_passed"].all()
    )
    if control_ready:
        robust_control_signal = (
            (
                (control_effects["hdi_95_low"].astype(float) > 1)
                | (control_effects["hdi_95_high"].astype(float) < 1)
            )
            & (
                control_effects["probability_direction"].astype(float)
                >= float(config["evidence"]["minimum_direction_probability"])
            )
        )
        negative_control_clear = bool(not robust_control_signal.any())
    else:
        negative_control_clear = False
    all_models = bool(rows and all(row["accepted"] for row in rows))
    return {
        "status": (
            "accepted" if all_models and control_ready and negative_control_clear else "not_accepted"
        ),
        "all_five_pm25_models_passed": all_models,
        "negative_control_ready": control_ready,
        "negative_control_clear": negative_control_clear,
        "sensitivities_complete": bool(
            len(sensitivity_effects) == 25 and len(commune_loo) == 260
        ),
        "reason": (
            None
            if all_models and control_ready and negative_control_clear
            else "Publication requires all diagnostics, stable year/access/prior/commune fits, and clear PM2.5/NO2 injury controls."
        ),
        "outcomes": rows,
    }


def _required_posterior_variables(
    *, spatial: bool, include_exposure: bool
) -> list[str]:
    variables = ["intercept", "gamma", "alpha", "mu"]
    if include_exposure:
        variables.append("beta")
    if spatial:
        variables.extend(["theta", "phi", "sigma", "rho"])
    return variables


def _task_model_inputs(
    task: ModelTask,
    smr: pd.DataFrame,
    annual: pd.DataFrame,
    exposures: pd.DataFrame,
    graph: Any,
    config: dict[str, Any],
) -> tuple[Any, bool, bool, list[float] | None, np.ndarray | None, dict[str, Any]]:
    definitions = exposure_definitions(config)
    primary_label = str(config["windows"]["primary"])
    primary = smr[smr["window"] == primary_label].copy()
    outcome_frame = primary
    window = primary_label
    covariates = config["covariates"]["core"]
    rho_prior = None
    metadata: dict[str, Any] = {}
    if task.phase == "sensitivities":
        if task.variant == "year_2018_core":
            outcome_frame = _aggregate_annual_window(annual, [2018], "year_2018")
            window = "year_2018"
        elif task.variant == "year_2019_core":
            outcome_frame = _aggregate_annual_window(annual, [2019], "year_2019")
            window = "year_2019"
        elif task.variant == "covid_2018_2020_core":
            window = str(config["windows"]["covid_sensitivity"])
            outcome_frame = smr[smr["window"] == window].copy()
        elif task.variant == "primary_access":
            covariates = config["covariates"]["access"]
        elif task.variant == "primary_rho_uniform":
            rho_prior = list(config["bym2"]["rho_prior_sensitivity"])
        else:
            raise ValueError(f"Unknown sensitivity variant: {task.variant}")
        metadata["sensitivity"] = task.variant
    definition = definitions[task.exposure]
    data = prepare_bayesian_model_data(
        outcome_frame,
        exposures,
        graph,
        outcome=task.outcome,
        exposure_name=task.exposure,
        source_column=str(definition["source_column"]),
        covariates=covariates,
        window=window,
    )
    spatial = task.model_name != "nb_nonspatial_exposure"
    include_exposure = task.model_name != "nb_bym2_null"
    observed_indices = None
    if task.phase == "commune-loo":
        try:
            excluded_index = data.spatial_ids.index(str(task.excluded_spatial_id))
        except ValueError as exc:
            raise ValueError(
                f"Unknown excluded spatial id: {task.excluded_spatial_id}"
            ) from exc
        observed_indices = np.delete(np.arange(len(data.observed)), excluded_index)
        metadata.update(
            {
                "excluded_spatial_id": task.excluded_spatial_id,
                "excluded_spatial_name": data.spatial_names[excluded_index],
            }
        )
    return (
        data,
        spatial,
        include_exposure,
        rho_prior,
        observed_indices,
        metadata,
    )


def _fit_registered_task(
    task: ModelTask,
    store: InferenceRunStore,
    smr: pd.DataFrame,
    annual: pd.DataFrame,
    exposures: pd.DataFrame,
    graph: Any,
    config: dict[str, Any],
    *,
    progressbar: bool,
) -> dict[str, Any]:
    (
        data,
        spatial,
        include_exposure,
        rho_prior,
        observed_indices,
        metadata,
    ) = _task_model_inputs(task, smr, annual, exposures, graph, config)
    bym2 = config["bym2"]

    def factory() -> Any:
        return build_pymc_nb_model(
            data,
            graph,
            bym2,
            spatial=spatial,
            include_exposure=include_exposure,
            rho_prior=rho_prior,
            observed_indices=observed_indices,
        )

    idata, diagnostics = fit_with_diagnostic_retry(
        factory,
        bym2,
        seed=stable_seed(int(config["seed"]), task.model_id),
        progressbar=progressbar,
    )
    diagnostics.update(
        {
            "outcome": task.outcome,
            "exposure": task.exposure,
            "window": data.window,
            "model": task.model_name,
            **metadata,
        }
    )
    effect = None
    if include_exposure:
        effect = summarize_bayesian_effect(
            idata, data, rope_rr=config["evidence"]["rope_rr"]
        )
        effect.update(
            {
                "model": task.model_name,
                "diagnostics_passed": diagnostics["diagnostics_passed"],
                "status": diagnostics["status"],
                **metadata,
            }
        )
    extras: dict[str, Any] = {}
    if task.phase == "primary":
        if diagnostics["diagnostics_passed"]:
            loo = psis_loo_with_exact_refits(
                idata,
                data,
                graph,
                bym2,
                spatial=spatial,
                include_exposure=include_exposure,
                rho_prior=rho_prior,
                seed=stable_seed(int(config["seed"]), task.model_id, "loo"),
                trace_dir=store.traces_dir / "reloo" / task.model_id,
                trace_prefix=task.model_id,
                progressbar=progressbar,
            )
            extras["loo"] = loo
            if task.model_name == "nb_bym2_exposure":
                ppc, ppc_communes = posterior_predictive_checks(
                    idata,
                    data,
                    seed=stable_seed(int(config["seed"]), task.model_id, "ppc"),
                )
                ppc.insert(0, "exposure", task.exposure)
                ppc.insert(0, "outcome", task.outcome)
                ppc_communes.insert(0, "exposure", task.exposure)
                ppc_communes.insert(0, "outcome", task.outcome)
                extras["ppc"] = ppc.to_dict(orient="records")
                extras["ppc_communes"] = ppc_communes.to_dict(orient="records")
        else:
            extras["loo"] = {"status": "excluded_failed_diagnostics"}
    return store.save_record(
        task,
        idata,
        diagnostics=diagnostics,
        effect=effect,
        extras=extras,
        required_variables=_required_posterior_variables(
            spatial=spatial, include_exposure=include_exposure
        ),
    )


def _aggregate_phase_records(
    phase: str,
    tasks: list[ModelTask],
    store: InferenceRunStore,
) -> dict[str, pd.DataFrame]:
    records = store.records(tasks)
    diagnostics = pd.DataFrame([record["diagnostics"] for record in records])
    effects = pd.DataFrame(
        [record["effect"] for record in records if record.get("effect") is not None]
    )
    if phase == "primary":
        loo_rows: list[dict[str, Any]] = []
        ppc_rows: list[dict[str, Any]] = []
        ppc_commune_rows: list[dict[str, Any]] = []
        for record in records:
            loo = record.get("extras", {}).get("loo", {})
            if loo.get("status") == "excluded_failed_diagnostics":
                loo_rows.append(
                    {
                        "outcome": record["outcome"],
                        "exposure": record["exposure"],
                        "model": record["model_name"],
                        "status": "excluded_failed_diagnostics",
                    }
                )
            elif loo:
                loo_rows.append(
                    {
                        "outcome": record["outcome"],
                        "exposure": record["exposure"],
                        "model": record["model_name"],
                        "status": "ok",
                        **{key: value for key, value in loo.items() if key != "reloo"},
                        "reloo_details": json.dumps(loo.get("reloo", [])),
                    }
                )
            ppc_rows.extend(record.get("extras", {}).get("ppc", []))
            ppc_commune_rows.extend(
                record.get("extras", {}).get("ppc_communes", [])
            )
        tables = {
            "effects": effects,
            "diagnostics": diagnostics,
            "loo": pd.DataFrame(loo_rows),
            "ppc": pd.DataFrame(ppc_rows),
            "ppc_communes": pd.DataFrame(ppc_commune_rows),
        }
        paths = {
            "effects": "bym2_effects.csv",
            "diagnostics": "bym2_diagnostics.csv",
            "loo": "bym2_model_comparison_loo.csv",
            "ppc": "posterior_predictive_checks.csv",
            "ppc_communes": "posterior_predictive_communes.csv",
        }
    elif phase == "negative-controls":
        tables = {"effects": effects, "diagnostics": diagnostics}
        paths = {
            "effects": "negative_control_bym2_effects.csv",
            "diagnostics": "negative_control_bym2_diagnostics.csv",
        }
    elif phase == "sensitivities":
        tables = {"effects": effects, "diagnostics": diagnostics}
        paths = {
            "effects": "bym2_sensitivity_effects.csv",
            "diagnostics": "bym2_sensitivity_diagnostics.csv",
        }
    elif phase == "commune-loo":
        tables = {
            "commune_loo_effects": effects,
            "commune_loo_diagnostics": diagnostics,
        }
        paths = {
            "commune_loo_effects": "bym2_commune_leave_one_out_effects.csv",
            "commune_loo_diagnostics": "bym2_commune_leave_one_out_diagnostics.csv",
        }
    else:
        raise ValueError(f"Unknown sampling phase: {phase}")
    for key, table in tables.items():
        atomic_write_csv(table, store.output_dir / paths[key])
    return tables


def _run_sampling_phase(
    phase: str,
    tasks: list[ModelTask],
    store: InferenceRunStore,
    smr: pd.DataFrame,
    annual: pd.DataFrame,
    exposures: pd.DataFrame,
    graph: Any,
    config: dict[str, Any],
    *,
    resume: bool,
    rerun_failed: bool,
    progressbar: bool,
) -> dict[str, pd.DataFrame]:
    try:
        import arviz  # noqa: F401
        import h5netcdf  # noqa: F401
        import h5py  # noqa: F401
        import pymc  # noqa: F401
    except ImportError as exc:
        raise InferenceStateError(
            "Sampling dependencies are incomplete; run "
            "`uv sync --extra dev --extra spatial` before MCMC"
        ) from exc
    selected = [task for task in tasks if task.phase == phase]
    preflight = store.preflight(
        selected, resume=resume, rerun_failed=rerun_failed
    )
    typer.echo(
        f"{phase}: {preflight['pending_models']} pending, "
        f"{preflight['completed_models']} reusable; "
        f"{preflight['free_gib']:.1f} GiB free"
    )
    for index, task in enumerate(selected, start=1):
        record = store.reusable_record(
            task, resume=resume, rerun_failed=rerun_failed
        )
        if record is not None:
            typer.echo(f"[{index}/{len(selected)}] reuse {task.model_id}")
            continue
        typer.echo(f"[{index}/{len(selected)}] sample {task.model_id}")
        _fit_registered_task(
            task,
            store,
            smr,
            annual,
            exposures,
            graph,
            config,
            progressbar=progressbar,
        )
        _aggregate_phase_records(phase, selected, store)
    return _aggregate_phase_records(phase, selected, store)


def _classical_marker_path(output_dir: Path) -> Path:
    return output_dir / "run_state" / "classical.json"


def _require_matching_classical(output_dir: Path, fingerprint: str) -> None:
    marker_path = _classical_marker_path(output_dir)
    if not marker_path.exists():
        raise InferenceStateError(
            "Classical products are missing. Run --mode classical before sampling."
        )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("scientific_fingerprint") != fingerprint:
        raise InferenceStateError(
            "Classical products were generated from different inputs/configuration; "
            "rerun --mode classical in a new output directory."
        )


def _load_classical_products(output_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "main_correlations": pd.read_csv(output_dir / "classical_correlations.csv"),
        "negative_control_status": pd.read_csv(
            output_dir / "negative_control_status.csv"
        ),
    }


def _finalize_publication(
    all_tasks: list[ModelTask],
    store: InferenceRunStore,
    config: dict[str, Any],
    required_inputs: list[Path],
) -> dict[str, Any]:
    state_rows = store.status_rows(
        all_tasks, resume=True, rerun_failed=False
    )
    invalid = [row for row in state_rows if row["state"] == "invalid"]
    if invalid:
        raise InferenceStateError(
            f"Cannot finalize with invalid model state: {invalid[0]['reason']}"
        )
    phase_tables = {
        phase: _aggregate_phase_records(
            phase, [task for task in all_tasks if task.phase == phase], store
        )
        for phase in ("primary", "negative-controls", "sensitivities", "commune-loo")
    }
    counts = {
        phase: sum(
            row["phase"] == phase and row["state"] in {"ok", "failed_diagnostics"}
            for row in state_rows
        )
        for phase in phase_tables
    }
    expected = {
        "primary": 15,
        "negative-controls": 2,
        "sensitivities": 25,
        "commune-loo": 260,
    }
    complete = counts == expected
    if complete:
        acceptance = _publication_acceptance(
            phase_tables["primary"],
            {
                **phase_tables["sensitivities"],
                **phase_tables["commune-loo"],
            },
            phase_tables["negative-controls"],
            _load_classical_products(store.output_dir),
            config,
        )
    else:
        acceptance = {
            "status": "incomplete",
            "model_counts": counts,
            "expected_model_counts": expected,
            "reason": "All registered phases must be terminal before publication finalization.",
        }
    acceptance["model_counts"] = counts
    acceptance_path = store.output_dir / "publication_acceptance.json"
    atomic_write_json(acceptance_path, acceptance)
    manifest_files = [
        *required_inputs,
        *[
            path
            for path in store.output_dir.rglob("*")
            if path.is_file()
            and path.suffix in {".csv", ".json"}
            and path.name != "manifest.json"
        ],
    ]
    manifest = build_inference_manifest(
        REPO_ROOT,
        config,
        manifest_files,
        run_mode="publication",
        status=str(acceptance["status"]),
    )
    manifest["scientific_fingerprint"] = store.fingerprint
    manifest["model_counts"] = counts
    atomic_write_json(store.output_dir / "manifest.json", manifest)
    return acceptance


@app.command()
def run(
    study: str = typer.Option(
        "santiago_communes", help="Canonical study id; legacy city configs are rejected"
    ),
    mode: str = typer.Option(
        "classical", help="classical, bayesian, or publication"
    ),
    phase: str = typer.Option(
        "all",
        help=(
            "Publication stage: primary, negative-controls, sensitivities, "
            "commune-loo, finalize, status, or all"
        ),
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Validate and reuse terminal model sidecars and NetCDF traces",
    ),
    rerun_failed: bool = typer.Option(
        False,
        help="Explicitly replace models whose terminal status is failed_diagnostics",
    ),
    dry_run: bool = typer.Option(
        False,
        help="Show registered tasks, saved state, gates, and storage without sampling",
    ),
    bayesian_family: list[str] = typer.Option(
        ["confirmatory_chronic"],
        "--bayesian-family",
        help="Hypothesis family to sample; repeat for multiple families",
    ),
    include_exploratory_outcomes: bool = typer.Option(
        False, help="Materialize the separate ten-outcome appendix family"
    ),
    elastic_net: bool = typer.Option(
        True, "--elastic-net/--no-elastic-net", help="Run exploratory nested elastic-net"
    ),
    progressbar: bool = typer.Option(
        True, "--progressbar/--no-progressbar", help="Show PyMC sampling progress"
    ),
    bootstrap_samples: int | None = typer.Option(
        None, min=0, help="Explicit smoke-run override; default comes from the protocol"
    ),
    moran_permutations: int | None = typer.Option(
        None, min=99, help="Explicit smoke-run override; default is 9,999"
    ),
    horn_permutations: int | None = typer.Option(
        None, min=10, help="Explicit smoke-run override; default is 1,000"
    ),
    stability_resamples: int | None = typer.Option(
        None, min=0, help="Explicit smoke-run override; default is 500"
    ),
    output_dir_override: Path | None = typer.Option(
        None,
        "--output-dir",
        help="Optional isolated output directory for smoke/validation runs",
    ),
) -> None:
    if study != "santiago_communes":
        raise typer.BadParameter("This registered inference is fixed to santiago_communes")
    if mode not in {"classical", "bayesian", "publication"}:
        raise typer.BadParameter("mode must be classical, bayesian, or publication")
    valid_phases = {
        "primary",
        "negative-controls",
        "sensitivities",
        "commune-loo",
        "finalize",
        "status",
        "all",
    }
    if phase not in valid_phases:
        raise typer.BadParameter(f"phase must be one of {sorted(valid_phases)}")
    resolved = load_config(study)
    config = deepcopy(resolved["neuro_hospitalizations"]["analysis"]["inference"])
    validate_inference_config(config)
    overrides = {}
    if bootstrap_samples is not None:
        config["correlations"]["bootstrap_samples"] = bootstrap_samples
        overrides["bootstrap_samples"] = bootstrap_samples
    if moran_permutations is not None:
        config["correlations"]["bivariate_moran_permutations"] = moran_permutations
        overrides["moran_permutations"] = moran_permutations
    if horn_permutations is not None:
        config["joint_exposome"]["horn_permutations"] = horn_permutations
        overrides["horn_permutations"] = horn_permutations
    if stability_resamples is not None:
        config["joint_exposome"]["stability_resamples"] = stability_resamples
        overrides["stability_resamples"] = stability_resamples
    config["run_overrides"] = overrides

    input_paths = {key: _path(value) for key, value in config["inputs"].items()}
    protocol_path = _path(config["protocol"])
    required = [
        input_paths["smr"],
        input_paths["annual_expected"],
        input_paths["exposures"],
        input_paths["master"],
        input_paths["geometry"],
        input_paths["mortality"],
        protocol_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing materialized inference inputs: {missing}")

    smr = _read_csv(input_paths["smr"])
    annual = _read_csv(input_paths["annual_expected"])
    raw_exposures = _read_csv(input_paths["exposures"])
    master = _read_csv(input_paths["master"])
    mortality = _read_csv(input_paths["mortality"])
    exposures = augment_exposure_matrix(raw_exposures, master)
    geometry = gpd.read_file(input_paths["geometry"])
    geometry["spatial_id"] = normalise_spatial_id(geometry["spatial_id"])
    output_dir = _path(output_dir_override or config["output_dir"])
    if output_dir_override is not None:
        config["run_overrides"]["output_dir"] = str(output_dir_override)
    output_dir.mkdir(parents=True, exist_ok=True)
    products: list[Path] = []
    # The scientific fingerprint follows materialized data plus the explicit
    # protocol_version. The manifest still hashes the Markdown protocol, but a
    # typo or documentation link edit must not invalidate multi-day MCMC state.
    input_hashes = {
        str(path.relative_to(REPO_ROOT)): file_sha256(path)
        for path in required
        if path != protocol_path
    }
    fingerprint = scientific_fingerprint(config, input_hashes)
    graph = build_queen_graph(geometry)
    all_tasks = publication_tasks(config, list(graph.spatial_ids))
    store = InferenceRunStore(output_dir, fingerprint)
    negative_status = negative_control_availability(smr, config)

    if phase == "status" or dry_run:
        selected = (
            all_tasks
            if phase in {"all", "status"}
            else [task for task in all_tasks if task.phase == phase]
        )
        rows = pd.DataFrame(
            store.status_rows(
                selected, resume=resume, rerun_failed=rerun_failed
            )
        )
        summary = (
            rows.groupby(["phase", "state"]).size().rename("models").reset_index()
        )
        typer.echo(summary.to_string(index=False))
        typer.echo(
            "negative_control_ready="
            f"{bool(negative_status['available_in_materialized_smr'].all())}"
        )
        if not rows["state"].eq("invalid").any():
            preflight = store.preflight(
                selected, resume=resume, rerun_failed=rerun_failed
            )
            typer.echo(json.dumps(preflight, indent=2))
        if dry_run or phase == "status":
            return

    run_status = "classical_complete"
    if mode == "classical" or (mode == "publication" and phase == "all"):
        _classical_products(
            smr,
            annual,
            exposures,
            mortality,
            geometry,
            config,
            output_dir,
            products,
            include_exploratory_outcomes=include_exploratory_outcomes,
            run_elastic_net=elastic_net,
        )
        atomic_write_json(
            _classical_marker_path(output_dir),
            {
                "schema_version": 1,
                "scientific_fingerprint": fingerprint,
                "input_hashes": input_hashes,
            },
        )
        products.append(_classical_marker_path(output_dir))
        if mode == "classical":
            manifest = build_inference_manifest(
                REPO_ROOT,
                config,
                [*required, *products],
                run_mode=mode,
                status=run_status,
            )
            manifest["scientific_fingerprint"] = fingerprint
            atomic_write_json(output_dir / "manifest.json", manifest)
    if mode == "classical":
        pass
    else:
        if set(bayesian_family) != {"confirmatory_chronic"}:
            raise typer.BadParameter(
                "The registered staged Bayesian workflow samples confirmatory_chronic only"
            )
        if mode == "bayesian" and phase == "all":
            phase = "primary"
        _require_matching_classical(output_dir, fingerprint)
        if phase == "finalize":
            acceptance = _finalize_publication(
                all_tasks, store, config, required
            )
            run_status = f"publication_{acceptance['status']}"
        else:
            if not negative_status["available_in_materialized_smr"].all():
                raise InferenceStateError(
                    "Publication sampling is blocked because injury_poisoning is absent "
                    "from the materialized SMR. Run `.venv/bin/python "
                    "scripts/run_hospitalization_exposome_analysis.py`, then rerun the "
                    "classical phase before starting MCMC."
                )
            phases = (
                ["primary", "negative-controls", "sensitivities", "commune-loo"]
                if phase == "all"
                else [phase]
            )
            for selected_phase in phases:
                _run_sampling_phase(
                    selected_phase,
                    all_tasks,
                    store,
                    smr,
                    annual,
                    exposures,
                    graph,
                    config,
                    resume=resume,
                    rerun_failed=rerun_failed,
                    progressbar=progressbar,
                )
            if phase == "all":
                acceptance = _finalize_publication(
                    all_tasks, store, config, required
                )
                run_status = f"publication_{acceptance['status']}"
            else:
                run_status = f"{phase}_complete"
    try:
        display_output = output_dir.relative_to(REPO_ROOT)
    except ValueError:
        display_output = output_dir
    typer.echo(f"Wrote inference products to {display_output}")
    typer.echo(f"Run status: {run_status}")


def main() -> None:
    """Run the Typer entrypoint with concise state-error reporting."""
    try:
        app()
    except InferenceStateError as exc:
        typer.echo(f"Inference state error: {exc}", err=True)
        raise SystemExit(2) from None
