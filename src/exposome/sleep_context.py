"""Sleep-circadian context layer for the Santiago exposome.

This layer does not estimate individual sleep duration or sleep quality.
Instead, it combines commune-level urban exposures that are plausibly linked to
sleep disruption: artificial light at night, warm nights, and social
vulnerability. Survey sources such as ENS/ENUT are used as regional context,
not as commune-level imputations.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from . import config


REQUIRED_MASTER_COLUMNS = [
    "name",
    "area_km2",
    "alan_radiance_pop_weighted",
    "om_tropical_nights_20c",
    "om_tmin_mean_summer_c",
    "hacinamiento_phh",
    "demo_pct_pop_65_plus",
    "nse_index",
]

OUTPUT_COLUMNS = [
    "name",
    "area_km2",
    "sleep_alan_log",
    "sleep_tropical_nights_20c",
    "sleep_summer_tmin_c",
    "sleep_exposure_index",
    "sleep_vulnerability_index",
    "sleep_context_index",
]


def _rank_percentile(values: pd.Series) -> pd.Series:
    """Return 0-100 percentile ranks where larger input means higher risk."""
    ranks = values.rank(method="average")
    if len(values) <= 1:
        return pd.Series(100.0, index=values.index)
    return (ranks - 1) / (len(values) - 1) * 100


def _validate_input(df: pd.DataFrame, expected_communes: int) -> None:
    missing = [col for col in REQUIRED_MASTER_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Master table is missing columns required for sleep context: {missing}")
    if len(df) != expected_communes:
        raise ValueError(f"Expected {expected_communes} communes, got {len(df)}")
    if df["name"].duplicated().any():
        dupes = df.loc[df["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    if df[REQUIRED_MASTER_COLUMNS].isna().any().any():
        missing_cols = df[REQUIRED_MASTER_COLUMNS].columns[
            df[REQUIRED_MASTER_COLUMNS].isna().any()
        ].tolist()
        raise ValueError(f"Missing values in sleep context inputs: {missing_cols}")


def _validate_output(df: pd.DataFrame, expected_communes: int) -> None:
    if len(df) != expected_communes:
        raise ValueError(f"Expected {expected_communes} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names in sleep context output")
    if df[OUTPUT_COLUMNS].isna().any().any():
        missing = df[OUTPUT_COLUMNS].columns[df[OUTPUT_COLUMNS].isna().any()].tolist()
        raise ValueError(f"Missing values in sleep context output: {missing}")
    if not df["sleep_context_index"].between(0, 100).all():
        raise ValueError("sleep_context_index must be bounded between 0 and 100")


def compute_sleep_context(master: pd.DataFrame) -> pd.DataFrame:
    """Compute commune-level sleep-circadian context indicators.

    Higher values always indicate a higher-risk sleep-circadian context.
    """
    out = master[["name", "area_km2"]].copy()
    out["sleep_alan_log"] = np.log1p(master["alan_radiance_pop_weighted"])
    out["sleep_tropical_nights_20c"] = master["om_tropical_nights_20c"]
    out["sleep_summer_tmin_c"] = master["om_tmin_mean_summer_c"]

    exposure_components = pd.DataFrame(
        {
            "alan": _rank_percentile(out["sleep_alan_log"]),
            "tropical_nights": _rank_percentile(out["sleep_tropical_nights_20c"]),
            "summer_tmin": _rank_percentile(out["sleep_summer_tmin_c"]),
        },
        index=out.index,
    )
    vulnerability_components = pd.DataFrame(
        {
            "overcrowding": _rank_percentile(master["hacinamiento_phh"]),
            "older_population": _rank_percentile(master["demo_pct_pop_65_plus"]),
            "lower_ses": _rank_percentile(-master["nse_index"]),
        },
        index=out.index,
    )

    out["sleep_exposure_index"] = exposure_components.mean(axis=1)
    out["sleep_vulnerability_index"] = vulnerability_components.mean(axis=1)
    out["sleep_context_index"] = (
        0.70 * out["sleep_exposure_index"] + 0.30 * out["sleep_vulnerability_index"]
    )

    for col in OUTPUT_COLUMNS:
        if col not in {"name"}:
            out[col] = out[col].round(4)
    return out[OUTPUT_COLUMNS].copy()


def build_sleep_context_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
    master_csv: Path | None = None,
    master_geojson: Path | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build and export the sleep-circadian context layer."""
    cfg = config.load_config(city)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if master_csv is None:
        legacy_master_csv = out_dir / f"{city}_exposome_master.csv"
        canonical_master_csv = out_dir.parent / "master.csv"
        master_csv = legacy_master_csv if legacy_master_csv.exists() else canonical_master_csv
    else:
        master_csv = Path(master_csv)
    if master_geojson is None:
        legacy_master_geojson = out_dir / f"{city}_exposome_master.geojson"
        canonical_master_geojson = out_dir.parent / "master.geojson"
        master_geojson = (
            legacy_master_geojson
            if legacy_master_geojson.exists()
            else canonical_master_geojson
        )
    else:
        master_geojson = Path(master_geojson)
    if not master_csv.exists():
        raise FileNotFoundError(
            f"Missing {master_csv}. Build the study master before the derived sleep layer."
        )
    if not master_geojson.exists():
        raise FileNotFoundError(
            f"Missing {master_geojson}. Build the study master before the derived sleep layer."
        )

    master = pd.read_csv(master_csv)
    expected_communes = int(cfg["expected_communes"])
    _validate_input(master, expected_communes)

    df = compute_sleep_context(master)
    _validate_output(df, expected_communes)

    gdf_base = gpd.read_file(master_geojson)[["name", "geometry"]].drop_duplicates("name")
    gdf = gdf_base.merge(df, on="name", how="right", validate="one_to_one")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    base_name = f"{city}_sleep_context"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    meta_path = out_dir / f"{base_name}_metadata.json"

    df.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": len(df),
        "warning": (
            "This is an environmental sleep-circadian context index, not a "
            "direct measurement of sleep duration, sleep quality, insomnia, or "
            "any clinical sleep disorder."
        ),
        "method": {
            "sleep_alan_log": "log1p(alan_radiance_pop_weighted)",
            "sleep_tropical_nights_20c": "om_tropical_nights_20c",
            "sleep_summer_tmin_c": "om_tmin_mean_summer_c",
            "sleep_exposure_index": (
                "Mean of 0-100 percentile ranks for log ALAN, tropical nights, "
                "and summer mean daily minimum temperature."
            ),
            "sleep_vulnerability_index": (
                "Mean of 0-100 percentile ranks for household overcrowding, "
                "older-population share, and lower socioeconomic position (-nse_index)."
            ),
            "sleep_context_index": (
                "0.70 * sleep_exposure_index + 0.30 * sleep_vulnerability_index"
            ),
        },
        "weights": {
            "exposure_index": {
                "sleep_alan_log": 1 / 3,
                "sleep_tropical_nights_20c": 1 / 3,
                "sleep_summer_tmin_c": 1 / 3,
            },
            "vulnerability_index": {
                "hacinamiento_phh": 1 / 3,
                "demo_pct_pop_65_plus": 1 / 3,
                "negative_nse_index": 1 / 3,
            },
            "sleep_context_index": {
                "sleep_exposure_index": 0.70,
                "sleep_vulnerability_index": 0.30,
            },
        },
        "sources": {
            "direct_sleep_reference_sources": {
                "ens_minsal": "https://epi.minsal.cl/bases-de-datos/",
                "enut_ine": "https://www.ine.gob.cl/estadisticas/sociales/genero/uso-del-tiempo/enut",
                "enut_2023_report": (
                    "https://www.ine.gob.cl/docs/default-source/uso-del-tiempo-tiempo-libre/"
                    "publicaciones-y-anuarios/ii-enut/informe-de-principales-resultados-ii-enut-2023.pdf"
                ),
                "ens_sleep_rm_substudy": (
                    "https://www.scielo.cl/scielo.php?pid=S0034-98872020000700895&script=sci_arttext"
                ),
            },
            "commune_exposure_inputs": {
                "alan": "santiago_alan_viirs_2024.csv",
                "climate": "santiago_climate_metrics_annual.csv",
                "socioeconomic_demography": "santiago_exposome_master.csv",
            },
        },
        "columns": df.columns.tolist(),
        "outputs": [csv_path.name, geojson_path.name],
    }
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {csv_path.name} / {geojson_path.name} ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf
