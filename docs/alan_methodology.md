# Artificial light at night (ALAN) — VIIRS Day/Night Band

This note documents the ALAN exposome layer: annual outdoor night-time
radiance from VIIRS Day/Night Band. The commune value is a derived zonal
summary; when a verified native COG is published, the map shows the original
VIIRS pixel grid clipped by the study AOI rather than a value repeated per
commune.

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
product). Band `avg_rad` reports average radiance in **nW/cm²/sr**; its native
grid is **15 arc-seconds** (nominal GEE scale **463.83 m** at the equator).
The companion band `cf_cvg` gives the number of cloud-free observations per
pixel. The grid definition — CRS and affine transform — is part of the
published provenance; a rounded "500 m" export is not accepted as equivalent.

**Why it:** No additional credentials beyond the GEE project already used by the
air-quality and green-coverage layers; current coverage (the annual composite
products lag further behind); and the same `col.mean()` annual-aggregation
pattern as `fetch_no2` in `src/exposome/air_quality.py`.

## Method

Implemented in `src/exposome/alan.py` (config block `alan:` in
`config/cities/santiago.yaml`), mirroring the air-quality pipeline:

1. **Annual radiance image.** Filter VCMSLCFG from `2024-01-01` to the exclusive
   upper bound `2025-01-01`, mask pixels with `cf_cvg == 0` (no cloud-free
   observation that month), average the monthly composites with `col.mean()`,
   and clamp negative radiance (sensor noise over dark areas) to zero.
2. **Zonal statistics** over the 52 communes (`gee.image_to_stats`, using the
   canonical 463.83 m nominal scale):
   - `alan_radiance_mean` — area-mean radiance.
   - `alan_radiance_median` — robust to a few very bright pixels.
   - `alan_radiance_sd` — within-commune heterogeneity.
   - `alan_radiance_max` — brightest pixel (peak exposure).
3. **Population-weighted mean** `alan_radiance_pop_weighted` = Σ(rad·pop)/Σ(pop)
   using the WorldPop 100 m unconstrained raster (Chile, 2020) as weights. This
   is the **primary human-exposure metric** used downstream in the master figure
   and in `sleep_context` because it emphasizes light *where people live*.
   Computed as two zonal sums; falls back to `alan_radiance_mean` for any commune
   the population raster does not cover.
4. **Spatial publication.** The native companion Study exports `avg_rad` on
   VIIRS's 15 arc-second grid. It is converted once to a Web Mercator COG with
   nearest-neighbour transport; the storage grid never changes the scientific
   support. Commune polygons only mask the AOI and derive the summaries.
5. **Strict validation** (52 rows, no duplicate names, no missing values), then
   export `data/processed/santiago_alan_viirs_2024.{csv,geojson}` plus a
   `_metadata.json` following the canonical schema.

## How to run

```bash
uv sync --all-extras
exposome run --study santiago_communes --layers alan --resume
# The human runs the remote native collection:
exposome run --study santiago_native --layers alan --resume
# Local publication after the native output exists:
exposome detail --study santiago_communes --indicators alan
```

GEE pulls use cache identities that include collection, band, cloud-free mask,
period, scale, population source and spatial fingerprint. Changing any of those
parameters creates a new cache entry instead of silently reusing a 500 m output.

## Limitations

- **Spatial blooming / atmospheric scattering** inflate radiance around bright
  sources, so values are a relative exposure proxy rather than ground-level
  illuminance.
- **15 arc-second resolution** is coarser than within-commune variation; the median and
  population-weighted metrics mitigate this but cannot remove it.
- **No spectral information**: VIIRS DNB cannot isolate the blue-light fraction
  most relevant to melatonin suppression (modern LED lighting).
- **Overpass timing** is ~01:30 local; it captures steady-state lighting, not
  evening exposure when people are awake.
- **Temporal comparability**: radiance levels are sensitive to the VIIRS product
  version and to LED retrofits over time; treat cross-year comparisons with care.
