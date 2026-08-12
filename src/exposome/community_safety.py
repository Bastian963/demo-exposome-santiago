"""AMBA community-safety exposure from Argentina's SAT property-crime data.

This layer intentionally measures *registered property-crime context*, not
individual victimization or a clinical outcome.  Homicides, suicides and road
deaths remain separate comparator/outcome products.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .spatial import load_spatial_units
from .studies import load_study


RAW_RELATIVE = Path("data/raw/ar/security_dnec/download_2026-07-12")
YEARS = tuple(range(2017, 2025))


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _unit_lookup(units: gpd.GeoDataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in units.itertuples(index=False):
        unit_id = str(row.spatial_id)
        if unit_id.startswith("caba_comuna_"):
            number = int(unit_id.rsplit("_", 1)[1])
            lookup[f"comuna {number}"] = unit_id
        else:
            lookup[_normalise(getattr(row, "nam", row.spatial_name))] = unit_id
            lookup[_normalise(row.spatial_name)] = unit_id
    return lookup


def _read_historic_population(
    path: Path,
    *,
    caba: bool,
    lookup: dict[str, str],
    years: tuple[int, ...] = YEARS,
) -> pd.DataFrame:
    frame = pd.read_excel(path, header=4, dtype={0: object})
    first = frame.columns[0]
    frame = frame.rename(columns={first: "raw_unit"})
    years = [year for year in years if year in frame.columns]
    frame = frame[["raw_unit", *years]].copy()
    frame["raw_unit"] = frame["raw_unit"].astype(str).str.strip()
    frame = frame[~frame["raw_unit"].isin(["", "nan", "Total"])]
    frame[years] = frame[years].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=years, how="all")
    # XLS sheets contain separate blocks for both sexes, women and men.  The
    # first block is explicitly labelled "Ambos sexos" and therefore provides
    # the denominator required here; retain its first occurrence only.
    frame = frame.drop_duplicates("raw_unit", keep="first")
    long = frame.melt("raw_unit", value_vars=years, var_name="year", value_name="population")
    long["year"] = pd.to_numeric(long["year"], errors="raise").astype(int)
    long["population"] = pd.to_numeric(long["population"], errors="coerce")
    if caba:
        long["spatial_id"] = long["raw_unit"].map(
            lambda value: lookup.get(f"comuna {int(float(value))}") if str(value).replace(".0", "").isdigit() else None
        )
    else:
        long["spatial_id"] = long["raw_unit"].map(lambda value: lookup.get(_normalise(value)))
    return long[["spatial_id", "year", "population"]].dropna()


def _read_current_population(
    path: Path,
    lookup: dict[str, str],
    years: tuple[int, ...] = YEARS,
) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype={"Código departamento": str})
    frame = frame[frame["Fecha"].isin(years)].copy()
    frame["population"] = pd.to_numeric(frame["Población"], errors="coerce")
    frame["year"] = pd.to_numeric(frame["Fecha"], errors="raise").astype(int)
    frame["spatial_id"] = None
    caba = frame["Nombre jurisdicción"].eq("CABA")
    frame.loc[caba, "spatial_id"] = frame.loc[caba, "Nombre departamento"].map(
        lambda value: lookup.get(_normalise(value))
    )
    buenos_aires = frame["Nombre jurisdicción"].eq("Buenos Aires")
    frame.loc[buenos_aires, "spatial_id"] = frame.loc[buenos_aires, "Código departamento"].map(
        lambda value: f"pba_{value}" if f"pba_{value}" in set(lookup.values()) else None
    )
    # The source contains one row per registered sex. Sum into a total.
    return (
        frame.dropna(subset=["spatial_id", "population"])
        .groupby(["spatial_id", "year"], as_index=False)["population"]
        .sum()
    )


def load_indec_population(
    raw_root: Path,
    units: gpd.GeoDataFrame,
    years: tuple[int, ...] = YEARS,
) -> pd.DataFrame:
    """Return one official population denominator for every AMBA unit-year."""
    lookup = _unit_lookup(units)
    historical = pd.concat(
        [
            _read_historic_population(
                raw_root / "population/indec_population_caba_2010_2025.xls",
                caba=True,
                lookup=lookup,
                years=years,
            ),
            _read_historic_population(
                raw_root / "population/indec_population_buenos_aires_2010_2025.xls",
                caba=False,
                lookup=lookup,
                years=years,
            ),
        ],
        ignore_index=True,
    )
    current = _read_current_population(
        raw_root / "population/indec_population_departments_2022_2035.csv",
        lookup,
        years,
    )
    # The 2022-base series supersedes the historical 2010-base estimates.
    population = pd.concat([historical[historical["year"] < 2022], current], ignore_index=True)
    expected = {(str(unit_id), year) for unit_id in units["spatial_id"] for year in years}
    actual = set(zip(population["spatial_id"].astype(str), population["year"].astype(int)))
    if expected != actual or (population["population"] <= 0).any():
        missing = sorted(expected - actual)[:20]
        extra = sorted(actual - expected)[:20]
        raise ValueError(f"INDEC population coverage mismatch; missing={missing}, extra={extra}")
    return population.sort_values(["spatial_id", "year"]).reset_index(drop=True)


def _map_sat_units(frame: pd.DataFrame, lookup: dict[str, str]) -> pd.DataFrame:
    result = frame.copy()
    is_caba = result["provincia_nombre"].eq("Ciudad Autónoma de Buenos Aires")
    result["spatial_id"] = None
    result.loc[is_caba, "spatial_id"] = result.loc[is_caba, "departamento_nombre"].map(
        lambda value: lookup.get(_normalise(value))
    )
    is_pba = result["provincia_nombre"].eq("Buenos Aires")
    result.loc[is_pba, "spatial_id"] = result.loc[is_pba, "departamento_nombre"].map(
        lambda value: lookup.get(_normalise(value))
    )
    return result


def build_community_safety_layer(
    city: str = "buenos_aires_amba",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[Path, Path, Path]:
    """Build the 2017-2024 AMBA property-crime exposure layer."""
    context = load_study(city)
    if context.study.id != "buenos_aires_amba":
        raise ValueError("community_safety currently supports only buenos_aires_amba")
    units = load_spatial_units(context)
    raw_root = context.repo_root / RAW_RELATIVE
    source = raw_root / "sat/csv/sat_propiedad_2017_2024.csv"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    crime = pd.read_csv(source, encoding="utf-8-sig", sep=None, engine="python")
    crime["anio"] = pd.to_numeric(crime["anio"], errors="coerce").astype("Int64")
    crime = crime[
        crime["anio"].isin(YEARS)
        & crime["provincia_nombre"].isin(["Ciudad Autónoma de Buenos Aires", "Buenos Aires"])
        & ~crime["departamento_nombre"].eq("Departamento sin determinar")
    ].copy()
    crime["cantidad_hechos"] = pd.to_numeric(crime["cantidad_hechos"], errors="raise")
    source_by_year = (
        crime.groupby("anio", as_index=False)
        .agg(source_rows=("cantidad_hechos", "size"), source_events=("cantidad_hechos", "sum"))
        .rename(columns={"anio": "year"})
    )
    crime = _map_sat_units(crime, _unit_lookup(units))
    unmatched = crime[crime["spatial_id"].isna()].copy()
    crime = crime.dropna(subset=["spatial_id"])
    mapped_by_year = (
        crime.groupby("anio", as_index=False)
        .agg(mapped_rows=("cantidad_hechos", "size"), mapped_events=("cantidad_hechos", "sum"))
        .rename(columns={"anio": "year"})
    )
    category = crime["nombre_delito_sat_prop"].astype(str).map(_normalise)
    crime["is_robbery"] = category.str.startswith("robo") | category.str.startswith("robos")
    crime["is_theft"] = category.str.startswith("hurto") | category.str.startswith("hurtos")
    crime["is_vehicle"] = category.str.contains("automotores|motocicletas", regex=True)
    by_year = (
        crime.assign(
            robbery=lambda d: d["cantidad_hechos"].where(d["is_robbery"], 0),
            theft=lambda d: d["cantidad_hechos"].where(d["is_theft"], 0),
            vehicle=lambda d: d["cantidad_hechos"].where(d["is_vehicle"], 0),
        )
        .groupby(["spatial_id", "anio"], as_index=False)
        .agg(
            crime_property_count=("cantidad_hechos", "sum"),
            crime_robbery_count=("robbery", "sum"),
            crime_theft_count=("theft", "sum"),
            crime_vehicle_count=("vehicle", "sum"),
            crime_public_space_count=("cantidad_hechos_lugar_via_publ", "sum"),
            crime_firearm_count=("cantidad_hechos_arma_de_fuego", "sum"),
        )
        .rename(columns={"anio": "year"})
    )
    population = load_indec_population(raw_root, units)
    annual = by_year.merge(population, on=["spatial_id", "year"], how="outer", validate="one_to_one")
    if annual.isna().any().any():
        raise ValueError("Property-crime or INDEC population data are incomplete for AMBA unit-years")
    for metric in ("property", "robbery", "theft", "vehicle"):
        annual[f"crime_{metric}_rate_100k"] = annual[f"crime_{metric}_count"] / annual["population"] * 100_000
    annual["crime_public_space_pct"] = annual["crime_public_space_count"] / annual["crime_property_count"] * 100
    annual["crime_firearm_pct"] = annual["crime_firearm_count"] / annual["crime_property_count"] * 100

    pooled = annual.groupby("spatial_id", as_index=False).agg(
        crime_property_count=("crime_property_count", "sum"),
        crime_robbery_count=("crime_robbery_count", "sum"),
        crime_theft_count=("crime_theft_count", "sum"),
        crime_vehicle_count=("crime_vehicle_count", "sum"),
        crime_public_space_count=("crime_public_space_count", "sum"),
        crime_firearm_count=("crime_firearm_count", "sum"),
        crime_population_person_years=("population", "sum"),
    )
    for metric in ("property", "robbery", "theft", "vehicle"):
        pooled[f"crime_{metric}_rate_100k"] = pooled[f"crime_{metric}_count"] / pooled["crime_population_person_years"] * 100_000
    pooled["crime_public_space_pct"] = pooled["crime_public_space_count"] / pooled["crime_property_count"] * 100
    pooled["crime_firearm_pct"] = pooled["crime_firearm_count"] / pooled["crime_property_count"] * 100
    annual_metrics = (
        "crime_property_rate_100k",
        "crime_robbery_rate_100k",
        "crime_theft_rate_100k",
        "crime_vehicle_rate_100k",
        "crime_public_space_pct",
        "crime_firearm_pct",
    )
    annual_wide = annual.pivot(
        index="spatial_id", columns="year", values=list(annual_metrics)
    )
    annual_wide.columns = [
        f"{metric}_{year}" for metric, year in annual_wide.columns.to_flat_index()
    ]
    result = units[["spatial_id", "spatial_name", "area_km2", "geometry"]].merge(pooled, on="spatial_id", how="left", validate="one_to_one")
    result = result.merge(annual_wide.reset_index(), on="spatial_id", how="left", validate="one_to_one")
    numeric = [column for column in result.columns if column.startswith("crime_")]
    result[numeric] = result[numeric].round(4)
    if len(result) != 55 or result[numeric].isna().any().any() or result["spatial_id"].duplicated().any():
        raise ValueError("Community-safety output does not satisfy the 55-unit AMBA contract")

    stem = "buenos_aires_amba_community_safety_sat_2017_2024"
    csv_path = out_dir / f"{stem}.csv"
    geojson_path = out_dir / f"{stem}.geojson"
    metadata_path = out_dir / f"{stem}_metadata.json"
    diagnostics_dir = out_dir / "diagnostics"
    diagnostics_dir.mkdir(exist_ok=True)
    private_columns = [
        column
        for column in result.columns
        if column.endswith("_count") or column.endswith("_person_years")
    ]
    result[["spatial_id", "spatial_name", *private_columns]].to_csv(
        diagnostics_dir / "community_safety_internal_counts.csv", index=False
    )
    public_result = result.drop(columns=private_columns)
    public_result.drop(columns="geometry").to_csv(csv_path, index=False)
    public_result.to_file(geojson_path, driver="GeoJSON")
    unmatched_path = diagnostics_dir / "community_safety_unmatched_sat_rows.csv"
    unmatched.groupby(["provincia_nombre", "departamento_nombre", "anio"], dropna=False).size().reset_index(name="rows").to_csv(unmatched_path, index=False)
    conservation_path = diagnostics_dir / "community_safety_conservation_by_year.csv"
    conservation = source_by_year.merge(mapped_by_year, on="year", how="outer", validate="one_to_one")
    conservation["unmapped_rows"] = conservation["source_rows"] - conservation["mapped_rows"]
    conservation["unmapped_events"] = conservation["source_events"] - conservation["mapped_events"]
    conservation.to_csv(conservation_path, index=False)
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "layer": "community_safety",
        "period": "2017-2024 pooled; annual values retained for all six public indicators",
        "unit": "registered property-crime events per 100,000 person-years",
        "method": "SAT-Propiedad counts by department/month/category, summed by AMBA unit and year; INDEC denominators; 2022-base INDEC series overrides 2010-base estimates from 2022 onward.",
        "sources": {
            "crime": "Dirección Nacional de Estadística Criminal, SAT Propiedad 2017-2024",
            "population_historical": "INDEC estimates by department/partido/comuna, 2010-2025",
            "population_current": "INDEC estimates by department/partido/comuna, 2022-2035",
        },
        "limitations": [
            "Measures registered events, not total victimization; reporting and recording practices can vary between jurisdictions and years.",
            "No causal or clinical interpretation should be assigned to this contextual exposure.",
            "Rows with Departamento sin determinar are excluded and reported separately.",
        ],
        "privacy": "Counts and population person-years are retained only in diagnostics; public layer outputs contain rates and percentages.",
        "methodology_doc": "docs/argentina_criminal_statistics_assessment.md",
        "columns": {column: str(public_result[column].dtype) for column in public_result.columns if column != "geometry"},
        "coverage": {
            "expected_units": 55,
            "actual_units": int(len(result)),
            "unmatched_rows": int(len(unmatched)),
            "conservation_report": conservation_path.relative_to(out_dir).as_posix(),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, geojson_path, metadata_path
