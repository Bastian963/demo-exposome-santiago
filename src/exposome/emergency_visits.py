"""Daily DEIS emergency-visit outcomes and acute-heat time-series models.

The DEIS files describe the reporting establishment, not patient residence.
Accordingly, this module builds a regional health-service-demand time series;
it does not create a commune-level exposome or an individual-risk estimate.
"""
from __future__ import annotations

import csv
import hashlib
import warnings
from collections import defaultdict
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import Any, Iterable, Mapping
from zipfile import ZipFile

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf


CAUSES: dict[str, str] = {
    "2": "respiratory",
    "12": "circulatory",
    "13": "ami",
    "14": "stroke",
    "35": "self_harm",
    "36": "mental",
}
AGE_COLUMNS: dict[str, str] = {
    "count_under_1": "Menores_1",
    "count_1_4": "De_1_a_4",
    "count_5_14": "De_5_a_14",
    "count_15_64": "De_15_a_64",
    "count_65_plus": "De_65_y_mas",
}
COUNT_COLUMNS = ("count_total", *AGE_COLUMNS)
REGION_METROPOLITANA = "13"


@dataclass(frozen=True)
class AggregationResult:
    daily: pd.DataFrame
    diagnostics: dict[str, Any]
    crosswalk_records: pd.DataFrame


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_member(archive: ZipFile) -> str:
    members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if len(members) != 1:
        raise ValueError(f"Expected exactly one CSV in ZIP, found {len(members)}")
    return members[0]


def _to_int(value: str | None) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def aggregate_emergency_zip(
    zip_path: Path,
    *,
    year: int,
    stable_crosswalk: Mapping[str, str] | None = None,
) -> AggregationResult:
    """Stream one national DEIS ZIP into a small RM daily outcome table.

    Years with explicit geography use ``CodigoRegion`` directly. Earlier years
    require a stable establishment-to-region crosswalk. Totals and age groups
    are accumulated within each cause; different cause totals are never added
    together.
    """

    sums: dict[tuple[str, str], np.ndarray] = defaultdict(
        lambda: np.zeros(len(COUNT_COLUMNS), dtype=np.int64)
    )
    reporters: dict[tuple[str, str], set[str]] = defaultdict(set)
    mappings: set[tuple[str, int, str, str, str]] = set()
    total_rows = 0
    relevant_rows = 0
    selected_rows = 0
    mapped_rows = 0
    mapped_relevant_rows = 0
    age_mismatches = 0
    bad_width_rows = 0

    with ZipFile(zip_path) as archive:
        member = _csv_member(archive)
        with archive.open(member) as raw:
            reader = csv.DictReader(
                TextIOWrapper(raw, encoding="latin1", newline=""), delimiter=";"
            )
            fieldnames = reader.fieldnames or []
            fieldnames[0] = fieldnames[0].lstrip("\ufeff")
            has_geography = "CodigoRegion" in fieldnames
            if not has_geography and stable_crosswalk is None:
                raise ValueError(f"{year} has no geography and no crosswalk was supplied")

            for row in reader:
                total_rows += 1
                if None in row:
                    bad_width_rows += 1
                    continue
                establishment = row["IdEstablecimiento"]
                if has_geography:
                    region = row["CodigoRegion"].strip()
                    mappings.add(
                        (
                            establishment,
                            year,
                            region,
                            row.get("CodigoComuna", "").strip(),
                            row.get("NombreComuna", "").strip(),
                        )
                    )
                    mapped_rows += 1
                else:
                    region = stable_crosswalk.get(establishment, "")
                    if region:
                        mapped_rows += 1

                cause_id = row["IdCausa"].strip()
                if cause_id not in CAUSES:
                    continue
                relevant_rows += 1
                if region:
                    mapped_relevant_rows += 1
                if region != REGION_METROPOLITANA:
                    continue

                selected_rows += 1
                total = _to_int(row["Total"])
                ages = [_to_int(row[source]) for source in AGE_COLUMNS.values()]
                if total != sum(ages):
                    age_mismatches += 1
                key = (row["fecha"].strip(), CAUSES[cause_id])
                sums[key] += np.asarray([total, *ages], dtype=np.int64)
                reporters[key].add(establishment)

    daily_rows: list[dict[str, Any]] = []
    for (date, outcome), values in sums.items():
        item: dict[str, Any] = {
            "date": date,
            "outcome": outcome,
            "reporting_establishments": len(reporters[(date, outcome)]),
            "source_year": year,
        }
        item.update(dict(zip(COUNT_COLUMNS, values.tolist(), strict=True)))
        daily_rows.append(item)
    daily = pd.DataFrame(daily_rows)
    if not daily.empty:
        daily["date"] = pd.to_datetime(daily["date"], format="%d/%m/%Y")
        daily = daily.sort_values(["date", "outcome"]).reset_index(drop=True)

    crosswalk_records = pd.DataFrame(
        sorted(mappings),
        columns=["establishment_id", "year", "region_code", "commune_code", "commune_name"],
    )
    diagnostics = {
        "year": year,
        "zip_path": str(zip_path),
        "zip_sha256": sha256_file(zip_path),
        "has_explicit_geography": has_geography,
        "total_rows": total_rows,
        "relevant_rows": relevant_rows,
        "selected_rm_rows": selected_rows,
        "mapped_rows": mapped_rows,
        "mapped_row_fraction": mapped_rows / total_rows if total_rows else 0.0,
        "mapped_relevant_rows": mapped_relevant_rows,
        "mapped_relevant_fraction": (
            mapped_relevant_rows / relevant_rows if relevant_rows else 0.0
        ),
        "age_mismatch_rows": age_mismatches,
        "bad_width_rows": bad_width_rows,
        "daily_dates": int(daily["date"].nunique()) if not daily.empty else 0,
        "daily_rows": len(daily),
    }
    return AggregationResult(daily, diagnostics, crosswalk_records)


def build_stable_crosswalk(records: pd.DataFrame) -> tuple[dict[str, str], pd.DataFrame]:
    """Return region mappings only for IDs stable across all observed direct years."""

    required = {"establishment_id", "year", "region_code", "commune_code", "commune_name"}
    missing = sorted(required - set(records.columns))
    if missing:
        raise ValueError(f"Crosswalk records are missing columns: {missing}")
    unique = records.drop_duplicates().copy()
    for column in ["establishment_id", "region_code", "commune_code", "commune_name"]:
        unique[column] = unique[column].fillna("").astype(str)
    unique["year"] = pd.to_numeric(unique["year"], errors="raise").astype(int)
    summary_rows: list[dict[str, Any]] = []
    stable: dict[str, str] = {}
    for establishment, group in unique.groupby("establishment_id"):
        locations = group[["region_code", "commune_code"]].drop_duplicates()
        is_stable = len(locations) == 1
        region_codes = sorted(group["region_code"].unique())
        commune_codes = sorted(group["commune_code"].unique())
        if is_stable:
            stable[str(establishment)] = region_codes[0]
        summary_rows.append(
            {
                "establishment_id": establishment,
                "years_observed": ",".join(map(str, sorted(group["year"].unique()))),
                "region_codes": ",".join(region_codes),
                "commune_codes": ",".join(commune_codes),
                "stable": is_stable,
            }
        )
    return stable, pd.DataFrame(summary_rows).sort_values("establishment_id")


def build_regional_temperature(
    climate_daily_path: Path,
    demography_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Population-weight commune daily weather into one RM exposure series."""

    climate = pd.read_csv(climate_daily_path, parse_dates=["date"])
    population = pd.read_csv(demography_path)[["name", "pop_total"]]
    if population["name"].nunique() != 52:
        raise ValueError("Demography must contain 52 unique Santiago communes")
    merged = climate.merge(population, on="name", how="inner", validate="many_to_one")
    if merged["name"].nunique() != 52:
        raise ValueError("Climate and demography did not match all 52 communes")
    variables = [
        "temperature_2m_max",
        "temperature_2m_mean",
        "apparent_temperature_max",
        "precipitation_sum",
    ]
    for variable in variables:
        merged[f"weighted_{variable}"] = merged[variable] * merged["pop_total"]
    aggregations: dict[str, tuple[str, str]] = {"population": ("pop_total", "sum")}
    aggregations.update(
        {variable: (f"weighted_{variable}", "sum") for variable in variables}
    )
    regional = merged.groupby("date", as_index=False).agg(**aggregations)
    for variable in variables:
        regional[variable] = regional[variable] / regional["population"]
    regional = regional.sort_values("date").reset_index(drop=True)
    expected_rows = len(pd.date_range(regional["date"].min(), regional["date"].max()))
    if len(regional) != expected_rows:
        raise ValueError("Regional climate series has missing dates")
    metadata = {
        "source_path": str(climate_daily_path),
        "source_sha256": sha256_file(climate_daily_path),
        "demography_path": str(demography_path),
        "demography_sha256": sha256_file(demography_path),
        "start_date": regional["date"].min().date().isoformat(),
        "end_date": regional["date"].max().date().isoformat(),
        "days": len(regional),
        "communes": int(merged["name"].nunique()),
        "weight": "Censo 2017 pop_total",
    }
    return regional, metadata


def add_heat_exposures(
    regional: pd.DataFrame,
    *,
    quantile: float = 0.95,
    lag_days: int = 3,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Add outcome-independent heat thresholds, lags, and a future placebo."""

    data = regional.sort_values("date").copy()
    thresholds = {
        "temperature_2m_max": float(data["temperature_2m_max"].quantile(quantile)),
        "apparent_temperature_max": float(
            data["apparent_temperature_max"].quantile(quantile)
        ),
    }
    for variable, prefix in [
        ("temperature_2m_max", "heat"),
        ("apparent_temperature_max", "apparent_heat"),
    ]:
        excess = (data[variable] - thresholds[variable]).clip(lower=0)
        data[f"{prefix}_excess"] = excess
        lagged = [excess.shift(lag) for lag in range(lag_days + 1)]
        data[f"{prefix}_excess_lag03"] = sum(lagged) / (lag_days + 1)
    data["heat_day"] = (data["heat_excess"] > 0).astype(int)
    data["placebo_heat_excess_lead7"] = data["heat_excess_lag03"].shift(-7)
    return data, thresholds


def prepare_model_frame(
    daily: pd.DataFrame,
    exposures: pd.DataFrame,
    *,
    outcome: str,
    count_column: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    selected = daily.loc[daily["outcome"].eq(outcome)].copy()
    selected["count"] = selected[count_column]
    merged = selected.merge(exposures, on="date", how="inner", validate="one_to_one")
    mask = merged["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    merged = merged.loc[mask].copy()
    merged["dow"] = merged["date"].dt.dayofweek.astype(str)
    merged["stratum"] = merged["date"].dt.to_period("M").astype(str) + "_" + merged["dow"]
    merged = merged.replace([np.inf, -np.inf], np.nan)
    return merged


def fit_poisson_hac(
    frame: pd.DataFrame,
    *,
    exposure: str,
    maxlags: int = 7,
) -> dict[str, Any]:
    columns = ["count", "reporting_establishments", "stratum", exposure]
    data = frame[columns].dropna().copy()
    if (data["reporting_establishments"] <= 0).any():
        raise ValueError("Reporting-establishment offset must be positive")
    model = smf.glm(
        f"count ~ {exposure} + C(stratum)",
        data=data,
        family=sm.families.Poisson(),
        offset=np.log(data["reporting_establishments"]),
    ).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    beta = float(model.params[exposure])
    se = float(model.bse[exposure])
    return {
        "method": "poisson_fixed_effects_hac7",
        "exposure": exposure,
        "n_days": len(data),
        "beta": beta,
        "se": se,
        "rr": float(np.exp(beta)),
        "ci_low": float(np.exp(beta - 1.96 * se)),
        "ci_high": float(np.exp(beta + 1.96 * se)),
        "p_value": float(model.pvalues[exposure]),
        "dispersion": float(model.pearson_chi2 / model.df_resid),
        "converged": bool(model.converged),
    }


def fit_negative_binomial(
    frame: pd.DataFrame,
    *,
    exposure: str,
) -> dict[str, Any]:
    columns = ["count", "reporting_establishments", "stratum", exposure]
    data = frame[columns].dropna().copy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.negativebinomial(
            f"count ~ {exposure} + C(stratum)",
            data=data,
            offset=np.log(data["reporting_establishments"]),
        ).fit(disp=0, maxiter=300)
    beta = float(model.params[exposure])
    se = float(model.bse[exposure])
    return {
        "method": "negative_binomial_fixed_effects",
        "exposure": exposure,
        "n_days": len(data),
        "beta": beta,
        "se": se,
        "rr": float(np.exp(beta)),
        "ci_low": float(np.exp(beta - 1.96 * se)),
        "ci_high": float(np.exp(beta + 1.96 * se)),
        "p_value": float(model.pvalues[exposure]),
        "dispersion": np.nan,
        "converged": bool(model.mle_retvals.get("converged", False)),
    }


def reporting_stability(frame: pd.DataFrame) -> float:
    """Minimum daily reporters relative to the corresponding monthly median."""

    data = frame.copy()
    data["month"] = data["date"].dt.to_period("M")
    medians = data.groupby("month")["reporting_establishments"].transform("median")
    return float((data["reporting_establishments"] / medians).min())


def retention_verdict(
    *,
    direct_frame: pd.DataFrame,
    primary_result: Mapping[str, Any],
    nb_result: Mapping[str, Any] | None,
    placebo_result: Mapping[str, Any],
    yearly_diagnostics: Iterable[Mapping[str, Any]],
    expected_direct_days: int = 731,
    min_crosswalk_fraction: float = 0.97,
) -> dict[str, Any]:
    """Apply outcome-independent quality gates; significance is not a gate."""

    direct_reasons: list[str] = []
    crosswalk_reasons: list[str] = []
    n_days = int(direct_frame["date"].nunique())
    heat_days = int(direct_frame.loc[direct_frame["heat_day"].eq(1), "date"].nunique())
    stability = reporting_stability(direct_frame)
    if n_days < int(expected_direct_days * 0.99):
        direct_reasons.append("fewer_than_99pct_expected_direct_days")
    if heat_days < 50:
        direct_reasons.append("fewer_than_50_heat_days")
    if stability < 0.90:
        direct_reasons.append("daily_reporting_below_90pct_monthly_median")
    if not bool(primary_result.get("converged")):
        direct_reasons.append("primary_model_did_not_converge")
    if nb_result and bool(nb_result.get("converged")):
        primary_beta = float(primary_result["beta"])
        nb_beta = float(nb_result["beta"])
        if primary_beta * nb_beta < 0 and min(abs(primary_beta), abs(nb_beta)) >= 0.02:
            direct_reasons.append("poisson_nb_material_direction_reversal")
    placebo_beta = abs(float(placebo_result["beta"]))
    primary_beta_abs = abs(float(primary_result["beta"]))
    if float(placebo_result["p_value"]) < 0.05 and placebo_beta >= primary_beta_abs:
        direct_reasons.append("future_temperature_placebo_stronger_than_primary")

    for diagnostic in yearly_diagnostics:
        if int(diagnostic["year"]) <= 2022:
            fraction = float(diagnostic.get("mapped_relevant_fraction", 0.0))
            if fraction < min_crosswalk_fraction:
                crosswalk_reasons.append(
                    f"{diagnostic['year']}_mapped_relevant_fraction_below_{min_crosswalk_fraction}"
                )
    if direct_reasons:
        verdict = "remove"
    elif crosswalk_reasons:
        verdict = "keep_direct_years"
    else:
        verdict = "keep_all"
    return {
        "verdict": verdict,
        "direct_gate_reasons": direct_reasons,
        "crosswalk_gate_reasons": crosswalk_reasons,
        "direct_days": n_days,
        "heat_days": heat_days,
        "minimum_reporting_ratio": stability,
        "significance_required": False,
    }
