"""Commune-level neuropsychiatric hospitalization comparator from DEIS exports.

This module builds an external morbidity table for ecological comparison
against the exposome master table. It is not an exposome layer.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from . import config, demography
from .neuro_mortality import residualize


OUTCOME_PREFIXES: dict[str, tuple[str, ...]] = {
    "mental_all": tuple(f"F{i:02d}" for i in range(0, 100)),
    "dementia": ("F00", "F01", "F02", "F03", "G30"),
    "alzheimer": ("G30",),
    "cerebrovascular": ("I60", "I61", "I62", "I63", "I64", "I65", "I66", "I67", "I68", "I69"),
    "parkinsonism": ("G20", "G21"),
    "substance": tuple(f"F{i:02d}" for i in range(10, 20)),
    "psychosis": tuple(f"F{i:02d}" for i in range(20, 30)),
    "mood": tuple(f"F{i:02d}" for i in range(30, 40)),
    "anxiety_stress": tuple(f"F{i:02d}" for i in range(40, 49)),
}
AGE_BINS = ("0_14", "15_64", "65_plus")
MIN_LOW_COUNT = 10


def clean_icd_code(value: Any) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"[^A-Z0-9.]", "", text)
    return text.replace(".", "")


def icd_matches(code: str, prefixes: tuple[str, ...]) -> bool:
    cleaned = clean_icd_code(code)
    if not cleaned:
        return False
    return any(cleaned.startswith(prefix) for prefix in prefixes)


def classify_egress_age_bin(age_group_value: Any) -> str | None:
    """Map DEIS hospitalization age-group labels to coarse age bins."""
    if age_group_value is None or pd.isna(age_group_value):
        return None
    text = str(age_group_value).lower().strip()
    text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    if not text:
        return None
    if "menor" in text:
        return "0_14"
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    if not numbers:
        return None
    lo = min(numbers)
    hi = max(numbers)
    if hi <= 14:
        return "0_14"
    if lo >= 65 or "mas" in text:
        return "65_plus"
    if lo >= 15 and hi <= 64:
        return "15_64"
    if lo <= 14:
        return "0_14"
    if hi >= 65:
        return "65_plus"
    return "15_64"


def ensure_source_file(cfg: dict[str, Any]) -> Path:
    src_cfg = cfg["neuro_hospitalizations"]["source"]
    local_path = Path(src_cfg["path"])
    if local_path.exists():
        return local_path
    raise FileNotFoundError(
        "Missing hospitalization source. "
        f"Expected local file at {local_path}. "
        "Place the DEIS egresos CSV there before running this comparator."
    )


def load_source_table(source_path: Path, source_cfg: dict[str, Any]) -> pd.DataFrame:
    sep = source_cfg.get("sep", ",")
    encoding = source_cfg.get("encoding")
    return pd.read_csv(source_path, sep=sep, encoding=encoding, low_memory=False)


def _coalesce_commune_name(raw: pd.Series, code_map: pd.DataFrame) -> pd.Series:
    norm = demography.normalize_comuna_name(raw.fillna("").astype(str))
    valid_names = set(code_map["name"])
    return norm.where(norm.isin(valid_names))


def prepare_hospitalization_records(
    raw: pd.DataFrame,
    cfg: dict[str, Any],
    code_map: pd.DataFrame,
) -> pd.DataFrame:
    hosp_cfg = cfg["neuro_hospitalizations"]
    src_cfg = hosp_cfg["source"]
    cols = src_cfg["columns"]

    year_col = cols["year"]
    cause_col = cols["cause"]
    commune_name_col = cols.get("commune_name")
    commune_code_col = cols.get("commune_code")
    region_code_col = cols.get("region_code")
    region_name_col = cols.get("region_name")
    age_group_col = cols.get("age_group")
    sex_col = cols.get("sex")
    days_col = cols.get("days_stay")
    discharge_col = cols.get("discharge_condition")

    df = raw.copy()
    df["year"] = pd.to_numeric(df[year_col], errors="coerce")
    df = df[df["year"].notna()].copy()
    df["year"] = df["year"].astype(int)
    years = {int(y) for y in hosp_cfg["years"]}
    df = df[df["year"].isin(years)].copy()

    region_code = hosp_cfg.get("region_code")
    if region_code and region_code_col and region_code_col in df.columns:
        region_values = pd.to_numeric(df[region_code_col], errors="coerce")
        df = df[region_values == int(region_code)].copy()
    region_filter = src_cfg.get("region_filter")
    if region_filter and region_name_col and region_name_col in df.columns:
        df = df[
            df[region_name_col].astype(str).str.contains(region_filter, case=False, na=False)
        ].copy()

    if commune_code_col and commune_code_col in df.columns:
        df["comuna_code"] = pd.to_numeric(df[commune_code_col], errors="coerce").astype("Int64")
        df = df.merge(code_map[["comuna_code", "name"]], on="comuna_code", how="left")
    else:
        df["name"] = pd.NA

    if commune_name_col and commune_name_col in df.columns:
        fallback_names = _coalesce_commune_name(df[commune_name_col], code_map)
        df["name"] = df["name"].fillna(fallback_names)

    df = df[df["name"].notna()].copy()
    df["name"] = demography.normalize_comuna_name(df["name"])
    df = df[df["name"].isin(set(code_map["name"]))].copy()

    df["cause_code"] = df[cause_col].map(clean_icd_code)
    df = df[df["cause_code"] != ""].copy()
    df["age_bin"] = df[age_group_col].map(classify_egress_age_bin) if age_group_col else None
    df["days_stay"] = pd.to_numeric(df[days_col], errors="coerce").fillna(0.0) if days_col else 0.0

    if discharge_col and discharge_col in df.columns:
        death_values = {str(v).strip() for v in src_cfg.get("in_hospital_death_values", [])}
        df["in_hospital_death"] = df[discharge_col].astype(str).str.strip().isin(death_values).astype(int)
    else:
        df["in_hospital_death"] = 0

    df["sex"] = df[sex_col].astype(str).str.strip() if sex_col else ""
    df["admissions"] = 1.0
    return df


def aggregate_outcome_hospitalizations(records: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for outcome, prefixes in OUTCOME_PREFIXES.items():
        subset = records[records["cause_code"].map(lambda code: icd_matches(code, prefixes))].copy()
        if subset.empty:
            continue
        grouped = (
            subset.groupby(["name", "year", "age_bin"], dropna=False)
            .agg(
                admissions=("admissions", "sum"),
                days_stay=("days_stay", "sum"),
                in_hospital_deaths=("in_hospital_death", "sum"),
            )
            .reset_index()
        )
        grouped["outcome"] = outcome
        frames.append(grouped)

    all_cause = (
        records.groupby(["name", "year", "age_bin"], dropna=False)
        .agg(
            admissions=("admissions", "sum"),
            days_stay=("days_stay", "sum"),
            in_hospital_deaths=("in_hospital_death", "sum"),
        )
        .reset_index()
    )
    all_cause["outcome"] = "all_cause"
    frames.append(all_cause)

    out = pd.concat(frames, ignore_index=True)
    for col in ["admissions", "days_stay", "in_hospital_deaths"]:
        out[col] = out[col].astype(float)
    return out


def _age_weight_map(demography_df: pd.DataFrame) -> dict[str, float]:
    totals = {
        "0_14": float(demography_df["pop_0_14"].sum()),
        "15_64": float(demography_df["pop_15_64"].sum()),
        "65_plus": float(demography_df["pop_65_plus"].sum()),
    }
    grand_total = sum(totals.values())
    return {key: value / grand_total for key, value in totals.items()}


def compute_commune_rates(
    aggregated: pd.DataFrame,
    demography_df: pd.DataFrame,
    years: list[int],
) -> pd.DataFrame:
    n_years = len(years)
    age_weights = _age_weight_map(demography_df)
    pop_lookup = demography_df.set_index("name")[
        ["pop_total", "pop_0_14", "pop_15_64", "pop_65_plus"]
    ]

    rows: list[dict[str, Any]] = []
    for outcome, subset in aggregated.groupby("outcome"):
        admissions_wide = (
            subset.groupby(["name", "age_bin"])["admissions"]
            .sum()
            .unstack("age_bin", fill_value=0.0)
            .reindex(columns=list(AGE_BINS), fill_value=0.0)
        )
        total_admissions = subset.groupby("name")["admissions"].sum()
        total_days = subset.groupby("name")["days_stay"].sum()
        total_deaths = subset.groupby("name")["in_hospital_deaths"].sum()

        for name in pop_lookup.index:
            pop = pop_lookup.loc[name]
            admissions_total = float(total_admissions.get(name, 0.0))
            days_total = float(total_days.get(name, 0.0))
            deaths_total = float(total_deaths.get(name, 0.0))
            crude_rate = admissions_total / (float(pop["pop_total"]) * n_years) * 100_000

            age_specific_rates: dict[str, float] = {}
            if name in admissions_wide.index:
                for age_bin in AGE_BINS:
                    denom = float(pop[f"pop_{age_bin}"])
                    admissions = float(admissions_wide.loc[name, age_bin])
                    age_specific_rates[age_bin] = admissions / (denom * n_years) * 100_000 if denom > 0 else np.nan
            else:
                age_specific_rates = {age_bin: 0.0 for age_bin in AGE_BINS}
            adj_rate = sum(age_specific_rates[age_bin] * age_weights[age_bin] for age_bin in AGE_BINS)

            row = {
                "name": name,
                "outcome": outcome,
                "hospital_year_start": min(years),
                "hospital_year_end": max(years),
                "hospital_n_years": n_years,
                "hospital_admissions_total": round(admissions_total, 2),
                "hospital_rate_crude_per_100k": round(crude_rate, 4),
                "hospital_rate_age_adjusted_per_100k": round(float(adj_rate), 4),
                "hospital_days_total": round(days_total, 2),
                "hospital_mean_los_days": round(days_total / admissions_total, 4) if admissions_total > 0 else np.nan,
                "hospital_in_hospital_deaths_total": round(deaths_total, 2),
                "hospital_low_count_flag": int(admissions_total < MIN_LOW_COUNT),
            }
            for age_bin in AGE_BINS:
                admissions = float(admissions_wide.loc[name, age_bin]) if name in admissions_wide.index else 0.0
                row[f"hospital_admissions_{age_bin}"] = round(admissions, 2)
                rate_val = age_specific_rates[age_bin]
                row[f"hospital_rate_{age_bin}_per_100k"] = round(float(rate_val), 4) if pd.notna(rate_val) else np.nan
            rows.append(row)

    return pd.DataFrame(rows).sort_values(["outcome", "name"]).reset_index(drop=True)


def build_neuro_hospitalization_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    cfg = config.load_config(city)
    hosp_cfg = cfg["neuro_hospitalizations"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_path = ensure_source_file(cfg)
    raw = load_source_table(source_path, hosp_cfg["source"])
    code_map = demography.load_comuna_code_name_map(
        Path(cache_dir),
        region_code=int(hosp_cfg.get("region_code", 13)),
    )
    demo = demography.load_commune_demography(
        Path(cache_dir),
        region_code=int(hosp_cfg.get("region_code", 13)),
    )
    records = prepare_hospitalization_records(raw, cfg, code_map)
    aggregated = aggregate_outcome_hospitalizations(records)
    rates = compute_commune_rates(
        aggregated,
        demo[["name", "pop_total", "pop_0_14", "pop_15_64", "pop_65_plus"]],
        [int(y) for y in hosp_cfg["years"]],
    )

    expected = int(cfg["expected_communes"])
    for outcome in rates["outcome"].unique():
        subset = rates[rates["outcome"] == outcome]
        if len(subset) != expected:
            raise ValueError(f"Outcome {outcome} has {len(subset)} communes, expected {expected}")
        if subset["name"].duplicated().any():
            raise ValueError(f"Duplicate commune names in outcome {outcome}")

    geom_path = out_dir / f"{city}_exposome_master.geojson"
    if not geom_path.exists():
        raise FileNotFoundError(f"Missing geometry source: {geom_path}")
    base_gdf = gpd.read_file(geom_path)[["name", "geometry"]].drop_duplicates("name")
    gdf = base_gdf.merge(rates, on="name", how="right", validate="one_to_many")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    year_start = min(int(y) for y in hosp_cfg["years"])
    year_end = max(int(y) for y in hosp_cfg["years"])
    base_name = f"{city}_neuro_hospitalizations_{year_start}_{year_end}"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    meta_path = out_dir / f"{base_name}_metadata.json"

    rates.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")
    meta_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "city": city,
                "n_rows": int(len(rates)),
                "n_communes": expected,
                "years": [int(y) for y in hosp_cfg["years"]],
                "source_path_used": str(source_path),
                "outcomes": {name: list(prefixes) for name, prefixes in OUTCOME_PREFIXES.items()},
                "age_bins": list(AGE_BINS),
                "standard_population": "Santiago commune demography aggregate from Censo 2017",
                "columns": rates.columns.tolist(),
                "note": (
                    "External ecological morbidity comparator derived from DEIS hospital discharge data. "
                    "Not an exposome layer and not suitable for individual-level inference."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return rates, gdf


def compute_exposome_correlations(
    hospital_df: pd.DataFrame,
    master_df: pd.DataFrame,
    exposures: list[str],
    outcomes: list[str],
    covariates: list[str],
) -> pd.DataFrame:
    from scipy.stats import spearmanr

    merged = hospital_df.merge(master_df, on="name", how="inner", validate="many_to_one")
    rows: list[dict[str, Any]] = []

    for outcome in outcomes:
        subset = merged[merged["outcome"] == outcome].copy()
        if subset.empty:
            continue
        y = subset["hospital_rate_age_adjusted_per_100k"]
        if y.isna().all():
            y = subset["hospital_rate_crude_per_100k"]
        y_rank = y.rank(method="average")

        for exposure in exposures:
            if exposure not in subset.columns:
                rows.append({"outcome": outcome, "exposure": exposure, "status": "missing_exposure"})
                continue
            x = subset[exposure]
            mask = x.notna() & y.notna()
            if int(mask.sum()) < 10:
                rows.append({"outcome": outcome, "exposure": exposure, "status": f"too_few_pairs:{int(mask.sum())}"})
                continue

            rho, pval = spearmanr(x[mask], y[mask])
            cov_df = subset.loc[mask, covariates].copy()
            x_res = residualize(x[mask].rank(method="average"), cov_df.rank(method="average"))
            y_res = residualize(y_rank[mask], cov_df.rank(method="average"))

            partial_rho = np.nan
            partial_p = np.nan
            partial_mask = x_res.notna() & y_res.notna()
            if int(partial_mask.sum()) >= 10:
                partial_rho, partial_p = spearmanr(x_res[partial_mask], y_res[partial_mask])

            rows.append(
                {
                    "outcome": outcome,
                    "exposure": exposure,
                    "n_pairs": int(mask.sum()),
                    "spearman_rho": round(float(rho), 4),
                    "spearman_p": float(pval),
                    "partial_spearman_rho": round(float(partial_rho), 4) if pd.notna(partial_rho) else np.nan,
                    "partial_spearman_p": float(partial_p) if pd.notna(partial_p) else np.nan,
                    "partial_covariates": ",".join(covariates),
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows)
