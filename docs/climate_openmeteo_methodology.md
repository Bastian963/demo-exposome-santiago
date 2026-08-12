# Methodology of the `climate_openmeteo` layer — Annual climate metrics (Santiago)

## Purpose

Provide a **comprehensive set of annual and seasonal climate
metrics** per commune in the Region Metropolitana de Santiago,
derived from the Open-Meteo Historical Weather API daily archive
(2024). This layer is the **Open-Meteo counterpart** to the
`climate_heat` layer (which uses both Open-Meteo and ERA5-Land);
it is delivered as a **separate, non-redundant layer** with the
`om_` prefix on all columns.

The metrics target **climate-exposure characterization** for the
urban exposome and brain-aging research. They are **not
strictly the heat-exposure** pillar; the broader set includes
diurnal range, frost days, tropical nights, heating/cooling
degree days, and seasonal amplitudes.

## Source

- **Provider:** Open-Meteo Historical Weather API
  (`https://archive-api.open-meteo.com/v1/archive`).
- **Model:** `best_match` (default), or `era5_land` (alternative).
- **Daily variables fetched:**
  - `temperature_2m_max`, `temperature_2m_min`,
    `temperature_2m_mean`, `apparent_temperature_max`,
    `precipitation_sum`.
- **Spatial resolution:** ~11 km per point (Open-Meteo
  pre-aggregated cells). One representative point per commune.
- **Temporal scope:** **2024 only** (the canonical
  climate_openmeteo CSV uses a single year, 19,032 rows = 52
  communes × 366 days).
- **Cache-first:** `scripts/run_climate_metrics.py` reuses the
  daily archive `data/processed/santiago_climate_openmeteo_daily_2024_2024.csv`
  when present; only re-fetches if the cache is missing.

## Why 2024-only scope

The `climate_heat` layer is **2024-only** (matching the rest of
the master, which is a 2024 cross-section). The
`climate_openmeteo` layer is **deliberately aligned** with
`climate_heat` to avoid a **temporal mismatch** in the master
and to keep the **two climate layers (`climate_heat` and
`climate_openmeteo`) strictly complementary**:

- `climate_heat` → 12 heat-stress-focused columns + 2 composite
  indices (`heat_exposure_index`, `urban_heat_anomaly_c`).
- `climate_openmeteo` → 30 broader annual/seasonal climate
  metrics with the `om_` prefix.

A wider 2015-2024 daily archive is available
(`data/processed/santiago_climate_era5land_daily_<YEAR>_<YEAR>.csv`)
but is **not used** by the canonical climate_openmeteo layer to
preserve byte-exact reproducibility with the rest of the master.

## Outputs

- `data/processed/santiago_climate_metrics_annual.csv` (52 rows
  × 31 columns).
- `data/processed/santiago_climate_metrics_annual.geojson`.
- `data/processed/santiago_climate_metrics_annual_metadata.json`.

After integration into the master, the columns are renamed with
the `om_` prefix (24 columns in the master).

## Metrics computed

The following annual and seasonal aggregates are computed by
`src/exposome/climate/metrics.py:calculate_climate_metrics()`:

### Annual mean temperatures
- `tmean_annual`, `tmax_mean_annual`, `tmin_mean_annual`

### Seasonal mean temperatures (Dec-Jan-Feb = summer;
   Jun-Jul-Aug = winter; Mar-Apr-May = autumn;
   Sep-Oct-Nov = spring)
- `tmean_summer`, `tmax_mean_summer`, `tmin_mean_summer`
- `tmean_winter`, `tmax_mean_winter`, `tmin_mean_winter`
- `tmean_autumn`, `tmax_mean_autumn`, `tmin_mean_autumn`
- `tmean_spring`, `tmax_mean_spring`, `tmin_mean_spring`

### Heat/cold exposure counts
- `hot_days_30c` — annual count of days with Tmax > 30 °C
- `hot_days_35c` — annual count of days with Tmax > 35 °C
- `tropical_nights_20c` — annual count of nights with Tmin > 20 °C
- `frost_days` — annual count of days with Tmin < 0 °C
- `heat_wave_days` — annual count of days inside a heat-wave
  (≥ 2 consecutive days with Tmax > p90 of the local reference
  period; default p90 of 2024)
- `cold_spell_days` — annual count of days inside a cold spell
  (≥ 2 consecutive days with Tmin < p10)

### Variability metrics
- `dtr_mean` — mean diurnal temperature range (Tmax − Tmin)
- `dtr_p95` — 95th-percentile DTR (within-year)
- `temp_monthly_sd` — standard deviation of monthly mean
  temperatures (seasonal-cycle amplitude proxy)
- `seasonal_amplitude` — max(monthly mean) − min(monthly mean)

### Threshold-based degree days
- `cdd_18` — cooling degree days (base 18 °C; sum of max(0,
  Tmean − 18) per day)
- `hdd_10` — heating degree days (base 10 °C; sum of max(0,
  10 − Tmean) per day)
- `ehdd` — extreme heating degree days (sum of max(0,
  18 − Tmean) per day; flags cold-stress)

### Extreme percentiles
- `tmax_p95` — 95th percentile of daily Tmax
- `tmin_p05` — 5th percentile of daily Tmin

## Reproducibility

- **Determinism:** the daily archive is fetched once and cached;
  the aggregation to annual metrics is purely deterministic
  (no random sampling).
- **Re-run:** `python scripts/run_climate_metrics.py --daily-csv
  data/processed/santiago_climate_openmeteo_daily_2024_2024.csv`.
- **Cache-only mode:** `--cache-only` flag forces no-network.
- **Pre-processed outputs:** byte-deterministic given the same
  daily archive.

## Relationship with `climate_heat`

| Property | `climate_heat` | `climate_openmeteo` |
|---|---|---|
| Source | ERA5-Land Daily Aggregated | Open-Meteo only |
| Default | ERA5-Land native pixels | Open-Meteo (`best_match`) |
| Temporal scope | 2024 master; annual products 2015–2024 | 2024 |
| Spatial scope | Native pixels, then area-weighted polygon intersection | Representative point per unit |
| Columns in master | 14 (heat-focused) | 24 (broad climate) |
| Composite indices | `heat_exposure_index`, `urban_heat_anomaly_c` | none |
| Cache | `<study>_era5land_grid_<YEAR>.csv` | `data/processed/santiago_climate_openmeteo_daily_<YEAR>_<YEAR>.csv` |
| Purpose | Heat stress characterization | Full climate profile |

The two layers are **complementary, not redundant**: `climate_heat` uses
ERA5-Land native pixels and computes heat-pillar indices, while
`climate_openmeteo` preserves a separate representative-point climate profile.
They do not share a canonical daily archive.

## Limitations

1. **Single-year scope (2024).** Multi-year metrics (climate
   normals, decadal trends) are not computed at the layer
   level; long-term Mann-Kendall trends are reported separately
   in `data/processed/time_series_trends.csv` (4 variables).
2. **Representative-point bias.** For each commune, we use a
   single representative point (typically the centroid or the
   most urbanized sub-area). This biases the metric toward the
   urban core for the 24 dense urban communes (24/52) where
   the Open-Meteo cell may not span the full commune area.
   The `climate_heat` layer documents this same bias in
   `docs/climate_heat_methodology.md`.
3. **No spatial downscaling.** The 11 km Open-Meteo cell is
   aggregated to a single point; the methodology does not
   downscale to the commune polygon. A pixel-zonal
   aggregation (1 km or finer) would be a v2.0 feature
   (requires `aggregate_predictions_to_postal_codes()` in
   `src/exposome/zipcodes.py:66`).
4. **No co-variate adjustment.** The metrics are raw climate
   exposures; they do not adjust for population, age structure,
   or adaptation (AC usage, green space). Joint analysis with
   `demography` and `greenspace_coverage` is the recommended
   way to operationalize exposure for brain-aging research.
5. **Open-Meteo model uncertainty.** Open-Meteo archives blend
   reanalysis with station data; for Santiago the
   `best_match` model has known cool bias in Tmax (compared to
   ERA5-Land). The `climate_heat` layer documents an ERA5 vs
   Open-Meteo bias of -1.4 to -3.8 °C in Tmax; the
   `climate_openmeteo` layer inherits this bias.

## Brain-health relevance

The 30 metrics cover the **heat-exposure, cold-exposure, and
variability** axes that the Lancet Commission on Dementia
Prevention (Livingston et al., 2024) lists as modifiable
environmental risk factors. Specifically:

- **Heat** (Tmax, hot days, tropical nights, heat waves, CDD) →
  dehydration, sleep disruption, cardiovascular stress.
- **Cold** (Tmin, frost days, cold spells, EHDD) →
  cardiovascular stress, indoor confinement, vitamin D
  deficiency.
- **Variability** (DTR, monthly SD, seasonal amplitude) →
  thermoregulation load on the autonomic nervous system.
- **Extreme percentiles** (Tmax p95, Tmin p05) → acute-event
  exposure.

In the cross-layer analysis, the climate_openmeteo metrics
supplement the heat-pillar (climate_heat) and feed the
**EBI-PCA** and the **time-series trends** (4 climate variables).

## Reproducibility checklist

- [x] Cache-first re-run (`scripts/run_climate_metrics.py`).
- [x] Deterministic output (no random seeds).
- [x] 52 communes, 31 columns (24 with `om_` prefix in master).
- [x] Integration into master verified.
- [x] 2024-only scope documented and aligned with `climate_heat`.
- [x] Limitations explicitly stated (representative-point bias,
  no downscaling, Open-Meteo model uncertainty).
- [x] Tests in `tests/test_climate_openmeteo.py` (covered in
  master integration tests).
