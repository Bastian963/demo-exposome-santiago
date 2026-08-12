"""Quality-gated ecological associations for AMBA outcome comparators."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from statsmodels.stats.outliers_influence import variance_inflation_factor
import statsmodels.api as sm

from .studies import load_study


REQUIRED_COVARIATES = (
    "census_pct_65_plus",
    "census_pct_male",
    "census_log_population_density",
    "census_material_deprivation",
    "is_caba",
)
MAX_VIF = 5.0
MAX_MORAN_P = 0.05
MAX_POISSON_DISPERSION = 1.5


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    if not len(values):
        return []
    order = np.argsort(values)
    ranked = values[order] * len(values) / np.arange(1, len(values) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    result = np.empty_like(ranked)
    result[order] = np.clip(ranked, 0, 1)
    return result.tolist()


def _vif(frame: pd.DataFrame) -> dict[str, float]:
    matrix = sm.add_constant(frame.astype(float), has_constant="add")
    return {
        column: float(variance_inflation_factor(matrix.to_numpy(), index))
        for index, column in enumerate(matrix.columns)
        if column != "const"
    }


def _moran(residuals: pd.Series, geometry: gpd.GeoDataFrame) -> dict[str, float]:
    import libpysal
    from esda.moran import Moran

    aligned = geometry.set_index("spatial_id").loc[residuals.index]
    weights = libpysal.weights.Queen.from_dataframe(aligned, use_index=True)
    weights.transform = "r"
    statistic = Moran(residuals.loc[aligned.index].to_numpy(), weights, permutations=999)
    return {"i": float(statistic.I), "p": float(statistic.p_sim)}


def evaluate_association(
    frame: pd.DataFrame,
    *,
    outcome_count: str,
    person_years: str,
    outcome_rate: str,
    exposure: str,
    covariates: Sequence[str] = REQUIRED_COVARIATES,
    geometry: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Fit one pre-specified single-exposure model and evaluate its release gate."""
    columns = ["spatial_id", outcome_count, person_years, outcome_rate, exposure, *covariates]
    data = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    result: dict[str, Any] = {
        "n": int(len(data)),
        "exposure_id": exposure,
        "release_status": "gated",
        "gate_reasons": [],
    }
    if len(data) < 45:
        result["gate_reasons"].append("fewer_than_45_complete_units")
        return result
    rho, rho_p = spearmanr(data[exposure], data[outcome_rate])
    result.update({"spearman_rho": float(rho), "spearman_p": float(rho_p)})

    x = data[[exposure, *covariates]].astype(float)
    x[exposure] = (x[exposure] - x[exposure].mean()) / x[exposure].std(ddof=0)
    vifs = _vif(x)
    result["vif"] = vifs
    if any(not np.isfinite(value) or value >= MAX_VIF for value in vifs.values()):
        result["gate_reasons"].append("vif_at_or_above_5")

    design = sm.add_constant(x, has_constant="add")
    outcome = data[outcome_count].astype(float)
    offset = np.log(data[person_years].astype(float))
    poisson = sm.GLM(outcome, design, family=sm.families.Poisson(), offset=offset).fit(
        cov_type="HC3"
    )
    dispersion = float(np.sum(poisson.resid_pearson**2) / poisson.df_resid)
    result["poisson_dispersion"] = dispersion
    model: Any = poisson
    method = "poisson_hc3"
    if dispersion > MAX_POISSON_DISPERSION:
        model = sm.NegativeBinomial(outcome, design, offset=offset).fit(
            disp=0, maxiter=300
        )
        method = "negative_binomial_2"
        converged = bool(model.mle_retvals.get("converged", False))
    else:
        converged = bool(getattr(model, "converged", True))
    result["method"] = method
    result["converged"] = converged
    if not converged:
        result["gate_reasons"].append("model_did_not_converge")

    beta = float(model.params[exposure])
    se = float(model.bse[exposure])
    result.update(
        {
            "adjusted_rr": float(np.exp(beta)),
            "ci_low": float(np.exp(beta - 1.96 * se)),
            "ci_high": float(np.exp(beta + 1.96 * se)),
            "p_value": float(model.pvalues[exposure]),
        }
    )
    residual_values = np.asarray(
        model.resid_pearson if hasattr(model, "resid_pearson") else model.resid,
        dtype=float,
    )
    residuals = pd.Series(residual_values, index=data["spatial_id"].astype(str))
    if geometry is None:
        result["gate_reasons"].append("spatial_diagnostic_missing")
    else:
        moran = _moran(residuals, geometry)
        result.update({"residual_moran_i": moran["i"], "residual_moran_p": moran["p"]})
        if moran["p"] < MAX_MORAN_P:
            result["gate_reasons"].append("residual_spatial_autocorrelation")
    result["points"] = [
        {"spatial_id": row.spatial_id, "x": float(getattr(row, exposure)), "y": float(getattr(row, outcome_rate))}
        for row in data.itertuples(index=False)
    ]
    if not result["gate_reasons"]:
        result["release_status"] = "released"
    return result


def build_argentina_associations(
    *,
    city: str = "buenos_aires_amba",
    processed_dir: Path | None = None,
    covariates_path: Path | None = None,
) -> Path:
    """Build public results only after the pre-specified quality gates pass."""
    context = load_study(city)
    processed = Path(processed_dir or context.paths.processed)
    covariates = Path(
        covariates_path
        or processed / "covariates" / "argentina_census2022_covariates.csv"
    )
    report_dir = processed / "analysis"
    report_dir.mkdir(parents=True, exist_ok=True)
    gate_path = report_dir / "association_gate_report.json"
    if not covariates.exists():
        gate_path.write_text(
            json.dumps(
                {
                    "created_utc": datetime.now(UTC).isoformat(),
                    "study_id": context.study.id,
                    "release_status": "gated",
                    "gate_reasons": ["missing_census2022_covariates"],
                    "required_columns": list(REQUIRED_COVARIATES),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return gate_path
    missing = sorted(set(REQUIRED_COVARIATES) - set(pd.read_csv(covariates, nrows=0).columns))
    if missing:
        raise ValueError(f"Argentina association covariates are missing: {missing}")
    # The modelling pass is intentionally not allowed to silently fall back to
    # crude outcomes. A future census ingest must materialize standardisation
    # diagnostics before this gate can open.
    gate_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(UTC).isoformat(),
                "study_id": context.study.id,
                "release_status": "gated",
                "gate_reasons": ["age_sex_standardisation_not_materialized"],
                "covariates_path": str(covariates),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return gate_path
