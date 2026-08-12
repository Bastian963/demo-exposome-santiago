"""AMBA registered community-violence exposome from SNIC departments.

The layer uses mutually exclusive top-level SNIC codes only.  It describes
institutionally registered events/victims and must not be interpreted as
individual victimisation or causal risk.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .community_safety import (
    RAW_RELATIVE,
    _map_sat_units,
    _unit_lookup,
    load_indec_population,
)
from .spatial import load_spatial_units
from .studies import load_study


YEARS = tuple(range(2017, 2026))
WINDOWS = tuple((start, start + 2) for start in range(2017, 2024))
SOURCE_RELATIVE = Path("snic/csv/snic_departamentos_anual_2000_2025.csv")

# metric -> (baseline SNIC codes, count field). Sexual-violence codes have a
# documented taxonomy break: grouped code 11 through 2022, child codes 11_1
# through 11_5 from 2023. ``_metric_codes_for_year`` is the source of truth.
METRICS: dict[str, tuple[tuple[str, ...], str]] = {
    "violence_homicide_victim_rate_100k": (("1",), "cantidad_victimas"),
    "violence_attempted_homicide_victim_rate_100k": (("2",), "cantidad_victimas"),
    "violence_intentional_injury_victim_rate_100k": (("5",), "cantidad_victimas"),
    "violence_sexual_victim_rate_100k": (("10", "11"), "cantidad_victimas"),
    "violence_aggravated_robbery_event_rate_100k": (("17",), "cantidad_hechos"),
}

SEXUAL_CHILD_CODES = ("11_1", "11_2", "11_3", "11_4", "11_5")


def _metric_codes_for_year(metric: str, year: int) -> tuple[str, ...]:
    if metric == "violence_sexual_victim_rate_100k":
        return ("10", "11") if year <= 2022 else ("10", *SEXUAL_CHILD_CODES)
    return METRICS[metric][0]


def _normalise_code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _load_source(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        sep=";",
        encoding="utf-8-sig",
        dtype={"codigo_delito_snic_id": str},
        low_memory=False,
    )
    required = {
        "anio",
        "provincia_nombre",
        "departamento_nombre",
        "codigo_delito_snic_id",
        "cantidad_hechos",
        "cantidad_victimas",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"SNIC departments source is missing columns: {missing}")
    frame["anio"] = pd.to_numeric(frame["anio"], errors="coerce").astype("Int64")
    frame["codigo_delito_snic_id"] = frame["codigo_delito_snic_id"].map(_normalise_code)
    return frame[
        frame["anio"].isin(YEARS)
        & frame["provincia_nombre"].isin(
            ["Ciudad Autónoma de Buenos Aires", "Buenos Aires"]
        )
        & ~frame["departamento_nombre"].eq("Departamento sin determinar")
    ].copy()


def _metric_annual_counts(source: pd.DataFrame, units: gpd.GeoDataFrame) -> pd.DataFrame:
    mapped = _map_sat_units(source, _unit_lookup(units))
    relevant_codes = {
        code
        for metric in METRICS
        for year in YEARS
        for code in _metric_codes_for_year(metric, year)
    }
    mapped = mapped[mapped["codigo_delito_snic_id"].isin(relevant_codes)].copy()
    # The official file covers every department in CABA and Buenos Aires
    # province (150 territories), while this study intentionally contains 55.
    # Out-of-scope departments are dropped here; the complete unit-year-code
    # grid validation below still fails if any of the 55 AMBA units is absent.
    mapped = mapped.dropna(subset=["spatial_id"])

    expected = pd.MultiIndex.from_product(
        [units["spatial_id"].astype(str), YEARS], names=["spatial_id", "year"]
    )
    result = pd.DataFrame(index=expected).reset_index()
    for metric, (_, count_field) in METRICS.items():
        allowed_by_year = {
            year: set(_metric_codes_for_year(metric, year)) for year in YEARS
        }
        metric_codes = set().union(*allowed_by_year.values())
        subset = mapped[
            mapped["codigo_delito_snic_id"].isin(metric_codes)
            & mapped.apply(
                lambda row: row["codigo_delito_snic_id"]
                in allowed_by_year[int(row["anio"])],
                axis=1,
            )
        ].copy()
        subset[count_field] = pd.to_numeric(subset[count_field], errors="coerce")
        coverage = subset.groupby(["spatial_id", "anio"])["codigo_delito_snic_id"].agg(set)
        incomplete: list[tuple[str, int, list[str]]] = []
        for spatial_id, year in expected:
            observed = coverage.get((spatial_id, year), set())
            missing = sorted(allowed_by_year[int(year)] - observed)
            if missing:
                incomplete.append((str(spatial_id), int(year), missing))
        if incomplete:
            raise ValueError(
                f"SNIC coverage is incomplete for {metric}; missing code rows at {incomplete[:10]}"
            )
        grouped = (
            subset.groupby(["spatial_id", "anio"], as_index=False)[count_field]
            .sum(min_count=1)
            .rename(columns={"anio": "year", count_field: metric.removesuffix("_rate_100k") + "_count"})
        )
        result = result.merge(grouped, on=["spatial_id", "year"], how="left", validate="one_to_one")
    if result.isna().any().any():
        raise ValueError("SNIC community-violence counts contain missing values")
    return result


def build_community_violence_layer(
    city: str = "buenos_aires_amba",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[Path, Path, Path]:
    """Build pooled and three-year-window AMBA violence-context indicators."""
    del cache_dir
    context = load_study(city)
    if context.study.id != "buenos_aires_amba":
        raise ValueError("community_violence currently supports only buenos_aires_amba")
    units = load_spatial_units(context)
    raw_root = context.repo_root / RAW_RELATIVE
    source_path = raw_root / SOURCE_RELATIVE
    if not source_path.exists():
        raise FileNotFoundError(
            f"Missing SNIC department source: {source_path}. Run the documented DNEC importer first."
        )
    source = _load_source(source_path)
    source_territories = int(
        source[["provincia_nombre", "departamento_nombre"]].drop_duplicates().shape[0]
    )
    annual = _metric_annual_counts(source, units)
    population = load_indec_population(raw_root, units, YEARS)
    annual = annual.merge(population, on=["spatial_id", "year"], validate="one_to_one")

    count_columns = [column for column in annual if column.endswith("_count")]
    rate_by_count = {
        metric.removesuffix("_rate_100k") + "_count": metric for metric in METRICS
    }
    for count_column, rate_column in rate_by_count.items():
        annual[rate_column] = annual[count_column] / annual["population"] * 100_000

    pooled = annual.groupby("spatial_id", as_index=False).agg(
        population_person_years=("population", "sum"),
        **{column: (column, "sum") for column in count_columns},
    )
    for count_column, rate_column in rate_by_count.items():
        pooled[rate_column] = pooled[count_column] / pooled["population_person_years"] * 100_000

    result = units[["spatial_id", "spatial_name", "area_km2", "geometry"]].merge(
        pooled, on="spatial_id", how="left", validate="one_to_one"
    )
    for start, end in WINDOWS:
        window = annual[annual["year"].between(start, end)]
        grouped = window.groupby("spatial_id", as_index=False).agg(
            population=("population", "sum"),
            **{column: (column, "sum") for column in count_columns},
        )
        for count_column, rate_column in rate_by_count.items():
            public_column = f"{rate_column}_{start}_{end}"
            grouped[public_column] = grouped[count_column] / grouped["population"] * 100_000
            grouped.loc[grouped[count_column] < 5, public_column] = pd.NA
        keep = ["spatial_id", *[f"{metric}_{start}_{end}" for metric in METRICS]]
        result = result.merge(grouped[keep], on="spatial_id", validate="one_to_one")

    numeric = [column for column in result if column.startswith("violence_")]
    result[numeric] = result[numeric].round(4)
    if len(result) != 55 or result["spatial_id"].duplicated().any():
        raise ValueError("Community-violence output does not satisfy the 55-unit AMBA contract")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "buenos_aires_amba_community_violence_snic_2017_2025"
    csv_path = out_dir / f"{stem}.csv"
    geojson_path = out_dir / f"{stem}.geojson"
    metadata_path = out_dir / f"{stem}_metadata.json"
    diagnostics_dir = out_dir / "diagnostics"
    diagnostics_dir.mkdir(exist_ok=True)
    private_columns = [
        column
        for column in result.columns
        if column.endswith("_count") or column == "population_person_years"
    ]
    result[["spatial_id", "spatial_name", *private_columns]].to_csv(
        diagnostics_dir / "community_violence_internal_counts.csv", index=False
    )
    public_result = result.drop(columns=private_columns)
    public_result.drop(columns="geometry").to_csv(csv_path, index=False)
    public_result.to_file(geojson_path, driver="GeoJSON")
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "layer": "community_violence",
        "classification": "social exposome: registered community-violence context",
        "period": "2017-2025 pooled; public three-year rolling windows",
        "source": "DNEC Sistema Nacional de Información Criminal, departamentos anual",
        "population_source": "INDEC department/partido/comuna population estimates",
        "source_scope": {
            "source_territories_caba_and_buenos_aires": source_territories,
            "study_territories_amba": int(len(units)),
            "out_of_study_territories_excluded": source_territories - int(len(units)),
        },
        "code_policy": {
            metric: {
                "codes_2017_2022": list(_metric_codes_for_year(metric, 2022)),
                "codes_2023_2025": list(_metric_codes_for_year(metric, 2023)),
                "count_field": field,
            }
            for metric, (_, field) in METRICS.items()
        },
        "privacy": "Public windows suppress rates backed by fewer than five registered events/victims.",
        "methodology_doc": "docs/community_violence_methodology.md",
        "limitations": [
            "Registered records are not total victimisation or individual risk.",
            "Reporting practices can differ by jurisdiction and year.",
            "SNIC taxonomy eras are explicit: grouped sexual code 11 through 2022 and child codes 11_1-11_5 from 2023, never both in the same year.",
        ],
        "columns": {column: str(public_result[column].dtype) for column in public_result if column != "geometry"},
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, geojson_path, metadata_path
