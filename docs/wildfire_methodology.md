# Wildfire Exposome Layer — MODIS Burned Area + FIRMS

## Why wildfire ("climate disasters" factor)

The exposome already captures the *continuous* climate hazards — heat waves and
cold spells (`climate_heat`, `climate_openmeteo`), drought (`precipitation_spi`,
SPI-3/6/12) and extreme precipitation (`precipitation`). The remaining gap is the
dominant *discrete* climate disaster of the Santiago Metropolitan Region:
**forest fires**, with catastrophic seasons in 2017, 2023 and 2024.

Wildfire is an exploratory environmental exposure for later brain-exposome
analyses. Plausible pathways are indirect: wildfire **smoke** drives acute
PM2.5/PM10 spikes (neuroinflammation, oxidative stress, accelerated cognitive
decline — complementing the air-quality layer), and recurrent fire brings chronic
stress, evacuation/displacement and loss of green space. This layer does not model
cognition, dementia, biomarkers or neuroimaging outcomes directly.

## Data sources

Two satellite products via Google Earth Engine (no extra API key beyond the GEE
project), plus an optional official enrichment:

| Source | Dataset | Provider | Resolution | Role |
|---|---|---|---|---|
| Burned area | `MODIS/061/MCD64A1` (band `BurnDate`) | NASA LP DAAC / MODIS | 500 m, monthly | Spatial *extent* of fire (area burned) |
| Active fire | `FIRMS` (band `T21`) | NASA FIRMS (MODIS + VIIRS) | ~1 km, daily | Fire *activity* / interface fires |
| Official (optional) | CONAF / itrend by commune | CONAF / itrend | commune | Fire count, cause, damaged ha |

- **Period:** 2015-2024 for the Santiago demo (matches the other climate layers).
- `BurnDate > 0` marks a burned pixel; it is used only as a burned/not-burned mask.
- FIRMS `T21` is the fire-pixel brightness temperature (K); non-fire pixels are masked.

## Pipeline

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_wildfire.py
python scripts/build_master_exposome.py
```

The extraction runs **year by year** to keep Earth Engine responses small, caches
the per-commune/per-year metrics under
`cache/santiago_wildfire_annual_2015_2024.csv` (safe to interrupt — only missing
years are re-fetched), and writes:

- `data/processed/santiago_wildfire_2015_2024.csv`
- `data/processed/santiago_wildfire_2015_2024.geojson`
- `data/processed/santiago_wildfire_2015_2024_metadata.json`

### Zonal computation

- **Burned area (km²):** for each year, the burned mask (`BurnDate > 0`) is
  multiplied by `ee.Image.pixelArea()` and summed per commune (`reduceRegions`,
  `sum`, scale 500 m).
- **FIRMS detections:** each daily image is reduced to a binary detection mask,
  summed over the year per pixel (detection-days), then summed per commune
  (`reduceRegions`, `sum`, scale 1 km).
- **Brightness:** annual max of `T21` per commune (`reduceRegions`, `max`),
  reported as an intensity proxy (0 = no detection).

## Metrics (columns)

| Column | Description |
|---|---|
| `fire_burned_area_km2_total` | Cumulative burned area over the period (km²) |
| `fire_burned_area_mean_annual_km2` | Mean annual burned area (km²) |
| `fire_burned_pct_mean_annual` | Mean annual burned area as % of commune area |
| `fire_burned_pct_max_year` | Worst single-year burned fraction (%) |
| `fire_burn_years_count` | Years (of 10) with a burn > 0.01 km² (recurrence) |
| `fire_detections_total` | Total FIRMS detection-days over the period |
| `fire_detections_per_km2` | FIRMS detection-days per km² (size-comparable) |
| `fire_detections_max_year` | FIRMS detection-days in the worst year |
| `fire_brightness_max_k` | Max FIRMS T21 brightness temperature (K); 0 = no detection |
| `fire_exposure_index` | Composite wildfire exposure index (0-100) |

Optional official columns (present only when a CONAF/itrend CSV is supplied):
`fire_official_n_fires`, `fire_official_damaged_ha`, `fire_official_human_cause_pct`.

## Composite exposure index (0-100)

A weighted average of three sqrt-normalised components (max commune = 100 per
component), configured under `wildfire.index_weights`:

```
fire_exposure_index = 0.4 · norm(burned_pct_mean_annual)
                    + 0.4 · norm(detections_per_km2)
                    + 0.2 · (burn_years_count / n_years · 100)
```

The `sqrt` transform moderates the heavy right-skew (a few rural/cordillera
communes dominate) before max-scaling. Densely built urban communes are near-zero
by design, which is the correct ecological reading.

## Optional official enrichment (CONAF / itrend)

The public itrend endpoint is an HTML landing page (no direct CSV) and the CONAF
"ocurrencia y daño por comuna 1985-2024" is distributed via the Centro Documental,
so official statistics are **opt-in**: drop a CSV at the path in
`wildfire.official.path` (default `data/raw/conaf_incendios_comuna.csv`) and adjust
the column mapping in the config. Commune names are harmonised with
`demography.normalize_comuna_name()`. When the file is absent the layer is built
from satellite alone, so reproducibility never depends on it.

Sources to obtain the file:
- CONAF — Estadísticas históricas (Centro Documental): "Resumen de ocurrencia y
  daño por comuna, 1985-2024".
- itrend / Plataforma de Datos: "Registro histórico de incendios forestales"
  (2002-2020), event-level with region/province/commune.

## Limitations

- **MCD64A1 at 500 m underestimates small and urban fires**; FIRMS complements it
  for wildland-urban interface fires that the burned-area product misses.
- Burned area in dense urban communes is near-zero (little burnable land) — a
  feature, not a bug.
- The optional official record (itrend) ends in 2020 and does not cover the
  2023/2024 megafire seasons; the satellite metrics (2015-2024) do.
- Ecological (commune-level) indicator, not individual exposure.
