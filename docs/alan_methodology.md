# Artificial light at night (ALAN) — VIIRS Day/Night Band

This note documents the ALAN exposome layer: commune-level outdoor night-time
light exposure for the 52 communes of Región Metropolitana, derived from the
VIIRS Day/Night Band via Google Earth Engine.

## Why ALAN, for brain health

Artificial light at night is a standard urban-exposome domain that is usually
missing from environmental datasets. Outdoor night-time light exposure is
associated with circadian-rhythm disruption, melatonin suppression and sleep
disturbance, with a growing epidemiological literature linking higher outdoor
ALAN to cognitive decline, Alzheimer's disease/dementia, depression and stroke.
It therefore complements the existing air-quality, heat and green-space layers
as a candidate correlate of brain-health biomarkers.

## Data source

**What it is:** `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` — the VIIRS Day/Night Band
monthly cloud-free composites, stray-light corrected (the `VCMSLCFG`/SLC
product). Band `avg_rad` reports average radiance in **nW/cm²/sr**; native
resolution is ~500 m (15 arc-seconds). The companion band `cf_cvg` gives the
number of cloud-free observations per pixel.

**Why it:** No additional credentials beyond the GEE project already used by the
air-quality and green-coverage layers; current coverage (the annual composite
products lag further behind); and the same `col.mean()` annual-aggregation
pattern as `fetch_no2` in `src/exposome/air_quality.py`.

## Method

Implemented in `src/exposome/alan.py` (config block `alan:` in
`config/cities/santiago.yaml`), mirroring the air-quality pipeline:

1. **Annual radiance image.** Filter VCMSLCFG to the configured year, mask pixels
   with `cf_cvg == 0` (no cloud-free observation that month), average the monthly
   composites with `col.mean()`, and clamp negative radiance (sensor noise over
   dark areas) to zero.
2. **Zonal statistics** over the 52 communes (`gee.image_to_stats`, EPSG:4326,
   `scale = 500 m`):
   - `alan_radiance_mean` — area-mean radiance (primary exposure).
   - `alan_radiance_median` — robust to a few very bright pixels.
   - `alan_radiance_sd` — within-commune heterogeneity.
   - `alan_radiance_max` — brightest pixel (peak exposure).
3. **Population-weighted mean** `alan_radiance_pop_weighted` = Σ(rad·pop)/Σ(pop)
   using the WorldPop 100 m unconstrained raster (Chile, 2020) as weights — the
   exposure-relevant metric (light *where people live*). Computed as two zonal
   sums; falls back to `alan_radiance_mean` for any commune the population raster
   does not cover (same pattern as the BLH fallback in the air-quality layer).
4. **Strict validation** (52 rows, no duplicate names, no missing values), then
   export `data/processed/santiago_alan_viirs_2024.{csv,geojson}` plus a
   `_metadata.json` following the canonical schema.

## How to run

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_alan.py
python scripts/build_master_exposome.py   # picks up the alan_* columns
```

Intermediate GEE pulls are cached in `cache/santiago_alan_radiance_2024.csv` and
`cache/santiago_alan_popweighted_2024.csv`, so re-runs are fast.

## Limitations

- **Spatial blooming / atmospheric scattering** inflate radiance around bright
  sources, so values are a relative exposure proxy rather than ground-level
  illuminance.
- **~500 m resolution** is coarser than within-commune variation; the median and
  population-weighted metrics mitigate this but cannot remove it.
- **No spectral information**: VIIRS DNB cannot isolate the blue-light fraction
  most relevant to melatonin suppression (modern LED lighting).
- **Overpass timing** is ~01:30 local; it captures steady-state lighting, not
  evening exposure when people are awake.
- **Temporal comparability**: radiance levels are sensitive to the VIIRS product
  version and to LED retrofits over time; treat cross-year comparisons with care.
