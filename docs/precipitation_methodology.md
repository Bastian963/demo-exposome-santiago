# Precipitation Exposome Layer — CHIRPS

## Why precipitation

Precipitation is included as an exploratory environmental exposure for later
brain-exposome analyses. Rainfall patterns can plausibly affect brain-health
pathways indirectly through mobility, social isolation, outdoor activity,
stress, flood disruption, humidity-related housing conditions, and broader
climate vulnerability. This layer does not model cognition, dementia,
biomarkers, or neuroimaging outcomes directly.

## Data source

- **Dataset:** CHIRPS Daily (`UCSB-CHG/CHIRPS/DAILY`)
- **Provider:** UCSB Climate Hazards Center
- **Access:** Google Earth Engine
- **Native variable:** daily precipitation in millimeters
- **Approximate resolution:** 0.05 degrees, configured as `5566 m`
- **Period:** 2015-2024 for the Santiago demo

## Pipeline

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/run_precipitation.py
python scripts/plot_precipitation_maps.py
python scripts/build_master_exposome.py
```

The extraction runs month by month to keep Earth Engine responses small, caches
one CSV per year under `cache/`, and writes:

- `data/processed/santiago_precipitation_chirps_daily_2015_2024.csv`
- `data/processed/santiago_precipitation_chirps_2015_2024.csv`
- `data/processed/santiago_precipitation_chirps_2015_2024.geojson`
- `data/processed/santiago_precipitation_chirps_2015_2024.json`
- `figures/precipitation_santiago_4panel.png`

## Metrics

All metrics are computed at commune level from daily area-mean precipitation:

- chronic rainfall: annual mean, standard deviation, coefficient of variation
- wetness: wet-day count and wet-day percentage using `>=1 mm`
- heavy rainfall: days `>=10 mm` and `>=20 mm`
- extremes: mean annual RX1day, RX5day, maximum consecutive dry days, and maximum consecutive wet days
- seasonality: mean winter and summer rainfall
- surveillance: latest-year total and anomaly percentage for 2024 versus the previous-year baseline
- summary: `precip_extremes_index`, a 0-100 percentile index combining heavy-rain frequency, RX5day, dry-spell length, and absolute latest-year anomaly

## Interpretation

The precipitation columns are intended as exposure candidates in the master
exposome table. In downstream BrainLat-style analyses, they should be joined to
participant residence, cohort, cognitive, biomarker, or neuroimaging data and
modeled with appropriate covariates, spatial uncertainty checks, and sensitivity
analyses. The demo keeps this as an ecological commune-level exposure layer.

## References

- CHIRPS Daily Earth Engine Data Catalog: https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY
- Weather Woes: Exploring Potential Links between Precipitation and Age-Related Cognitive Decline: https://www.mdpi.com/1660-4601/17/23/9011
