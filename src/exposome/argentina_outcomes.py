"""Internal AMBA mortality comparators from Argentina DNEC SAT microdata.

These are ecological outcome/comparator products, not exposome layers.  They
intentionally exclude all point coordinates and person-level fields from their
outputs.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import geopandas as gpd
import pandas as pd

from .community_safety import (
    RAW_RELATIVE,
    YEARS,
    _map_sat_units,
    _unit_lookup,
    load_indec_population,
)
from .spatial import load_spatial_units
from .studies import load_study


OutcomeKind = Literal["suicide_mortality", "road_traffic_mortality"]
WINDOWS = tuple((start, start + 2) for start in range(2017, 2023))
PUBLIC_CELL_THRESHOLD = 5

_SPECS: dict[OutcomeKind, dict[str, str]] = {
    "suicide_mortality": {
        "source_file": "sat_suicidios_2017_2024.csv",
        "prefix": "suicide",
        "label": "suicide deaths",
        "source": "Dirección Nacional de Estadística Criminal, SAT Suicidios 2017-2024",
        "person_filter": "all_rows_are_suicide_victims",
        "count_rule": "Count unique tipo_persona_id (one suicide victim per person record); id_hecho is retained only for diagnostics.",
    },
    "road_traffic_mortality": {
        "source_file": "sat_muertes_viales_2017_2024.csv",
        "prefix": "road_traffic",
        "label": "road-traffic deaths",
        "source": "Dirección Nacional de Estadística Criminal, SAT Muertes Viales 2017-2024",
        "person_filter": "tipo_persona == Víctima",
        "count_rule": "Filter tipo_persona == Víctima, then count unique tipo_persona_id; imputed persons are excluded.",
    },
}


def _spec(kind: OutcomeKind) -> dict[str, str]:
    try:
        return _SPECS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown Argentina outcome comparator: {kind}") from exc


def _source_records(kind: OutcomeKind, raw_root: Path) -> pd.DataFrame:
    spec = _spec(kind)
    frame = pd.read_csv(raw_root / "sat/csv" / spec["source_file"], encoding="utf-8-sig", sep=None, engine="python")
    frame["anio"] = pd.to_numeric(frame["anio"], errors="coerce").astype("Int64")
    frame = frame[
        frame["anio"].isin(YEARS)
        & frame["provincia_nombre"].isin(["Ciudad Autónoma de Buenos Aires", "Buenos Aires"])
        & ~frame["departamento_nombre"].eq("Departamento sin determinar")
    ].copy()
    if kind == "road_traffic_mortality":
        frame = frame[frame["tipo_persona"].eq("Víctima")].copy()
    if frame["tipo_persona_id"].isna().any() or frame["id_hecho"].isna().any():
        raise ValueError(f"{kind} has missing person or event identifiers")
    return frame


def _conservation(source: pd.DataFrame, mapped: pd.DataFrame) -> pd.DataFrame:
    source_stats = (
        source.groupby("anio", as_index=False)
        .agg(source_rows=("tipo_persona_id", "size"), source_persons=("tipo_persona_id", "nunique"), source_events=("id_hecho", "nunique"))
        .rename(columns={"anio": "year"})
    )
    mapped_stats = (
        mapped.groupby("anio", as_index=False)
        .agg(mapped_rows=("tipo_persona_id", "size"), mapped_persons=("tipo_persona_id", "nunique"), mapped_events=("id_hecho", "nunique"))
        .rename(columns={"anio": "year"})
    )
    result = source_stats.merge(mapped_stats, on="year", how="outer", validate="one_to_one")
    for measure in ("rows", "persons", "events"):
        result[f"unmapped_{measure}"] = result[f"source_{measure}"] - result[f"mapped_{measure}"]
    return result


def build_argentina_outcome_comparator(
    kind: OutcomeKind,
    *,
    city: str = "buenos_aires_amba",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[Path, Path, Path]:
    """Build one internal, 55-unit SAT mortality comparator."""
    del cache_dir  # Kept for the shared runner signature; inputs are local and versioned.
    context = load_study(city)
    if context.study.id != "buenos_aires_amba":
        raise ValueError(f"{kind} currently supports only buenos_aires_amba")
    spec = _spec(kind)
    units = load_spatial_units(context)
    raw_root = context.repo_root / RAW_RELATIVE
    source = _source_records(kind, raw_root)
    mapped = _map_sat_units(source, _unit_lookup(units))
    unmatched = mapped[mapped["spatial_id"].isna()].copy()
    mapped = mapped.dropna(subset=["spatial_id"])
    conservation = _conservation(source, mapped)

    annual_counts = (
        mapped.groupby(["spatial_id", "anio"], as_index=False)["tipo_persona_id"]
        .nunique()
        .rename(columns={"anio": "year", "tipo_persona_id": "death_count"})
    )
    population = load_indec_population(raw_root, units)
    full_index = pd.MultiIndex.from_product(
        [units["spatial_id"].astype(str), YEARS], names=["spatial_id", "year"]
    )
    annual = (
        population.set_index(["spatial_id", "year"])
        .reindex(full_index)
        .join(annual_counts.set_index(["spatial_id", "year"]), how="left")
        .reset_index()
    )
    if annual["population"].isna().any():
        raise ValueError(f"INDEC population is incomplete for {kind}")
    annual["death_count"] = annual["death_count"].fillna(0).astype(int)
    annual["rate_100k"] = annual["death_count"] / annual["population"] * 100_000

    prefix = spec["prefix"]
    pooled = annual.groupby("spatial_id", as_index=False).agg(
        **{
            f"{prefix}_death_count": ("death_count", "sum"),
            f"{prefix}_population_person_years": ("population", "sum"),
        }
    )
    pooled[f"{prefix}_mortality_rate_100k"] = (
        pooled[f"{prefix}_death_count"] / pooled[f"{prefix}_population_person_years"] * 100_000
    )
    annual_counts_wide = annual.pivot(index="spatial_id", columns="year", values="death_count")
    annual_counts_wide.columns = [f"{prefix}_death_count_{year}" for year in annual_counts_wide.columns]
    annual_rates_wide = annual.pivot(index="spatial_id", columns="year", values="rate_100k")
    annual_rates_wide.columns = [f"{prefix}_mortality_rate_100k_{year}" for year in annual_rates_wide.columns]
    result = units[["spatial_id", "spatial_name", "area_km2", "geometry"]].merge(
        pooled, on="spatial_id", how="left", validate="one_to_one"
    )
    result = result.merge(annual_counts_wide.reset_index(), on="spatial_id", how="left", validate="one_to_one")
    result = result.merge(annual_rates_wide.reset_index(), on="spatial_id", how="left", validate="one_to_one")
    numeric = [column for column in result.columns if column.startswith(prefix)]
    result[numeric] = result[numeric].round(4)
    if len(result) != 55 or result["spatial_id"].duplicated().any() or result[numeric].isna().any().any():
        raise ValueError(f"{kind} output does not satisfy the 55-unit AMBA contract")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"buenos_aires_amba_{kind}_sat_2017_2024"
    csv_path = out_dir / f"{stem}.csv"
    geojson_path = out_dir / f"{stem}.geojson"
    metadata_path = out_dir / f"{stem}_metadata.json"
    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result.to_file(geojson_path, driver="GeoJSON")
    diagnostics = out_dir / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    conservation_path = diagnostics / f"{kind}_conservation_by_year.csv"
    conservation.to_csv(conservation_path, index=False)
    unmatched_path = diagnostics / f"{kind}_unmatched_records.csv"
    unmatched.groupby(["provincia_nombre", "departamento_nombre", "anio"], dropna=False).agg(
        rows=("tipo_persona_id", "size"), persons=("tipo_persona_id", "nunique"), events=("id_hecho", "nunique")
    ).reset_index().to_csv(unmatched_path, index=False)

    # A deliberately separate, disclosure-controlled derivative is the only
    # outcome asset eligible for the web bundle. The internal comparator above
    # retains counts for modelling and conservation tests.
    web_dir = out_dir / "web"
    web_dir.mkdir(exist_ok=True)
    web_result = units[["spatial_id", "spatial_name", "area_km2", "geometry"]].merge(
        pooled[["spatial_id", f"{prefix}_mortality_rate_100k"]],
        on="spatial_id",
        how="left",
        validate="one_to_one",
    )
    window_columns: dict[str, str] = {}
    for start, end in WINDOWS:
        window = (
            annual[annual["year"].between(start, end)]
            .groupby("spatial_id", as_index=False)
            .agg(death_count=("death_count", "sum"), population=("population", "sum"))
        )
        column = f"{prefix}_mortality_rate_100k_{start}_{end}"
        window[column] = window["death_count"] / window["population"] * 100_000
        window.loc[window["death_count"] < PUBLIC_CELL_THRESHOLD, column] = pd.NA
        web_result = web_result.merge(
            window[["spatial_id", column]], on="spatial_id", validate="one_to_one"
        )
        window_columns[f"{start}–{end}"] = column
    rate_columns = [column for column in web_result if column.startswith(prefix)]
    web_result[rate_columns] = web_result[rate_columns].round(4)
    web_geojson = web_dir / f"{kind}.geojson"
    web_result.to_file(web_geojson, driver="GeoJSON")
    catalog_entry = {
        "id": kind,
        "title": "Mortalidad por suicidio" if kind == "suicide_mortality" else "Mortalidad vial",
        "column": f"{prefix}_mortality_rate_100k",
        "unit": "muertes / 100 mil personas-año",
        "period": "2017–2024",
        "default_period": "2022–2024",
        "period_columns": window_columns,
        "asset": f"outcomes/{kind}.geojson",
        "suppression_threshold": PUBLIC_CELL_THRESHOLD,
        "release_status": "maps_ready_associations_gated",
        "association_gate": (
            "Pendientes la estandarización por edad/sexo, las covariables "
            "censales y el diagnóstico espacial."
        ),
        "source": spec["source"],
        "methodology": "outcomes_methodology",
    }
    (web_dir / "catalog_entry.json").write_text(
        json.dumps(catalog_entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "layer": kind,
        "classification": "ecological outcome comparator; excluded from the exposome master; web publication is limited to the sanitized derivative",
        "period": "2017-2024 pooled; annual values retained as columns",
        "unit": f"{spec['label']} per 100,000 person-years",
        "count_rule": spec["count_rule"],
        "person_filter": spec["person_filter"],
        "sources": {
            "outcome": spec["source"],
            "population_historical": "INDEC estimates by department/partido/comuna, 2010-2025",
            "population_current": "INDEC estimates by department/partido/comuna, 2022-2035",
        },
        "privacy": "The modelling output is internal. The separate web derivative contains rates only and suppresses three-year cells backed by fewer than five deaths.",
        "limitations": [
            "A zero is no released SAT victim record for that unit-year; it does not establish absence of mortality or homogeneous reporting coverage.",
            "This ecological comparator is not a causal or clinical outcome estimate.",
            "Rows with Departamento sin determinar are excluded and reported in diagnostics.",
            "SAT-MV coordinates are intentionally not read into the output because the source documents them as approximate.",
        ],
        "coverage": {
            "expected_units": 55,
            "actual_units": int(len(result)),
            "conservation_report": conservation_path.relative_to(out_dir).as_posix(),
            "unmatched_report": unmatched_path.relative_to(out_dir).as_posix(),
            "web_geojson": web_geojson.relative_to(out_dir).as_posix(),
        },
        "columns": {column: str(result[column].dtype) for column in result.columns if column != "geometry"},
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path, geojson_path, metadata_path


def build_suicide_mortality_comparator(**kwargs: object) -> tuple[Path, Path, Path]:
    return build_argentina_outcome_comparator("suicide_mortality", **kwargs)


def build_road_traffic_mortality_comparator(**kwargs: object) -> tuple[Path, Path, Path]:
    return build_argentina_outcome_comparator("road_traffic_mortality", **kwargs)
