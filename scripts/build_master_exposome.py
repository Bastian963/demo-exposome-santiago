from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
sys.path.insert(0, str(ROOT / "src"))

from exposome.master import (  # noqa: E402 - scripts add src to sys.path above
    LayerOutputSpec,
    StudyMasterResult,
    build_study_master,
)


LAYER_SPECS = [
    {
        "name": "socioeconomic",
        "csv": "socioeconomic_exposome_rm_santiago.csv",
        "geojson": "socioeconomic_exposome_rm_santiago.geojson",
        "columns": [
            "poblacion",
            "ingreso",
            "escolaridad",
            "pobreza_pct",
            "pobreza_ci_low",
            "pobreza_ci_high",
            "pobreza_multi_pct",
            "viv_materialidad_deficitaria_pct",
            "hacinamiento_phh",
            "nse_index",
            "nse_index_pca",
            "nse_quintil",
        ],
        "optional_columns": [
            "tasa_delitos_violentos",
            "tasa_delitos_propiedad",
            "paes_puntaje_promedio",
            "pct_fonasa_tramo_a_b",
            "ipp_per_capita",
        ],
    },
    {
        # Legacy CAMS air quality (~11 km). PM2.5 is intentionally dropped here:
        # it is superseded by the high-resolution ACAG layer below (the coarse
        # CSV/figures are kept for the documented CAMS-vs-satellite comparison).
        # `no2_mean` is also dropped from the master to avoid a name
        # collision with the satellite layer (the satellite `no2_mean`
        # is the canonical value going forward); the master keeps the
        # legacy `no2_who_ratio` for the documented CAMS-vs-satellite
        # comparison only.
        "name": "air_quality",
        "csv": "air_quality_exposome_rm_santiago.csv",
        "columns": ["n_grid", "no2_who_ratio"],
    },
    {
        # Chronic high-resolution PM2.5 (~1 km) from ACAG/van Donkelaar via GEE.
        # This is the canonical pm25_* in the master (Lancet 2024 dementia driver).
        # Required, not optional: since it replaced the legacy guaranteed pm25,
        # a missing CSV must fail loudly (run scripts/run_pm25.py first) instead
        # of silently dropping PM2.5 from the integrated table.
        "name": "air_quality_pm25",
        "csv": "santiago_pm25_acag_2015_2022.csv",
        "columns": ["pm25_mean", "pm25_pop_weighted", "pm25_who_ratio"],
    },
    {
        # Industrial heavy-metal air emissions from RETC point sources (MMA).
        # Completes the chemical/toxin pillar absent from PM2.5/NO2 layers.
        # Run scripts/run_heavy_metals.py to generate this CSV.
        "name": "heavy_metals",
        "csv": "santiago_heavy_metals_retc_2015_2022.csv",
        "optional_layer": True,  # new layer — allow build before first run
        "columns": ["hm_pb_kg", "hm_mn_kg", "hm_as_kg", "hm_cd_kg", "hm_hg_kg",
                    "hm_pb_log", "hm_as_log", "n_sources", "hm_index"],
    },
    {
        "name": "air_quality_satellite",
        "csv": "santiago_air_quality_satellite_2024.csv",
        "columns": [
            "blh_mean", "aod_mean",
            "ae_470_550_mean", "fine_mode_fraction_mean", "o3_mean",
            "no2_surface_ug_m3", "no2_who_ratio",
        ],
        "rename": {
            # The satellite-derived NO2/WHO ratio is more accurate than
            # the legacy CAMS-derived one; rename in the master so we
            # overwrite the legacy value.
            "no2_who_ratio": "no2_who_ratio_satellite",
        },
    },
    {
        "name": "wind",
        "csv": "santiago_wind.csv",
        "optional_layer": True,
        "columns": [
            "wind_u_mean", "wind_v_mean", "wind_speed_mean",
            "wind_speed_max_p99", "wind_calm_pct", "wind_dir_prevailing",
            "wind_u_mean_winter", "wind_v_mean_winter",
            "wind_speed_mean_winter", "wind_speed_max_p99_winter",
            "wind_calm_pct_winter", "wind_dir_winter_mean",
            "wind_u_mean_summer", "wind_v_mean_summer",
            "wind_speed_mean_summer", "wind_speed_max_p99_summer",
            "wind_calm_pct_summer", "wind_dir_summer_mean",
        ],
    },
    {
        "name": "alan",
        "csv": "santiago_alan_viirs_2024.csv",
        "columns": [
            "alan_radiance_mean",
            "alan_radiance_median",
            "alan_radiance_sd",
            "alan_radiance_max",
            "alan_radiance_pop_weighted",
        ],
    },
    {
        "name": "sleep_context",
        "csv": "santiago_sleep_context.csv",
        "optional_layer": True,
        "columns": [
            "sleep_alan_log",
            "sleep_tropical_nights_20c",
            "sleep_summer_tmin_c",
            "sleep_exposure_index",
            "sleep_vulnerability_index",
            "sleep_context_index",
        ],
    },
    {
        "name": "greenspace_access",
        "csv": "santiago_greenspace_access.csv",
        "columns": [
            "green_osm_km2",
            "green_osm_pct",
            "green_osm_n",
            "dist_to_nearest_park_m",
            "green_area_within_300m_km2",
            "green_area_within_500m_km2",
            "green_area_within_1000m_km2",
            "green_count_within_300m",
            "green_count_within_500m",
            "green_count_within_1000m",
        ],
        "rename": {
            "green_osm_km2": "green_km2",
            "green_osm_pct": "green_pct",
            "green_osm_n": "n_green",
        },
    },
    {
        "name": "greenspace_coverage",
        "csv": "santiago_greenspace_coverage.csv",
        "columns": [
            "ndvi_mean",
            "ndvi_max",
            "evi_mean",
            "evi_max",
            "green_cover_pct_ndvi",
            "green_cover_pct_evi",
        ],
    },
    {
        "name": "greenspace_multisource",
        "csv": "santiago_greenspace_multisource.csv",
        "columns": [
            "green_total_pct",
            "tree_pct",
            "grass_pct",
            "canopy_cover_pct",
            "canopy_mean_height_m",
        ],
    },
    {
        "name": "healthcare",
        "csv": "santiago_healthcare_access.csv",
        "columns": [
            "n_total",
            "n_public_total",
            "n_private_total",
            "n_hospital",
            "n_hospital_public",
            "n_hospital_private",
            "n_clinic",
            "n_clinic_public",
            "n_clinic_private",
            "n_primary_care",
            "n_primary_care_public",
            "n_primary_care_private",
            "n_pharmacy",
            "n_laboratory",
            "n_laboratory_public",
            "n_laboratory_private",
            "n_dental",
            "n_dental_public",
            "n_dental_private",
            "n_mental_health",
            "n_mental_health_public",
            "n_mental_health_private",
            "density_per_km2",
            "n_access_grid",
            "mean_nearest_health_m",
            "median_nearest_health_m",
            "p90_nearest_health_m",
            "mean_nearest_hospital_m",
            "median_nearest_hospital_m",
            "p90_nearest_hospital_m",
            "mean_nearest_primary_care_m",
            "median_nearest_primary_care_m",
            "p90_nearest_primary_care_m",
        ],
        "optional_columns": [
            "mean_nearest_health_network_m",
            "median_nearest_health_network_m",
            "p90_nearest_health_network_m",
            "mean_nearest_hospital_network_m",
            "median_nearest_hospital_network_m",
            "p90_nearest_hospital_network_m",
            "mean_nearest_primary_care_network_m",
            "median_nearest_primary_care_network_m",
            "p90_nearest_primary_care_network_m",
        ],
        "rename": {
            "n_total": "health_n_total",
            "n_public_total": "health_n_public_total",
            "n_private_total": "health_n_private_total",
            "n_hospital": "health_n_hospital",
            "n_hospital_public": "health_n_hospital_public",
            "n_hospital_private": "health_n_hospital_private",
            "n_clinic": "health_n_clinic",
            "n_clinic_public": "health_n_clinic_public",
            "n_clinic_private": "health_n_clinic_private",
            "n_primary_care": "health_n_primary_care",
            "n_primary_care_public": "health_n_primary_care_public",
            "n_primary_care_private": "health_n_primary_care_private",
            "n_pharmacy": "health_n_pharmacy",
            "n_laboratory": "health_n_laboratory",
            "n_laboratory_public": "health_n_laboratory_public",
            "n_laboratory_private": "health_n_laboratory_private",
            "n_dental": "health_n_dental",
            "n_dental_public": "health_n_dental_public",
            "n_dental_private": "health_n_dental_private",
            "n_mental_health": "health_n_mental_health",
            "n_mental_health_public": "health_n_mental_health_public",
            "n_mental_health_private": "health_n_mental_health_private",
            "density_per_km2": "health_density_per_km2",
            "n_access_grid": "health_n_access_grid",
        },
    },
    {
        "name": "demography",
        "csv": "santiago_demography.csv",
        "columns": [
            "comuna_code",
            "pop_total",
            "pop_male",
            "pop_female",
            "pop_0_14",
            "pop_15_64",
            "pop_65_plus",
            "pct_pop_0_14",
            "pct_pop_15_64",
            "pct_pop_65_plus",
        ],
        "rename": {
            "pop_total": "demo_pop_total",
            "pop_male": "demo_pop_male",
            "pop_female": "demo_pop_female",
            "pop_0_14": "demo_pop_0_14",
            "pop_15_64": "demo_pop_15_64",
            "pop_65_plus": "demo_pop_65_plus",
            "pct_pop_0_14": "demo_pct_pop_0_14",
            "pct_pop_15_64": "demo_pct_pop_15_64",
            "pct_pop_65_plus": "demo_pct_pop_65_plus",
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
    {
        "name": "precipitation",
        "csv": "santiago_precipitation_chirps_2015_2024.csv",
        "columns": [
            "precip_annual_mean_mm",
            "precip_annual_sd_mm",
            "precip_annual_cv",
            "precip_wet_days",
            "precip_wet_day_pct",
            "precip_heavy_days_10mm",
            "precip_very_heavy_days_20mm",
            "precip_rx1day_mm",
            "precip_rx5day_mm",
            "precip_cdd_days",
            "precip_cwd_days",
            "precip_intensity_wet_day_mm",
            "precip_winter_mean_mm",
            "precip_summer_mean_mm",
            "precip_latest_year_mm",
            "precip_latest_anomaly_mm",
            "precip_latest_anomaly_pct",
            "precip_extremes_index",
            "precip_n_years",
            "precip_n_days",
        ],
    },
    {
        "name": "precipitation_spi",
        "csv": "santiago_precipitation_spi.csv",
        "columns": [
            "drought_months_pct",
            "drought_severe_months_pct",
            "drought_max_duration_months",
            "precip_trend_mm_per_decade",
            "spi_12_latest",
            "spi_3_mean",
            "spi_3_std",
            "spi_6_mean",
            "spi_12_mean",
        ],
    },
    {
        "name": "climate_openmeteo",
        "csv": "santiago_climate_metrics_annual.csv",
        "columns": [
            "tmean_annual",
            "tmax_mean_annual",
            "tmin_mean_annual",
            "tmean_summer",
            "tmax_mean_summer",
            "tmin_mean_summer",
            "tmean_winter",
            "tmax_mean_winter",
            "tmin_mean_winter",
            "hot_days_30c",
            "hot_days_35c",
            "tropical_nights_20c",
            "frost_days",
            "heat_wave_days",
            "cold_spell_days",
            "dtr_mean",
            "dtr_p95",
            "temp_monthly_sd",
            "seasonal_amplitude",
            "cdd_18",
            "hdd_10",
            "ehdd",
            "tmax_p95",
            "tmin_p05",
        ],
        "rename": {
            "tmean_annual": "om_tmean_annual_c",
            "tmax_mean_annual": "om_tmax_mean_annual_c",
            "tmin_mean_annual": "om_tmin_mean_annual_c",
            "tmean_summer": "om_tmean_summer_c",
            "tmax_mean_summer": "om_tmax_mean_summer_c",
            "tmin_mean_summer": "om_tmin_mean_summer_c",
            "tmean_winter": "om_tmean_winter_c",
            "tmax_mean_winter": "om_tmax_mean_winter_c",
            "tmin_mean_winter": "om_tmin_mean_winter_c",
            "hot_days_30c": "om_hot_days_30c",
            "hot_days_35c": "om_hot_days_35c",
            "tropical_nights_20c": "om_tropical_nights_20c",
            "frost_days": "om_frost_days",
            "heat_wave_days": "om_heat_wave_days",
            "cold_spell_days": "om_cold_spell_days",
            "dtr_mean": "om_dtr_mean_c",
            "dtr_p95": "om_dtr_p95_c",
            "temp_monthly_sd": "om_temp_monthly_sd",
            "seasonal_amplitude": "om_seasonal_amplitude_c",
            "cdd_18": "om_cdd_18",
            "hdd_10": "om_hdd_10",
            "ehdd": "om_ehdd",
            "tmax_p95": "om_tmax_p95_c",
            "tmin_p05": "om_tmin_p05_c",
        },
    },
    {
        "name": "wildfire",
        "csv": "santiago_wildfire_2015_2024.csv",
        "geojson": "santiago_wildfire_2015_2024.geojson",
        "columns": [
            "fire_burned_area_km2_total",
            "fire_burned_area_mean_annual_km2",
            "fire_burned_pct_mean_annual",
            "fire_burned_pct_max_year",
            "fire_burn_years_count",
            "fire_worst_year",
            "fire_trend_km2_per_decade",
            "fire_detections_total",
            "fire_detections_per_km2",
            "fire_detections_max_year",
            "fire_brightness_max_k",
            "fire_exposure_index",
        ],
        "optional_columns": [
            "fire_official_n_fires",
            "fire_official_damaged_ha",
            "fire_official_human_cause_pct",
        ],
    },
    {
        "name": "noise",
        "csv": "santiago_noise_mma_2023.csv",
        "geojson": "santiago_noise_mma_2023.geojson",
        "optional_layer": True,
        "columns": [
            "noise_ld_pop_exposed",
            "noise_ld_pct_exposed",
            "noise_ln_pop_exposed",
            "noise_ln_pct_exposed",
            "noise_combined_pct",
            "noise_in_gsu_map",
        ],
    },
    {
        "name": "walkability",
        "csv": "santiago_walkability.csv",
        "geojson": "santiago_walkability.geojson",
        "optional_layer": True,
        "columns": [
            "walk_intersection_density",
            "walk_street_density_km_km2",
            "walk_avg_street_length_m",
            "walk_streets_per_node",
            "walk_circuity",
            "walk_n_nodes",
            "walk_index",
        ],
    },
    {
        "name": "public_transport",
        "csv": "santiago_public_transport.csv",
        "geojson": "santiago_public_transport.geojson",
        "optional_layer": True,
        "columns": [
            "transit_n_bus_stops",
            "transit_n_metro_stations",
            "transit_n_rail_stations",
            "transit_bus_density",
            "transit_metro_density",
            "transit_mean_dist_bus_m",
            "transit_p90_dist_bus_m",
            "transit_bus_coverage_300m",
            "transit_bus_coverage_500m",
            "transit_mean_dist_metro_m",
            "transit_metro_coverage_1000m",
            "transit_has_metro",
            "transit_index",
        ],
    },
    {
        "name": "social_infrastructure",
        "csv": "santiago_social_infrastructure.csv",
        "geojson": "santiago_social_infrastructure.geojson",
        "optional_layer": True,
        "columns": [
            "social_n_total",
            "social_n_library",
            "social_n_cultural",
            "social_n_community",
            "social_n_senior",
            "social_n_sports",
            "social_n_public_space",
            "social_category_diversity",
            "social_density_per_km2",
            "social_points_per_10k",
            "social_mean_nearest_m",
            "social_median_nearest_m",
            "social_p90_nearest_m",
            "social_coverage_500m",
            "social_coverage_1000m",
            "social_n_access_grid",
            "social_index",
        ],
    },
    {
        "name": "food_environment",
        "csv": "santiago_food_environment.csv",
        "geojson": "santiago_food_environment.geojson",
        "optional_layer": True,
        "columns": [
            "food_n_supermarket",
            "food_n_greengrocer",
            "food_n_marketplace",
            "food_n_fastfood",
            "food_n_convenience",
            "food_n_healthy",
            "food_n_unhealthy",
            "food_healthy_density",
            "food_unhealthy_density",
            "food_mrfei",
            "food_swamp_ratio",
            "food_mean_dist_supermarket_m",
            "food_index",
        ],
    },
    {
        # CASEN 2020/2022 small-area estimates of moderate-severe food
        # insecurity (household experience, FIES/Rasch). Complements, does
        # not replace, the OSM-based food_environment supply-side layer.
        "name": "food_insecurity",
        "csv": "santiago_food_insecurity.csv",
        "geojson": "santiago_food_insecurity.geojson",
        "optional_layer": True,
        "columns": [
            "food_insec_2020",
            "food_insec_ci_low_2020",
            "food_insec_ci_high_2020",
            "food_insec_sae_type_2020",
            "food_insec_2022",
            "food_insec_ci_low_2022",
            "food_insec_ci_high_2022",
            "food_insec_sae_type_2022",
            "food_insec_change",
        ],
    },
    {
        # Per-year heat metrics 2015-2023 built with the same canonical
        # pipeline as climate_heat (scripts/run_climate_heat_annual.py).
        # 2024 is not suffixed: the climate_heat layer above carries it.
        # Feeds the webapp year slider (palette.json year_columns).
        "name": "climate_heat_by_year",
        "csv": "santiago_climate_heat_by_year.csv",
        "optional_layer": True,
        "columns": [
            f"{metric}_{year}"
            for metric in ("summer_tmax_mean_c", "hot_days_30c", "tropical_nights_20c")
            for year in range(2015, 2024)
        ],
    },
    {
        # Per-year CHIRPS rainfall 2015-2024 (scripts/run_precipitation_annual.py).
        # The canonical precipitation layer's chronic metrics are the
        # multi-year means of these columns. Feeds the webapp year slider.
        "name": "precipitation_by_year",
        "csv": "santiago_precipitation_by_year.csv",
        "optional_layer": True,
        "columns": [
            f"{stem}_{year}"
            for stem in ("precip_annual_mm", "precip_cdd_days", "precip_heavy_days_10mm")
            for year in range(2015, 2025)
        ],
    },
    {
        # Official MDSF small-area estimates (SAE) of income and
        # multidimensional poverty, 2017-2024. Not comparable across years
        # (see docs/pobreza_sae_methodology.md); also feeds the corrected
        # pobreza_pct/pobreza_multi_pct in the socioeconomic layer.
        "name": "pobreza_sae",
        "csv": "santiago_pobreza_sae.csv",
        "geojson": "santiago_pobreza_sae.geojson",
        "optional_layer": True,
        "columns": [
            "pobreza_ing_2017", "pobreza_ing_ci_low_2017", "pobreza_ing_ci_high_2017", "pobreza_ing_sae_type_2017",
            "pobreza_ing_2020", "pobreza_ing_ci_low_2020", "pobreza_ing_ci_high_2020", "pobreza_ing_sae_type_2020",
            "pobreza_ing_2022", "pobreza_ing_ci_low_2022", "pobreza_ing_ci_high_2022", "pobreza_ing_sae_type_2022",
            "pobreza_ing_2024", "pobreza_ing_ci_low_2024", "pobreza_ing_ci_high_2024", "pobreza_ing_sae_type_2024",
            "pobreza_ing_change_2017_2022",
            "pobreza_multi_2017", "pobreza_multi_ci_low_2017", "pobreza_multi_ci_high_2017", "pobreza_multi_sae_type_2017",
            "pobreza_multi_2022", "pobreza_multi_ci_low_2022", "pobreza_multi_ci_high_2022", "pobreza_multi_sae_type_2022",
            "pobreza_multi_2024", "pobreza_multi_ci_low_2024", "pobreza_multi_ci_high_2024", "pobreza_multi_sae_type_2024",
            "pobreza_multi_change_2017_2024",
        ],
    },
]


def load_layer(spec: dict) -> pd.DataFrame | None:
    path = DATA_DIR / spec["csv"]
    if not path.exists():
        if spec.get("optional_layer"):
            print(f"Skipping optional layer {spec['name']}: missing {path.name}")
            return None
        raise FileNotFoundError(f"Missing layer CSV: {path.name}")

    df = pd.read_csv(path)
    required = ["name", *spec["columns"]]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")

    # Optional columns are included when present (e.g. network distances).
    optional = [col for col in spec.get("optional_columns", []) if col in df.columns]
    out = df[required + optional].copy()
    out = out.rename(columns=spec.get("rename", {}))
    return out


def build_master(
    city: str = "santiago",
    base_geojson: Path | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the master exposome table for the given city.

    Parameters
    ----------
    city : str
        City config name (e.g. "santiago"). The expected number of
        spatial units (communes, zip codes, etc.) is read from
        ``expected_communes`` in ``config/cities/<city>.yaml``.
    base_geojson : Path | None
        Override the base GeoJSON used to provide geometries. If
        None, the function looks for ``socioeconomic_exposome_rm_<city>.geojson``
        first, then ``climate_heat_exposome_rm_<city>.geojson`` as
        a fallback. The same key is used to provide the geometry
        for any city-level spatial unit (communes, zip codes).

    Notes
    -----
    The master builder is **unit-agnostic**: it does not assume
    "commune" semantics anywhere. The 52-row hardcoded check was
    replaced with a config-driven ``expected_communes`` so the
    same script can build a master for zip codes (typically
    1000-3000 units in Santiago RM).
    """
    from exposome import config as exposome_config

    cfg = exposome_config.load_config(city)
    expected_n = int(cfg.get("expected_communes", 52))

    if base_geojson is None:
        base_geojson = DATA_DIR / f"socioeconomic_exposome_rm_{city}.geojson"
        if not base_geojson.exists():
            base_geojson = DATA_DIR / f"climate_heat_exposome_rm_{city}.geojson"
    if base_geojson is None or not Path(base_geojson).exists():
        raise FileNotFoundError(
            f"Need a local GeoJSON layer to provide geometries for {city!r}"
        )

    gdf = gpd.read_file(base_geojson)
    if "area_km2" not in gdf.columns:
        metric = gdf.to_crs("EPSG:32719")
        gdf["area_km2"] = metric.geometry.area / 1e6
    gdf = gdf[["name", "area_km2", "geometry"]].drop_duplicates("name").copy()
    gdf["area_km2"] = gdf["area_km2"].round(2)

    master = pd.DataFrame(gdf.drop(columns="geometry"))
    for spec in LAYER_SPECS:
        layer = load_layer(spec)
        if layer is None:
            continue
        master = master.merge(layer, on="name", how="left", validate="one_to_one")

    # Derived health-accessibility ratios using demography.
    if "demo_pop_total" in master.columns:
        pop = master["demo_pop_total"]
        ratio_pairs = [
            ("demo_pop_total", "health_n_hospital", "health_inhabitants_per_hospital"),
            ("demo_pop_total", "health_n_primary_care", "health_inhabitants_per_primary_care"),
            ("demo_pop_total", "health_n_clinic", "health_inhabitants_per_clinic"),
            ("demo_pop_total", "health_n_public_total", "health_inhabitants_per_public_facility"),
            ("demo_pop_total", "health_n_private_total", "health_inhabitants_per_private_facility"),
            ("demo_pop_total", "health_n_total", "health_inhabitants_per_facility"),
        ]
        for _, facility_col, out_col in ratio_pairs:
            if facility_col in master.columns:
                master[out_col] = np.where(
                    master[facility_col] > 0,
                    (pop / master[facility_col]).round(1),
                    np.nan,
                )

    if len(master) != expected_n:
        raise ValueError(
            f"Expected {expected_n} spatial units for {city!r}, "
            f"got {len(master)}"
        )
    if master["name"].duplicated().any():
        dupes = master.loc[master["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    # Ratios such as inhabitants_per_hospital are undefined when a commune
    # has zero facilities of that type. Those NaNs are meaningful, so we
    # exclude ratio columns from the strict non-null check. Likewise, a
    # handful of pobreza_sae confidence-interval cells are genuinely absent
    # from the source workbook for synthetic-only estimates (e.g. Vitacura,
    # income 2017 -- see src/exposome/pobreza_sae.py).
    _known_source_gaps = {"pobreza_ing_ci_low_2017", "pobreza_ing_ci_high_2017"}
    non_ratio_cols = [
        c for c in master.columns if "_per_" not in c and c not in _known_source_gaps
    ]
    if master[non_ratio_cols].isna().any().any():
        missing = master.columns[master.isna().any()].tolist()
        raise ValueError(f"Master table has missing values in: {missing}")

    gdf_master = gdf[["name", "geometry"]].merge(master, on="name", how="right", validate="one_to_one")
    gdf_master = gdf_master.set_geometry("geometry")
    return master.sort_values("name").reset_index(drop=True), gdf_master.sort_values("name").reset_index(drop=True)


def main() -> None:
    master, gdf_master = build_master(city="santiago")

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
