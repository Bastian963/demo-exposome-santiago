# Climate data sources — Open-Meteo vs. ERA5-Land

This note documents the two historical climate pipelines available for the
Santiago exposome, and why we are currently using ERA5-Land as the primary
source.

## Open-Meteo (option A)

**What it is:** Free REST API that provides historical reanalysis data at
~11 km resolution, including daily max/min/mean temperature, apparent
temperature, and precipitation.

**Pros:**
- Fast for single-year / single-location queries.
- No GEE credentials required.
- Higher effective spatial resolution than ERA5-Land for point queries.

**Cons:**
- Aggressive rate limiting when querying many locations/years in a loop.
- 429 errors become persistent and can block the pipeline for tens of minutes.
- Requires careful retry/back-off logic.

**When to use:** Best for small pilots, single-city single-year demos, or when
GEE authentication is not available. Once Open-Meteo lifts its rate limit for
your IP, re-running `scripts/run_climate_openmeteo.py` will resume from cache
and complete the full 2015–2024 period.

**How to retry later:**

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_climate_openmeteo.py
```

The module caches per-commune files in `cache/openmeteo_<commune>_<start>_<end>.csv`,
so interrupted runs can be resumed safely.

## ERA5-Land via GEE (option B, current default)

**What it is:** ECMWF ERA5-Land daily aggregates extracted server-side from
Google Earth Engine at ~11.1 km resolution.

**Pros:**
- Reliable for bulk historical extractions.
- No 429-style rate limits from Open-Meteo.
- Native daily min/max/mean temperature and dewpoint.

**Cons:**
- Slower per call than a single Open-Meteo request.
- Requires GEE authentication and project `exposome-api`.
- Slightly coarser spatial resolution.

**How to run:**

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_climate_fetch.py
```

## Recommended workflow

1. **Production / multi-year:** use `scripts/run_climate_fetch.py` (ERA5-Land).
2. **Validation / quick checks:** use `scripts/run_climate_openmeteo.py` for a
   single year once rate limits allow.
3. **Cross-check:** compare annual summaries from both sources for 2024 to
   quantify local bias before downscaling.
