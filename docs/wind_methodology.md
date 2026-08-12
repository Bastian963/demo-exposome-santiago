# Wind exposure layer (ERA5-Land 10-m wind)

Administrative-unit wind exposure derived from the **ERA5-Land hourly
reanalysis** (ECMWF) via Google Earth Engine. The layer summarizes the
**atmospheric dispersion environment** of each unit (mean wind speed,
calm-fraction, prevailing
direction) — not a pollutant. Wind modulates the **effective
exposure** to PM2.5, NO2, O3, and other airborne pollutants: low
wind + high emissions = poor ventilation = higher local dose.

## Why include wind

Atmospheric dispersion capacity is a structural determinant of
effective air-pollution exposure. Two communes with the same annual
NO2 column can have very different **inhalation doses** if one is
in a high-wind corridor and the other is in a topographic basin
(Andean foothills, valley). For the BrainLat exposome, this layer
serves as a **modifier of effect** for all the air-quality
indicators: it should be modelled jointly with NO2, PM2.5, O3, and
heat, not as a standalone exposure.

Wind is also an indirect pathway for the BrainLat dementia risk
factor **air pollution** (Lancet Commission 2024, ~3% of
attributable dementia risk). The wind layer does not add a new
pathway; it qualifies the existing air-pollution pathway.

## Regional reference values

- **Central Chile wind climatology** (ERA5 10-m annual mean):
  1.0-2.5 m/s (coastal valleys); 3-5 m/s (Andean ridges).
  Santiago RM sits in a **valley basin** with the Andes to the east
  and a coastal range to the west, so annual means are typically
  1.0-2.0 m/s with strong diurnal mountain-valley breeze patterns.
- **"Calm" threshold** (WMO standard): wind speed < 1 m/s at 10 m.
  We use a more permissive 2 m/s threshold to reflect that under
  2 m/s, near-surface dispersion is significantly reduced in
  typical urban canyons.
- **Dispersion regimes:**
  - v < 1 m/s: stagnation; very poor dispersion.
  - 1 ≤ v < 2 m/s: low dispersion; calm episodes.
  - 2 ≤ v < 4 m/s: moderate dispersion.
  - v ≥ 4 m/s: good dispersion; pollutants flushed quickly.

## Inputs

- `data/processed/<country>/<location>/<study>/wind/*.csv` — valores por
  unidad administrativa.
- `data/processed/<country>/<location>/<study>/wind/*.geojson` — los mismos
  valores con geometría.
- `data/processed/<country>/<location>/<study>/wind/*_metadata.json` —
  procedencia, colección, umbral y limitaciones.
- `cache/<country>/<location>/<study>/wind/<study>_wind_<collection>_*.csv` —
  caches anuales de GEE; el namespace de colección impide reutilizar caches
  ERA5 al migrar a ERA5-Land.

## Pipeline

```bash
source .venv/bin/activate
exposome run --study <study> --layers wind --force --no-build-master
```

`run_wind.py` calls `build_wind_layer()` in
`src/exposome/wind.py`, which:

1. Loads commune polygons (`boundaries.get_communes`).
2. Queries ERA5-Land hourly 10-m U and V components for the configured year.
3. Computes hourly wind speed `sqrt(u^2 + v^2)`, mean per commune
   per year.
4. Computes the **fraction of calm hours** (speed < threshold, default
   2 m/s) as a chronic low-dispersion index.
5. Computes 99th percentile of wind speed.
6. Computes prevailing wind direction from annual mean U/V via
   `atan2(-u, -v)`.

`plot_wind_map.py` produces a 4-panel figure. The master builder
integrates 6 columns.

## Metrics

The layer emits the following core columns for every configured spatial unit
(plus winter and summer variants):

- **`name`** — commune name.
- **`area_km2`** — commune area (km²).
- **`wind_u_mean`** — annual mean U (eastward) component [m/s].
- **`wind_v_mean`** — annual mean V (northward) component [m/s].
- **`wind_speed_mean`** — annual mean wind speed (per-hour sqrt(u^2+v^2),
  then averaged) [m/s]. Range 1.28-2.15.
- **`wind_speed_max_p99`** — 99th percentile of hourly wind speed [m/s].
  Range 3.17-5.85.
- **`wind_calm_pct`** — fraction of hours with wind speed < 2 m/s
  [unitless, 0-1]. Range 0.55-0.83.
- **`wind_dir_prevailing`** — annual mean direction the wind is
  coming FROM, in degrees clockwise from North [0, 360). Range 24-343.

### Santiago validation example: top 5 / bottom 5 by `wind_speed_mean`

- **Top 5 (highest mean speed):** San Pedro 2.15, María Pinto 1.67,
  Melipilla 1.63, Conchalí 1.59, Independencia 1.59 m/s.
- **Bottom 5 (lowest mean speed, most stagnant):** San José de Maipo
  1.28, La Florida 1.35, La Reina 1.35, Peñalolén 1.35, Puente Alto
  1.37 m/s.

## Interpretation

For the Santiago validation release, the pattern matches the **Andean
foothills shadow effect**: communes
on the periphery of the RM (San Pedro, María Pinto, Melipilla) have
higher wind because they sit on the **outflow plains**, where
mountain-valley winds accelerate. The central depression (San José
de Maipo, La Florida, La Reina, Peñalolén, Puente Alto) is more
sheltered by the Andean front range and shows lower mean speeds and
higher calm fraction.

The prevailing direction is **predominantly southwesterly** (annual
mean 200-250° from N) for most communes, consistent with the
**Pacific subtropical anticyclone** that drives the regional
circulation. San José de Maipo (343°) is an outlier because the
valley channels the wind northward up the Maipo canyon.

**Effective-exposure interpretation:** High `wind_calm_pct`
communes (San José de Maipo, La Florida, La Reina, Peñalolén, Puente
Alto) are the most likely to experience **local air-quality
amplification** under stagnant conditions. They should be modelled
jointly with NO2 and PM2.5 to test whether the air-quality exposure
is higher per unit of pollutant than in the well-ventilated
periphery.

## Critical caveats

- **ERA5-Land native ~11.132 km grid** is still coarse for commune-scale analysis.
  Commune polygons in the RM range from 6 to 5000 km²; the
  largest communes (San José de Maipo, Lo Barnechea, Pirque) may
  span several ERA5-Land pixels, while the smallest (< 10 km²) are below
  the pixel resolution. Sub-commune heterogeneity is hidden.
- **Topography (Andean valleys) not resolved.** ERA5-Land smooths
  local orographic effects. San José de Maipo's wind is likely
  **stronger in reality** than ERA5 reports because the canyon
  channels and accelerates the flow.
- **The annual summary hides seasonality.** Separate winter and summer fields
  capture the broad contrast, but neither resolves the diurnal cycle.
- **Prevailing direction is annual mean**, so seasonal reversals
  (mountain-valley breeze is daily, not seasonal) are smoothed.
- **Calm-fraction is highly sensitive to the threshold.** A 1 m/s
  threshold (WMO standard) gives much higher calm fractions than
  our 2 m/s. We chose 2 m/s because it matches the operational
  urban-canyon dispersion threshold better.

## Brain-health / exposome interpretation

- **Air-pollution modifier pathway (SUPPORTED with current data):**
  low wind_calm_pct + high NO2 / PM2.5 implies poor ventilation
  and higher effective dose. The layer should be used as an
  interaction term, not as a standalone exposure.
- **No direct exposure pathway:** wind is not a pollutant. There
  is no brain-health effect of wind per se, only through its
  modulation of other exposures.
- **Equity:** the most stagnant communes (San José de Maipo,
  La Florida, Peñalolén) are middle-NSE residential areas with
  moderate PM2.5 exposure. The combination of "moderate pollutant
  + poor ventilation" can yield effective exposure comparable to
  high-pollutant + well-ventilated central communes.
- **Heat pathway interaction:** low wind amplifies the heat
  exposure (less convective cooling). The interaction
  `heat_exposure_index × wind_calm_pct` may be a useful
  composite.

## Jensen's inequality and the U/V vs speed distinction

The annual mean `wind_speed_mean` is **substantially larger** than
`sqrt(wind_u_mean² + wind_v_mean²)` because of Jensen's inequality.
We compute two different reductions of the same hourly data:

- **`wind_u_mean`, `wind_v_mean`**: per-hour U and V components
  → temporal mean → zonal mean. This is the **vector-mean wind**,
  i.e. the mean direction the air is being transported.
- **`wind_speed_mean`**: per-hour `sqrt(u² + v²)` → temporal mean
  → zonal mean. This is the **scalar-mean wind**, i.e. the mean
  effective wind that matters for dispersion.

The scalar mean is always ≥ the vector mean, with the ratio
proportional to the directional variability.

**v1.3 (ERA5-Land 11.132 km)**: median ratio is **3.49** — each commune
now captures more of its own directional variability
(mountain-valley breeze, synoptic storms, sea breeze from the
coastal range) because the pixel grid is approximately 2.7× finer linearly
than the former 30 km product.
The scalar mean is 3-4x the vector mean instead of 1.8x.

**v1.2 (ERA5 30 km)**: median ratio was 1.82 (coarse grid smoothed
directional variability across neighbours).

Both metrics are correct, but they answer different questions:
use the **scalar mean for dispersion capacity** (the "effective"
wind for flushing pollutants), use the **vector mean for
transport direction** (the prevailing wind).

This is locked-in by `test_jensen_ratio_bounded` in
`tests/test_wind.py`, which fails if the ratio drifts outside
[1.5, 5.0]. The lower bound is a physical floor; the upper bound
accommodates the 9-km grid's higher directional variability.

## ERA5-Land pixel sharing

The ERA5-Land grid (~11.132 km) means most small communes have their
own pixel. In v1.3 data, **only 2/52 communes share the most
common pixel value** (down from 17/52 in v1.2 with ERA5 30 km).
This is a 8.5x reduction in pixel sharing and makes the layer
usable for future zip-code level analysis (50-100x smaller
polygons than communes).

The 2-commune block is locked-in by `test_era5_pixel_sharing` in
`tests/test_wind.py`, which fails if the most common pixel value
is shared by 10+ communes (i.e., the resolution has regressed
back to ~30 km).

## Limitations

1. **ERA5-Land spatial resolution (~11.132 km)** still limits fine-scale
   interpretation; very small zip codes (under 0.5 km²) will
   still be over-smoothed. The layer is best read as
   commune-level climatology, not as neighborhood conditions.
2. **Seasonal averages still mask the diurnal cycle** (mountain-valley
   breeze is daily, not seasonal). For diurnal analysis, a separate
   downscaling or local station layer would be required.
3. **No surface wind (10 m is above urban canopy).** True
   pedestrian-level wind in urban canyons can be 30-50% lower
   than 10-m wind.
4. **No gusts.** Extreme winds (e.g., coastal storms) are
   smoothed out by averaging.
5. **The master is a single-year snapshot.** The 2024 master value is not a
   climatology; optional annual products provide 2015–2024 variability without
   inflating the master.

## Seasonal analysis (winter vs summer)

Annual mean wind hides the strongest contrast in central Chile:
**winter stagnation** is the worst air-quality season in Santiago
(subsidence inversions trap PM2.5, NO2, and combustion by-products
under a stable boundary layer). The wind layer therefore exposes
**per-season** versions of the same five indicators:

| Column | Definition |
|---|---|
| `wind_speed_mean_<season>` | mean hourly wind speed in the season [m/s] |
| `wind_speed_max_p99_<season>` | 99th-percentile hourly wind speed in the season |
| `wind_calm_pct_<season>` | fraction of hours with speed < 2 m/s in the season |
| `wind_u_mean_<season>` | mean U (eastward) component in the season |
| `wind_v_mean_<season>` | mean V (northward) component in the season |
| `wind_dir_<season>_mean` | prevailing direction in the season [deg from N] |

**Season definitions (southern-hemisphere meteorological seasons):**

- **Winter:** June-August of `year` (single calendar year).
- **Summer:** December of `year` + January-February of `year+1`
  (crosses calendar year; configured via `wind.summer_months`).

### Observed winter vs summer values (2024)

Sample for **Calera de Tango** (a periphery commune on the south
plains of the RM):

| Indicator | Annual | Winter | Summer |
|---|---|---|---|
| `wind_speed_mean` | 1.544 | 1.262 | 1.895 |
| `wind_calm_pct`  | 0.729 | 0.910 | 0.554 |
| `wind_dir_*_mean` | 228.1 | 200.5 | 251.2 |

Pattern matches the regional climatology:

- **Winter is more stagnant** (`wind_speed_mean_winter` typically
  1.2-1.4 m/s vs annual 1.3-2.2; `wind_calm_pct_winter` 0.85-0.92
  vs annual 0.55-0.83). The seasonal subsidence inversion reduces
  near-surface wind for weeks at a time. This is the season with
  the highest effective PM2.5 dose.
- **Summer is more ventilated** (1.8-2.4 m/s; calm 0.40-0.65).
  Coastal sea breeze and stronger mountain-valley circulation
  flush pollutants.
- **Prevailing direction** shifts from southwesterly in winter
  (Pacific storm tracks) to more southerly/southeasterly in
  summer (deep convective regime).

A regression test (`test_winter_calm_ge_annual_calm` in
`tests/test_wind.py`) locks in the expectation that **at least
60% of communes have `wind_calm_pct_winter >= wind_calm_pct_annual`**.
A reversal of this ordering would indicate a season-definition
bug or a zonal-stats drift.

### Effective-exposure interpretation

The seasonal wind layer is what should enter the air-pollution
**interaction term** in the BrainLat exposome:

```text
effective_pm25_dose ~ pm25_annual * wind_calm_pct_winter
```

Equivalently, communes with **high winter PM2.5 + high winter
calm fraction** are the candidates for the highest wintertime
inhalation dose. Annual-only analysis would dilute this signal.

## Reproducibility

- Source: `ECMWF/ERA5_LAND/HOURLY` via GEE.
- Bands: `u_component_of_wind_10m`, `v_component_of_wind_10m`.
- Wind speed computed as `sqrt(u^2 + v^2)` per hour.
- Calm threshold: 2 m/s (configurable via `wind.threshold_calm_m_s`).
- Resolution: ERA5-Land native grid, requested at 11,132 m; no artificial
  fine-grid product is published.
- Re-run: `.venv/bin/exposome run --study <study> --layers wind --force
  --no-build-master` (requires GEE; collection-qualified caches live below the
  study's canonical `cache/.../wind/` directory).
- Random seeds: none.
- Pre-processed output: deterministic given the same ERA5-Land
  snapshot.
