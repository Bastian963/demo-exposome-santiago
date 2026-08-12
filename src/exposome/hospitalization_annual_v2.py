"""Annual exposome--hospitalization inference for Santiago (protocol v2).

The module only consumes materialized aggregate artifacts.  It deliberately
contains no provider or Earth Engine client and never reads individual DEIS
records.  Preparation, screening and Bayesian tasks are independently
checkpointed by the thin runner in :mod:`hospitalization_annual_v2_runner`.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm
import yaml
from sklearn.decomposition import PCA
from sklearn.model_selection import GroupKFold
from statsmodels.stats.multitest import multipletests

from exposome.hospitalization_inference import (
    SpatialGraph,
    extract_loo_result,
    require_bayesian_dependencies,
    sample_pymc_model,
    stable_seed,
)
from exposome.inference_run_state import ModelTask, atomic_write_csv, atomic_write_json


EXPECTED_SCOPE = {
    "product": "offline_data_analysis",
    "webapp": False,
    "exposome_master": False,
    "automated_publish": False,
}


@dataclass(frozen=True)
class AnnualExposureSpec:
    id: str
    layer: str
    column: str
    direction: int
    expected_years: tuple[int, ...]
    core_mixture: bool = False
    bayesian_primary: bool = False
    sensitivity: bool = False
    replaces: str | None = None
    limited_overlap: bool = False


@dataclass(frozen=True)
class PanelBayesianData:
    """Aligned arrays for one outcome/exposure/timing panel model."""

    spatial_ids: tuple[str, ...]
    spatial_names: tuple[str, ...]
    years: tuple[int, ...]
    observed: np.ndarray
    expected: np.ndarray
    area_index: np.ndarray
    year_design: np.ndarray
    year_names: tuple[str, ...]
    exposure_within: np.ndarray
    exposure_between: np.ndarray
    deprivation: np.ndarray
    interaction: np.ndarray
    outcome: str
    exposure_name: str
    timing: str
    window: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalise_spatial_id(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    numeric = pd.to_numeric(values, errors="coerce")
    integer = numeric.notna() & np.isclose(numeric % 1, 0)
    values.loc[integer] = numeric.loc[integer].astype("Int64").astype("string")
    return values.astype(str)


def load_analysis_config(path: Path) -> dict[str, Any]:
    path = Path(path)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Analysis config must be a mapping: {path}")
    validate_analysis_config(config)
    return config


def validate_analysis_config(config: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "study",
        "protocol",
        "protocol_version",
        "seed",
        "scope",
        "annual_artifact_contract",
        "paths",
        "windows",
        "outcomes",
        "exposures",
        "socioeconomic",
        "joint_exposome",
        "screening",
        "bym2",
        "evidence",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Annual hospitalization config is missing: {missing}")
    if int(config["schema_version"]) != 1:
        raise ValueError("Unsupported annual hospitalization config schema")
    if dict(config["scope"]) != EXPECTED_SCOPE:
        raise ValueError("Annual hospitalization inference must remain offline-only")
    timings = list(config["windows"].get("timings", []))
    if timings != ["same_year", "lag1"]:
        raise ValueError("timings must be exactly [same_year, lag1]")
    primary = list(config["outcomes"].get("primary", []))
    if len(primary) != 5 or len(set(primary)) != 5:
        raise ValueError("Exactly five unique primary outcomes are required")
    specs = exposure_specs(config, include_sensitivities=True)
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("Exposure ids must be unique")
    if {spec.direction for spec in specs}.difference({-1, 1}):
        raise ValueError("Exposure directions must be -1 or +1")
    core = [spec for spec in specs if spec.core_mixture]
    minimum = int(config["joint_exposome"]["minimum_complete_components"])
    if len(core) != minimum:
        raise ValueError(
            "minimum_complete_components must match the prespecified core mixture"
        )


def exposure_specs(
    config: Mapping[str, Any], *, include_sensitivities: bool = False
) -> list[AnnualExposureSpec]:
    rows: list[tuple[Mapping[str, Any], bool]] = [
        (item, False) for item in config["exposures"]
    ]
    if include_sensitivities:
        rows.extend((item, True) for item in config.get("method_sensitivities", []))
    return [
        AnnualExposureSpec(
            id=str(item["id"]),
            layer=str(item["layer"]),
            column=str(item["column"]),
            direction=int(item["direction"]),
            expected_years=tuple(int(year) for year in item["expected_years"]),
            core_mixture=bool(item.get("core_mixture", False)),
            bayesian_primary=bool(item.get("bayesian_primary", False)),
            sensitivity=sensitivity,
            replaces=(str(item["replaces"]) if item.get("replaces") else None),
            limited_overlap=bool(item.get("limited_overlap", False)),
        )
        for item, sensitivity in rows
    ]


def resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(repo_root) / path


def _validate_annual_artifact(
    annual_path: Path,
    manifest_path: Path,
    spec: AnnualExposureSpec,
    year: int,
    study: str,
    supported_schema_versions: Sequence[int] = (1, 2),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not manifest_path.is_file() or not annual_path.is_file():
        raise FileNotFoundError(
            f"Missing annual v2 artifact for {spec.id} {year}: {annual_path.parent}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_version = int(manifest.get("schema_version", -1))
    checks = {
        "schema_version": schema_version in {int(value) for value in supported_schema_versions},
        "study": str(manifest.get("study_id", manifest.get("study"))) == study,
        "layer": str(manifest.get("layer_id")) == spec.layer,
        "year": int(manifest.get("year", -1)) == int(year),
        "annual_table": str(manifest.get("annual_table")) == annual_path.name,
        "sha256": str(manifest.get("sha256")) == sha256_file(annual_path),
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError(
            f"Invalid annual artifact {spec.id} {year}; failed checks: {failed}"
        )
    frame = pd.read_csv(annual_path)
    required = {"spatial_id", "spatial_name", "year", spec.column}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{annual_path} is missing columns: {missing}")
    frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    if frame["spatial_id"].duplicated().any():
        raise ValueError(f"Duplicate spatial_id in {annual_path}")
    if set(frame["year"]) != {int(year)}:
        raise ValueError(f"Year content mismatch in {annual_path}")
    if int(manifest.get("n_rows", -1)) != len(frame) or len(frame) != 52:
        raise ValueError(f"Expected 52 communes in {annual_path}, found {len(frame)}")
    values = pd.to_numeric(frame[spec.column], errors="coerce")
    result = frame[["spatial_id", "spatial_name", "year"]].copy()
    result[spec.id] = values
    provenance = {
        "exposure": spec.id,
        "layer": spec.layer,
        "source_column": spec.column,
        "year": int(year),
        "n_rows": int(len(frame)),
        "n_complete": int(values.notna().sum()),
        "annual_path": str(annual_path),
        "annual_sha256": checks["sha256"] and manifest["sha256"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "source": manifest.get("source"),
        "sensitivity": spec.sensitivity,
        "manifest_schema_version": schema_version,
    }
    return result, provenance


def load_annual_exposure_panel(
    repo_root: Path,
    config: Mapping[str, Any],
    *,
    include_sensitivities: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate every annual artifact and return one commune-year wide panel."""
    root = resolve_repo_path(repo_root, config["paths"]["temporal_root"])
    supported_schema_versions = config["annual_artifact_contract"][
        "supported_schema_versions"
    ]
    combined: pd.DataFrame | None = None
    provenance: list[dict[str, Any]] = []
    for spec in exposure_specs(config, include_sensitivities=include_sensitivities):
        exposure_rows: list[pd.DataFrame] = []
        for year in spec.expected_years:
            directory = root / spec.layer / str(year)
            frame, record = _validate_annual_artifact(
                directory / "annual.csv",
                directory / "manifest.json",
                spec,
                year,
                str(config["study"]),
                supported_schema_versions,
            )
            exposure_rows.append(frame)
            provenance.append(record)
        exposure = pd.concat(exposure_rows, ignore_index=True)
        if combined is None:
            combined = exposure
        else:
            combined = combined.merge(
                exposure,
                on=["spatial_id", "year"],
                how="outer",
                suffixes=("", "__incoming"),
                validate="one_to_one",
            )
            incoming = "spatial_name__incoming"
            if incoming in combined:
                mismatch = (
                    combined["spatial_name"].notna()
                    & combined[incoming].notna()
                    & (combined["spatial_name"] != combined[incoming])
                )
                if mismatch.any():
                    raise ValueError("Annual artifacts disagree on spatial_name")
                combined["spatial_name"] = combined["spatial_name"].fillna(
                    combined[incoming]
                )
                combined = combined.drop(columns=incoming)
    if combined is None:
        raise ValueError("No annual exposures configured")
    combined = combined.sort_values(["spatial_id", "year"]).reset_index(drop=True)
    return combined, pd.DataFrame(provenance)


def load_outcomes(repo_root: Path, config: Mapping[str, Any]) -> pd.DataFrame:
    path = resolve_repo_path(repo_root, config["paths"]["outcomes"])
    frame = pd.read_csv(path)
    required = {
        "spatial_id",
        "spatial_name",
        "year",
        "outcome",
        "observed",
        "expected",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Outcome file is missing: {missing}")
    frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    frame["observed"] = pd.to_numeric(frame["observed"], errors="coerce")
    frame["expected"] = pd.to_numeric(frame["expected"], errors="coerce")
    if frame.duplicated(["spatial_id", "year", "outcome"]).any():
        raise ValueError("Outcome panel has duplicate commune-year-outcome rows")
    expected_outcomes = {
        value
        for family in ("primary", "exploratory", "negative_control")
        for value in config["outcomes"][family]
    }
    missing_outcomes = sorted(expected_outcomes.difference(frame["outcome"].unique()))
    if missing_outcomes:
        raise ValueError(f"Outcome panel lacks prespecified outcomes: {missing_outcomes}")
    return frame


def _zscore(values: pd.Series, *, mean: float | None = None, sd: float | None = None) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    mean = float(numeric.mean()) if mean is None else float(mean)
    sd = float(numeric.std(ddof=0)) if sd is None else float(sd)
    if not math.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (numeric - mean) / sd


def attach_socioeconomic_and_joint_scores(
    exposures: pd.DataFrame,
    master: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Add static deprivation, oriented components, burden and double burden."""
    exposures = exposures.copy()
    master = master.copy()
    master["spatial_id"] = normalise_spatial_id(master["spatial_id"])
    socioeconomic = config["socioeconomic"]
    columns = [
        "spatial_id",
        "spatial_name",
        str(socioeconomic["primary_column"]),
        str(socioeconomic["sensitivity_column"]),
        str(socioeconomic["quintile_column"]),
    ]
    missing = sorted(set(columns).difference(master.columns))
    if missing:
        raise ValueError(f"Master is missing socioeconomic fields: {missing}")
    if master["spatial_id"].duplicated().any() or len(master) != 52:
        raise ValueError("Master must contain exactly 52 unique communes")
    static = master[columns].copy()
    primary = str(socioeconomic["primary_column"])
    sensitivity = str(socioeconomic["sensitivity_column"])
    orientation = int(socioeconomic.get("orientation", -1))
    static["deprivation_z"] = orientation * _zscore(static[primary])
    static["deprivation_sensitivity_z"] = orientation * _zscore(static[sensitivity])
    static["deprivation_percentile"] = static["deprivation_z"].rank(pct=True)
    panel = exposures.merge(
        static.drop(columns="spatial_name"),
        on="spatial_id",
        how="left",
        validate="many_to_one",
    )
    if panel["deprivation_z"].isna().any():
        raise ValueError("Could not attach socioeconomic values to every commune")

    reference_years = set(int(year) for year in config["windows"]["burden_reference_years"])
    q_low, q_high = [float(value) for value in config["joint_exposome"]["winsor_quantiles"]]
    scaling: dict[str, Any] = {
        "reference_years": sorted(reference_years),
        "winsor_quantiles": [q_low, q_high],
        "components": {},
    }
    oriented_columns: list[str] = []
    for spec in exposure_specs(config):
        if not spec.core_mixture:
            continue
        reference = pd.to_numeric(
            panel.loc[panel["year"].isin(reference_years), spec.id], errors="coerce"
        ).dropna()
        low, high = (float(reference.quantile(q_low)), float(reference.quantile(q_high)))
        clipped_reference = reference.clip(low, high)
        mean = float(clipped_reference.mean())
        sd = float(clipped_reference.std(ddof=0))
        if not math.isfinite(sd) or sd <= 0:
            raise ValueError(f"Core exposure {spec.id} is constant in reference years")
        column = f"{spec.id}__oriented_z"
        panel[column] = spec.direction * (
            pd.to_numeric(panel[spec.id], errors="coerce").clip(low, high) - mean
        ) / sd
        oriented_columns.append(column)
        scaling["components"][spec.id] = {
            "source_column": spec.column,
            "direction": spec.direction,
            "winsor_low": low,
            "winsor_high": high,
            "mean_after_winsor": mean,
            "sd_after_winsor": sd,
        }
    minimum = int(config["joint_exposome"]["minimum_complete_components"])
    complete_count = panel[oriented_columns].notna().sum(axis=1)
    panel["environmental_burden"] = panel[oriented_columns].mean(axis=1).where(
        complete_count >= minimum
    )
    reference_burden = panel.loc[
        panel["year"].isin(reference_years), "environmental_burden"
    ].dropna()
    if reference_burden.empty:
        raise ValueError("No complete environmental burden rows in reference years")
    sorted_reference = np.sort(reference_burden.to_numpy(dtype=float))
    burden_values = panel["environmental_burden"].to_numpy(dtype=float)
    percentiles = np.full(len(panel), np.nan)
    valid = np.isfinite(burden_values)
    percentiles[valid] = np.searchsorted(
        sorted_reference, burden_values[valid], side="right"
    ) / len(sorted_reference)
    panel["environmental_burden_percentile"] = percentiles
    panel["double_burden"] = 0.5 * (
        panel["environmental_burden_percentile"] + panel["deprivation_percentile"]
    )
    scaling["burden"] = {
        "components": [spec.id for spec in exposure_specs(config) if spec.core_mixture],
        "minimum_complete_components": minimum,
        "reference_n": int(len(reference_burden)),
        "reference_mean": float(reference_burden.mean()),
        "reference_sd": float(reference_burden.std(ddof=0)),
    }
    return panel, scaling


def analysis_fingerprint(
    repo_root: Path,
    config_path: Path,
    config: Mapping[str, Any],
    provenance: pd.DataFrame,
) -> tuple[str, dict[str, str]]:
    inputs = {
        "config": sha256_file(config_path),
        "protocol": sha256_file(resolve_repo_path(repo_root, config["protocol"])),
        "implementation": sha256_file(Path(__file__)),
        "runner": sha256_file(Path(__file__).with_name("hospitalization_annual_v2_runner.py")),
        "inference_implementation": sha256_file(
            Path(__file__).with_name("hospitalization_inference.py")
        ),
        "run_state_implementation": sha256_file(
            Path(__file__).with_name("inference_run_state.py")
        ),
        "outcomes": sha256_file(resolve_repo_path(repo_root, config["paths"]["outcomes"])),
        "master": sha256_file(resolve_repo_path(repo_root, config["paths"]["master"])),
        "geometry": sha256_file(resolve_repo_path(repo_root, config["paths"]["geometry"])),
    }
    for row in provenance.itertuples(index=False):
        annual_path = resolve_repo_path(repo_root, str(row.annual_path))
        manifest_path = resolve_repo_path(repo_root, str(row.manifest_path))
        annual_hash = sha256_file(annual_path)
        manifest_hash = sha256_file(manifest_path)
        if annual_hash != str(row.annual_sha256):
            raise ValueError(f"Annual artifact changed after preparation: {annual_path}")
        if manifest_hash != str(row.manifest_sha256):
            raise ValueError(f"Annual manifest changed after preparation: {manifest_path}")
        inputs[f"annual:{row.exposure}:{row.year}"] = annual_hash
        inputs[f"manifest:{row.exposure}:{row.year}"] = manifest_hash
    return canonical_hash({"config": config, "inputs": inputs}), inputs


def annual_exposure_quality(
    panel: pd.DataFrame, config: Mapping[str, Any]
) -> pd.DataFrame:
    """Summarize coverage and genuine within-commune annual variation."""
    rows: list[dict[str, Any]] = []
    for spec in exposure_specs(config, include_sensitivities=True):
        subset = panel[["spatial_id", "year", spec.id]].dropna().copy()
        within = subset[spec.id] - subset.groupby("spatial_id")[spec.id].transform(
            "mean"
        )
        actual_years = sorted(int(value) for value in subset["year"].unique())
        rows.append(
            {
                "exposure": spec.id,
                "layer": spec.layer,
                "source_column": spec.column,
                "expected_years": ",".join(str(value) for value in spec.expected_years),
                "actual_years": ",".join(str(value) for value in actual_years),
                "year_coverage_complete": actual_years == list(spec.expected_years),
                "n_rows": int(len(subset)),
                "n_communes": int(subset["spatial_id"].nunique()),
                "n_years": int(len(actual_years)),
                "n_unique_values": int(subset[spec.id].nunique()),
                "overall_sd": float(subset[spec.id].std(ddof=0)),
                "within_commune_sd": float(within.std(ddof=0)),
                "has_within_commune_variation": bool(within.std(ddof=0) > 0),
                "limited_overlap": spec.limited_overlap,
                "sensitivity": spec.sensitivity,
            }
        )
    burden = panel[["spatial_id", "year", "environmental_burden"]].dropna()
    burden_within = burden["environmental_burden"] - burden.groupby("spatial_id")[
        "environmental_burden"
    ].transform("mean")
    rows.append(
        {
            "exposure": "environmental_burden",
            "layer": "joint_exposome",
            "source_column": "mean_of_oriented_components",
            "expected_years": "2016,2017,2018,2019,2020,2021,2022",
            "actual_years": ",".join(
                str(value) for value in sorted(burden["year"].unique())
            ),
            "year_coverage_complete": True,
            "n_rows": int(len(burden)),
            "n_communes": int(burden["spatial_id"].nunique()),
            "n_years": int(burden["year"].nunique()),
            "n_unique_values": int(burden["environmental_burden"].nunique()),
            "overall_sd": float(burden["environmental_burden"].std(ddof=0)),
            "within_commune_sd": float(burden_within.std(ddof=0)),
            "has_within_commune_variation": bool(burden_within.std(ddof=0) > 0),
            "limited_overlap": False,
            "sensitivity": False,
        }
    )
    return pd.DataFrame(rows)


def prepare_analysis(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate local inputs and materialize the immutable analysis panel."""
    config = load_analysis_config(config_path)
    output = output_dir or resolve_repo_path(repo_root, config["paths"]["output_dir"])
    exposures, provenance = load_annual_exposure_panel(repo_root, config)
    master = pd.read_csv(resolve_repo_path(repo_root, config["paths"]["master"]))
    panel, scaling = attach_socioeconomic_and_joint_scores(exposures, master, config)
    outcomes = load_outcomes(repo_root, config)
    fingerprint, input_hashes = analysis_fingerprint(
        repo_root, config_path, config, provenance
    )
    output.mkdir(parents=True, exist_ok=True)
    previous_state_path = output / "prepared_state.json"
    if previous_state_path.is_file():
        previous = json.loads(previous_state_path.read_text(encoding="utf-8"))
        downstream_exists = any(
            (output / name).exists() for name in ("screening", "joint", "bayesian")
        )
        if (
            downstream_exists
            and previous.get("scientific_fingerprint") != fingerprint
        ):
            raise ValueError(
                "The output directory contains downstream results from another "
                "scientific fingerprint; use a new --output-dir"
            )
    atomic_write_csv(panel, output / "annual_exposures.csv")
    atomic_write_csv(outcomes, output / "annual_outcomes.csv")
    atomic_write_csv(provenance, output / "annual_artifact_provenance.csv")
    atomic_write_csv(
        annual_exposure_quality(panel, config),
        output / "annual_exposure_quality.csv",
    )
    atomic_write_json(output / "burden_scaling.json", scaling)
    horn, pca_scores, pca_loadings = materialize_joint_structure(panel, config)
    atomic_write_csv(horn, output / "joint_horn_parallel_analysis.csv")
    atomic_write_csv(pca_scores, output / "joint_pca_scores.csv")
    atomic_write_csv(pca_loadings, output / "joint_pca_loadings.csv")
    state = {
        "schema_version": 1,
        "study": config["study"],
        "protocol_version": config["protocol_version"],
        "scientific_fingerprint": fingerprint,
        "input_hashes": input_hashes,
        "rows": {"exposures": len(panel), "outcomes": len(outcomes)},
        "coverage": {
            "communes": int(panel["spatial_id"].nunique()),
            "exposure_year_min": int(panel["year"].min()),
            "exposure_year_max": int(panel["year"].max()),
            "outcome_year_min": int(outcomes["year"].min()),
            "outcome_year_max": int(outcomes["year"].max()),
        },
    }
    atomic_write_json(output / "prepared_state.json", state)
    return state


def require_prepared_state(
    repo_root: Path,
    config_path: Path,
    *,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    config = load_analysis_config(config_path)
    output = output_dir or resolve_repo_path(repo_root, config["paths"]["output_dir"])
    state_path = output / "prepared_state.json"
    if not state_path.is_file():
        raise FileNotFoundError("Run --phase prepare before this phase")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    provenance = pd.read_csv(output / "annual_artifact_provenance.csv")
    current, _ = analysis_fingerprint(repo_root, config_path, config, provenance)
    if state.get("scientific_fingerprint") != current:
        raise ValueError(
            "Prepared annual-v2 inputs are stale; rerun --phase prepare in a new/clean output"
        )
    return config, state, output


def _standardize(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    sd = float(numeric.std(ddof=0))
    if not math.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=values.index, dtype=float)
    return (numeric - float(numeric.mean())) / sd


def build_timed_frame(
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    exposure: str,
    outcome: str,
    timing: str,
    outcome_years: Sequence[int],
) -> pd.DataFrame:
    """Align one annual exposure with an outcome and apply Mundlak decomposition."""
    exposures = exposures.copy()
    outcomes = outcomes.copy()
    exposures["spatial_id"] = normalise_spatial_id(exposures["spatial_id"])
    outcomes["spatial_id"] = normalise_spatial_id(outcomes["spatial_id"])
    if timing not in {"same_year", "lag1"}:
        raise ValueError(f"Unsupported timing: {timing}")
    if exposure not in exposures:
        raise ValueError(f"Exposure column does not exist: {exposure}")
    exposure_columns = [
        "spatial_id",
        "spatial_name",
        "year",
        exposure,
        "deprivation_z",
        "deprivation_sensitivity_z",
        "deprivation_percentile",
    ]
    socioeconomic = [column for column in exposures if column == "nse_quintil"]
    exposure_columns.extend(socioeconomic)
    x = exposures[exposure_columns].copy()
    x = x.rename(columns={"year": "exposure_year", exposure: "exposure_value"})
    x["outcome_year"] = x["exposure_year"] + (1 if timing == "lag1" else 0)
    y = outcomes[
        (outcomes["outcome"] == outcome)
        & outcomes["year"].isin([int(value) for value in outcome_years])
    ].copy()
    y = y.rename(columns={"year": "outcome_year"})
    frame = y.merge(
        x.drop(columns="spatial_name"),
        on=["spatial_id", "outcome_year"],
        how="inner",
        validate="one_to_one",
    )
    frame = frame[
        frame["expected"].gt(0)
        & frame["observed"].ge(0)
        & pd.to_numeric(frame["exposure_value"], errors="coerce").notna()
    ].copy()
    frame["exposure_between"] = frame.groupby("spatial_id")["exposure_value"].transform(
        "mean"
    )
    frame["exposure_within"] = frame["exposure_value"] - frame["exposure_between"]
    frame["exposure_within_z"] = _standardize(frame["exposure_within"])
    frame["exposure_between_z"] = _standardize(frame["exposure_between"])
    frame["deprivation_z"] = _standardize(frame["deprivation_z"])
    frame["interaction_z"] = frame["exposure_within_z"] * frame["deprivation_z"]
    frame["log_smr"] = np.log((frame["observed"] + 0.5) / (frame["expected"] + 0.5))
    return frame.sort_values(["spatial_id", "outcome_year"]).reset_index(drop=True)


def estimability(frame: pd.DataFrame, screening: Mapping[str, Any]) -> tuple[bool, str | None]:
    communes = int(frame["spatial_id"].nunique()) if not frame.empty else 0
    years = int(frame["outcome_year"].nunique()) if not frame.empty else 0
    if communes < int(screening["minimum_communes"]):
        return False, f"communes={communes} below minimum"
    if years < int(screening["minimum_years"]):
        return False, f"years={years} below minimum"
    if frame["exposure_within"].std(ddof=0) <= 0:
        return False, "no within-commune exposure variation"
    return True, None


def _fixed_effect_design(
    frame: pd.DataFrame,
    *,
    include_interaction: bool,
    commune_column: str = "spatial_id",
) -> pd.DataFrame:
    continuous = ["exposure_within_z"]
    if include_interaction:
        continuous.append("interaction_z")
    design = frame[continuous].astype(float).reset_index(drop=True)
    commune = pd.get_dummies(
        frame[commune_column].astype(str), prefix="commune", drop_first=True, dtype=float
    ).reset_index(drop=True)
    years = pd.get_dummies(
        frame["outcome_year"].astype(str), prefix="year", drop_first=True, dtype=float
    ).reset_index(drop=True)
    return sm.add_constant(pd.concat([design, commune, years], axis=1), has_constant="add")


def _residualize_two_way(
    frame: pd.DataFrame,
    values: str,
    *,
    commune_column: str = "spatial_id",
) -> np.ndarray:
    commune = pd.get_dummies(
        frame[commune_column].astype(str), drop_first=True, dtype=float
    ).reset_index(drop=True)
    years = pd.get_dummies(
        frame["outcome_year"].astype(str), drop_first=True, dtype=float
    ).reset_index(drop=True)
    design = sm.add_constant(pd.concat([commune, years], axis=1), has_constant="add")
    y = frame[values].to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(design.to_numpy(dtype=float), y, rcond=None)
    return y - design.to_numpy(dtype=float) @ coefficients


def residualized_spearman(
    frame: pd.DataFrame,
    *,
    bootstrap_samples: int,
    confidence: float,
    seed: int,
) -> dict[str, Any]:
    x = _residualize_two_way(frame, "exposure_value")
    y = _residualize_two_way(frame, "log_smr")
    observed = st.spearmanr(x, y).statistic
    rng = np.random.default_rng(seed)
    communes = frame["spatial_id"].drop_duplicates().to_numpy()
    simulated: list[float] = []
    for _ in range(int(bootstrap_samples)):
        selected = rng.choice(communes, size=len(communes), replace=True)
        blocks: list[pd.DataFrame] = []
        for clone, spatial_id in enumerate(selected):
            block = frame[frame["spatial_id"] == spatial_id].copy()
            block["bootstrap_commune"] = f"{clone}:{spatial_id}"
            blocks.append(block)
        sample = pd.concat(blocks, ignore_index=True)
        sample_x = _residualize_two_way(
            sample, "exposure_value", commune_column="bootstrap_commune"
        )
        sample_y = _residualize_two_way(
            sample, "log_smr", commune_column="bootstrap_commune"
        )
        value = st.spearmanr(sample_x, sample_y).statistic
        if math.isfinite(value):
            simulated.append(float(value))
    alpha = 1 - float(confidence)
    if not simulated:
        low = high = float("nan")
    else:
        low, high = np.quantile(simulated, [alpha / 2, 1 - alpha / 2])
    return {
        "spearman_residualized": float(observed),
        "spearman_ci_low": float(low),
        "spearman_ci_high": float(high),
        "spearman_bootstrap_samples": len(simulated),
    }


def _fit_ppml_core(frame: pd.DataFrame, *, include_interaction: bool = True) -> Any:
    design = _fixed_effect_design(frame, include_interaction=include_interaction)
    model = sm.GLM(
        frame["observed"].to_numpy(dtype=float),
        design,
        family=sm.families.Poisson(),
        offset=np.log(frame["expected"].to_numpy(dtype=float)),
    )
    return model.fit(
        maxiter=300,
        cov_type="cluster",
        cov_kwds={"groups": frame["spatial_id"].astype(str).to_numpy()},
    )


def fit_ppml_mundlak(frame: pd.DataFrame) -> dict[str, Any]:
    """Within/between decomposition without commune FE, clustered by commune."""
    continuous = [
        "exposure_within_z",
        "exposure_between_z",
        "deprivation_z",
        "interaction_z",
    ]
    years = pd.get_dummies(
        frame["outcome_year"].astype(str), prefix="year", drop_first=True, dtype=float
    ).reset_index(drop=True)
    design = sm.add_constant(
        pd.concat([frame[continuous].astype(float).reset_index(drop=True), years], axis=1),
        has_constant="add",
    )
    model = sm.GLM(
        frame["observed"].to_numpy(dtype=float),
        design,
        family=sm.families.Poisson(),
        offset=np.log(frame["expected"].to_numpy(dtype=float)),
    )
    result = model.fit(
        maxiter=300,
        cov_type="cluster",
        cov_kwds={"groups": frame["spatial_id"].astype(str).to_numpy()},
    )
    rows: dict[str, Any] = {"mundlak_converged": bool(result.converged)}
    for term, label in (
        ("exposure_within_z", "within"),
        ("exposure_between_z", "between"),
        ("deprivation_z", "deprivation"),
        ("interaction_z", "interaction"),
    ):
        beta = float(result.params[term])
        se = float(result.bse[term])
        rows.update(
            {
                f"mundlak_beta_{label}": beta,
                f"mundlak_se_{label}_cluster": se,
                f"mundlak_rr_{label}": float(np.exp(beta)),
                f"mundlak_rr_{label}_ci_low": float(np.exp(beta - 1.96 * se)),
                f"mundlak_rr_{label}_ci_high": float(np.exp(beta + 1.96 * se)),
                f"mundlak_p_{label}": float(result.pvalues[term]),
            }
        )
    return rows


def socioeconomic_index_sensitivity(frame: pd.DataFrame) -> dict[str, Any]:
    """Repeat SES moderation with the original (non-PCA) socioeconomic index."""
    if "deprivation_sensitivity_z" not in frame:
        return {}
    sensitivity = frame.copy()
    sensitivity["deprivation_z"] = _standardize(
        sensitivity["deprivation_sensitivity_z"]
    )
    sensitivity["interaction_z"] = (
        sensitivity["exposure_within_z"] * sensitivity["deprivation_z"]
    )
    fixed = _fit_ppml_core(sensitivity)
    mundlak = fit_ppml_mundlak(sensitivity)
    return {
        "ses_sensitivity_index": "nse_index",
        "ses_sensitivity_beta_interaction": float(fixed.params["interaction_z"]),
        "ses_sensitivity_se_interaction_cluster": float(fixed.bse["interaction_z"]),
        "ses_sensitivity_p_interaction": float(fixed.pvalues["interaction_z"]),
        "ses_sensitivity_mundlak_beta_deprivation": mundlak[
            "mundlak_beta_deprivation"
        ],
        "ses_sensitivity_mundlak_p_deprivation": mundlak[
            "mundlak_p_deprivation"
        ],
    }


def fit_ppml_fixed_effects(
    frame: pd.DataFrame,
    *,
    leave_one_commune_out: bool,
) -> tuple[dict[str, Any], np.ndarray]:
    """PPML commune/year FE; static between/SES main effects are absorbed."""
    result = _fit_ppml_core(frame)
    beta = float(result.params["exposure_within_z"])
    se = float(result.bse["exposure_within_z"])
    interaction = float(result.params.get("interaction_z", np.nan))
    interaction_se = float(result.bse.get("interaction_z", np.nan))
    rows = {
        "ppml_beta_within": beta,
        "ppml_se_within_cluster": se,
        "ppml_rr_within": float(np.exp(beta)),
        "ppml_rr_ci_low": float(np.exp(beta - 1.96 * se)),
        "ppml_rr_ci_high": float(np.exp(beta + 1.96 * se)),
        "ppml_p_value": float(result.pvalues["exposure_within_z"]),
        "ppml_beta_interaction": interaction,
        "ppml_se_interaction_cluster": interaction_se,
        "ppml_rr_interaction": float(np.exp(interaction)),
        "ppml_interaction_p_value": float(result.pvalues.get("interaction_z", np.nan)),
        "ppml_converged": bool(result.converged),
        "ppml_deviance": float(result.deviance),
    }
    if leave_one_commune_out:
        coefficients: list[float] = []
        failures = 0
        for spatial_id in frame["spatial_id"].drop_duplicates():
            subset = frame[frame["spatial_id"] != spatial_id].copy()
            try:
                fit = _fit_ppml_core(subset)
                coefficients.append(float(fit.params["exposure_within_z"]))
            except Exception:
                failures += 1
        rows.update(
            {
                "loo_communes_succeeded": len(coefficients),
                "loo_communes_failed": failures,
                "loo_beta_min": float(min(coefficients)) if coefficients else np.nan,
                "loo_beta_max": float(max(coefficients)) if coefficients else np.nan,
                "loo_sign_stable": bool(
                    coefficients
                    and all(value >= 0 for value in coefficients)
                    or coefficients
                    and all(value <= 0 for value in coefficients)
                ),
            }
        )
    return rows, np.asarray(result.resid_pearson, dtype=float)


def socioeconomic_stratified_ppml(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Descriptive within-commune effects by static socioeconomic quintile."""
    if "nse_quintil" not in frame:
        return []
    rows: list[dict[str, Any]] = []
    for quintile, subset in frame.groupby("nse_quintil", dropna=True):
        subset = subset.copy()
        base = {
            "nse_quintile": int(quintile),
            "n": int(len(subset)),
            "n_communes": int(subset["spatial_id"].nunique()),
            "n_years": int(subset["outcome_year"].nunique()),
            "interpretation": "descriptive_heterogeneity_only",
        }
        if (
            base["n_communes"] < 8
            or base["n_years"] < 3
            or subset["exposure_within_z"].std(ddof=0) <= 0
        ):
            rows.append({**base, "status": "not_estimable"})
            continue
        try:
            result = _fit_ppml_core(subset, include_interaction=False)
            beta = float(result.params["exposure_within_z"])
            se = float(result.bse["exposure_within_z"])
            rows.append(
                {
                    **base,
                    "status": "ok",
                    "beta_within": beta,
                    "se_cluster": se,
                    "rr_within": float(np.exp(beta)),
                    "rr_ci_low": float(np.exp(beta - 1.96 * se)),
                    "rr_ci_high": float(np.exp(beta + 1.96 * se)),
                    "p_value_descriptive": float(result.pvalues["exposure_within_z"]),
                }
            )
        except Exception as exc:
            rows.append(
                {**base, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
            )
    return rows


def residual_moran(
    frame: pd.DataFrame,
    residuals: np.ndarray,
    graph: SpatialGraph,
    *,
    permutations: int,
    seed: int,
) -> dict[str, Any]:
    residual_frame = frame[["spatial_id"]].copy()
    residual_frame["residual"] = residuals
    aggregate = residual_frame.groupby("spatial_id", as_index=True)["residual"].mean()
    if set(aggregate.index) != set(graph.spatial_ids):
        return {
            "residual_moran_i": np.nan,
            "residual_moran_p": np.nan,
            "residual_moran_reason": "incomplete graph coverage",
        }
    values = aggregate.reindex(graph.spatial_ids).to_numpy(dtype=float)
    centered = values - values.mean()
    weights = graph.adjacency.astype(float)
    row_sums = weights.sum(axis=1)
    weights = weights / row_sums[:, None]
    denominator = float(centered @ centered)
    observed = float(len(values) / weights.sum() * (centered @ weights @ centered) / denominator)
    rng = np.random.default_rng(seed)
    simulated = np.empty(int(permutations), dtype=float)
    for index in range(int(permutations)):
        permuted = rng.permutation(centered)
        simulated[index] = float(
            len(values) / weights.sum() * (permuted @ weights @ permuted) / denominator
        )
    p_value = float(
        (1 + np.sum(np.abs(simulated - simulated.mean()) >= abs(observed - simulated.mean())))
        / (len(simulated) + 1)
    )
    return {
        "residual_moran_i": observed,
        "residual_moran_p": p_value,
        "residual_moran_permutations": int(permutations),
        "residual_moran_reason": None,
    }


def screen_one_pair(
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    graph: SpatialGraph,
    config: Mapping[str, Any],
    *,
    exposure: str,
    outcome: str,
    timing: str,
    window: str,
    bootstrap_samples: int | None = None,
    moran_permutations: int | None = None,
) -> dict[str, Any]:
    years = config["windows"][
        "primary_outcome_years" if window == "primary" else "covid_sensitivity_years"
    ]
    frame = build_timed_frame(
        exposures,
        outcomes,
        exposure=exposure,
        outcome=outcome,
        timing=timing,
        outcome_years=years,
    )
    base = {
        "exposure": exposure,
        "outcome": outcome,
        "timing": timing,
        "window": window,
        "n": int(len(frame)),
        "n_communes": int(frame["spatial_id"].nunique()) if not frame.empty else 0,
        "n_years": int(frame["outcome_year"].nunique()) if not frame.empty else 0,
        "outcome_year_min": int(frame["outcome_year"].min()) if not frame.empty else None,
        "outcome_year_max": int(frame["outcome_year"].max()) if not frame.empty else None,
    }
    ok, reason = estimability(frame, config["screening"])
    if not ok:
        return {**base, "status": "not_estimable", "reason": reason}
    bootstrap_samples = int(
        bootstrap_samples or config["screening"]["bootstrap_samples"]
    )
    moran_permutations = int(
        moran_permutations or config["screening"]["moran_permutations"]
    )
    seed = int(config["seed"])
    correlation = residualized_spearman(
        frame,
        bootstrap_samples=bootstrap_samples,
        confidence=float(config["screening"]["bootstrap_confidence"]),
        seed=stable_seed(seed, "spearman", exposure, outcome, timing, window),
    )
    ppml, residuals = fit_ppml_fixed_effects(
        frame,
        leave_one_commune_out=bool(config["screening"]["leave_one_commune_out"]),
    )
    mundlak = fit_ppml_mundlak(frame)
    ses_sensitivity = socioeconomic_index_sensitivity(frame)
    moran = residual_moran(
        frame,
        residuals,
        graph,
        permutations=moran_permutations,
        seed=stable_seed(seed, "moran", exposure, outcome, timing, window),
    )
    strata = socioeconomic_stratified_ppml(frame)
    return {
        **base,
        "status": "ok",
        "reason": None,
        **correlation,
        **ppml,
        **mundlak,
        **ses_sensitivity,
        **moran,
        "socioeconomic_strata": strata,
    }


def outcome_family(config: Mapping[str, Any], outcome: str) -> str:
    for family in ("primary", "exploratory", "negative_control"):
        if outcome in config["outcomes"][family]:
            return family
    raise ValueError(f"Unknown outcome: {outcome}")


def screening_tasks(config: Mapping[str, Any]) -> list[dict[str, str]]:
    exposures = [spec.id for spec in exposure_specs(config, include_sensitivities=True)]
    exposures.append("environmental_burden")
    outcomes = [
        outcome
        for family in ("primary", "exploratory", "negative_control")
        for outcome in config["outcomes"][family]
    ]
    return [
        {
            "exposure": exposure,
            "outcome": outcome,
            "timing": timing,
            "window": window,
            "outcome_family": outcome_family(config, outcome),
        }
        for window in ("primary", "covid")
        for timing in config["windows"]["timings"]
        for outcome in outcomes
        for exposure in exposures
    ]


def task_slug(task: Mapping[str, Any]) -> str:
    text = "__".join(
        str(task[key]) for key in ("window", "timing", "outcome", "exposure")
    )
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-.")


def apply_screening_multiplicity(
    results: pd.DataFrame, config: Mapping[str, Any]
) -> pd.DataFrame:
    results = results.copy()
    results["outcome_family"] = results["outcome"].map(
        lambda value: outcome_family(config, str(value))
    )
    results["hypothesis_family"] = (
        results["outcome_family"].astype(str)
        + ":"
        + results["window"].astype(str)
        + ":"
        + results["timing"].astype(str)
    )
    results["ppml_q_value"] = np.nan
    for _, index in results.groupby("hypothesis_family").groups.items():
        valid = results.loc[index, "ppml_p_value"].dropna()
        if valid.empty:
            continue
        adjusted = multipletests(
            valid.to_numpy(dtype=float),
            method=str(config["screening"].get("fdr_method", "fdr_bh")),
        )[1]
        results.loc[valid.index, "ppml_q_value"] = adjusted
    return results


def materialize_joint_structure(
    panel: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run Horn parallel analysis and return retained PCA scores/loadings."""
    component_ids = [spec.id for spec in exposure_specs(config) if spec.core_mixture]
    columns = [f"{value}__oriented_z" for value in component_ids]
    reference_years = [int(value) for value in config["windows"]["burden_reference_years"]]
    complete = panel.loc[
        panel["year"].isin(reference_years),
        ["spatial_id", "spatial_name", "year", *columns],
    ].dropna()
    values = complete[columns].to_numpy(dtype=float)
    if len(values) <= len(columns):
        raise ValueError("Insufficient complete rows for joint PCA")
    observed = PCA().fit(values).explained_variance_
    permutations = int(config["joint_exposome"]["horn_permutations"])
    percentile = float(config["joint_exposome"].get("horn_percentile", 0.95))
    rng = np.random.default_rng(stable_seed(int(config["seed"]), "horn-v2"))
    null = np.empty((permutations, len(columns)), dtype=float)
    for permutation in range(permutations):
        permuted = np.column_stack(
            [rng.permutation(values[:, column]) for column in range(values.shape[1])]
        )
        null[permutation] = PCA().fit(permuted).explained_variance_
    cutoff = np.quantile(null, percentile, axis=0)
    retained = 0
    for keep in observed > cutoff:
        if not keep:
            break
        retained += 1
    horn = pd.DataFrame(
        {
            "component": np.arange(1, len(columns) + 1),
            "observed_eigenvalue": observed,
            "null_percentile_eigenvalue": cutoff,
            "retain": np.arange(1, len(columns) + 1) <= retained,
            "retained_components": retained,
            "permutations": permutations,
        }
    )
    scores = complete[["spatial_id", "spatial_name", "year"]].reset_index(drop=True)
    loading_rows: list[dict[str, Any]] = []
    if retained:
        model = PCA(n_components=retained).fit(values)
        transformed = model.transform(values)
        for index in range(retained):
            scores[f"PC{index + 1}"] = transformed[:, index]
        loading_rows = [
            {
                "exposure": component_ids[exposure_index],
                "component": f"PC{component + 1}",
                "loading": float(model.components_[component, exposure_index]),
                "explained_variance_ratio": float(
                    model.explained_variance_ratio_[component]
                ),
            }
            for component in range(retained)
            for exposure_index in range(len(component_ids))
        ]
    loadings = pd.DataFrame(
        loading_rows,
        columns=["exposure", "component", "loading", "explained_variance_ratio"],
    )
    return horn, scores, loadings


def _joint_model_frame(
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    outcome: str,
    timing: str,
    window: str,
) -> tuple[pd.DataFrame, list[str]]:
    years = config["windows"][
        "primary_outcome_years" if window == "primary" else "covid_sensitivity_years"
    ]
    component_ids = [spec.id for spec in exposure_specs(config) if spec.core_mixture]
    columns = [f"{value}__oriented_z" for value in component_ids]
    x = exposures[
        ["spatial_id", "year", "deprivation_z", *columns]
    ].dropna().copy()
    x = x.rename(columns={"year": "exposure_year"})
    x["outcome_year"] = x["exposure_year"] + (1 if timing == "lag1" else 0)
    y = outcomes[
        (outcomes["outcome"] == outcome) & outcomes["year"].isin(years)
    ].rename(columns={"year": "outcome_year"})
    frame = y.merge(
        x,
        on=["spatial_id", "outcome_year"],
        how="inner",
        validate="one_to_one",
    )
    frame = frame[frame["expected"].gt(0) & frame["observed"].ge(0)].copy()
    return frame.reset_index(drop=True), columns


def _joint_design(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    design = frame[list(columns)].astype(float).reset_index(drop=True)
    design["deprivation_z"] = frame["deprivation_z"].to_numpy(dtype=float)
    years = pd.get_dummies(
        frame["outcome_year"].astype(str), prefix="year", drop_first=True, dtype=float
    ).reset_index(drop=True)
    return sm.add_constant(pd.concat([design, years], axis=1), has_constant="add")


def _poisson_deviance_terms(
    observed: Sequence[float] | np.ndarray,
    prediction: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Return half-deviance terms without evaluating ``log(0)``.

    ``np.where`` evaluates both branches eagerly, so using it around
    ``observed * log(observed / prediction)`` still emits divide-by-zero and
    invalid-value warnings for valid zero-count observations.
    """
    observed_array = np.asarray(observed, dtype=float)
    prediction_array = np.asarray(prediction, dtype=float)
    if observed_array.shape != prediction_array.shape:
        raise ValueError("Observed and predicted arrays must have the same shape")
    if np.any(observed_array < 0):
        raise ValueError("Poisson observations must be non-negative")
    if np.any(prediction_array <= 0):
        raise ValueError("Poisson predictions must be positive")
    terms = prediction_array.copy()
    positive = observed_array > 0
    terms[positive] = (
        observed_array[positive]
        * np.log(observed_array[positive] / prediction_array[positive])
        - (observed_array[positive] - prediction_array[positive])
    )
    return terms


def fit_joint_elastic_net(
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    outcome: str,
    timing: str,
    window: str = "primary",
    stability_resamples: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Elastic-net Poisson mixture with commune-grouped cross-validation."""
    frame, columns = _joint_model_frame(
        exposures, outcomes, config, outcome=outcome, timing=timing, window=window
    )
    ok, reason = estimability(
        build_timed_frame(
            exposures,
            outcomes,
            exposure="environmental_burden",
            outcome=outcome,
            timing=timing,
            outcome_years=config["windows"]["primary_outcome_years"],
        ),
        config["screening"],
    )
    if not ok:
        return (
            pd.DataFrame([{"outcome": outcome, "timing": timing, "status": "not_estimable", "reason": reason}]),
            pd.DataFrame(),
        )
    design = _joint_design(frame, columns)
    y = frame["observed"].to_numpy(dtype=float)
    offset = np.log(frame["expected"].to_numpy(dtype=float))
    groups = frame["spatial_id"].astype(str).to_numpy()
    unique_groups = np.unique(groups)
    folds = min(int(config["joint_exposome"]["grouped_cv_folds"]), len(unique_groups))
    splitter = GroupKFold(n_splits=folds)
    tuning_rows: list[dict[str, Any]] = []
    for alpha in config["joint_exposome"]["elastic_net_alphas"]:
        for l1_ratio in config["joint_exposome"]["elastic_net_l1_ratios"]:
            deviances: list[float] = []
            for train, test in splitter.split(design, y, groups=groups):
                model = sm.GLM(
                    y[train],
                    design.iloc[train],
                    family=sm.families.Poisson(),
                    offset=offset[train],
                )
                fitted = model.fit_regularized(
                    alpha=float(alpha), L1_wt=float(l1_ratio), maxiter=1000
                )
                prediction = model.predict(
                    fitted.params,
                    exog=design.iloc[test],
                    offset=offset[test],
                )
                prediction = np.clip(np.asarray(prediction, dtype=float), 1e-9, None)
                observed = y[test]
                terms = _poisson_deviance_terms(observed, prediction)
                deviances.append(float(2 * np.mean(terms)))
            tuning_rows.append(
                {
                    "outcome": outcome,
                    "timing": timing,
                    "window": window,
                    "alpha": float(alpha),
                    "l1_ratio": float(l1_ratio),
                    "grouped_cv_mean_poisson_deviance": float(np.mean(deviances)),
                    "grouped_cv_sd_poisson_deviance": float(np.std(deviances, ddof=1)),
                    "folds": folds,
                    "status": "ok",
                }
            )
    tuning = pd.DataFrame(tuning_rows).sort_values(
        ["grouped_cv_mean_poisson_deviance", "alpha", "l1_ratio"]
    )
    selected = tuning.iloc[0]
    full_model = sm.GLM(
        y,
        design,
        family=sm.families.Poisson(),
        offset=offset,
    )
    full_fit = full_model.fit_regularized(
        alpha=float(selected["alpha"]),
        L1_wt=float(selected["l1_ratio"]),
        maxiter=2000,
    )
    component_names = list(columns)
    coefficient_rows = [
        {
            "outcome": outcome,
            "timing": timing,
            "window": window,
            "term": name.replace("__oriented_z", ""),
            "coefficient": float(full_fit.params[name]),
            "selection_frequency": np.nan,
            "selected_alpha": float(selected["alpha"]),
            "selected_l1_ratio": float(selected["l1_ratio"]),
        }
        for name in component_names
    ]
    resamples = int(
        stability_resamples
        if stability_resamples is not None
        else config["joint_exposome"]["stability_resamples"]
    )
    rng = np.random.default_rng(
        stable_seed(int(config["seed"]), "elastic-stability", outcome, timing, window)
    )
    selections = {name: 0 for name in component_names}
    succeeded = 0
    for _ in range(resamples):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([np.flatnonzero(groups == group) for group in sampled])
        try:
            model = sm.GLM(
                y[indices],
                design.iloc[indices],
                family=sm.families.Poisson(),
                offset=offset[indices],
            )
            fitted = model.fit_regularized(
                alpha=float(selected["alpha"]),
                L1_wt=float(selected["l1_ratio"]),
                maxiter=1000,
            )
        except Exception:
            continue
        succeeded += 1
        for name in component_names:
            selections[name] += abs(float(fitted.params[name])) > 1e-10
    for row in coefficient_rows:
        source = f"{row['term']}__oriented_z"
        row["selection_frequency"] = (
            float(selections[source] / succeeded) if succeeded else np.nan
        )
        row["stability_resamples_succeeded"] = succeeded
    return tuning, pd.DataFrame(coefficient_rows)


def build_panel_bayesian_data(
    frame: pd.DataFrame,
    graph: SpatialGraph,
    *,
    outcome: str,
    exposure: str,
    timing: str,
    window: str,
) -> PanelBayesianData:
    """Align a complete panel with the fixed areal graph."""
    frame = frame.copy()
    if set(frame["spatial_id"].unique()) != set(graph.spatial_ids):
        raise ValueError("Bayesian panel does not cover the complete connected graph")
    area_lookup = {value: index for index, value in enumerate(graph.spatial_ids)}
    frame["area_index"] = frame["spatial_id"].map(area_lookup).astype(int)
    frame = frame.sort_values(["outcome_year", "area_index"]).reset_index(drop=True)
    years = sorted(int(value) for value in frame["outcome_year"].unique())
    year_names = tuple(f"year_{year}" for year in years[1:])
    if len(years) > 1:
        year_design = np.column_stack(
            [(frame["outcome_year"].to_numpy(dtype=int) == year).astype(float) for year in years[1:]]
        )
    else:
        year_design = np.empty((len(frame), 0), dtype=float)
    names = (
        frame[["spatial_id", "spatial_name"]]
        .drop_duplicates("spatial_id")
        .set_index("spatial_id")["spatial_name"]
        .reindex(graph.spatial_ids)
    )
    arrays = frame[
        [
            "observed",
            "expected",
            "exposure_within_z",
            "exposure_between_z",
            "deprivation_z",
            "interaction_z",
        ]
    ].to_numpy(dtype=float)
    if not np.all(np.isfinite(arrays)):
        raise ValueError("Bayesian panel contains non-finite model values")
    return PanelBayesianData(
        spatial_ids=graph.spatial_ids,
        spatial_names=tuple(names.astype(str)),
        years=tuple(frame["outcome_year"].astype(int)),
        observed=frame["observed"].to_numpy(dtype=int),
        expected=frame["expected"].to_numpy(dtype=float),
        area_index=frame["area_index"].to_numpy(dtype=int),
        year_design=year_design,
        year_names=year_names,
        exposure_within=frame["exposure_within_z"].to_numpy(dtype=float),
        exposure_between=frame["exposure_between_z"].to_numpy(dtype=float),
        deprivation=frame["deprivation_z"].to_numpy(dtype=float),
        interaction=frame["interaction_z"].to_numpy(dtype=float),
        outcome=outcome,
        exposure_name=exposure,
        timing=timing,
        window=window,
    )


def build_panel_bym2_model(
    data: PanelBayesianData,
    graph: SpatialGraph,
    bym2_config: Mapping[str, Any],
    *,
    include_exposure: bool,
    rho_prior: Sequence[float] | None = None,
    observed_indices: Sequence[int] | None = None,
) -> Any:
    """Negative-binomial BYM2 panel with within/between and SES moderation."""
    pm, _, pt = require_bayesian_dependencies()
    indices = np.asarray(
        np.arange(len(data.observed)) if observed_indices is None else observed_indices,
        dtype=int,
    )
    coords: dict[str, Any] = {
        "area": list(data.spatial_ids),
        "observation": np.arange(len(data.observed)),
        "observed_observation": indices,
    }
    if data.year_names:
        coords["year_effect"] = list(data.year_names)
    coefficient_sd = float(bym2_config["coefficient_sd"])
    with pm.Model(coords=coords) as model:
        intercept = pm.Normal("intercept", mu=0, sigma=1)
        linear = pt.repeat(intercept, len(data.observed))
        if data.year_names:
            gamma_year = pm.Normal(
                "gamma_year", mu=0, sigma=coefficient_sd, dims="year_effect"
            )
            linear = linear + pt.dot(data.year_design, gamma_year)
        beta_deprivation = pm.Normal(
            "beta_deprivation", mu=0, sigma=coefficient_sd
        )
        linear = linear + beta_deprivation * data.deprivation
        if include_exposure:
            beta_within = pm.Normal("beta_within", mu=0, sigma=coefficient_sd)
            beta_between = pm.Normal("beta_between", mu=0, sigma=coefficient_sd)
            beta_interaction = pm.Normal(
                "beta_interaction", mu=0, sigma=coefficient_sd
            )
            linear = (
                linear
                + beta_within * data.exposure_within
                + beta_between * data.exposure_between
                + beta_interaction * data.interaction
            )
        theta = pm.Normal("theta", mu=0, sigma=1, dims="area")
        phi = pm.ICAR("phi", W=graph.adjacency, dims="area")
        tail_probability = float(
            bym2_config["spatial_sigma_tail_probability_above_one"]
        )
        sigma = pm.Exponential("sigma", lam=-math.log(tail_probability))
        rho_parameters = rho_prior or bym2_config["rho_prior"]
        rho = pm.Beta(
            "rho", alpha=float(rho_parameters[0]), beta=float(rho_parameters[1])
        )
        mixture = pm.Deterministic(
            "bym2_mixture",
            pt.sqrt(1 - rho) * theta
            + pt.sqrt(rho / graph.scaling_factor) * phi,
            dims="area",
        )
        spatial_effect = pm.Deterministic(
            "spatial_effect", sigma * mixture, dims="area"
        )
        linear = linear + spatial_effect[data.area_index]
        alpha = pm.LogNormal(
            "alpha",
            mu=float(bym2_config["log_alpha_mean"]),
            sigma=float(bym2_config["log_alpha_sd"]),
        )
        mu = pm.Deterministic(
            "mu",
            pt.exp(np.log(data.expected) + linear),
            dims="observation",
        )
        pm.NegativeBinomial(
            "observed",
            mu=mu[indices],
            alpha=alpha,
            observed=data.observed[indices],
            dims="observed_observation",
        )
    return model


def panel_bayesian_diagnostics(
    idata: Any, thresholds: Mapping[str, Any]
) -> dict[str, Any]:
    """Convergence diagnostics including every v2 regression coefficient."""
    _, az, _ = require_bayesian_dependencies()
    candidates = [
        "intercept",
        "gamma_year",
        "beta_within",
        "beta_between",
        "beta_deprivation",
        "beta_interaction",
        "alpha",
        "sigma",
        "rho",
        "theta",
        "phi",
    ]
    variables = [value for value in candidates if value in idata.posterior]
    summary = az.summary(idata, var_names=variables, kind="diagnostics")
    max_rhat = float(summary["r_hat"].max())
    min_ess_bulk = float(summary["ess_bulk"].min())
    min_ess_tail = float(summary["ess_tail"].min())
    divergences = int(np.asarray(idata.sample_stats["diverging"]).sum())
    min_bfmi = float(np.min(_diagnostic_numeric_array(az.bfmi(idata))))
    passed = bool(
        divergences <= int(thresholds["max_divergences"])
        and max_rhat <= float(thresholds["max_rhat"])
        and min_ess_bulk >= float(thresholds["min_ess_bulk"])
        and min_ess_tail >= float(thresholds["min_ess_tail"])
        and min_bfmi > float(thresholds["min_bfmi"])
    )
    return {
        "diagnostics_passed": passed,
        "divergences": divergences,
        "max_rhat": max_rhat,
        "min_ess_bulk": min_ess_bulk,
        "min_ess_tail": min_ess_tail,
        "min_bfmi": min_bfmi,
    }


def _diagnostic_numeric_array(value: Any) -> np.ndarray:
    """Normalize ArviZ diagnostics across ndarray, xarray and DataTree APIs."""
    dataset = getattr(value, "dataset", None)
    if dataset is not None:
        value = dataset
    to_array = getattr(value, "to_array", None)
    if callable(to_array):
        value = to_array()
    values = getattr(value, "values", None)
    if values is not None and not callable(values):
        value = values
    array = np.asarray(value, dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("Bayesian diagnostic contains no finite numeric values")
    return array


def summarize_panel_effect(
    idata: Any,
    data: PanelBayesianData,
    *,
    rope_rr: Sequence[float],
) -> dict[str, Any]:
    _, az, _ = require_bayesian_dependencies()
    result: dict[str, Any] = {
        "outcome": data.outcome,
        "exposure": data.exposure_name,
        "timing": data.timing,
        "window": data.window,
        "n": len(data.observed),
        "n_communes": len(data.spatial_ids),
        "n_years": len(set(data.years)),
    }
    for variable, label in (
        ("beta_within", "within"),
        ("beta_between", "between"),
        ("beta_deprivation", "deprivation"),
        ("beta_interaction", "interaction"),
    ):
        if variable not in idata.posterior:
            continue
        values = np.asarray(idata.posterior[variable]).reshape(-1)
        rr = np.exp(values)
        hdi = np.asarray(az.hdi(rr, prob=0.95))
        above = float(np.mean(rr > 1))
        below = float(np.mean(rr < 1))
        result.update(
            {
                f"rr_{label}": float(np.median(rr)),
                f"rr_{label}_hdi_low": float(hdi[0]),
                f"rr_{label}_hdi_high": float(hdi[1]),
                f"probability_{label}_gt_1": above,
                f"probability_{label}_lt_1": below,
                f"probability_{label}_direction": max(above, below),
                f"probability_{label}_in_rope": float(
                    np.mean(
                        (rr >= float(rope_rr[0]))
                        & (rr <= float(rope_rr[1]))
                    )
                ),
            }
        )
    return result


def panel_psis_loo(
    idata: Any,
    data: PanelBayesianData,
    graph: SpatialGraph,
    bym2_config: Mapping[str, Any],
    *,
    include_exposure: bool,
    rho_prior: Sequence[float] | None,
    seed: int,
    exact_reloo: bool,
    progressbar: bool,
) -> dict[str, Any]:
    """PSIS-LOO with optional exact refits for observations above Pareto-k."""
    _, az, _ = require_bayesian_dependencies()
    loo = extract_loo_result(az.loo(idata, pointwise=True))
    threshold = float(bym2_config["pareto_k_reloo_threshold"])
    influential = np.flatnonzero(loo["pareto_k"] > threshold)
    result: dict[str, Any] = {
        "elpd_loo_psis": loo["elpd_loo"],
        "se_psis": loo["se"],
        "p_loo": loo["p_loo"],
        "pareto_k_threshold": threshold,
        "pareto_k_max": float(np.max(loo["pareto_k"])),
        "pareto_k_high_count": int(len(influential)),
        "exact_reloo_requested": bool(exact_reloo),
        "exact_reloo_completed": 0,
    }
    if not exact_reloo or not len(influential):
        result["elpd_loo_final"] = loo["elpd_loo"]
        return result
    corrected = loo["loo_i"].copy()
    draws = int(bym2_config["draws"])
    tune = int(bym2_config["tune"])
    chains = int(bym2_config["chains"])
    for index in influential:
        retained = np.delete(np.arange(len(data.observed)), index)
        model = build_panel_bym2_model(
            data,
            graph,
            bym2_config,
            include_exposure=include_exposure,
            rho_prior=rho_prior,
            observed_indices=retained,
        )
        heldout = sample_pymc_model(
            model,
            draws=draws,
            tune=tune,
            chains=chains,
            target_accept=float(bym2_config["target_accept"]),
            seed=stable_seed(seed, "reloo", int(index)),
            progressbar=progressbar,
        )
        mu = np.asarray(heldout.posterior["mu"])[..., index].reshape(-1)
        alpha = np.asarray(heldout.posterior["alpha"]).reshape(-1)
        probability = alpha / (alpha + mu)
        logp = st.nbinom.logpmf(int(data.observed[index]), alpha, probability)
        from scipy.special import logsumexp

        corrected[index] = float(logsumexp(logp) - np.log(len(logp)))
        result["exact_reloo_completed"] += 1
    result["elpd_loo_final"] = float(corrected.sum())
    result["reloo_delta"] = float(corrected.sum() - loo["elpd_loo"])
    return result


def bayesian_tasks(config: Mapping[str, Any]) -> list[ModelTask]:
    """Deterministic registry for primary, controls and prespecified sensitivities."""
    tasks: list[ModelTask] = []
    exposures = [
        spec.id for spec in exposure_specs(config) if spec.bayesian_primary
    ] + ["environmental_burden"]
    for outcome in config["outcomes"]["primary"]:
        for timing in config["windows"]["timings"]:
            variant = f"primary__{timing}"
            tasks.append(
                ModelTask(
                    phase="annual-v2-primary",
                    model_id=task_slug(
                        {
                            "window": "primary",
                            "timing": timing,
                            "outcome": outcome,
                            "exposure": "null",
                        }
                    ),
                    outcome=str(outcome),
                    exposure="environmental_burden",
                    model_name="nb_bym2_panel_null",
                    variant=variant,
                )
            )
            tasks.append(
                ModelTask(
                    phase="annual-v2-prior-sensitivity",
                    model_id=task_slug(
                        {
                            "window": "primary",
                            "timing": timing,
                            "outcome": outcome,
                            "exposure": "environmental_burden-rho-uniform",
                        }
                    ),
                    outcome=str(outcome),
                    exposure="environmental_burden",
                    model_name="nb_bym2_panel_rho_prior_sensitivity",
                    variant=variant,
                )
            )
            for exposure in exposures:
                tasks.append(
                    ModelTask(
                        phase="annual-v2-primary",
                        model_id=task_slug(
                            {
                                "window": "primary",
                                "timing": timing,
                                "outcome": outcome,
                                "exposure": exposure,
                            }
                        ),
                        outcome=str(outcome),
                        exposure=exposure,
                        model_name="nb_bym2_panel_exposure",
                        variant=variant,
                    )
                )
            for sensitivity in config.get("method_sensitivities", []):
                tasks.append(
                    ModelTask(
                        phase="annual-v2-method-sensitivity",
                        model_id=task_slug(
                            {
                                "window": "primary",
                                "timing": timing,
                                "outcome": outcome,
                                "exposure": sensitivity["id"],
                            }
                        ),
                        outcome=str(outcome),
                        exposure=str(sensitivity["id"]),
                        model_name="nb_bym2_panel_method_sensitivity",
                        variant=variant,
                    )
                )
            tasks.append(
                ModelTask(
                    phase="annual-v2-covid-sensitivity",
                    model_id=task_slug(
                        {
                            "window": "covid",
                            "timing": timing,
                            "outcome": outcome,
                            "exposure": "environmental_burden",
                        }
                    ),
                    outcome=str(outcome),
                    exposure="environmental_burden",
                    model_name="nb_bym2_panel_covid_sensitivity",
                    variant=f"covid__{timing}",
                )
            )
    for timing in config["windows"]["timings"]:
        tasks.append(
            ModelTask(
                phase="annual-v2-negative-control",
                model_id=task_slug(
                    {
                        "window": "primary",
                        "timing": timing,
                        "outcome": config["outcomes"]["negative_control"][0],
                        "exposure": "environmental_burden",
                    }
                ),
                outcome=str(config["outcomes"]["negative_control"][0]),
                exposure="environmental_burden",
                model_name="nb_bym2_panel_negative_control",
                variant=f"primary__{timing}",
            )
        )
    ids = [task.model_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise AssertionError("Bayesian annual-v2 model ids are not unique")
    return tasks


def parse_task_variant(task: ModelTask) -> tuple[str, str]:
    if not task.variant or "__" not in task.variant:
        raise ValueError(f"Malformed annual-v2 task variant: {task.variant}")
    window, timing = task.variant.split("__", 1)
    return window, timing


def task_panel_data(
    task: ModelTask,
    exposures: pd.DataFrame,
    outcomes: pd.DataFrame,
    config: Mapping[str, Any],
    graph: SpatialGraph,
) -> PanelBayesianData:
    window, timing = parse_task_variant(task)
    years = config["windows"][
        "primary_outcome_years" if window == "primary" else "covid_sensitivity_years"
    ]
    frame = build_timed_frame(
        exposures,
        outcomes,
        exposure=task.exposure,
        outcome=task.outcome,
        timing=timing,
        outcome_years=years,
    )
    ok, reason = estimability(frame, config["screening"])
    if not ok:
        raise ValueError(f"Bayesian task {task.model_id} is not estimable: {reason}")
    return build_panel_bayesian_data(
        frame,
        graph,
        outcome=task.outcome,
        exposure=task.exposure,
        timing=timing,
        window=window,
    )


def classify_evidence(row: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    """Conservative label shared by screening-only and Bayesian results."""
    if str(row.get("status")) == "not_estimable":
        return "not_estimable"
    diagnostics = row.get("diagnostics_passed")
    sign_stable = row.get("loo_sign_stable")
    negative_control_clear = row.get("negative_control_clear")
    moran_p = row.get("residual_moran_p")
    if (
        diagnostics is False
        or sign_stable is False
        or (
            bool(config["evidence"].get("require_negative_control_clear", True))
            and negative_control_clear is False
        )
        or (
            bool(config["evidence"].get("require_residual_moran_clear", True))
            and moran_p is not None
            and pd.notna(moran_p)
            and float(moran_p) < 0.05
        )
    ):
        return "unstable"
    q_value = row.get("ppml_q_value")
    probability = row.get("probability_within_direction")
    hdi_low = row.get("rr_within_hdi_low")
    hdi_high = row.get("rr_within_hdi_high")
    bayesian_supported = (
        probability is not None
        and pd.notna(probability)
        and float(probability) >= float(config["evidence"]["minimum_direction_probability"])
        and hdi_low is not None
        and hdi_high is not None
        and pd.notna(hdi_low)
        and pd.notna(hdi_high)
        and (float(hdi_low) > 1 or float(hdi_high) < 1)
    )
    frequentist_supported = q_value is not None and pd.notna(q_value) and float(q_value) < 0.05
    if bayesian_supported and frequentist_supported and sign_stable is not False:
        return "supported"
    if bayesian_supported or frequentist_supported:
        return "suggestive"
    return "null"
