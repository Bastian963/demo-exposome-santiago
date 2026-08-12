"""Commune-level neuro-sanitary mortality comparator from DEIS mortality exports.

This module builds an external outcome table for ecological comparison against
the exposome master table. It does not represent an exposome layer.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from . import config, demography
from .neuro_outcomes_stats import compute_exposome_correlations as _compute_exposome_correlations
from .neuro_outcomes_stats import residualize


OUTCOME_PREFIXES: dict[str, tuple[str, ...]] = {
    "dementia": ("F00", "F01", "F02", "F03", "G30"),
    "alzheimer": ("G30",),
    "cerebrovascular": ("I60", "I61", "I62", "I63", "I64", "I65", "I66", "I67", "I68", "I69"),
    "parkinsonism": ("G20", "G21"),
    # Ischemic heart disease + heart failure. Disjoint from cerebrovascular (I60-I69) above.
    "cardiovascular": ("I20", "I21", "I22", "I23", "I24", "I25", "I50"),
    # Pneumonia + acute lower respiratory + chronic/COPD. J30-J39 (upper respiratory)
    # deliberately excluded as etiologically distinct from chronic exposome-linked disease.
    "respiratory": (
        "J12", "J13", "J14", "J15", "J16", "J17", "J18",
        "J20", "J21", "J22",
        "J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47",
    ),
    # Respiratory subcauses (disjoint partition of `respiratory`): splitting buys
    # specificity at the cost of per-outcome counts. COPD/chronic lower is the arm
    # most biologically plausible for chronic PM2.5; pneumonia is more infectious.
    "respiratory_pneumonia": ("J12", "J13", "J14", "J15", "J16", "J17", "J18"),
    "respiratory_acute_lower": ("J20", "J21", "J22"),
    "respiratory_copd": ("J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47"),
}
AGE_BINS = ("0_14", "15_64", "65_plus")
MIN_LOW_COUNT = 10


def _strip_accents(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def _clean_icd_code(value: Any) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"[^A-Z0-9.]", "", text)
    return text.replace(".", "")


def _icd_matches(code: str, prefixes: tuple[str, ...]) -> bool:
    cleaned = _clean_icd_code(code)
    if not cleaned:
        return False
    return any(cleaned.startswith(prefix) for prefix in prefixes)


def classify_age_bin(
    age_value: Any = None,
    age_group_value: Any = None,
    age_type_value: Any = None,
) -> str | None:
    """Map a numeric age or age-group label to the repo's coarse age bins."""
    if age_type_value is not None and pd.notna(age_type_value):
        age_type = str(age_type_value).strip()
        if age_type in {"2", "2.0", "3", "3.0", "4", "4.0"}:
            return "0_14"
        if age_type in {"0", "0.0"}:
            return None

    if age_value is not None and pd.notna(age_value):
        age = pd.to_numeric(pd.Series([age_value]), errors="coerce").iloc[0]
        if pd.notna(age):
            age_num = float(age)
            if age_num < 0:
                return None
            if age_num <= 14:
                return "0_14"
            if age_num <= 64:
                return "15_64"
            return "65_plus"

    if age_group_value is None or pd.isna(age_group_value):
        return None

    text = _strip_accents(str(age_group_value).lower().strip())
    text = text.replace("anos", "anios").replace("año", "anio").replace("años", "anios")
    if not text:
        return None
    if any(token in text for token in ["65", "mas", "y mas", "o mas", "mayor", "anciano"]):
        if "15" not in text and "14" not in text:
            return "65_plus"
    if any(token in text for token in ["0-14", "0 a 14", "00-14", "menor de 15", "nino", "adolesc"]):
        return "0_14"
    if any(token in text for token in ["15-64", "15 a 64", "15- 64", "adult"]):
        return "15_64"

    numbers = [int(n) for n in re.findall(r"\d+", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        if numbers[0] <= 14:
            return "0_14"
        if numbers[0] <= 64:
            return "15_64"
        return "65_plus"

    lo, hi = min(numbers), max(numbers)
    if hi <= 14:
        return "0_14"
    if lo >= 65:
        return "65_plus"
    if lo >= 15 and hi <= 64:
        return "15_64"
    if lo <= 14 and hi <= 64:
        return "15_64"
    if hi >= 65:
        return "65_plus"
    return None


def _download_file(url: str, dest: Path, timeout: int = 180) -> None:
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=8192):
            fh.write(chunk)


def _discover_latest_resource_url(ckan_url: str, allowed_formats: set[str] | None = None) -> str:
    response = requests.get(ckan_url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise ValueError(f"CKAN API call failed: {payload}")

    resources = payload["result"].get("resources", [])
    allowed = {fmt.lower() for fmt in (allowed_formats or {"csv", "xlsx", "xls"})}
    candidates = [
        r for r in resources
        if str(r.get("format", "")).lower() in allowed
    ]
    if not candidates:
        raise ValueError("No matching resource found in CKAN package")
    candidates.sort(
        key=lambda r: r.get("last_modified", r.get("created", "")),
        reverse=True,
    )
    return str(candidates[0]["url"])


def ensure_source_file(cfg: dict[str, Any], cache_dir: Path, refresh: bool = False) -> Path:
    src_cfg = cfg["neuro_mortality"]["source"]
    local_path = Path(src_cfg["path"])
    if local_path.exists():
        return local_path

    filename = src_cfg.get("cache_name") or Path(src_cfg.get("url", "neuro_mortality_source")).name or "neuro_mortality_source.csv"
    cache_path = Path(cache_dir) / filename
    if cache_path.exists() and not refresh:
        return cache_path

    url = src_cfg.get("url")
    ckan_url = src_cfg.get("ckan_package_url")
    if ckan_url:
        try:
            url = _discover_latest_resource_url(
                ckan_url,
                allowed_formats=set(src_cfg.get("allowed_formats", ["csv", "xlsx", "xls"])),
            )
        except Exception as err:  # noqa: BLE001
            if not url:
                raise ValueError(f"Could not discover mortality resource via CKAN: {err}") from err
    if not url:
        raise FileNotFoundError(
            "Missing mortality source. "
            f"Expected local file at {local_path}. "
            "Place the DEIS CSV there or configure a download URL/CKAN source."
        )

    _download_file(url, cache_path)
    return cache_path


def load_source_table(source_path: Path, source_cfg: dict[str, Any]) -> pd.DataFrame:
    fmt = source_cfg.get("format")
    suffix = source_path.suffix.lower()
    if fmt == "excel" or suffix in {".xlsx", ".xls"}:
        sheet_name = source_cfg.get("sheet_name", 0)
        return pd.read_excel(source_path, sheet_name=sheet_name)
    sep = source_cfg.get("sep", ",")
    encoding = source_cfg.get("encoding")
    return pd.read_csv(source_path, sep=sep, encoding=encoding, low_memory=False)


def _coalesce_commune_name(raw: pd.Series, code_map: pd.DataFrame) -> pd.Series:
    norm = demography.normalize_comuna_name(raw.fillna("").astype(str))
    valid_names = set(code_map["name"])
    return norm.where(norm.isin(valid_names))


def prepare_mortality_records(
    raw: pd.DataFrame,
    cfg: dict[str, Any],
    code_map: pd.DataFrame,
) -> pd.DataFrame:
    mort_cfg = cfg["neuro_mortality"]
    src_cfg = mort_cfg["source"]
    cols = src_cfg["columns"]

    year_col = cols["year"]
    cause_col = cols["cause"]
    commune_name_col = cols.get("commune_name")
    commune_code_col = cols.get("commune_code")
    age_col = cols.get("age")
    age_group_col = cols.get("age_group")
    age_type_col = cols.get("age_type")
    deaths_col = cols.get("deaths")
    region_name_col = cols.get("region_name")

    df = raw.copy()
    df["year"] = pd.to_numeric(df[year_col], errors="coerce")
    df = df[df["year"].notna()].copy()
    df["year"] = df["year"].astype(int)
    years = {int(y) for y in mort_cfg["years"]}
    df = df[df["year"].isin(years)].copy()

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

    bbox_names = set(code_map["name"])
    df = df[df["name"].isin(bbox_names)].copy()

    if deaths_col and deaths_col in df.columns:
        df["deaths"] = pd.to_numeric(df[deaths_col], errors="coerce").fillna(0)
    else:
        df["deaths"] = 1.0

    df["cause_code"] = df[cause_col].map(_clean_icd_code)
    df = df[df["cause_code"] != ""].copy()

    if age_col and age_col in df.columns:
        age_series = df[age_col]
    else:
        age_series = pd.Series([None] * len(df), index=df.index)
    if age_group_col and age_group_col in df.columns:
        age_group_series = df[age_group_col]
    else:
        age_group_series = pd.Series([None] * len(df), index=df.index)
    if age_type_col and age_type_col in df.columns:
        age_type_series = df[age_type_col]
    else:
        age_type_series = pd.Series([None] * len(df), index=df.index)
    df["age_bin"] = [
        classify_age_bin(age_val, age_group_val, age_type_val)
        for age_val, age_group_val, age_type_val in zip(age_series, age_group_series, age_type_series)
    ]
    return df


def aggregate_outcome_deaths(records: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for outcome, prefixes in OUTCOME_PREFIXES.items():
        subset = records[records["cause_code"].map(lambda code: _icd_matches(code, prefixes))].copy()
        if subset.empty:
            continue
        grouped = (
            subset.groupby(["name", "year", "age_bin"], dropna=False)["deaths"]
            .sum()
            .reset_index()
        )
        grouped["outcome"] = outcome
        frames.append(grouped)

    all_cause = (
        records.groupby(["name", "year", "age_bin"], dropna=False)["deaths"]
        .sum()
        .reset_index()
    )
    all_cause["outcome"] = "all_cause"
    frames.append(all_cause)

    out = pd.concat(frames, ignore_index=True)
    out["deaths"] = out["deaths"].astype(float)
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
    *,
    allow_crude_only: bool = False,
) -> pd.DataFrame:
    n_years = len(years)
    age_weights = _age_weight_map(demography_df)
    pop_lookup = demography_df.set_index("name")[
        ["pop_total", "pop_0_14", "pop_15_64", "pop_65_plus"]
    ]

    if aggregated["age_bin"].notna().sum() == 0 and not allow_crude_only:
        raise ValueError("Mortality source has no usable age information; rerun with allow_crude_only=True.")

    rows: list[dict[str, Any]] = []
    for outcome, subset in aggregated.groupby("outcome"):
        deaths_wide = (
            subset.groupby(["name", "age_bin"])["deaths"]
            .sum()
            .unstack("age_bin", fill_value=0.0)
            .reindex(columns=list(AGE_BINS), fill_value=0.0)
        )
        total_deaths = subset.groupby("name")["deaths"].sum()

        for name in pop_lookup.index:
            pop = pop_lookup.loc[name]
            deaths_total = float(total_deaths.get(name, 0.0))
            crude_rate = deaths_total / (float(pop["pop_total"]) * n_years) * 100_000

            age_specific_rates: dict[str, float] = {}
            if name in deaths_wide.index:
                for age_bin in AGE_BINS:
                    denom = float(pop[f"pop_{age_bin}"])
                    deaths = float(deaths_wide.loc[name, age_bin])
                    age_specific_rates[age_bin] = deaths / (denom * n_years) * 100_000 if denom > 0 else np.nan
            else:
                age_specific_rates = {age_bin: 0.0 for age_bin in AGE_BINS}

            if aggregated["age_bin"].notna().sum() == 0:
                adj_rate = np.nan
            else:
                adj_rate = sum(age_specific_rates[age_bin] * age_weights[age_bin] for age_bin in AGE_BINS)

            row = {
                "name": name,
                "outcome": outcome,
                "mortality_year_start": min(years),
                "mortality_year_end": max(years),
                "mortality_n_years": n_years,
                "mortality_deaths_total": round(deaths_total, 2),
                "mortality_rate_crude_per_100k": round(crude_rate, 4),
                "mortality_rate_age_adjusted_per_100k": round(float(adj_rate), 4) if pd.notna(adj_rate) else np.nan,
                "mortality_low_count_flag": int(deaths_total < MIN_LOW_COUNT),
            }
            for age_bin in AGE_BINS:
                row[f"mortality_deaths_{age_bin}"] = round(float(deaths_wide.loc[name, age_bin]), 2) if name in deaths_wide.index else 0.0
                rate_val = age_specific_rates[age_bin]
                row[f"mortality_rate_{age_bin}_per_100k"] = round(float(rate_val), 4) if pd.notna(rate_val) else np.nan
            rows.append(row)

    return pd.DataFrame(rows).sort_values(["outcome", "name"]).reset_index(drop=True)


def build_neuro_mortality_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    *,
    refresh: bool = False,
    allow_crude_only: bool = False,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    cfg = config.load_config(city)
    mort_cfg = cfg["neuro_mortality"]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_path = ensure_source_file(cfg, cache_dir, refresh=refresh)
    raw = load_source_table(source_path, mort_cfg["source"])
    code_map = demography.load_comuna_code_name_map(cache_dir, region_code=int(mort_cfg.get("region_code", 13)))
    demo = demography.load_commune_demography(cache_dir, region_code=int(mort_cfg.get("region_code", 13)))
    records = prepare_mortality_records(raw, cfg, code_map)
    aggregated = aggregate_outcome_deaths(records)
    rates = compute_commune_rates(
        aggregated,
        demo[["name", "pop_total", "pop_0_14", "pop_15_64", "pop_65_plus"]],
        [int(y) for y in mort_cfg["years"]],
        allow_crude_only=allow_crude_only,
    )

    expected = int(cfg["expected_communes"])
    for outcome in rates["outcome"].unique():
        subset = rates[rates["outcome"] == outcome]
        if len(subset) != expected:
            raise ValueError(f"Outcome {outcome} has {len(subset)} communes, expected {expected}")
        if subset["name"].duplicated().any():
            raise ValueError(f"Duplicate commune names in outcome {outcome}")

    geom_path = out_dir / "santiago_exposome_master.geojson"
    if not geom_path.exists():
        raise FileNotFoundError(f"Missing geometry source: {geom_path}")
    base_gdf = gpd.read_file(geom_path)[["name", "geometry"]].drop_duplicates("name")
    gdf = base_gdf.merge(rates, on="name", how="right", validate="one_to_many")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    year_start = min(int(y) for y in mort_cfg["years"])
    year_end = max(int(y) for y in mort_cfg["years"])
    base_name = f"{city}_neuro_mortality_{year_start}_{year_end}"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    meta_path = out_dir / f"{base_name}_metadata.json"

    rates.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": int(len(rates)),
        "n_communes": expected,
        "years": [int(y) for y in mort_cfg["years"]],
        "coverage_window": {
            "start": int(min(mort_cfg["years"])),
            "end": int(max(mort_cfg["years"])),
            "n_years": int(len(mort_cfg["years"])),
            # The chronic-exposure design pairs this outcome window with an
            # antecedent PM2.5 window (2000-2017). DEIS hospitalization discharge
            # data currently sits on a different window (only 2006 is on disk), so
            # any mortality/hospitalization comparison must not assume a shared
            # temporal frame -- see docs/methodology_chronic_exposome_mortality.md.
            "temporal_mismatch_with_hospitalizations": (
                "Mortality covers 2018-2022; local DEIS hospital discharge export is 2006. "
                "Matching windows requires acquiring 2018-2022 egresos before pooling the two sources."
            ),
        },
        "source_path_used": str(source_path),
        "allow_crude_only": bool(allow_crude_only),
        "outcomes": {name: list(prefixes) for name, prefixes in OUTCOME_PREFIXES.items()},
        "age_bins": list(AGE_BINS),
        "standard_population": "Santiago commune demography aggregate from Censo 2017",
        "columns": rates.columns.tolist(),
        "note": (
            "External ecological outcome comparator derived from DEIS mortality data. "
            "Not an exposome layer and not suitable for individual-level inference."
        ),
    }
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return rates, gdf


def compute_exposome_correlations(
    mortality_df: pd.DataFrame,
    master_df: pd.DataFrame,
    exposures: list[str],
    outcomes: list[str],
    covariates: list[str],
) -> pd.DataFrame:
    return _compute_exposome_correlations(
        outcome_df=mortality_df,
        master_df=master_df,
        exposures=exposures,
        outcomes=outcomes,
        covariates=covariates,
        outcome_rate_col="mortality_rate_age_adjusted_per_100k",
        fallback_rate_col="mortality_rate_crude_per_100k",
    )
