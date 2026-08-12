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

## Brain-health / exposome interpretation

The wildfire layer is **exploratory** — it does not model cognition, biomarkers
or neuroimaging outcomes. It is meant to feed future brain-exposome analyses
through the `fire_exposure_index` (composite 0-100) and the supporting
component metrics. The plausible biological pathways are:

- **Wildfire smoke → neuroinflammation.** Acute PM2.5/PM10 spikes from
  biomass burning reach the CNS via the olfactory and systemic routes;
  chronic exposure is associated with accelerated cognitive decline
  (weaker episodic memory, slower processing speed) and with
  neuroinflammatory markers. The wildfire layer **complements** the
  `pm25_pop_weighted` chronic-PM2.5 layer with the **acute** smoke
  signal; in the master, the two should be analysed together to separate
  chronic traffic/industrial PM2.5 from episodic biomass burning.
- **Recurrent fire exposure → chronic stress, HPA-axis dysregulation.**
  Repeated smoke episodes and the anticipation of the next fire season
  act as a chronic stressor. Together with displacement and
  wildland-urban-interface loss of housing, this contributes to
  sustained cortisol elevation and downstream hippocampal vulnerability
  (relevant to dementia risk).
- **Displacement and evacuation → social isolation.** Major fire seasons
  (2017, 2023, 2024) triggered evacuations in the Andean foothills.
  In the master, the natural cross is `fire_exposure_index` with the
  social-infrastructure and demographics layers, to test whether
  high-fire communes show higher social-isolation proxies in census
  data.

**Informative cross-tabulations in the master**

| Cross | Rationale |
|---|---|
| `fire_exposure_index` × `pm25_pop_weighted` | Smoke potentiates chronic PM2.5 in fire-prone communes. |
| `fire_burned_pct_max_year` × `green_cover_pct_ndvi` | Post-fire loss of green cover; the difference across years 2015-2024 is the exposed signal. |
| `fire_exposure_index` × `heat_exposure_index` | Drought + heat → flamability; the two should co-occur in the same Andean communes. |
| `fire_burn_years_count` × `precip_spi_12` | Recurrence against multi-year drought; communes with consecutive low SPI should show more burn-years. |

## Sentinel `fire_brightness_max_k = 0`

`fire_brightness_max_k` is the maximum FIRMS T21 brightness temperature
(Kelvin) observed anywhere in the commune across the 2015-2024 period.
A value of **0 K is not physically meaningful**, so `0` is reserved as
the **"no FIRMS detection" sentinel**:

- For communes without wildland-urban interface (small dense urban
  communes such as La Cisterna, San Joaquín, San Ramón in the 2024
  layer), MODIS/VIIRS never records a fire pixel, and the GEE
  `reduceRegions(max)` returns 0.
- The wildfire module does **not** coerce this sentinel to `NaN`: the
  master CSV is fully populated on this column, and downstream ratios
  (e.g. `health_inhabitants_per_*` from the demography layer) compute
  normally against the zero value.
- Non-sentinel brightness values are constrained to the physically
  plausible MODIS/VIIRS fire-pixel range (≈ 300-500 K) by construction
  (T21 is masked on the active-fire band, which only contains pixels
  already flagged as thermal anomalies by NASA FIRMS).

If a future analysis needs to distinguish "no detection" from "missing
data", filter with `df.loc[df["fire_brightness_max_k"] > 0, :]` or
join against a wildland-urban-interface mask.

## Note on the 2015 anchor

The 2015 austral summer saw a catastrophic mega-fire season in central
Chile (the Valparaiso fires of April 2015, the worst in the modern
record). For most communes in the RM, **2015 is `fire_worst_year`**: in
the canonical 2015-2024 layer, 33 of the 52 communes record 2015 as
their peak burned-area year. The metric is therefore a **calendar
anchor** more than a year of *intensity* — the OLS slope on a window
that starts with such a large anomaly is heavily leveraged by the
endpoint.

Consequences for interpretation of `fire_trend_km2_per_decade`:

- Only 10 data points — high inter-annual variability (single
  mega-seasons dominate). Statistical inference on the slope is
  underpowered.
- The trend is **sensitive to the choice of temporal window**. Removing
  2015 (a clear outlier) would push many slopes toward zero or
  negative; including 2023/2024 (the other two mega-seasons) keeps the
  slope in the same range but reverses some commune rankings. Users
  should report the window explicitly when quoting trend values, and
  treat the metric as descriptive rather than inferential.
- The 2017, 2023 and 2024 mega-seasons are listed in
  `metadata.peak_seasons` and are visible as 2015/2017/2023/2024
  clusters in the `fire_worst_year` distribution.

## Verification of the review run (opencode audit, 2026-06-29)

The cache-first re-run reproduces the canonical outputs without
invoking Google Earth Engine:

- `cache/santiago_wildfire_annual_2015_2024.csv` contains
  **520 rows** (10 years × 52 communes) of per-year
  `burned_km2`, `detections`, `brightness_max_k`.
- `python scripts/run_wildfire.py` (cache-first) wrote
  `data/processed/santiago_wildfire_2015_2024.csv` and
  `santiago_wildfire_2015_2024.geojson` **byte-identical** to the
  canonical outputs (verified by MD5); only the `_metadata.json`
  `created_utc` field changed.
- Metadata reports `n_rows=52`, `period=2015-2024`,
  `index_weights` 0.4 / 0.4 / 0.2, `peak_seasons = [2017, 2023, 2024]`
  and `limitations` non-empty. Every core column has a
  `columns_description` entry.
- `data/processed/santiago_exposome_master.csv` contains the 12 core
  `fire_*` columns and **does not** contain the 3
  `fire_official_*` columns (no CONAF/itrend CSV is present; the
  opt-in enrichment is skipped gracefully).
- `figures/wildfire_santiago_4panel.png` shows the four core metrics
  across the 52 communes (chronic load, recurrence, composite index,
  FIRMS intensity).
- `tests/test_wildfire.py` runs **10 tests** (all green) covering
  schema, metadata, distribution, sentinel handling, master
  integration, official-enrichment skip, and build-layer
  reproducibility from cache.
