"""Publication-oriented ecological inference for DEIS hospitalizations.

The module consumes already materialized SMR/count and exposure matrices.  It
never reads individual DEIS discharge records and never contacts a provider.
PyMC and ArviZ are optional, lazily imported only by the Bayesian entrypoints.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy.stats as st
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform
from scipy.special import logsumexp
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import mean_poisson_deviance
from statsmodels.stats.multitest import multipletests


CLASSICAL_METHODS = (
    "pearson_log_smr",
    "pearson_raw_smr",
    "spearman_raw_smr",
    "kendall_raw_smr",
    "partial_spearman_core",
    "partial_spearman_access",
)


@dataclass(frozen=True)
class SpatialGraph:
    """Stable spatial ordering plus a symmetric binary adjacency matrix."""

    spatial_ids: tuple[str, ...]
    adjacency: np.ndarray
    scaling_factor: float


@dataclass(frozen=True)
class BayesianModelData:
    """Numeric arrays aligned to one connected areal graph."""

    spatial_ids: tuple[str, ...]
    spatial_names: tuple[str, ...]
    observed: np.ndarray
    expected: np.ndarray
    exposure: np.ndarray
    covariates: np.ndarray
    covariate_names: tuple[str, ...]
    exposure_mean: float
    exposure_sd: float
    outcome: str
    exposure_name: str
    window: str


def stable_seed(base_seed: int, *parts: Any) -> int:
    """Derive a reproducible NumPy-compatible seed without Python hash state."""
    token = "|".join(str(part) for part in parts).encode("utf-8")
    return int((int(base_seed) + zlib.crc32(token)) % (2**32 - 1))


def normalise_spatial_id(series: pd.Series) -> pd.Series:
    """Normalise CUT-like identifiers while preserving non-numeric ids."""
    values = series.astype("string").str.strip()
    numeric = pd.to_numeric(values, errors="coerce")
    is_integer = numeric.notna() & np.isclose(numeric % 1, 0)
    values.loc[is_integer] = numeric.loc[is_integer].astype("Int64").astype("string")
    return values.astype(str)


def validate_inference_config(config: Mapping[str, Any]) -> None:
    """Fail early when the declarative inference contract is incomplete."""
    required = {
        "schema_version",
        "study",
        "protocol",
        "protocol_version",
        "scope",
        "seed",
        "inputs",
        "output_dir",
        "windows",
        "outcomes",
        "exposures",
        "covariates",
        "missingness",
        "correlations",
        "multiplicity",
        "joint_exposome",
        "bym2",
        "evidence",
    }
    missing = sorted(required.difference(config))
    if missing:
        raise ValueError(f"Hospitalization inference config is missing: {missing}")
    if int(config["schema_version"]) != 1:
        raise ValueError("Unsupported hospitalization inference schema_version")
    if not str(config["protocol_version"]).strip():
        raise ValueError("Hospitalization inference protocol_version cannot be empty")
    expected_scope = {
        "product": "offline_data_analysis",
        "webapp": False,
        "exposome_master": False,
        "automated_publish": False,
    }
    if dict(config["scope"]) != expected_scope:
        raise ValueError(
            "Hospitalization inference must remain offline analysis only; "
            f"expected scope {expected_scope}"
        )
    exposures = list(config["exposures"])
    ids = [str(item["id"]) for item in exposures]
    columns = [str(item["source_column"]) for item in exposures]
    if len(ids) != 10 or len(set(ids)) != 10 or len(set(columns)) != 10:
        raise ValueError("Inference requires ten unique exposure ids/source columns")
    outcomes = list(config["outcomes"]["confirmatory"])
    if len(outcomes) != 5 or len(set(outcomes)) != 5:
        raise ValueError("Inference requires five unique confirmatory outcomes")
    if config["missingness"].get("impute") is not False:
        raise ValueError("Primary hospitalization inference must not impute exposures")


def exposure_definitions(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): dict(item) for item in config["exposures"]}


def augment_exposure_matrix(exposures: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Attach prespecified ecological covariates to the existing matrix."""
    exposures = exposures.copy()
    master = master.copy()
    exposures["spatial_id"] = normalise_spatial_id(exposures["spatial_id"])
    master["spatial_id"] = normalise_spatial_id(master["spatial_id"])
    required = [
        "spatial_id",
        "demo_pct_pop_65_plus",
        "demo_pop_total",
        "area_km2",
        "health_n_primary_care",
    ]
    missing = [column for column in required if column not in master]
    if missing:
        raise ValueError(f"Master is missing inference covariates: {missing}")
    supplement_columns = [
        column for column in required if column == "spatial_id" or column not in exposures.columns
    ]
    supplement = master[supplement_columns].copy()
    if supplement["spatial_id"].duplicated().any():
        raise ValueError("Master has duplicate spatial_id values")
    merged = exposures.merge(supplement, on="spatial_id", how="left", validate="one_to_one")
    density = merged["demo_pop_total"] / merged["area_km2"]
    primary_care_rate = merged["health_n_primary_care"] / merged["demo_pop_total"] * 100_000
    merged["log_population_density"] = np.log(density.where(density > 0))
    merged["log_primary_care_per_100k"] = np.log1p(
        primary_care_rate.where(primary_care_rate >= 0)
    )
    return merged


def validate_analysis_inputs(
    smr: pd.DataFrame,
    exposures: pd.DataFrame,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Return one row per prespecified main pair and validate the 50-pair contract."""
    smr = smr.copy()
    exposures = exposures.copy()
    smr["spatial_id"] = normalise_spatial_id(smr["spatial_id"])
    exposures["spatial_id"] = normalise_spatial_id(exposures["spatial_id"])
    if exposures["spatial_id"].duplicated().any():
        raise ValueError("Exposure matrix has duplicate spatial_id values")
    window = str(config["windows"]["primary"])
    outcomes = [str(value) for value in config["outcomes"]["confirmatory"]]
    definitions = exposure_definitions(config)
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        outcome_frame = smr[(smr["window"] == window) & (smr["outcome"] == outcome)]
        for exposure_id, definition in definitions.items():
            column = str(definition["source_column"])
            if column not in exposures:
                n_complete = 0
            else:
                merged = outcome_frame[["spatial_id", "smr"]].merge(
                    exposures[["spatial_id", column]], on="spatial_id", how="inner"
                )
                n_complete = int(merged[["smr", column]].dropna().shape[0])
            rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure_id,
                    "source_column": column,
                    "hypothesis_family": definition["family"],
                    "evidence_level": definition["evidence_level"],
                    "window": window,
                    "n_complete": n_complete,
                }
            )
    index = pd.DataFrame(rows)
    if len(index) != 50:
        raise AssertionError(f"Expected exactly 50 main pairs, found {len(index)}")
    return index


def _rank_residual(values: np.ndarray, covariates: np.ndarray) -> np.ndarray:
    ranked = st.rankdata(values, method="average")
    ranked_covariates = np.column_stack(
        [st.rankdata(covariates[:, index], method="average") for index in range(covariates.shape[1])]
    )
    design = np.column_stack([np.ones(len(values)), ranked_covariates])
    coefficients = np.linalg.lstsq(design, ranked, rcond=None)[0]
    return ranked - design @ coefficients


def partial_spearman(
    x: Sequence[float],
    y: Sequence[float],
    covariates: np.ndarray,
) -> tuple[float, float]:
    """Rank residual correlation with the correct residual degrees of freedom."""
    x_array = np.asarray(x, dtype=float)
    y_array = np.asarray(y, dtype=float)
    covariate_array = np.asarray(covariates, dtype=float)
    if covariate_array.ndim == 1:
        covariate_array = covariate_array[:, None]
    residual_x = _rank_residual(x_array, covariate_array)
    residual_y = _rank_residual(y_array, covariate_array)
    estimate = float(st.pearsonr(residual_x, residual_y).statistic)
    degrees = len(x_array) - covariate_array.shape[1] - 2
    if degrees <= 0 or abs(estimate) >= 1:
        p_value = 0.0 if abs(estimate) >= 1 else math.nan
    else:
        statistic = estimate * math.sqrt(degrees / (1 - estimate**2))
        p_value = float(2 * st.t.sf(abs(statistic), degrees))
    return estimate, p_value


def correlation_estimate(
    method: str,
    x: np.ndarray,
    smr: np.ndarray,
    covariates: np.ndarray | None = None,
) -> tuple[float, float]:
    """Calculate one prespecified classical association."""
    x = np.asarray(x, dtype=float)
    smr = np.asarray(smr, dtype=float)
    if method == "pearson_log_smr":
        result = st.pearsonr(x, np.log(smr))
    elif method == "pearson_raw_smr":
        result = st.pearsonr(x, smr)
    elif method == "spearman_raw_smr":
        result = st.spearmanr(x, smr)
    elif method == "kendall_raw_smr":
        result = st.kendalltau(x, smr)
    elif method.startswith("partial_spearman_"):
        if covariates is None:
            raise ValueError(f"{method} requires covariates")
        return partial_spearman(x, smr, covariates)
    else:
        raise ValueError(f"Unknown correlation method: {method}")
    return float(result.statistic), float(result.pvalue)


def bootstrap_correlation_interval(
    method: str,
    x: np.ndarray,
    smr: np.ndarray,
    covariates: np.ndarray | None,
    *,
    samples: int,
    confidence: float,
    seed: int,
) -> tuple[float, float, int]:
    """Percentile interval using paired commune bootstrap samples."""
    if samples <= 0:
        return math.nan, math.nan, 0
    rng = np.random.default_rng(seed)
    estimates: list[float] = []
    n = len(x)
    for _ in range(samples):
        index = rng.integers(0, n, size=n)
        try:
            estimate, _ = correlation_estimate(
                method,
                x[index],
                smr[index],
                None if covariates is None else covariates[index],
            )
        except (ValueError, FloatingPointError):
            continue
        if math.isfinite(estimate):
            estimates.append(estimate)
    minimum = max(100, int(samples * 0.8))
    if len(estimates) < minimum:
        return math.nan, math.nan, len(estimates)
    alpha = (1 - confidence) / 2
    low, high = np.quantile(estimates, [alpha, 1 - alpha])
    return float(low), float(high), len(estimates)


def leave_one_out_correlations(
    method: str,
    x: np.ndarray,
    smr: np.ndarray,
    covariates: np.ndarray | None,
    spatial_ids: Sequence[str],
    full_estimate: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, spatial_id in enumerate(spatial_ids):
        keep = np.arange(len(x)) != index
        estimate, _ = correlation_estimate(
            method,
            x[keep],
            smr[keep],
            None if covariates is None else covariates[keep],
        )
        rows.append(
            {
                "excluded_spatial_id": str(spatial_id),
                "estimate": estimate,
                "delta_from_full": estimate - full_estimate,
                "sign_changed": bool(
                    full_estimate != 0 and estimate != 0 and np.sign(estimate) != np.sign(full_estimate)
                ),
            }
        )
    return pd.DataFrame(rows)


def _method_covariates(method: str, config: Mapping[str, Any]) -> list[str]:
    if method == "partial_spearman_core":
        return [str(value) for value in config["covariates"]["core"]]
    if method == "partial_spearman_access":
        return [str(value) for value in config["covariates"]["access"]]
    return []


def _eligible_pair_frame(
    outcome_frame: pd.DataFrame,
    exposures: pd.DataFrame,
    source_column: str,
    covariate_columns: Sequence[str],
) -> pd.DataFrame:
    keep = ["spatial_id", "spatial_name", "smr", "observed", "expected"]
    exposure_keep = list(dict.fromkeys(["spatial_id", source_column, *covariate_columns]))
    frame = outcome_frame[keep].merge(
        exposures[exposure_keep], on="spatial_id", how="inner", validate="one_to_one"
    )
    required = ["smr", source_column, *covariate_columns]
    frame[required] = frame[required].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=required)
    frame = frame[(frame["smr"] > 0) & (frame["expected"] > 0)].copy()
    return frame.sort_values("spatial_id").reset_index(drop=True)


def apply_multiplicity(table: pd.DataFrame) -> pd.DataFrame:
    """Apply BH within method/family and Holm to the confirmatory family only."""
    table = table.copy()
    table["q_bh"] = np.nan
    table["p_holm"] = np.nan
    valid = table["status"].eq("ok") & table["p_value"].notna()
    for (_, _), index in table[valid].groupby(["method", "multiplicity_family"]).groups.items():
        p_values = table.loc[index, "p_value"].astype(float).to_numpy()
        table.loc[index, "q_bh"] = multipletests(p_values, method="fdr_bh")[1]
        if table.loc[index, "multiplicity_family"].iloc[0] == "confirmatory_chronic":
            table.loc[index, "p_holm"] = multipletests(p_values, method="holm")[1]
    return table


def classical_correlation_analysis(
    smr: pd.DataFrame,
    exposures: pd.DataFrame,
    config: Mapping[str, Any],
    *,
    outcomes: Sequence[str] | None = None,
    multiplicity_family: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calculate classical correlations, detailed LOO influence, and exclusions."""
    definitions = exposure_definitions(config)
    target_outcomes = list(outcomes or config["outcomes"]["confirmatory"])
    window = str(config["windows"]["primary"])
    minimum_n = int(config["missingness"]["minimum_communes"])
    minimum_unique = int(config["missingness"]["minimum_distinct_values"])
    bootstrap_samples = int(config["correlations"]["bootstrap_samples"])
    confidence = float(config["correlations"]["confidence"])
    base_seed = int(config["seed"])
    smr = smr.copy()
    smr["spatial_id"] = normalise_spatial_id(smr["spatial_id"])
    rows: list[dict[str, Any]] = []
    loo_frames: list[pd.DataFrame] = []
    exclusions: list[dict[str, Any]] = []
    for outcome in target_outcomes:
        outcome_frame = smr[(smr["window"] == window) & (smr["outcome"] == outcome)].copy()
        for exposure_id, definition in definitions.items():
            source_column = str(definition["source_column"])
            for method in CLASSICAL_METHODS:
                covariate_columns = _method_covariates(method, config)
                base = {
                    "outcome": outcome,
                    "exposure": exposure_id,
                    "source_column": source_column,
                    "method": method,
                    "window": window,
                    "hypothesis_family": definition["family"],
                    "multiplicity_family": multiplicity_family or definition["family"],
                    "evidence_level": definition["evidence_level"],
                    "spatial": False,
                    "causal": False,
                }
                missing_columns = [
                    value
                    for value in [source_column, *covariate_columns]
                    if value not in exposures.columns
                ]
                if missing_columns:
                    base.update({"status": "missing_columns", "n": 0})
                    rows.append(base)
                    exclusions.append({**base, "reason": ",".join(missing_columns)})
                    continue
                frame = _eligible_pair_frame(
                    outcome_frame, exposures, source_column, covariate_columns
                )
                n_unique = int(frame[source_column].nunique())
                if len(frame) < minimum_n or n_unique < minimum_unique:
                    reason = "insufficient_communes" if len(frame) < minimum_n else "low_variation"
                    base.update({"status": reason, "n": int(len(frame)), "n_unique": n_unique})
                    rows.append(base)
                    exclusions.append({**base, "reason": reason})
                    continue
                x = frame[source_column].to_numpy(dtype=float)
                y = frame["smr"].to_numpy(dtype=float)
                covariates = (
                    frame[covariate_columns].to_numpy(dtype=float)
                    if covariate_columns
                    else None
                )
                estimate, p_value = correlation_estimate(method, x, y, covariates)
                ci_low, ci_high, valid_bootstrap = bootstrap_correlation_interval(
                    method,
                    x,
                    y,
                    covariates,
                    samples=bootstrap_samples,
                    confidence=confidence,
                    seed=stable_seed(base_seed, outcome, exposure_id, method),
                )
                influence = leave_one_out_correlations(
                    method,
                    x,
                    y,
                    covariates,
                    frame["spatial_id"].tolist(),
                    estimate,
                )
                influence.insert(0, "method", method)
                influence.insert(0, "exposure", exposure_id)
                influence.insert(0, "outcome", outcome)
                loo_frames.append(influence)
                most_influential = influence.iloc[influence["delta_from_full"].abs().argmax()]
                base.update(
                    {
                        "status": "ok",
                        "n": int(len(frame)),
                        "n_unique": n_unique,
                        "estimate": estimate,
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                        "confidence": confidence,
                        "bootstrap_valid": valid_bootstrap,
                        "p_value": p_value,
                        "loo_min": float(influence["estimate"].min()),
                        "loo_max": float(influence["estimate"].max()),
                        "loo_sign_change": bool(influence["sign_changed"].any()),
                        "most_influential_spatial_id": str(
                            most_influential["excluded_spatial_id"]
                        ),
                        "max_abs_loo_delta": float(
                            influence["delta_from_full"].abs().max()
                        ),
                    }
                )
                rows.append(base)
    result = apply_multiplicity(pd.DataFrame(rows))
    loo = pd.concat(loo_frames, ignore_index=True) if loo_frames else pd.DataFrame()
    exclusion_table = pd.DataFrame(exclusions)
    if exclusion_table.empty:
        exclusion_table = pd.DataFrame(
            columns=["outcome", "exposure", "source_column", "method", "reason"]
        )
    return result, loo, exclusion_table


def oriented_exposure_matrix(
    exposures: pd.DataFrame,
    config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return original and burden-oriented z scores without overwriting inputs."""
    definitions = exposure_definitions(config)
    output = exposures[["spatial_id", "spatial_name"]].copy()
    metadata: list[dict[str, Any]] = []
    for exposure_id, definition in definitions.items():
        column = str(definition["source_column"])
        values = pd.to_numeric(exposures[column], errors="coerce")
        mean = float(values.mean())
        sd = float(values.std(ddof=0))
        if not math.isfinite(sd) or sd <= 0:
            raise ValueError(f"Cannot orient constant exposure {exposure_id}")
        orientation = int(definition["orientation"])
        output[f"{exposure_id}__original"] = values
        output[exposure_id] = orientation * (values - mean) / sd
        metadata.append(
            {
                "exposure": exposure_id,
                "source_column": column,
                "orientation": orientation,
                "original_mean": mean,
                "original_sd": sd,
                "higher_oriented_value": "greater_burden",
            }
        )
    return output, pd.DataFrame(metadata)


def _vif(values: np.ndarray, column: int) -> float:
    target = values[:, column]
    others = np.delete(values, column, axis=1)
    design = np.column_stack([np.ones(len(values)), others])
    fitted = design @ np.linalg.lstsq(design, target, rcond=None)[0]
    residual_sum = float(np.sum((target - fitted) ** 2))
    total_sum = float(np.sum((target - target.mean()) ** 2))
    if total_sum <= 0:
        return math.inf
    r_squared = 1 - residual_sum / total_sum
    return math.inf if r_squared >= 1 else float(1 / (1 - r_squared))


def collinearity_diagnostics(
    oriented: pd.DataFrame,
    exposure_ids: Sequence[str],
    *,
    rho_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return long correlation matrix, VIF table, and deterministic clusters."""
    exposure_ids = [str(value) for value in exposure_ids]
    complete = oriented[exposure_ids].dropna()
    pearson = complete.corr(method="pearson")
    spearman = complete.corr(method="spearman")
    correlation_rows = [
        {
            "exposure_a": first,
            "exposure_b": second,
            "pearson": float(pearson.loc[first, second]),
            "spearman": float(spearman.loc[first, second]),
            "nonseparable": bool(
                first != second and abs(float(spearman.loc[first, second])) >= rho_threshold
            ),
        }
        for first in exposure_ids
        for second in exposure_ids
    ]
    values = complete.to_numpy(dtype=float)
    vif = pd.DataFrame(
        {
            "exposure": exposure_ids,
            "vif": [_vif(values, index) for index in range(len(exposure_ids))],
        }
    )
    distance = (1 - spearman.abs()).clip(lower=0, upper=1).copy()
    distance_array = distance.to_numpy(copy=True)
    np.fill_diagonal(distance_array, 0)
    linkage = hierarchy.linkage(squareform(distance_array, checks=False), method="average")
    labels = hierarchy.fcluster(linkage, t=1 - rho_threshold, criterion="distance")
    raw_clusters = pd.DataFrame({"exposure": exposure_ids, "raw_cluster": labels})
    order = {
        value: index + 1
        for index, value in enumerate(
            sorted(raw_clusters["raw_cluster"].unique(), key=lambda item: exposure_ids.index(
                raw_clusters.loc[raw_clusters["raw_cluster"] == item, "exposure"].iloc[0]
            ))
        )
    }
    clusters = raw_clusters.assign(
        cluster_id=raw_clusters["raw_cluster"].map(order).astype(int)
    ).drop(columns="raw_cluster")
    return pd.DataFrame(correlation_rows), vif, clusters


def horn_parallel_analysis(
    oriented: pd.DataFrame,
    exposure_ids: Sequence[str],
    *,
    permutations: int,
    seed: int,
    percentile: float = 0.95,
) -> pd.DataFrame:
    """Horn parallel analysis using independently permuted exposure columns."""
    exposure_ids = [str(value) for value in exposure_ids]
    values = oriented[exposure_ids].dropna().to_numpy(dtype=float)
    observed = PCA().fit(values).explained_variance_
    rng = np.random.default_rng(seed)
    null = np.empty((permutations, len(exposure_ids)), dtype=float)
    for permutation in range(permutations):
        permuted = np.column_stack([rng.permutation(values[:, column]) for column in range(values.shape[1])])
        null[permutation] = PCA().fit(permuted).explained_variance_
    cutoff = np.quantile(null, percentile, axis=0)
    retained = observed > cutoff
    # Components are ordered; retain the leading contiguous run only.
    retained_count = 0
    for keep in retained:
        if not keep:
            break
        retained_count += 1
    return pd.DataFrame(
        {
            "component": np.arange(1, len(exposure_ids) + 1),
            "observed_eigenvalue": observed,
            "null_percentile_eigenvalue": cutoff,
            "retain": np.arange(1, len(exposure_ids) + 1) <= retained_count,
            "retained_components": retained_count,
            "permutations": permutations,
        }
    )


def retained_pca_outputs(
    oriented: pd.DataFrame,
    exposure_ids: Sequence[str],
    horn: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Materialize retained PCA scores/loadings selected by Horn, if any."""
    exposure_ids = [str(value) for value in exposure_ids]
    retained = int(horn["retained_components"].iloc[0]) if not horn.empty else 0
    complete = oriented[["spatial_id", "spatial_name", *exposure_ids]].dropna()
    if retained == 0:
        return (
            complete[["spatial_id", "spatial_name"]].copy(),
            pd.DataFrame(columns=["exposure", "component", "loading"]),
        )
    model = PCA(n_components=retained).fit(complete[exposure_ids].to_numpy(dtype=float))
    scores = model.transform(complete[exposure_ids].to_numpy(dtype=float))
    score_table = complete[["spatial_id", "spatial_name"]].reset_index(drop=True)
    for index in range(retained):
        score_table[f"PC{index + 1}"] = scores[:, index]
    loading_rows = [
        {
            "exposure": exposure_id,
            "component": f"PC{component + 1}",
            "loading": float(model.components_[component, exposure_index]),
            "explained_variance_ratio": float(model.explained_variance_ratio_[component]),
        }
        for component in range(retained)
        for exposure_index, exposure_id in enumerate(exposure_ids)
    ]
    return score_table, pd.DataFrame(loading_rows)


def hospitalization_mortality_triangulation(
    smr: pd.DataFrame,
    mortality: pd.DataFrame,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Contrast compatible area rankings without combining the two products."""
    window = str(config["windows"]["primary"])
    outcomes = [str(value) for value in config["outcomes"]["confirmatory"]]
    hospitalization = smr[
        (smr["window"] == window) & smr["outcome"].isin(outcomes)
    ][["spatial_id", "outcome", "smr"]].copy()
    mortality = mortality[mortality["outcome"].isin(outcomes)][
        ["spatial_id", "outcome", "mortality_rate_age_adjusted_per_100k"]
    ].copy()
    hospitalization["spatial_id"] = normalise_spatial_id(hospitalization["spatial_id"])
    mortality["spatial_id"] = normalise_spatial_id(mortality["spatial_id"])
    merged = hospitalization.merge(
        mortality, on=["spatial_id", "outcome"], how="inner", validate="one_to_one"
    )
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        frame = merged[merged["outcome"] == outcome].dropna()
        if len(frame) < 20:
            rows.append({"outcome": outcome, "status": "insufficient_overlap", "n": len(frame)})
            continue
        result = st.spearmanr(
            frame["smr"], frame["mortality_rate_age_adjusted_per_100k"]
        )
        rows.append(
            {
                "outcome": outcome,
                "status": "ok",
                "n": int(len(frame)),
                "spearman": float(result.statistic),
                "p_value_descriptive": float(result.pvalue),
                "hospitalization_window": window,
                "mortality_window": "2018-2022",
                "combined_or_meta_analyzed": False,
                "interpretation": "descriptive_triangulation_only",
            }
        )
    return pd.DataFrame(rows)


def build_queen_graph(geometry: Any) -> SpatialGraph:
    """Build and validate the stable Queen graph used by Moran and BYM2."""
    import libpysal

    if "spatial_id" not in geometry.columns:
        raise ValueError("Geometry requires spatial_id")
    frame = geometry.copy()
    frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    if frame["spatial_id"].duplicated().any():
        raise ValueError("Geometry has duplicate spatial_id values")
    frame = frame.sort_values("spatial_id").set_index("spatial_id")
    weights = libpysal.weights.Queen.from_dataframe(frame, use_index=True, silence_warnings=True)
    spatial_ids = tuple(frame.index.astype(str))
    position = {spatial_id: index for index, spatial_id in enumerate(spatial_ids)}
    adjacency = np.zeros((len(frame), len(frame)), dtype=np.int8)
    for spatial_id, neighbors in weights.neighbors.items():
        for neighbor in neighbors:
            adjacency[position[str(spatial_id)], position[str(neighbor)]] = 1
    adjacency = np.maximum(adjacency, adjacency.T)
    np.fill_diagonal(adjacency, 0)
    if not np.array_equal(adjacency, adjacency.T):
        raise ValueError("Queen graph is not symmetric")
    if (adjacency.sum(axis=1) == 0).any():
        islands = np.asarray(spatial_ids)[adjacency.sum(axis=1) == 0].tolist()
        raise ValueError(f"Queen graph contains islands: {islands}")
    components, _ = connected_components(adjacency, directed=False)
    if components != 1:
        raise ValueError(f"Queen graph is disconnected ({components} components)")
    return SpatialGraph(spatial_ids, adjacency, icar_scaling_factor(adjacency))


def icar_scaling_factor(adjacency: np.ndarray) -> float:
    """Geometric mean marginal variance under the zero-sum ICAR constraint."""
    adjacency = np.asarray(adjacency, dtype=float)
    if adjacency.ndim != 2 or adjacency.shape[0] != adjacency.shape[1]:
        raise ValueError("Adjacency must be square")
    if not np.allclose(adjacency, adjacency.T):
        raise ValueError("Adjacency must be symmetric")
    precision = np.diag(adjacency.sum(axis=1)) - adjacency
    covariance = np.linalg.pinv(precision, hermitian=True)
    diagonal = np.diag(covariance)
    if np.any(diagonal <= 0) or not np.all(np.isfinite(diagonal)):
        raise ValueError("Could not derive positive ICAR marginal variances")
    return float(np.exp(np.mean(np.log(diagonal))))


def deterministic_spatial_blocks(geometry: Any, *, n_blocks: int, seed: int) -> pd.DataFrame:
    """Create stable centroid-based blocks for spatial cross-validation."""
    frame = geometry.copy()
    frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    frame = frame.sort_values("spatial_id").reset_index(drop=True)
    metric = frame.to_crs(frame.estimate_utm_crs()) if getattr(frame, "crs", None) else frame
    centroids = metric.geometry.centroid
    coordinates = np.column_stack([centroids.x, centroids.y])
    raw = KMeans(n_clusters=n_blocks, n_init=20, random_state=seed).fit_predict(coordinates)
    centers = pd.DataFrame(coordinates, columns=["x", "y"]).assign(raw=raw).groupby("raw").mean()
    ordered = centers.sort_values(["x", "y"]).index.tolist()
    stable = {value: index + 1 for index, value in enumerate(ordered)}
    return pd.DataFrame(
        {
            "spatial_id": frame["spatial_id"],
            "block": pd.Series(raw).map(stable).astype(int),
            "centroid_x": coordinates[:, 0],
            "centroid_y": coordinates[:, 1],
        }
    )


def bivariate_moran(
    x: Sequence[float],
    y: Sequence[float],
    adjacency: np.ndarray,
    *,
    permutations: int,
    seed: int,
) -> dict[str, Any]:
    """Bivariate Moran statistic with a separate two-sided permutation p-value."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    adjacency = np.asarray(adjacency, dtype=float)
    if len(x) != len(y) or adjacency.shape != (len(x), len(x)):
        raise ValueError("Moran arrays and adjacency have incompatible shapes")
    row_sum = adjacency.sum(axis=1)
    if np.any(row_sum == 0):
        raise ValueError("Moran subgraph contains an island")
    weights = adjacency / row_sum[:, None]
    zx = (x - x.mean()) / x.std(ddof=0)
    zy = (y - y.mean()) / y.std(ddof=0)
    denominator = float(zx @ zx)
    observed = float(zx @ weights @ zy / denominator)
    rng = np.random.default_rng(seed)
    simulated = np.empty(permutations, dtype=float)
    for index in range(permutations):
        simulated[index] = float(zx @ weights @ rng.permutation(zy) / denominator)
    center = float(simulated.mean())
    p_value = float(
        (1 + np.sum(np.abs(simulated - center) >= abs(observed - center)))
        / (permutations + 1)
    )
    return {
        "moran_bv": observed,
        "p_permutation_two_sided": p_value,
        "permutation_mean": center,
        "permutation_sd": float(simulated.std(ddof=1)),
        "permutations": permutations,
    }


def bivariate_moran_analysis(
    smr: pd.DataFrame,
    exposures: pd.DataFrame,
    graph: SpatialGraph,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Run the 50 main bivariate Moran tests without mixing their p-values."""
    definitions = exposure_definitions(config)
    outcomes = [str(value) for value in config["outcomes"]["confirmatory"]]
    window = str(config["windows"]["primary"])
    permutations = int(config["correlations"]["bivariate_moran_permutations"])
    base_seed = int(config["seed"])
    exposures = exposures.copy()
    exposures["spatial_id"] = normalise_spatial_id(exposures["spatial_id"])
    smr = smr.copy()
    smr["spatial_id"] = normalise_spatial_id(smr["spatial_id"])
    rows: list[dict[str, Any]] = []
    graph_position = {value: index for index, value in enumerate(graph.spatial_ids)}
    for outcome in outcomes:
        outcome_frame = smr[(smr["window"] == window) & (smr["outcome"] == outcome)]
        for exposure_id, definition in definitions.items():
            column = str(definition["source_column"])
            frame = _eligible_pair_frame(outcome_frame, exposures, column, [])
            frame = frame[frame["spatial_id"].isin(graph_position)].copy()
            frame["position"] = frame["spatial_id"].map(graph_position)
            frame = frame.sort_values("position")
            positions = frame["position"].to_numpy(dtype=int)
            base = {
                "outcome": outcome,
                "exposure": exposure_id,
                "source_column": column,
                "hypothesis_family": definition["family"],
                "window": window,
                "n": int(len(frame)),
                "p_values_separate_from_classical": True,
            }
            if len(frame) < int(config["missingness"]["minimum_communes"]):
                rows.append({**base, "status": "insufficient_communes"})
                continue
            subgraph = graph.adjacency[np.ix_(positions, positions)]
            if (subgraph.sum(axis=1) == 0).any() or connected_components(
                subgraph, directed=False
            )[0] != 1:
                rows.append({**base, "status": "disconnected_complete_case_graph"})
                continue
            result = bivariate_moran(
                frame[column].to_numpy(dtype=float),
                np.log(frame["smr"].to_numpy(dtype=float)),
                subgraph,
                permutations=permutations,
                seed=stable_seed(base_seed, "moran", outcome, exposure_id),
            )
            rows.append({**base, "status": "ok", **result})
    table = pd.DataFrame(rows)
    if len(table) != 50:
        raise AssertionError(f"Expected 50 bivariate Moran rows, found {len(table)}")
    return table


def _fit_regularized_poisson(
    x: np.ndarray,
    observed: np.ndarray,
    expected: np.ndarray,
    *,
    alpha: float,
    l1_ratio: float,
) -> np.ndarray:
    """Fit offset Poisson elastic-net with an analytic convex objective.

    A differentiable, numerically tiny approximation to ``abs(beta)`` makes the
    hundreds of nested spatial-CV fits tractable with L-BFGS.  Coefficients at
    the approximation scale are set to exact zero after optimization; the
    approximation and threshold are recorded here rather than hidden in output.
    """
    from scipy.optimize import minimize

    x = np.asarray(x, dtype=float)
    observed = np.asarray(observed, dtype=float)
    expected = np.asarray(expected, dtype=float)
    if np.any(expected <= 0):
        raise ValueError("Poisson offset requires positive expected counts")
    offset = np.log(expected)
    initial = np.zeros(x.shape[1] + 1, dtype=float)
    initial[0] = math.log(max(observed.sum(), 1.0) / expected.sum())
    l1_penalty = float(alpha) * float(l1_ratio)
    l2_penalty = float(alpha) * (1 - float(l1_ratio))
    smooth_absolute_epsilon = 1e-6

    def objective_gradient(value: np.ndarray) -> tuple[float, np.ndarray]:
        eta = np.clip(offset + value[0] + x @ value[1:], -30, 30)
        mu = np.exp(eta)
        coefficients = value[1:]
        smooth_absolute = np.sqrt(coefficients**2 + smooth_absolute_epsilon**2)
        objective = (
            np.mean(mu - observed * eta)
            + l1_penalty * np.sum(smooth_absolute - smooth_absolute_epsilon)
            + 0.5 * l2_penalty * np.sum(coefficients**2)
        )
        residual = np.exp(eta) - observed
        gradient = np.r_[
            residual.mean(),
            x.T @ residual / len(x)
            + l1_penalty * coefficients / smooth_absolute
            + l2_penalty * coefficients,
        ]
        return float(objective), gradient

    result = minimize(
        objective_gradient,
        initial,
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 250, "ftol": 1e-9, "gtol": 1e-6},
    )
    coefficients = np.asarray(result.x, dtype=float)
    coefficients[1:][np.abs(coefficients[1:]) <= 1e-6] = 0
    return coefficients


def _poisson_predictions(x: np.ndarray, expected: np.ndarray, params: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    return np.exp(np.log(expected) + design @ params)


def _select_elastic_net_parameters(
    x: np.ndarray,
    observed: np.ndarray,
    expected: np.ndarray,
    blocks: np.ndarray,
    candidates: Sequence[tuple[float, float]],
) -> tuple[float, float, float]:
    scores: list[tuple[float, float, float]] = []
    for l1_ratio, alpha in candidates:
        fold_scores: list[float] = []
        for block in sorted(np.unique(blocks)):
            train = blocks != block
            test = ~train
            try:
                params = _fit_regularized_poisson(
                    x[train], observed[train], expected[train], alpha=alpha, l1_ratio=l1_ratio
                )
                prediction = _poisson_predictions(x[test], expected[test], params)
                fold_scores.append(mean_poisson_deviance(observed[test], prediction))
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                fold_scores.append(math.inf)
        scores.append((float(np.mean(fold_scores)), l1_ratio, alpha))
    score, l1_ratio, alpha = min(scores, key=lambda value: (value[0], value[1], value[2]))
    return l1_ratio, alpha, score


def elastic_net_poisson_nested_cv(
    outcomes: pd.DataFrame,
    oriented: pd.DataFrame,
    blocks: pd.DataFrame,
    exposure_ids: Sequence[str],
    config: Mapping[str, Any],
    *,
    stability_resamples: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Exploratory block-nested elastic-net Poisson selection with an offset."""
    exposure_ids = [str(value) for value in exposure_ids]
    joint = config["joint_exposome"]
    candidates = [
        (float(l1_ratio), float(alpha))
        for l1_ratio in joint["elastic_net_l1_ratios"]
        for alpha in joint["elastic_net_alphas"]
    ]
    n_resamples = int(
        joint["stability_resamples"] if stability_resamples is None else stability_resamples
    )
    base_seed = int(config["seed"])
    merged_exposure = oriented[["spatial_id", *exposure_ids]].merge(
        blocks[["spatial_id", "block"]], on="spatial_id", validate="one_to_one"
    )
    performance_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    stability_rows: list[dict[str, Any]] = []
    for outcome in config["outcomes"]["confirmatory"]:
        frame = outcomes[outcomes["outcome"] == outcome][
            ["spatial_id", "observed", "expected"]
        ].merge(merged_exposure, on="spatial_id", how="inner", validate="one_to_one")
        frame = frame.dropna(subset=["observed", "expected", *exposure_ids])
        frame = frame[frame["expected"] > 0].sort_values("spatial_id")
        x = frame[exposure_ids].to_numpy(dtype=float)
        observed = frame["observed"].to_numpy(dtype=float)
        expected = frame["expected"].to_numpy(dtype=float)
        block_values = frame["block"].to_numpy(dtype=int)
        predictions = np.full(len(frame), np.nan)
        selected: list[tuple[float, float]] = []
        for outer_block in sorted(np.unique(block_values)):
            train = block_values != outer_block
            test = ~train
            inner_blocks = block_values[train]
            l1_ratio, alpha, inner_score = _select_elastic_net_parameters(
                x[train], observed[train], expected[train], inner_blocks, candidates
            )
            params = _fit_regularized_poisson(
                x[train], observed[train], expected[train], alpha=alpha, l1_ratio=l1_ratio
            )
            predictions[test] = _poisson_predictions(x[test], expected[test], params)
            selected.append((l1_ratio, alpha))
            performance_rows.append(
                {
                    "outcome": outcome,
                    "outer_block": int(outer_block),
                    "selected_l1_ratio": l1_ratio,
                    "selected_alpha": alpha,
                    "inner_mean_poisson_deviance": inner_score,
                    "outer_poisson_deviance": float(
                        mean_poisson_deviance(observed[test], predictions[test])
                    ),
                    "role": "exploratory_predictive_selection",
                }
            )
        final_l1, final_alpha, final_cv_score = _select_elastic_net_parameters(
            x, observed, expected, block_values, candidates
        )
        final_params = _fit_regularized_poisson(
            x, observed, expected, alpha=final_alpha, l1_ratio=final_l1
        )
        performance_rows.append(
            {
                "outcome": outcome,
                "outer_block": "all",
                "selected_l1_ratio": final_l1,
                "selected_alpha": final_alpha,
                "inner_mean_poisson_deviance": final_cv_score,
                "outer_poisson_deviance": float(
                    mean_poisson_deviance(observed, predictions)
                ),
                "role": "nested_spatial_cv_summary",
            }
        )
        for exposure_id, coefficient in zip(exposure_ids, final_params[1:]):
            coefficient_rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure_id,
                    "coefficient": float(coefficient),
                    "selected": bool(abs(coefficient) > 1e-8),
                    "l1_ratio": final_l1,
                    "alpha": final_alpha,
                    "causal_effect": False,
                }
            )
        rng = np.random.default_rng(stable_seed(base_seed, "elastic_net", outcome))
        bootstrap_coefficients = np.zeros((n_resamples, len(exposure_ids)), dtype=float)
        for sample_index in range(n_resamples):
            sampled: list[int] = []
            for block in sorted(np.unique(block_values)):
                members = np.flatnonzero(block_values == block)
                sampled.extend(rng.choice(members, size=len(members), replace=True).tolist())
            index = np.asarray(sampled, dtype=int)
            try:
                params = _fit_regularized_poisson(
                    x[index],
                    observed[index],
                    expected[index],
                    alpha=final_alpha,
                    l1_ratio=final_l1,
                )
                bootstrap_coefficients[sample_index] = params[1:]
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                bootstrap_coefficients[sample_index] = np.nan
        for column, exposure_id in enumerate(exposure_ids):
            coefficients = bootstrap_coefficients[:, column]
            coefficients = coefficients[np.isfinite(coefficients)]
            selected_mask = np.abs(coefficients) > 1e-8
            stability_rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure_id,
                    "valid_resamples": int(len(coefficients)),
                    "selection_frequency": float(selected_mask.mean()) if len(coefficients) else np.nan,
                    "positive_frequency": float((coefficients > 1e-8).mean()) if len(coefficients) else np.nan,
                    "negative_frequency": float((coefficients < -1e-8).mean()) if len(coefficients) else np.nan,
                    "resamples_requested": n_resamples,
                    "causal_interpretation": False,
                }
            )
    return (
        pd.DataFrame(performance_rows),
        pd.DataFrame(coefficient_rows),
        pd.DataFrame(stability_rows),
    )


def prepare_bayesian_model_data(
    outcome_frame: pd.DataFrame,
    exposures: pd.DataFrame,
    graph: SpatialGraph,
    *,
    outcome: str,
    exposure_name: str,
    source_column: str,
    covariates: Sequence[str],
    window: str,
) -> BayesianModelData:
    """Align, validate, and standardize one model to the stable graph order."""
    columns = ["spatial_id", "spatial_name", "observed", "expected"]
    frame = outcome_frame[outcome_frame["outcome"] == outcome][columns].merge(
        exposures[["spatial_id", source_column, *covariates]],
        on="spatial_id",
        how="inner",
        validate="one_to_one",
    )
    frame["spatial_id"] = normalise_spatial_id(frame["spatial_id"])
    position = {value: index for index, value in enumerate(graph.spatial_ids)}
    frame["position"] = frame["spatial_id"].map(position)
    required = ["observed", "expected", source_column, *covariates, "position"]
    frame[required] = frame[required].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=required)
    frame = frame[frame["expected"] > 0].sort_values("position")
    if tuple(frame["spatial_id"]) != graph.spatial_ids:
        missing = sorted(set(graph.spatial_ids).difference(frame["spatial_id"]))
        raise ValueError(f"Bayesian model requires the complete connected graph; missing {missing}")
    exposure_values = frame[source_column].to_numpy(dtype=float)
    exposure_mean = float(exposure_values.mean())
    exposure_sd = float(exposure_values.std(ddof=0))
    if not math.isfinite(exposure_sd) or exposure_sd <= 0:
        raise ValueError(f"Exposure {exposure_name} is constant")
    exposure_z = (exposure_values - exposure_mean) / exposure_sd
    covariate_values = frame[list(covariates)].to_numpy(dtype=float)
    covariate_sd = covariate_values.std(axis=0, ddof=0)
    if np.any(~np.isfinite(covariate_sd)) or np.any(covariate_sd <= 0):
        raise ValueError("Bayesian model has a constant covariate")
    covariate_z = (covariate_values - covariate_values.mean(axis=0)) / covariate_sd
    return BayesianModelData(
        spatial_ids=tuple(frame["spatial_id"]),
        spatial_names=tuple(frame["spatial_name"]),
        observed=frame["observed"].to_numpy(dtype=int),
        expected=frame["expected"].to_numpy(dtype=float),
        exposure=exposure_z,
        covariates=covariate_z,
        covariate_names=tuple(str(value) for value in covariates),
        exposure_mean=exposure_mean,
        exposure_sd=exposure_sd,
        outcome=outcome,
        exposure_name=exposure_name,
        window=window,
    )


class _ArviZCompatibility:
    """Keep diagnostic return types stable across ArviZ/xarray releases."""

    def __init__(self, module: Any) -> None:
        self._module = module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)

    def bfmi(self, data: Any, *args: Any, **kwargs: Any) -> Any:
        result = self._module.bfmi(data, *args, **kwargs)
        # ArviZ >=1 returns a DataTree for idata-like input.  Existing
        # diagnostics consume the numeric BFMI values, so expose the dataset
        # at the selected group as a DataArray without changing the statistic.
        if result.__class__.__name__ == "DataTree" and hasattr(result, "to_dataset"):
            return result.to_dataset().to_array()
        return result


def require_bayesian_dependencies() -> tuple[Any, Any, Any]:
    """Import optional spatial dependencies only for explicit Bayesian runs."""
    try:
        import arviz as az
        import pymc as pm
        import pytensor.tensor as pt
    except ImportError as exc:
        raise RuntimeError(
            "Bayesian inference requires the optional spatial environment: "
            "run `uv sync --extra dev --extra spatial` first"
        ) from exc
    return pm, _ArviZCompatibility(az), pt


def build_pymc_nb_model(
    data: BayesianModelData,
    graph: SpatialGraph,
    bym2_config: Mapping[str, Any],
    *,
    spatial: bool,
    include_exposure: bool,
    rho_prior: Sequence[float] | None = None,
    observed_indices: Sequence[int] | None = None,
) -> Any:
    """Construct the prespecified NB, NB-BYM2-null, or NB-BYM2 model."""
    pm, _, pt = require_bayesian_dependencies()
    indices = np.asarray(
        list(range(len(data.observed))) if observed_indices is None else observed_indices,
        dtype=int,
    )
    coords = {
        "area": list(data.spatial_ids),
        "covariate": list(data.covariate_names),
        "observed_area": [data.spatial_ids[index] for index in indices],
    }
    coefficient_sd = float(bym2_config["coefficient_sd"])
    with pm.Model(coords=coords) as model:
        intercept = pm.Normal("intercept", mu=0, sigma=1)
        gamma = pm.Normal("gamma", mu=0, sigma=coefficient_sd, dims="covariate")
        linear = intercept + pt.dot(data.covariates, gamma)
        if include_exposure:
            beta = pm.Normal("beta", mu=0, sigma=coefficient_sd)
            linear = linear + beta * data.exposure
        alpha = pm.LogNormal(
            "alpha",
            mu=float(bym2_config["log_alpha_mean"]),
            sigma=float(bym2_config["log_alpha_sd"]),
        )
        if spatial:
            theta = pm.Normal("theta", mu=0, sigma=1, dims="area")
            phi = pm.ICAR("phi", W=graph.adjacency, dims="area")
            tail_probability = float(
                bym2_config["spatial_sigma_tail_probability_above_one"]
            )
            sigma = pm.Exponential("sigma", lam=-math.log(tail_probability))
            rho_parameters = rho_prior or bym2_config["rho_prior"]
            rho = pm.Beta("rho", alpha=float(rho_parameters[0]), beta=float(rho_parameters[1]))
            mixture = pm.Deterministic(
                "bym2_mixture",
                pt.sqrt(1 - rho) * theta
                + pt.sqrt(rho / graph.scaling_factor) * phi,
                dims="area",
            )
            spatial_effect = pm.Deterministic("spatial_effect", sigma * mixture, dims="area")
            linear = linear + spatial_effect
        mu = pm.Deterministic("mu", pt.exp(np.log(data.expected) + linear), dims="area")
        pm.NegativeBinomial(
            "observed",
            mu=mu[indices],
            alpha=alpha,
            observed=data.observed[indices],
            dims="observed_area",
        )
    return model


def sample_pymc_model(
    model: Any,
    *,
    draws: int,
    tune: int,
    chains: int,
    target_accept: float,
    seed: int,
    progressbar: bool = True,
) -> Any:
    pm, _, _ = require_bayesian_dependencies()
    with model:
        idata = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            cores=min(chains, 4),
            target_accept=target_accept,
            random_seed=seed,
            return_inferencedata=True,
            progressbar=progressbar,
        )
        pm.compute_log_likelihood(
            idata,
            model=model,
            extend_inferencedata=True,
            progressbar=progressbar,
        )
        return idata


def _diagnostic_numeric_array(value: Any) -> np.ndarray:
    """Normalize ArviZ/xarray diagnostic containers without requiring names."""
    dataset = getattr(value, "dataset", None)
    if dataset is not None:
        value = dataset
    if hasattr(value, "to_array"):
        value = value.to_array()
    if hasattr(value, "to_numpy"):
        value = value.to_numpy()
    elif hasattr(value, "values"):
        value = value.values
    return np.asarray(value, dtype=float)


def bayesian_diagnostics(idata: Any, thresholds: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the prespecified convergence diagnostics and pass/fail state."""
    _, az, _ = require_bayesian_dependencies()
    variables = [
        value
        for value in ["intercept", "beta", "gamma", "alpha", "sigma", "rho", "theta", "phi"]
        if value in idata.posterior
    ]
    summary = az.summary(idata, var_names=variables, kind="diagnostics")
    max_rhat = float(summary["r_hat"].max())
    min_ess_bulk = float(summary["ess_bulk"].min())
    min_ess_tail = float(summary["ess_tail"].min())
    divergences = int(np.asarray(idata.sample_stats["diverging"]).sum())
    bfmi_values = _diagnostic_numeric_array(az.bfmi(idata))
    min_bfmi = float(np.min(bfmi_values))
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


def _posterior_values(idata: Any, variable: str) -> np.ndarray:
    return np.asarray(idata.posterior[variable]).reshape(-1)


def summarize_bayesian_effect(
    idata: Any,
    data: BayesianModelData,
    *,
    rope_rr: Sequence[float],
) -> dict[str, Any]:
    """Report RR and posterior probabilities without inventing a Bayesian p-value."""
    _, az, _ = require_bayesian_dependencies()
    beta = _posterior_values(idata, "beta")
    rr = np.exp(beta)
    hdi = np.asarray(az.hdi(rr, prob=0.95))
    probability_above = float(np.mean(rr > 1))
    probability_below = float(np.mean(rr < 1))
    result = {
        "outcome": data.outcome,
        "exposure": data.exposure_name,
        "window": data.window,
        "n": len(data.observed),
        "exposure_mean": data.exposure_mean,
        "exposure_sd": data.exposure_sd,
        "rr_per_sd": float(np.median(rr)),
        "hdi_95_low": float(hdi[0]),
        "hdi_95_high": float(hdi[1]),
        "probability_rr_gt_1": probability_above,
        "probability_rr_lt_1": probability_below,
        "probability_direction": max(probability_above, probability_below),
        "probability_in_rope": float(
            np.mean((rr >= float(rope_rr[0])) & (rr <= float(rope_rr[1])))
        ),
        "bayesian_p_value": None,
        "alpha_median": float(np.median(_posterior_values(idata, "alpha"))),
    }
    if "sigma" in idata.posterior:
        sigma = _posterior_values(idata, "sigma")
        rho = _posterior_values(idata, "rho")
        result.update(
            {
                "spatial_sigma_median": float(np.median(sigma)),
                "rho_median": float(np.median(rho)),
            }
        )
    return result


def posterior_predictive_checks(
    idata: Any,
    data: BayesianModelData,
    *,
    seed: int,
    max_draws: int = 1000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate NB replications and summarize global and commune diagnostics."""
    mu = np.asarray(idata.posterior["mu"]).reshape(-1, len(data.observed))
    alpha = _posterior_values(idata, "alpha")
    rng = np.random.default_rng(seed)
    if len(alpha) > max_draws:
        selected = rng.choice(len(alpha), size=max_draws, replace=False)
        mu = mu[selected]
        alpha = alpha[selected]
    probability = alpha[:, None] / (alpha[:, None] + mu)
    replicated = rng.negative_binomial(alpha[:, None], probability)
    statistics = {
        "total": lambda values: values.sum(axis=1),
        "variance": lambda values: values.var(axis=1, ddof=1),
        "maximum": lambda values: values.max(axis=1),
        "commune_q10": lambda values: np.quantile(values, 0.10, axis=1),
        "commune_median": lambda values: np.median(values, axis=1),
        "commune_q90": lambda values: np.quantile(values, 0.90, axis=1),
    }
    rows: list[dict[str, Any]] = []
    observed_2d = data.observed[None, :]
    for name, function in statistics.items():
        values = function(replicated)
        observed = float(function(observed_2d)[0])
        rows.append(
            {
                "statistic": name,
                "observed": observed,
                "predictive_median": float(np.median(values)),
                "predictive_hdi_95_low": float(np.quantile(values, 0.025)),
                "predictive_hdi_95_high": float(np.quantile(values, 0.975)),
                "posterior_predictive_tail_probability": float(
                    2 * min(np.mean(values >= observed), np.mean(values <= observed))
                ),
            }
        )
    commune = pd.DataFrame(
        {
            "spatial_id": data.spatial_ids,
            "spatial_name": data.spatial_names,
            "observed": data.observed,
            "predictive_median": np.median(replicated, axis=0),
            "predictive_hdi_95_low": np.quantile(replicated, 0.025, axis=0),
            "predictive_hdi_95_high": np.quantile(replicated, 0.975, axis=0),
        }
    )
    return pd.DataFrame(rows), commune


def extract_loo_result(loo: Any) -> dict[str, Any]:
    """Normalize pointwise PSIS-LOO fields across ArviZ API generations.

    ArviZ before 1.0 exposed ``elpd_loo``, ``p_loo`` and ``loo_i``. ArviZ 1
    delegates to arviz-stats, whose ``ELPDData`` exposes ``elpd``, ``p`` and
    ``elpd_i``. Both represent the same log-scale quantities used by reloo.
    """

    def first(*names: str) -> Any:
        for name in names:
            try:
                value = getattr(loo, name)
            except AttributeError:
                try:
                    value = loo[name]
                except (KeyError, TypeError, AttributeError):
                    continue
            if value is not None:
                return value
        raise ValueError(f"PSIS-LOO result is missing compatible fields: {names}")

    return {
        "elpd_loo": float(first("elpd_loo", "elpd")),
        "se": float(first("se")),
        "p_loo": float(first("p_loo", "p")),
        "loo_i": np.asarray(first("loo_i", "elpd_i"), dtype=float).reshape(-1),
        "pareto_k": np.asarray(first("pareto_k"), dtype=float).reshape(-1),
    }


def psis_loo_with_exact_refits(
    idata: Any,
    data: BayesianModelData,
    graph: SpatialGraph,
    bym2_config: Mapping[str, Any],
    *,
    spatial: bool,
    include_exposure: bool,
    rho_prior: Sequence[float] | None,
    seed: int,
    trace_dir: Path | None = None,
    trace_prefix: str = "model",
    progressbar: bool = True,
) -> dict[str, Any]:
    """Compute PSIS-LOO and replace high-k terms with exact held-out refits."""
    _, az, _ = require_bayesian_dependencies()
    loo = az.loo(idata, pointwise=True)
    loo_values = extract_loo_result(loo)
    pareto = loo_values["pareto_k"]
    loo_i = loo_values["loo_i"]
    if len(pareto) != len(data.observed) or len(loo_i) != len(data.observed):
        raise ValueError(
            "Pointwise PSIS-LOO output does not match observations: "
            f"pareto_k={len(pareto)}, loo_i={len(loo_i)}, "
            f"observed={len(data.observed)}"
        )
    threshold = float(bym2_config["pareto_k_reloo_threshold"])
    high = np.flatnonzero(pareto > threshold)
    adjusted = loo_values["elpd_loo"]
    exact_rows: list[dict[str, Any]] = []
    for index in high:
        keep = np.delete(np.arange(len(data.observed)), index)
        model = build_pymc_nb_model(
            data,
            graph,
            bym2_config,
            spatial=spatial,
            include_exposure=include_exposure,
            rho_prior=rho_prior,
            observed_indices=keep,
        )
        refit = sample_pymc_model(
            model,
            draws=int(bym2_config["draws"]),
            tune=int(bym2_config["tune"]),
            chains=int(bym2_config["chains"]),
            target_accept=float(bym2_config["target_accept"]),
            seed=stable_seed(seed, "reloo", data.spatial_ids[index]),
            progressbar=progressbar,
        )
        if trace_dir is not None:
            from exposome.inference_run_state import write_trace_atomic

            trace_dir.mkdir(parents=True, exist_ok=True)
            required_variables = ["intercept", "gamma", "alpha", "mu"]
            if include_exposure:
                required_variables.append("beta")
            if spatial:
                required_variables.extend(["theta", "phi", "sigma", "rho"])
            write_trace_atomic(
                refit,
                trace_dir
                / f"{trace_prefix}__reloo_{data.spatial_ids[index]}.nc",
                required_variables=required_variables,
                expected_chains=int(bym2_config["chains"]),
                expected_draws=int(bym2_config["draws"]),
            )
        mu = np.asarray(refit.posterior["mu"])[..., index].reshape(-1)
        alpha = _posterior_values(refit, "alpha")
        probability = alpha / (alpha + mu)
        log_density = st.nbinom.logpmf(data.observed[index], alpha, probability)
        exact = float(logsumexp(log_density) - math.log(len(log_density)))
        adjusted += exact - float(loo_i[index])
        exact_rows.append(
            {
                "spatial_id": data.spatial_ids[index],
                "pareto_k": float(pareto[index]),
                "psis_elpd_i": float(loo_i[index]),
                "exact_elpd_i": exact,
            }
        )
    return {
        "elpd_loo": adjusted,
        "elpd_loo_psis": loo_values["elpd_loo"],
        "se": loo_values["se"],
        "p_loo": loo_values["p_loo"],
        "max_pareto_k": float(np.max(pareto)),
        "reloo_count": int(len(high)),
        "reloo": exact_rows,
    }


def fit_with_diagnostic_retry(
    model_factory: Any,
    bym2_config: Mapping[str, Any],
    *,
    seed: int,
    progressbar: bool = True,
) -> tuple[Any, dict[str, Any]]:
    """Sample once, then make the single prespecified stronger retry if needed."""
    attempts = [
        (
            int(bym2_config["draws"]),
            int(bym2_config["tune"]),
            float(bym2_config["target_accept"]),
        ),
        (
            int(bym2_config["retry_draws"]),
            int(bym2_config["retry_tune"]),
            float(bym2_config["retry_target_accept"]),
        ),
    ]
    last_idata = None
    last_diagnostics: dict[str, Any] = {}
    for attempt, (draws, tune, target_accept) in enumerate(attempts, start=1):
        last_idata = sample_pymc_model(
            model_factory(),
            draws=draws,
            tune=tune,
            chains=int(bym2_config["chains"]),
            target_accept=target_accept,
            seed=stable_seed(seed, "attempt", attempt),
            progressbar=progressbar,
        )
        last_diagnostics = bayesian_diagnostics(
            last_idata, bym2_config["diagnostics"]
        )
        last_diagnostics.update(
            {
                "attempt": attempt,
                "chains": int(bym2_config["chains"]),
                "draws": draws,
                "tune": tune,
                "target_accept": target_accept,
                "status": (
                    "ok"
                    if last_diagnostics["diagnostics_passed"]
                    else "retry_required" if attempt == 1 else "failed_diagnostics"
                ),
            }
        )
        if last_diagnostics["diagnostics_passed"]:
            break
    return last_idata, last_diagnostics


def negative_control_availability(
    smr: pd.DataFrame,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    """Record rather than conceal a control missing from a materialized SMR table."""
    available = set(smr["outcome"].astype(str).unique())
    rows = []
    for outcome in config["outcomes"]["negative_control"]:
        for exposure in ("pm25_hist", "no2"):
            rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure,
                    "available_in_materialized_smr": outcome in available,
                    "status": "ready" if outcome in available else "missing_requires_local_reaggregation",
                    "microdata_reprocessed_by_inference_cli": False,
                    "interpretation_scope": "environmental_air_pollution_only",
                }
            )
    return pd.DataFrame(rows)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_inference_manifest(
    repo_root: Path,
    config: Mapping[str, Any],
    files: Sequence[Path],
    *,
    run_mode: str,
    status: str,
) -> dict[str, Any]:
    """Create the auditable run manifest with hashes, versions, seed, and git state."""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        git_status = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        revision = None
        git_status = []
    packages = {}
    for package in [
        "numpy",
        "pandas",
        "scipy",
        "statsmodels",
        "scikit-learn",
        "geopandas",
        "libpysal",
        "esda",
        "pymc",
        "arviz",
        "h5netcdf",
    ]:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    records = []
    for path in sorted({Path(value).resolve() for value in files if Path(value).exists()}):
        try:
            relative = path.relative_to(repo_root.resolve())
        except ValueError:
            relative = path
        records.append(
            {
                "path": str(relative),
                "size_bytes": int(path.stat().st_size),
                "sha256": file_sha256(path),
            }
        )
    canonical_config = json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study": config["study"],
        "run_mode": run_mode,
        "status": status,
        "seed": int(config["seed"]),
        "config_sha256": hashlib.sha256(canonical_config.encode("utf-8")).hexdigest(),
        "python": platform.python_version(),
        "packages": packages,
        "git": {
            "revision": revision,
            "dirty": bool(git_status),
            "status_short": git_status,
        },
        "files": records,
        "ecological_not_individual": True,
        "causal_claim": False,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
