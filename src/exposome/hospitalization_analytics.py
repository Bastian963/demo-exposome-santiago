"""Streaming DEIS hospitalization ingestion and ecological analysis helpers.

The raw DEIS exports contain one row per hospital-discharge episode.  This
module never writes those individual rows back to disk: it filters them while
streaming and persists only commune/year/sex/age/outcome aggregates.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests


HARMONIZED_AGE_BANDS = (
    "0_9",
    "10_19",
    "20_29",
    "30_39",
    "40_49",
    "50_59",
    "60_69",
    "70_79",
    "80_plus",
)
KNOWN_SEXES = ("male", "female")

OUTCOME_PREFIXES: dict[str, tuple[str, ...]] = {
    "mental_all": ("F",),
    "dementia": ("F00", "F01", "F02", "F03", "G30"),
    "alzheimer": ("G30",),
    "cerebrovascular": tuple(f"I{i:02d}" for i in range(60, 70)),
    "parkinsonism": ("G20", "G21"),
    "substance": tuple(f"F{i:02d}" for i in range(10, 20)),
    "psychosis": tuple(f"F{i:02d}" for i in range(20, 30)),
    "mood": tuple(f"F{i:02d}" for i in range(30, 40)),
    "anxiety_stress": tuple(f"F{i:02d}" for i in range(40, 49)),
    "cardiovascular": ("I20", "I21", "I22", "I23", "I24", "I25", "I50"),
    "respiratory": (
        "J12",
        "J13",
        "J14",
        "J15",
        "J16",
        "J17",
        "J18",
        "J20",
        "J21",
        "J22",
        "J40",
        "J41",
        "J42",
        "J43",
        "J44",
        "J45",
        "J46",
        "J47",
    ),
    "respiratory_pneumonia": ("J12", "J13", "J14", "J15", "J16", "J17", "J18"),
    "respiratory_acute_lower": ("J20", "J21", "J22"),
    "respiratory_copd": ("J40", "J41", "J42", "J43", "J44", "J45", "J46", "J47"),
    # Prespecified negative-control outcome for environmental air-pollution
    # analyses.  T99 is deliberately excluded to match S00--T98 exactly.
    "injury_poisoning": tuple(
        [f"S{i:02d}" for i in range(100)] + [f"T{i:02d}" for i in range(99)]
    ),
}
ALL_OUTCOMES = ("all_cause", *OUTCOME_PREFIXES)

CARDIORESPIRATORY_PRIMARY = ("cardiovascular", "respiratory", "respiratory_copd")
NEUROPSYCHIATRIC_PRIMARY = ("cerebrovascular", "mental_all")
OUTCOME_ARMS = {
    **{outcome: "cardiorespiratory" for outcome in CARDIORESPIRATORY_PRIMARY},
    **{outcome: "neuropsychiatric" for outcome in NEUROPSYCHIATRIC_PRIMARY},
}

REQUIRED_SOURCE_FIELDS = (
    "year",
    "commune_code",
    "commune_name",
    "region_code",
    "region_name",
    "cause",
    "age_group",
    "sex",
    "days_stay",
    "discharge_condition",
)


def clean_icd_code(value: Any) -> str:
    text = str(value or "").upper().strip()
    return re.sub(r"[^A-Z0-9.]", "", text).replace(".", "")


def normalize_sex(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"1", "1.0", "HOMBRE", "H", "MALE"}:
        return "male"
    if text in {"2", "2.0", "MUJER", "M", "FEMALE"}:
        return "female"
    return "unknown"


def harmonize_age_group(value: Any) -> str | None:
    """Map every observed 2011-2020 DEIS age label to decadal bands.

    The 2012 export is more detailed (neonatal and five-year bands); grouping
    it to the same decadal support avoids splitting the 10-19 and 60-69 bands
    used in the other years.
    """
    if value is None or pd.isna(value):
        return None
    text = str(value).lower().strip()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    if not text:
        return None
    if "menor" in text or "mes" in text or "dia" in text:
        return "0_9"
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    if not numbers:
        return None
    lower = min(numbers)
    if lower < 10:
        return "0_9"
    if lower < 20:
        return "10_19"
    if lower < 30:
        return "20_29"
    if lower < 40:
        return "30_39"
    if lower < 50:
        return "40_49"
    if lower < 60:
        return "50_59"
    if lower < 70:
        return "60_69"
    if lower < 80:
        return "70_79"
    return "80_plus"


def age_to_harmonized_band(age: Any) -> str | None:
    numeric = pd.to_numeric(pd.Series([age]), errors="coerce").iloc[0]
    if pd.isna(numeric) or float(numeric) < 0:
        return None
    years = int(numeric)
    if years >= 80:
        return "80_plus"
    decade = (years // 10) * 10
    return f"{decade}_{decade + 9}"


def _source_columns(source_cfg: Mapping[str, Any]) -> list[str]:
    columns = source_cfg["columns"]
    missing_keys = [field for field in REQUIRED_SOURCE_FIELDS if field not in columns]
    if missing_keys:
        raise ValueError(f"Missing DEIS source column mappings: {missing_keys}")
    return list(dict.fromkeys(str(columns[field]) for field in REQUIRED_SOURCE_FIELDS))


def iter_source_chunks(
    paths: Sequence[Path],
    source_cfg: Mapping[str, Any],
    *,
    chunksize: int | None = None,
) -> Iterator[tuple[Path, str, pd.DataFrame]]:
    """Yield selected DEIS columns from plain CSVs or ZIP-contained CSVs."""
    chunksize = int(chunksize or source_cfg.get("chunksize", 250_000))
    read_kwargs = {
        "sep": source_cfg.get("sep", ";"),
        "encoding": source_cfg.get("encoding", "latin1"),
        "usecols": _source_columns(source_cfg),
        "chunksize": chunksize,
        "low_memory": False,
    }
    for path in paths:
        path = Path(path)
        if path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                csv_members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if len(csv_members) != 1:
                    raise ValueError(
                        f"{path} must contain exactly one CSV member; found {csv_members}"
                    )
                member = csv_members[0]
                with archive.open(member) as handle:
                    for chunk in pd.read_csv(handle, **read_kwargs):
                        yield path, member, chunk
        else:
            for chunk in pd.read_csv(path, **read_kwargs):
                yield path, path.name, chunk


def archive_inventory(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        path = Path(path)
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        members: list[dict[str, Any]] = []
        dictionary_sha256 = None
        if path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                bad_member = archive.testzip()
                if bad_member is not None:
                    raise ValueError(f"CRC failure in {path}: {bad_member}")
                for info in archive.infolist():
                    members.append({"name": info.filename, "size_bytes": int(info.file_size)})
                    if info.filename.lower().endswith(".xlsx"):
                        dictionary_sha256 = hashlib.sha256(archive.read(info.filename)).hexdigest()
        rows.append(
            {
                "path": str(path),
                "size_bytes": int(path.stat().st_size),
                "sha256": digest.hexdigest(),
                "members": members,
                "dictionary_sha256": dictionary_sha256,
                "crc_ok": True,
            }
        )
    return rows


def _crosswalk_for_streaming(crosswalk: pd.DataFrame) -> pd.DataFrame:
    if {"spatial_id", "spatial_name"}.issubset(crosswalk.columns):
        out = crosswalk[["spatial_id", "spatial_name"]].copy()
    elif {"comuna_code", "name"}.issubset(crosswalk.columns):
        out = crosswalk[["comuna_code", "name"]].rename(
            columns={"comuna_code": "spatial_id", "name": "spatial_name"}
        )
    else:
        raise ValueError("Crosswalk needs spatial_id/spatial_name or comuna_code/name")
    out["spatial_id"] = pd.to_numeric(out["spatial_id"], errors="raise").astype(int).astype(str)
    if out["spatial_id"].duplicated().any():
        raise ValueError("Duplicate spatial_id values in commune crosswalk")
    return out


def _prepare_chunk(
    raw: pd.DataFrame,
    source_cfg: Mapping[str, Any],
    crosswalk: pd.DataFrame,
    years: set[int],
    region_code: int,
) -> tuple[pd.DataFrame, Counter[str]]:
    columns = source_cfg["columns"]
    qc: Counter[str] = Counter(total_rows=int(len(raw)))

    year = pd.to_numeric(raw[columns["year"]], errors="coerce")
    region = pd.to_numeric(raw[columns["region_code"]], errors="coerce")
    commune = pd.to_numeric(raw[columns["commune_code"]], errors="coerce")
    qc["unknown_year_rows"] = int(year.isna().sum())
    qc["outside_requested_year_rows"] = int((year.notna() & ~year.isin(years)).sum())
    qc["rm_rows_before_year_filter"] = int((region == region_code).sum())

    keep = year.isin(years) & (region == region_code)
    df = raw.loc[keep].copy()
    year = year.loc[keep].astype(int)
    commune = commune.loc[keep]
    qc["rm_requested_year_rows"] = int(len(df))

    commune_lookup = _crosswalk_for_streaming(crosswalk).set_index("spatial_id")["spatial_name"]
    df["spatial_id"] = commune.astype("Int64").astype(str)
    df["spatial_name"] = df["spatial_id"].map(commune_lookup)
    qc["invalid_commune_rows"] = int(df["spatial_name"].isna().sum())
    df = df[df["spatial_name"].notna()].copy()
    df["year"] = year.loc[df.index].astype(int)

    cause = df[columns["cause"]].fillna("").astype(str).str.upper().str.strip()
    df["cause_code"] = cause.str.replace(r"[^A-Z0-9.]", "", regex=True).str.replace(
        ".", "", regex=False
    )
    qc["missing_diag1_rows"] = int((df["cause_code"] == "").sum())
    df = df[df["cause_code"] != ""].copy()

    age_raw = df[columns["age_group"]]
    age_map = {value: harmonize_age_group(value) for value in age_raw.drop_duplicates()}
    df["age_band"] = age_raw.map(age_map)
    qc["unknown_age_rows"] = int(df["age_band"].isna().sum())

    sex_raw = df[columns["sex"]]
    sex_map = {value: normalize_sex(value) for value in sex_raw.drop_duplicates()}
    df["sex"] = sex_raw.map(sex_map)
    qc["unknown_sex_rows"] = int((df["sex"] == "unknown").sum())

    days = pd.to_numeric(df[columns["days_stay"]], errors="coerce")
    valid_days = days.between(0, 3650, inclusive="both")
    qc["invalid_or_extreme_los_rows"] = int((~valid_days).sum())
    df["days_stay"] = days.where(valid_days)

    death_values = {str(value).strip() for value in source_cfg.get("in_hospital_death_values", ["2"])}
    df["in_hospital_death"] = (
        df[columns["discharge_condition"]].astype(str).str.strip().isin(death_values).astype(int)
    )
    return df, qc


def _aggregate_prepared_chunk(prepared: pd.DataFrame) -> pd.DataFrame:
    group_columns = ["spatial_id", "spatial_name", "year", "sex", "age_band"]
    frames: list[pd.DataFrame] = []
    definitions: dict[str, tuple[str, ...] | None] = {"all_cause": None, **OUTCOME_PREFIXES}
    for outcome, prefixes in definitions.items():
        subset = prepared if prefixes is None else prepared[prepared["cause_code"].str.startswith(prefixes)]
        if subset.empty:
            continue
        grouped = (
            subset.groupby(group_columns, dropna=False)
            .agg(
                admissions=("cause_code", "size"),
                days_stay=("days_stay", "sum"),
                valid_los_admissions=("days_stay", "count"),
                in_hospital_deaths=("in_hospital_death", "sum"),
            )
            .reset_index()
        )
        grouped["outcome"] = outcome
        frames.append(grouped)
    return pd.concat(frames, ignore_index=True)


def aggregate_hospitalization_stream(
    paths: Sequence[Path],
    source_cfg: Mapping[str, Any],
    crosswalk: pd.DataFrame,
    years: Sequence[int],
    *,
    region_code: int = 13,
    chunksize: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Stream raw rows and return only a compact outcome cube plus QC."""
    requested_years = {int(year) for year in years}
    partials: list[pd.DataFrame] = []
    totals: Counter[str] = Counter()
    by_archive: dict[str, Counter[str]] = defaultdict(Counter)
    member_by_archive: dict[str, str] = {}

    for path, member, raw in iter_source_chunks(paths, source_cfg, chunksize=chunksize):
        prepared, qc = _prepare_chunk(raw, source_cfg, crosswalk, requested_years, region_code)
        totals.update(qc)
        by_archive[path.name].update(qc)
        member_by_archive[path.name] = member
        if not prepared.empty:
            partials.append(_aggregate_prepared_chunk(prepared))

    if not partials:
        raise ValueError("No valid DEIS hospitalization rows remained after filtering")
    cube = pd.concat(partials, ignore_index=True)
    dimensions = ["spatial_id", "spatial_name", "year", "sex", "age_band", "outcome"]
    cube = (
        cube.groupby(dimensions, dropna=False)[
            ["admissions", "days_stay", "valid_los_admissions", "in_hospital_deaths"]
        ]
        .sum()
        .reset_index()
        .sort_values(dimensions)
        .reset_index(drop=True)
    )
    qc_report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "requested_years": sorted(requested_years),
        "region_code": int(region_code),
        "totals": dict(totals),
        "by_archive": {
            name: {"csv_member": member_by_archive[name], **dict(counts)}
            for name, counts in sorted(by_archive.items())
        },
        "cube_rows_before_population_completion": int(len(cube)),
        "n_communes": int(cube["spatial_id"].nunique()),
        "outcomes": list(ALL_OUTCOMES),
        "age_bands": list(HARMONIZED_AGE_BANDS),
    }
    return cube, qc_report


def load_ine_population_person_years(
    path: Path,
    crosswalk: pd.DataFrame,
    years: Sequence[int],
    *,
    region_code: int = 13,
) -> pd.DataFrame:
    """Load official INE base-2017 commune population by year, sex and age."""
    years = sorted({int(year) for year in years})
    population_columns = [f"Poblacion {year}" for year in years]
    usecols = ["Region", "Comuna", "Sexo (1=Hombre 2=Mujer)", "Edad", *population_columns]
    raw = pd.read_csv(path, encoding="latin1", usecols=usecols, low_memory=False)
    raw = raw[pd.to_numeric(raw["Region"], errors="coerce") == int(region_code)].copy()
    raw["spatial_id"] = pd.to_numeric(raw["Comuna"], errors="coerce").astype("Int64").astype(str)
    lookup = _crosswalk_for_streaming(crosswalk).set_index("spatial_id")["spatial_name"]
    raw["spatial_name"] = raw["spatial_id"].map(lookup)
    raw = raw[raw["spatial_name"].notna()].copy()
    raw["sex"] = raw["Sexo (1=Hombre 2=Mujer)"].map({1: "male", 2: "female"})
    raw["age_band"] = raw["Edad"].map(age_to_harmonized_band)

    long = raw.melt(
        id_vars=["spatial_id", "spatial_name", "sex", "age_band"],
        value_vars=population_columns,
        var_name="year",
        value_name="population",
    )
    long["year"] = long["year"].str.extract(r"(\d{4})")[0].astype(int)
    long["population"] = pd.to_numeric(long["population"], errors="coerce")
    if long[["sex", "age_band", "population"]].isna().any().any():
        missing = long[long[["sex", "age_band", "population"]].isna().any(axis=1)].head()
        raise ValueError(f"Invalid INE population rows:\n{missing}")
    population = (
        long.groupby(["spatial_id", "spatial_name", "year", "sex", "age_band"])["population"]
        .sum()
        .reset_index()
        .sort_values(["spatial_id", "year", "sex", "age_band"])
        .reset_index(drop=True)
    )
    expected_rows = len(lookup) * len(years) * len(KNOWN_SEXES) * len(HARMONIZED_AGE_BANDS)
    if len(population) != expected_rows:
        raise ValueError(f"INE population has {len(population)} rows, expected {expected_rows}")
    if (population["population"] <= 0).any():
        raise ValueError("INE population contains non-positive commune/year/sex/age cells")
    return population


def complete_cube_with_population(cube: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    outcomes = pd.DataFrame({"outcome": list(ALL_OUTCOMES)})
    known_grid = population.merge(outcomes, how="cross")
    metrics = ["admissions", "days_stay", "valid_los_admissions", "in_hospital_deaths"]
    dimensions = ["spatial_id", "spatial_name", "year", "sex", "age_band", "outcome"]
    known_counts = cube[cube["sex"].isin(KNOWN_SEXES)].copy()
    completed = known_grid.merge(known_counts, on=dimensions, how="left", validate="one_to_one")
    completed[metrics] = completed[metrics].fillna(0.0)

    unknown = cube[~cube["sex"].isin(KNOWN_SEXES)].copy()
    if not unknown.empty:
        unknown["population"] = np.nan
        completed = pd.concat([completed, unknown[completed.columns]], ignore_index=True)
    return completed.sort_values(dimensions).reset_index(drop=True)


def _expected_by_stratum(cube: pd.DataFrame) -> pd.DataFrame:
    known = cube[cube["sex"].isin(KNOWN_SEXES) & cube["population"].notna()].copy()
    reference_dimensions = ["outcome", "year", "sex", "age_band"]
    reference = (
        known.groupby(reference_dimensions)[["admissions", "population"]]
        .sum()
        .reset_index()
    )
    reference["reference_rate"] = reference["admissions"] / reference["population"]
    known = known.merge(
        reference[reference_dimensions + ["reference_rate"]],
        on=reference_dimensions,
        how="left",
        validate="many_to_one",
    )
    known["expected"] = known["population"] * known["reference_rate"]
    return known


def compute_window_smr(cube: pd.DataFrame, years: Sequence[int], label: str) -> pd.DataFrame:
    years = sorted({int(year) for year in years})
    expected = _expected_by_stratum(cube[cube["year"].isin(years)])
    grouped = (
        expected.groupby(["spatial_id", "spatial_name", "outcome"])
        .agg(
            observed=("admissions", "sum"),
            expected=("expected", "sum"),
            population_person_years=("population", "sum"),
            hospital_days_total=("days_stay", "sum"),
            valid_los_admissions=("valid_los_admissions", "sum"),
            in_hospital_deaths=("in_hospital_deaths", "sum"),
        )
        .reset_index()
    )
    grouped["smr"] = grouped["observed"] / grouped["expected"]
    grouped["rate_crude_per_100k"] = (
        grouped["observed"] / grouped["population_person_years"] * 100_000
    )
    grouped["mean_los_days"] = grouped["hospital_days_total"] / grouped[
        "valid_los_admissions"
    ].replace(0, np.nan)
    grouped["window"] = label
    grouped["year_start"] = min(years)
    grouped["year_end"] = max(years)
    grouped["n_years"] = len(years)
    grouped["low_count_flag"] = (grouped["observed"] < 10).astype(int)
    return grouped.sort_values(["outcome", "spatial_name"]).reset_index(drop=True)


def compute_annual_expected(cube: pd.DataFrame, years: Sequence[int]) -> pd.DataFrame:
    expected = _expected_by_stratum(cube[cube["year"].isin({int(y) for y in years})])
    return (
        expected.groupby(["spatial_id", "spatial_name", "year", "outcome"])
        .agg(
            observed=("admissions", "sum"),
            expected=("expected", "sum"),
            population_person_years=("population", "sum"),
        )
        .reset_index()
        .sort_values(["outcome", "spatial_id", "year"])
        .reset_index(drop=True)
    )


def _fit_negative_binomial(
    frame: pd.DataFrame,
    exposure: str,
    covariates: Sequence[str],
) -> tuple[dict[str, Any], pd.Series | None]:
    columns = ["observed", "expected", exposure, *covariates]
    model = frame.dropna(subset=columns).copy()
    model = model[model["expected"] > 0].copy()
    if len(model) < 20 or model[exposure].nunique() < 3:
        return {"status": "insufficient_data", "n": int(len(model))}, None
    exposure_sd = float(model[exposure].std(ddof=0))
    if not math.isfinite(exposure_sd) or exposure_sd <= 0:
        return {"status": "constant_exposure", "n": int(len(model))}, None
    model["exposure_z"] = (model[exposure] - model[exposure].mean()) / exposure_sd
    design = model[["exposure_z", *covariates]].astype(float)
    design = sm.add_constant(design, has_constant="add")
    try:
        result = sm.NegativeBinomial(
            model["observed"].astype(float),
            design,
            offset=np.log(model["expected"].astype(float)),
        ).fit(disp=0, maxiter=300)
        beta = float(result.params["exposure_z"])
        standard_error = float(result.bse["exposure_z"])
        p_value = float(result.pvalues["exposure_z"])
        residual = pd.Series(np.asarray(result.resid), index=model["spatial_id"].astype(str))
        return {
            "status": "ok",
            "n": int(len(model)),
            "exposure_sd": exposure_sd,
            "rr_per_sd": float(np.exp(beta)),
            "ci_low": float(np.exp(beta - 1.96 * standard_error)),
            "ci_high": float(np.exp(beta + 1.96 * standard_error)),
            "p_value": p_value,
            "alpha": float(result.params.get("alpha", np.nan)),
        }, residual
    except Exception as exc:  # convergence failures must be explicit in the table
        return {"status": f"model_error:{type(exc).__name__}", "n": int(len(model))}, None


def fit_chronic_associations(
    smr: pd.DataFrame,
    exposures: pd.DataFrame,
    exposure_columns: Sequence[str],
    *,
    covariates: Sequence[str] = ("nse_index",),
) -> tuple[pd.DataFrame, dict[tuple[str, str], pd.Series]]:
    merged = smr.merge(exposures, on=["spatial_id", "spatial_name"], how="inner")
    rows: list[dict[str, Any]] = []
    residuals: dict[tuple[str, str], pd.Series] = {}
    for outcome, arm in OUTCOME_ARMS.items():
        subset = merged[merged["outcome"] == outcome].copy()
        for exposure in exposure_columns:
            result, residual = _fit_negative_binomial(subset, exposure, covariates)
            result.update(
                {
                    "arm": arm,
                    "outcome": outcome,
                    "exposure": exposure,
                    "model": "negative_binomial_offset_expected",
                    "covariates": "+".join(covariates),
                    "window": subset["window"].iloc[0] if not subset.empty else None,
                }
            )
            rows.append(result)
            if residual is not None:
                residuals[(outcome, exposure)] = residual
    table = pd.DataFrame(rows)
    table["q_value"] = np.nan
    for arm, index in table[table["status"] == "ok"].groupby("arm").groups.items():
        p_values = table.loc[index, "p_value"].astype(float)
        table.loc[index, "q_value"] = multipletests(p_values, method="fdr_bh")[1]
    return table.sort_values(["arm", "outcome", "exposure"]).reset_index(drop=True), residuals


def fit_panel_ppml(
    annual_outcomes: pd.DataFrame,
    annual_exposures: pd.DataFrame,
    exposure_columns: Sequence[str],
    years: Sequence[int],
    *,
    window_label: str,
) -> pd.DataFrame:
    merged = annual_outcomes.merge(
        annual_exposures, on=["spatial_id", "spatial_name", "year"], how="inner"
    )
    merged = merged[merged["year"].isin({int(year) for year in years})].copy()
    rows: list[dict[str, Any]] = []
    panel_outcomes = (*CARDIORESPIRATORY_PRIMARY, "cerebrovascular")
    for outcome in panel_outcomes:
        subset = merged[merged["outcome"] == outcome].copy()
        arm = OUTCOME_ARMS[outcome]
        for exposure in exposure_columns:
            model = subset.dropna(subset=["observed", "expected", exposure]).copy()
            model = model[model["expected"] > 0]
            result_row: dict[str, Any] = {
                "arm": arm,
                "outcome": outcome,
                "exposure": exposure,
                "model": "poisson_ppml_commune_year_fixed_effects",
                "window": window_label,
                "n": int(len(model)),
                "n_communes": int(model["spatial_id"].nunique()),
                "n_years": int(model["year"].nunique()),
            }
            if len(model) < 100 or model[exposure].nunique() < 3:
                result_row["status"] = "insufficient_data"
                rows.append(result_row)
                continue
            exposure_sd = float(model[exposure].std(ddof=0))
            model["exposure_z"] = (model[exposure] - model[exposure].mean()) / exposure_sd
            commune_dummies = pd.get_dummies(
                model["spatial_id"], prefix="commune", drop_first=True, dtype=float
            )
            year_dummies = pd.get_dummies(model["year"], prefix="year", drop_first=True, dtype=float)
            design = pd.concat(
                [model[["exposure_z"]].astype(float), commune_dummies, year_dummies], axis=1
            )
            design = sm.add_constant(design, has_constant="add")
            try:
                fitted = sm.GLM(
                    model["observed"].astype(float),
                    design,
                    family=sm.families.Poisson(),
                    offset=np.log(model["expected"].astype(float)),
                ).fit(cov_type="cluster", cov_kwds={"groups": model["spatial_id"]})
                beta = float(fitted.params["exposure_z"])
                se = float(fitted.bse["exposure_z"])
                result_row.update(
                    {
                        "status": "ok",
                        "exposure_sd": exposure_sd,
                        "rr_per_sd": float(np.exp(beta)),
                        "ci_low": float(np.exp(beta - 1.96 * se)),
                        "ci_high": float(np.exp(beta + 1.96 * se)),
                        "p_value": float(fitted.pvalues["exposure_z"]),
                    }
                )
            except Exception as exc:
                result_row["status"] = f"model_error:{type(exc).__name__}"
            rows.append(result_row)
    table = pd.DataFrame(rows)
    table["q_value"] = np.nan
    for arm, index in table[table["status"] == "ok"].groupby("arm").groups.items():
        table.loc[index, "q_value"] = multipletests(
            table.loc[index, "p_value"].astype(float), method="fdr_bh"
        )[1]
    return table.sort_values(["arm", "outcome", "exposure"]).reset_index(drop=True)


def residual_morans_i(
    residuals: Mapping[tuple[str, str], pd.Series],
    geometry_path: Path,
    *,
    exposure: str,
) -> pd.DataFrame:
    import geopandas as gpd
    import libpysal
    from esda.moran import Moran

    geometry = gpd.read_file(geometry_path)
    id_column = "spatial_id" if "spatial_id" in geometry.columns else None
    if id_column is None:
        crosswalk_path = Path("data/reference/cl/santiago/santiago_communes/cut_crosswalk.csv")
        crosswalk = pd.read_csv(crosswalk_path, dtype={"spatial_id": str})
        geometry = geometry.merge(
            crosswalk[["spatial_id", "legacy_name"]],
            left_on="name",
            right_on="legacy_name",
            how="left",
        )
        id_column = "spatial_id"
    geometry[id_column] = geometry[id_column].astype(str)
    rows: list[dict[str, Any]] = []
    for (outcome, current_exposure), series in residuals.items():
        if current_exposure != exposure:
            continue
        aligned = geometry[[id_column, "geometry"]].merge(
            series.rename("residual"), left_on=id_column, right_index=True, how="inner"
        )
        weights = libpysal.weights.Queen.from_dataframe(aligned, use_index=False)
        weights.transform = "r"
        moran = Moran(aligned["residual"].to_numpy(), weights, permutations=999)
        rows.append(
            {
                "outcome": outcome,
                "exposure": current_exposure,
                "morans_i": float(moran.I),
                "p_sim": float(moran.p_sim),
                "z_sim": float(moran.z_sim),
                "bym2_required": bool(moran.p_sim < 0.05),
            }
        )
    return pd.DataFrame(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
