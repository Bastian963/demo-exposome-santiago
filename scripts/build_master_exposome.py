from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"


LAYER_SPECS = [
    {
        "name": "socioeconomic",
        "csv": "socioeconomic_exposome_rm_santiago.csv",
        "geojson": "socioeconomic_exposome_rm_santiago.geojson",
        "columns": ["poblacion", "pobreza_pct", "ingreso", "escolaridad", "nse_index"],
    },
    {
        "name": "air_quality",
        "csv": "air_quality_exposome_rm_santiago.csv",
        "columns": ["pm25_mean", "no2_mean", "n_grid", "pm25_who_ratio", "no2_who_ratio"],
    },
    {
        "name": "green",
        "csv": "green_exposome_rm_santiago.csv",
        "columns": ["green_km2", "green_pct", "n_green"],
    },
    {
        "name": "healthcare",
        "csv": "healthcare_exposome_rm_santiago.csv",
        "columns": [
            "n_total",
            "n_hospital",
            "n_pharmacy",
            "density_per_km2",
            "n_access_grid",
            "mean_nearest_health_m",
            "median_nearest_health_m",
            "p90_nearest_health_m",
            "mean_nearest_hospital_m",
            "median_nearest_hospital_m",
            "p90_nearest_hospital_m",
        ],
        "rename": {
            "n_total": "health_n_total",
            "n_hospital": "health_n_hospital",
            "n_pharmacy": "health_n_pharmacy",
            "density_per_km2": "health_density_per_km2",
            "n_access_grid": "health_n_access_grid",
        },
    },
    {
        "name": "climate_heat",
        "csv": "climate_heat_exposome_rm_santiago.csv",
        "geojson": "climate_heat_exposome_rm_santiago.geojson",
        "columns": [
            "tmean_annual_c",
            "tmax_mean_annual_c",
            "summer_tmax_mean_c",
            "tmax_p95_c",
            "tmax_abs_c",
            "apparent_tmax_mean_c",
            "hot_days_30c",
            "hot_days_35c",
            "apparent_hot_days_35c",
            "tropical_nights_20c",
            "precip_annual_mm",
            "heat_exposure_index",
            "urban_heat_anomaly_c",
            "n_area_grid_points",
            "nearest_climate_m",
            "used_nearest_fallback",
            "n_days",
        ],
        "rename": {
            "n_area_grid_points": "climate_n_area_grid_points",
            "nearest_climate_m": "climate_nearest_point_m",
            "used_nearest_fallback": "climate_used_nearest_fallback",
            "n_days": "climate_n_days",
        },
    },
]


def load_layer(spec: dict) -> pd.DataFrame:
    path = DATA_DIR / spec["csv"]
    if not path.exists():
        raise FileNotFoundError(f"Missing layer CSV: {path.name}")

    df = pd.read_csv(path)
    required = ["name", *spec["columns"]]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")

    out = df[required].copy()
    out = out.rename(columns=spec.get("rename", {}))
    return out


def build_master() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    base_geojson = DATA_DIR / "socioeconomic_exposome_rm_santiago.geojson"
    if not base_geojson.exists():
        base_geojson = DATA_DIR / "climate_heat_exposome_rm_santiago.geojson"
    if not base_geojson.exists():
        raise FileNotFoundError("Need a local GeoJSON layer to provide commune geometries")

    gdf = gpd.read_file(base_geojson)
    if "area_km2" not in gdf.columns:
        metric = gdf.to_crs("EPSG:32719")
        gdf["area_km2"] = metric.geometry.area / 1e6
    gdf = gdf[["name", "area_km2", "geometry"]].drop_duplicates("name").copy()
    gdf["area_km2"] = gdf["area_km2"].round(2)

    master = pd.DataFrame(gdf.drop(columns="geometry"))
    for spec in LAYER_SPECS:
        layer = load_layer(spec)
        master = master.merge(layer, on="name", how="left", validate="one_to_one")

    if len(master) != 52:
        raise ValueError(f"Expected 52 communes, got {len(master)}")
    if master["name"].duplicated().any():
        dupes = master.loc[master["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    if master.isna().any().any():
        missing = master.columns[master.isna().any()].tolist()
        raise ValueError(f"Master table has missing values in: {missing}")

    gdf_master = gdf[["name", "geometry"]].merge(master, on="name", how="right", validate="one_to_one")
    gdf_master = gdf_master.set_geometry("geometry")
    return master.sort_values("name").reset_index(drop=True), gdf_master.sort_values("name").reset_index(drop=True)


def main() -> None:
    master, gdf_master = build_master()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_out = DATA_DIR / "santiago_exposome_master.csv"
    geojson_out = DATA_DIR / "santiago_exposome_master.geojson"
    metadata_out = DATA_DIR / "santiago_exposome_master_metadata.json"

    master.to_csv(csv_out, index=False)
    gdf_master.to_file(geojson_out, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_communes": int(len(master)),
        "n_variables_including_name_area": int(master.shape[1]),
        "layers": [
            {"name": spec["name"], "csv": spec["csv"], "columns": spec["columns"]}
            for spec in LAYER_SPECS
        ],
        "outputs": [csv_out.name, geojson_out.name],
    }
    metadata_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {csv_out.name}: {master.shape[0]} rows x {master.shape[1]} columns")
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {metadata_out.name}")


if __name__ == "__main__":
    main()
