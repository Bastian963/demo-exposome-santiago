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
from .neuro_outcomes_stats import compute_exposome_correlations as _compute_exposome_correlations


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
    # Mirror of neuro_mortality.OUTCOME_PREFIXES so the hospitalization comparator
    # yields the same cardiovascular/respiratory morbidity axes for the chronic
    # exposome analysis. Ischemic heart disease + heart failure (disjoint from
    # cerebrovascular I60-I69). Respiratory = pneumonia + acute lower + COPD,
    # excluding J30-J39 upper respiratory; split into the same disjoint subcauses.
    "cardiovascular": ("I20", "I21", "I22", "I23", "I24", "I25", "I50"),
    "respiratory": (
        "J12", "J13", "J14", "J15", "J16", "J17", "J18",
        "J20", "J21", "J22",
        "J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47",
    ),
    "respiratory_pneumonia": ("J12", "J13", "J14", "J15", "J16", "J17", "J18"),
    "respiratory_acute_lower": ("J20", "J21", "J22"),
    "respiratory_copd": ("J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47"),
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


def resolve_source_paths(cfg: dict[str, Any]) -> list[Path]:
    """Resolve the egresos source to one or more local CSV paths.

    Supports three config shapes so that adding the 2018-2022 window (one large
    DEIS CSV per year) needs no code change, only config:
      - source.paths: [<file>, <file>, ...]  explicit list of per-year files
      - source.path:  "…/EGRE_*_*.csv"       glob pattern (matched, sorted)
      - source.path:  "…/EGRE_2006.csv"      single file (back-compat)
    """
    src_cfg = cfg["neuro_hospitalizations"]["source"]
    explicit = src_cfg.get("paths")
    if explicit:
        paths = [Path(p) for p in explicit]
    else:
        raw_path = str(src_cfg["path"])
        if any(ch in raw_path for ch in "*?["):
            paths = sorted(Path().glob(raw_path))
        else:
            paths = [Path(raw_path)]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise FileNotFoundError(
            "Missing hospitalization source. Expected local DEIS egresos CSV(s) at "
            f"{[str(p) for p in paths] or src_cfg.get('path')}. "
            "Download the per-year files from https://deis.minsal.cl/#datosabiertos "
            "and place them under data/raw/deis/egresos/ before running this comparator."
        )
    return existing


def ensure_source_file(cfg: dict[str, Any]) -> Path:
    """Back-compat single-path accessor; returns the first resolved source."""
    return resolve_source_paths(cfg)[0]


def load_source_table(source: Path | list[Path], source_cfg: dict[str, Any]) -> pd.DataFrame:
    sep = source_cfg.get("sep", ",")
    encoding = source_cfg.get("encoding")
    paths = [source] if isinstance(source, (str, Path)) else list(source)
    frames = [pd.read_csv(p, sep=sep, encoding=encoding, low_memory=False) for p in paths]
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


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

    source_paths = resolve_source_paths(cfg)
    streaming_qc: dict[str, Any] | None = None
    streaming_mode = hosp_cfg["source"].get("format") == "zip_csv"
    if streaming_mode:
        from .hospitalization_analytics import (
            aggregate_hospitalization_stream,
            complete_cube_with_population,
            compute_window_smr,
            load_ine_population_person_years,
        )

        crosswalk_path = Path(
            "data/reference/cl/santiago/santiago_communes/cut_crosswalk.csv"
        )
        crosswalk = pd.read_csv(crosswalk_path, dtype={"spatial_id": str})
        cube_counts, streaming_qc = aggregate_hospitalization_stream(
            source_paths,
            hosp_cfg["source"],
            crosswalk,
            hosp_cfg["years"],
            region_code=int(hosp_cfg.get("region_code", 13)),
        )
        population_path = Path(hosp_cfg["population"]["path"])
        population = load_ine_population_person_years(
            population_path,
            crosswalk,
            hosp_cfg["years"],
            region_code=int(hosp_cfg.get("region_code", 13)),
        )
        cube = complete_cube_with_population(cube_counts, population)
        summary = compute_window_smr(cube, hosp_cfg["years"], "full_ingestion")
        regional = (
            summary.groupby("outcome")[["observed", "population_person_years"]]
            .sum()
            .reset_index()
        )
        regional["regional_rate_per_100k"] = (
            regional["observed"] / regional["population_person_years"] * 100_000
        )
        summary = summary.merge(
            regional[["outcome", "regional_rate_per_100k"]],
            on="outcome",
            how="left",
            validate="many_to_one",
        )
        rates = summary.assign(
            name=summary["spatial_name"],
            hospital_year_start=summary["year_start"],
            hospital_year_end=summary["year_end"],
            hospital_n_years=summary["n_years"],
            hospital_admissions_total=summary["observed"],
            hospital_rate_crude_per_100k=summary["rate_crude_per_100k"],
            hospital_rate_age_adjusted_per_100k=(
                summary["smr"] * summary["regional_rate_per_100k"]
            ),
            hospital_expected=summary["expected"],
            hospital_smr=summary["smr"],
            hospital_population_person_years=summary["population_person_years"],
            hospital_days_total=summary["hospital_days_total"],
            hospital_mean_los_days=summary["mean_los_days"],
            hospital_in_hospital_deaths_total=summary["in_hospital_deaths"],
            hospital_low_count_flag=summary["low_count_flag"],
        )[
            [
                "name",
                "outcome",
                "hospital_year_start",
                "hospital_year_end",
                "hospital_n_years",
                "hospital_admissions_total",
                "hospital_rate_crude_per_100k",
                "hospital_rate_age_adjusted_per_100k",
                "hospital_expected",
                "hospital_smr",
                "hospital_population_person_years",
                "hospital_days_total",
                "hospital_mean_los_days",
                "hospital_in_hospital_deaths_total",
                "hospital_low_count_flag",
            ]
        ]
    else:
        raw = load_source_table(source_paths, hosp_cfg["source"])
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

    geometry_candidates = [
        out_dir / f"{city}_exposome_master.geojson",
        Path("data/processed/cl/santiago/santiago_communes/master.geojson"),
        Path("data/processed/santiago_exposome_master.geojson"),
    ]
    geom_path = next((path for path in geometry_candidates if path.exists()), None)
    if geom_path is None:
        raise FileNotFoundError(f"Missing geometry source; checked {geometry_candidates}")
    base_gdf = gpd.read_file(geom_path)[["name", "geometry"]].drop_duplicates("name")
    gdf = base_gdf.merge(rates, on="name", how="right", validate="one_to_many")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    loaded_years = sorted(int(y) for y in hosp_cfg["years"])
    year_start = min(loaded_years)
    year_end = max(loaded_years)
    base_name = f"{city}_neuro_hospitalizations_{year_start}_{year_end}"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    meta_path = out_dir / f"{base_name}_metadata.json"

    rates.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")

    # DEIS publishes hospital-discharge "datos abiertos" per year, 2006 onward.
    deis_available = list(range(2006, 2024))
    missing_years = [y for y in deis_available if y not in loaded_years]
    single_year_smoke_test = len(loaded_years) == 1

    coverage_window = {
        "start": year_start,
        "end": year_end,
        "n_years": len(loaded_years),
        "temporal_mismatch": (
            "Hospitalizations cover only 2006, but the exposome master and the PM2.5 "
            "exposure windows span 2000-2022 with no antecedent window aligned to 2006. "
            "A 2006-only run is therefore a code smoke test of the pipeline, not a valid "
            "chronic-exposome morbidity result."
            if single_year_smoke_test
            else "The full 2011-2020 ingestion supports trend checks. Chronic models use "
            "2018-2019 as the primary pre-COVID outcome window and antecedent PM2.5 "
            "(2000-2017); 2020 is sensitivity-only."
        ),
    }
    if streaming_mode:
        coverage_gap = {
            "status": "current_analysis_window_complete",
            "loaded_years": loaded_years,
            "outside_current_window": missing_years,
            "extension": (
                "Download later annual ZIPs only to extend the registered 2011-2020 series, "
                "then update the config and re-run "
                "scripts/run_hospitalization_exposome_analysis.py."
            ),
        }
        use_cases = [
            "Pre-COVID chronic ecological comparison using 2018-2019 outcomes and antecedent "
            "PM2.5 (2000-2017).",
            "Descriptive 2011-2019 trends and annual fixed-effect panels for exposures with "
            "year-matched local inputs.",
            "Explicitly labelled 2020 COVID-period sensitivity analysis.",
        ]
    else:
        coverage_gap = {
            "status": "documented_known_gap",
            "loaded_years": loaded_years,
            "missing_years": missing_years,
            "remediation_steps": [
                "Download additional annual DEIS files from "
                "https://deis.minsal.cl/#datosabiertos.",
                "Place the per-year CSVs under data/raw/deis/egresos/.",
                "Update neuro_hospitalizations.source and years in the city config.",
                "Re-run scripts/run_neuro_hospitalizations.py.",
            ],
            "estimated_effort_hours": 2,
        }
        use_cases = [
            "Smoke test of the extended cardiovascular/respiratory outcome definitions.",
            "Single-year cross-sectional description only; not chronic inference.",
        ]

    meta_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "city": city,
                "n_rows": int(len(rates)),
                "n_communes": expected,
                "years": loaded_years,
                "coverage_window": coverage_window,
                "coverage_gap": coverage_gap,
                "use_cases": use_cases,
                "source_path_used": [str(p) for p in source_paths],
                "outcomes": {name: list(prefixes) for name, prefixes in OUTCOME_PREFIXES.items()},
                "age_bins": (
                    ["0_9", "10_19", "20_29", "30_39", "40_49", "50_59", "60_69", "70_79", "80_plus"]
                    if streaming_mode
                    else list(AGE_BINS)
                ),
                "standard_population": (
                    "INE base-2017 commune projections by year, sex and single year of age; "
                    "indirect standardization to the RM reference"
                    if streaming_mode
                    else "Santiago commune demography aggregate from Censo 2017"
                ),
                "streaming_qc": streaming_qc,
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
    return _compute_exposome_correlations(
        outcome_df=hospital_df,
        master_df=master_df,
        exposures=exposures,
        outcomes=outcomes,
        covariates=covariates,
        outcome_rate_col="hospital_rate_age_adjusted_per_100k",
        fallback_rate_col="hospital_rate_crude_per_100k",
    )
