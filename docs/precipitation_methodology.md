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
- **Reference:** Funk C. et al. (2015). *The climate hazards infrared
  precipitation with stations — a new environmental record for
  monitoring extremes.* Scientific Data 2:150066.

**Limitaciones conocidas de CHIRPS para Chile central:**

- **RMSE vs estaciones DMC**: ~5-15 mm/mes (Funk et al. 2015).
- **Sesgo sistemático**: sobreestima ~5-15% en zonas áridas
  (Santiago RM es semiárida), subestima en zonas húmedas andinas.
- **Resolución 0.05° (~5.5 km)**: suaviza topografía andina, lo que
  puede sub-representar gradientes de precipitación orográfica.
- **Validación fina**: para análisis con precisión sub-comunal,
  complementar con datos DGA/DMC por estación. La capa canónica
  no incluye este cross-check; queda como brecha conocida.

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

## Brain-health / exposome interpretation

The precipitation layer is **exploratory** — it does not model cognition,
biomarkers or neuroimaging outcomes. It is meant to feed future
brain-exposome analyses through the `precip_extremes_index` (0-100 rank
composite) and the supporting chronic / seasonal / latest-year anomaly
metrics. Plausible biological and behavioural pathways:

- **Mobility and outdoor activity.** Heavy-rain days reduce outdoor
  mobility and physical activity (an established protective factor for
  cognitive ageing); extended dry spells have the opposite effect. The
  `precip_heavy_days_10mm` and `precip_cdd_days` columns capture the
  two ends of this trade-off.
- **Social isolation in Mediterranean winters.** Central Chile has
  wet winters (JJA) and dry summers (DJF). Persistent winter rain
  shifts socialising indoors, which compounds isolation risk for older
  adults. The natural cross is `precip_winter_mean_mm` with the
  social-infrastructure layer.
- **Flood-related acute stress.** RX5day spikes (panel C of the
  4-panel figure) are the satellite analog of riverine flooding
  episodes; the 2015-2024 record includes the August 2015 and June
  2024 frontal systems that triggered the RM-wide flood warnings.
- **Drought × heat compound events.** Multi-year drought in central
  Chile (2015-2021, the "Mega Drought") interacts with heat exposure
  and is the dominant driver of the 2017/2023/2024 fire seasons.
  The `precip_latest_anomaly_pct` and `precip_extremes_index` should
  be analysed jointly with `heat_exposure_index` and
  `fire_exposure_index`.
- **Humidity and housing conditions.** Persistent damp housing
  promotes mould and respiratory conditions that secondarily affect
  cognition and mood. This pathway is hard to model from satellite
  precipitation alone but motivates the inclusion of `precip_wet_days`
  in cohort-level covariate lists.

**Informative cross-tabulations in the master**

| Cross | Rationale |
|---|---|
| `precip_extremes_index` x `fire_exposure_index` | Drought co-drives the catastrophic fire seasons (2017, 2023, 2024). |
| `precip_latest_anomaly_pct` x `green_cover_pct_ndvi` | Recent rainfall deficits reduce vegetation; the difference is the exposed signal. |
| `precip_cdd_days` x `heat_exposure_index` | Compound drought-heat events; the joint extremes are the most dangerous. |
| `precip_heavy_days_10mm` x `health_n_primary_care` | Heavy-rain days reduce primary-care visits (mobility); check the cross for non-linearity. |
| `precip_winter_mean_mm` x `social_infrastructure` | Wet winters shift socialising indoors; communes with weaker infrastructure face worse isolation risk. |

## Note on the 10-year window and `n_days = 3653`

The canonical precipitation layer is built on a 10-year daily series
(2015-01-01 to 2024-12-31) from CHIRPS, gap-filled by UCSB. The total
number of daily records per commune is `precip_n_days = 3653`, which
equals 10 x 365.3 (CHIRPS reports 365 or 366 days per year, averaging
365.3 over the decade with leap years). The columns `precip_n_years`
and `precip_n_days` are included in the canonical CSV so that:

- the count is fully traceable per commune (e.g. a future fix that
  partially rebuilds the series can be detected by an unexpected
  drop in `n_days`);
- downstream `precip_*` ratios that depend on sample size (CV,
  wet-day percentage) are auditable.

Two practical consequences for the master:

- The chronic rainfall statistics (`precip_annual_mean_mm`,
  `precip_annual_cv`, etc.) are means of 10 annual values per commune
  — high inter-annual variability (the 2015-2024 record includes the
  driest and wettest years of the past two decades) makes single-year
  comparisons fragile.
- `precip_latest_anomaly_pct` is calculated against a 9-year baseline
  (years strictly before `latest_year = 2024`); a commune that
  experienced its wettest year on record in 2024 will show a
  strong positive anomaly.

## Verification of the review run (opencode audit, 2026-06-29)

The cache-first re-run reproduces the canonical outputs without
invoking Google Earth Engine:

- `cache/santiago_precipitation_chirps_2015.csv` ... `_2024.csv`
  contain **10 yearly CHIRPS extracts** (516-562 KB each) covering
  the 52 communes at the ~5.5 km native scale.
- `python scripts/run_precipitation.py` (cache-first) wrote
  `data/processed/santiago_precipitation_chirps_2015_2024.csv` and
  `santiago_precipitation_chirps_2015_2024.geojson` **byte-identical**
  to the canonical outputs (verified by MD5); only the `_metadata.json`
  `created_utc` field changed.
- Metadata reports `n_rows=52`, `period=2015-2024`,
  `latest_year=2024`, `thresholds_mm` {1.0, 10.0, 20.0}, sources for
  CHIRPS, a complete `columns_description` for all 22 output columns,
  a non-empty `limitations` field and a 5-entry
  `brain_health_relevance` block. The metadata is now consistent with
  the format of the wildfire, healthcare, and climate_heat layers.
- `data/processed/santiago_exposome_master.csv` contains the 20
  precipitation core columns; `precip_annual_mm` (added by the
  `climate_heat` layer) and `precip_trend_mm_per_decade` (added by the
  `precipitation_spi` layer) are also present, as expected.
- `figures/precipitation_santiago_4panel.png` shows the four core
  metrics across the 52 communes (chronic load, wet-day frequency,
  RX5day extremes, composite 0-100 index). The choropleth is the
  dedicated 4-panel for this layer, separated from the
  `climate_metrics_santiago.png` figure that the audit script shared
  with `climate_openmeteo`.
- `tests/test_precipitation.py` runs **12 tests** (all green)
  covering schema, metadata, distribution, Mediterranean-climate
  seasonality (winter > summer), hierarchical threshold semantics
  (count>=20mm <= count>=10mm), master integration, and build-layer
  reproducibility from cache.

# Apéndice: `precipitation_spi` (sequía estandarizada)

La capa `precipitation_spi` se construye **sobre el mismo archivo
diario CHIRPS** (`santiago_precipitation_chirps_daily_2015_2024.csv`)
que la capa principal, y agrega **índices de sequía estandarizada
(SPI)** por comuna, complementando la exposición hídrica crónica con
una caracterización formal de la variabilidad intra- y multi-anual.

## Anomalía 2024 y validación CHIRPS

La ventana `spi_12_latest` (Dic 2024) muestra valores uniformemente
positivos (rango 1.30-2.23, media 1.83) porque **2024 fue un año
genuinamente húmedo** en Chile central:

- 2024 RM media: **464 mm/yr**
- Baseline 2015-2023 (mega-sequía): **261 mm/yr**
- Anomalía: **+78%** sobre la media reciente

El evento responde al patrón de **ríos atmosféricos** del invierno
2024 (sistemas frontales intensos en junio-agosto). En perspectiva
climatológica (1991-2020), 2024 estuvo ~7% sobre la normal — no es
históricamente extremo, pero rompe la racha de 13 años bajo lo normal
(2010-2023, "mega-sequía"). La **anomalía +78%** es alta para CHIRPS
dado su RMSE típico de ~5-15 mm/mes en Chile central; podría
sobre-estimar entre un 10-20% por el sesgo conocido de CHIRPS en
zonas áridas.

**Limitaciones conocidas de CHIRPS para esta capa:**

- **RMSE vs estaciones DMC**: ~5-15 mm/mes en Chile central
  (Funk et al. 2015).
- **Sesgo sistemático**: sobreestima ~5-15% en zonas áridas,
  subestima en zonas húmedas andinas. Santiago RM es semiárida,
  así que el sesgo de sobre-estimación es el dominante.
- **Resolución 0.05° (~5.5 km)**: suaviza la topografía andina,
  sub-representando gradientes de precipitación orográfica.
- **Validación fina**: para análisis que requieren precisión sub-comunal
  (ej. correlación con outcomes individuales BrainLat), complementar
  con datos DGA/DMC por estación.

## Contraste urbano/rural en `precip_extremes_index`

El `precip_extremes_index` rankea comunas por frecuencia de eventos
extremos (lluvias ≥10 mm/día, RX5day). Hallazgo contraintuitivo:

- **Bottom 5** (menos extremos): Recoleta, Santiago, Ñuñoa, Providencia,
  Macul — comunas urbanas densas del centro-norte.
- **Top 5** (más extremos): La Cisterna, Lo Espejo, Talagante, El
  Bosque, Pirque — comunas del sur/poniente con mayor exposición a
  sistemas frontales del Pacífico.

**Interpretación tentativa**: las comunas urbanas centrales pueden
experimentar **supresión de convección local** por el efecto isla de
calor (el calentamiento superficial sube la base de condensación,
reduciendo la frecuencia de tormentas convectivas estivales). Es una
hipótesis que requiere validación con datos de radar DMC; se documenta
como hallazgo descriptivo, no causal. Alternativamente, podría ser un
artefacto de la grilla CHIRPS a 5.5 km de resolución, que suaviza
eventos extremos en celdas urbanas pequeñas.

## Serie anual 2015-2024 (selector de año del webapp)

`scripts/run_precipitation_annual.py` resume el archivo diario CHIRPS ya
procesado (`santiago_precipitation_chirps_daily_2015_2024.csv`) por comuna
y año con la misma lógica por-año que alimenta las métricas crónicas
(`exposome.precipitation.calculate_annual_precipitation_table`) y escribe
`data/processed/santiago_precipitation_by_year.csv` (52 comunas × 30
columnas): `precip_annual_mm_<año>`, `precip_cdd_days_<año>` (racha seca
máxima, umbral de día húmedo 1 mm) y `precip_heavy_days_10mm_<año>`.

- Consistencia verificada en el script: la media de los `precip_annual_mm_<año>`
  reproduce `precip_annual_mean_mm` de la capa canónica (max |diff| < 0.01 mm).
- `precip_extremes_index` **no** tiene versión anual: es un compuesto de
  z-scores del período completo.
- En el webapp, el stop "Prom." del slider muestra las columnas crónicas
  canónicas; los años intercambian la columna del coroplético
  (`year_columns` en `palette.json`).

## Métricas derivadas (52 comunas)

- **`drought_months_pct`**: % de meses con SPI-3 < -1.0 (sequía
  moderada McKee 1993). Rango canónico 11.0 – 18.6 %.
- **`drought_severe_months_pct`**: % de meses con SPI-3 < -2.0
  (sequía severa). Rango 0.0 – 0.85 %.
- **`drought_max_duration_months`**: meses consecutivos más largos
  en sequía moderada. Rango 3 – 6.
- **`precip_trend_mm_per_decade`**: pendiente OLS de precipitación
  anual (mm/yr) × 10. Rango -53.7 (San Pedro) a +82.9 (San José
  de Maipo). Indica si la comuna se está secando o humedeciendo.
- **`spi_12_latest`**: SPI-12 del mes más reciente del registro
  (Diciembre 2024). Rango 1.30 – 2.23 (todas positivas: 2024 fue
  húmedo en la RM).
- **`spi_3_mean`, `spi_3_std`, `spi_6_mean`, **`spi_12_mean`**:
  media y SD de cada escala sobre todo el registro 2015-2024. La
  media es ~0 por construcción (estandarización). `spi_3_std` ≈ 1
  indica variabilidad bien capturada.

## Algoritmo SPI

McKee et al. 1993:

1. Acumulación rolling de precipitación mensual en ventanas de 3,
   6 y 12 meses.
2. Para cada mes calendario, ajuste de distribución Gamma
   (`scipy.stats.gamma.fit`, MLE con `floc=0`) sobre los valores
   no-cero del histórico.
3. CDF mixta: `P(X=0) + (1 - P(X=0)) × Gamma_CDF(x)` para
   manejar la zero-inflation típica de climas áridos.
4. Transformada a N(0,1) vía `norm.ppf(cdf)`.

## Importancia para salud cerebral

- **Sequía crónica** → estrés hídrico, presión psicológica,
  neuroinflamación. La sequía "mega" chilena (2010-presente)
  impacta salud mental en adultos mayores.
- **Tendencia de secado** → exposición acumulada al cambio
  climático, presión sobre sistemas alimentarios e hídricos.
- **Variabilidad SPI** → impredecibilidad de precipitación
  → disrupción agrícola y de servicios → mediador socioeconómico
  de outcomes neurocognitivos.

## Salidas (`data/processed/santiago_precipitation_spi.*`)

- `santiago_precipitation_spi.csv` (52 × 11)
- `santiago_precipitation_spi.geojson`
- `santiago_precipitation_spi_metadata.json` (incluye period 2015-2024,
  n_days=3653, SPI algorithm completo, columns_description, brain_health_relevance)
- `figures/precipitation_spi_santiago_4panel.png` (4-panel dedicada)

## Reproducibilidad

- **Idempotencia**: re-ejecutar
  `python scripts/run_precipitation_spi.py` produce CSV byte-idéntico
  (md5 `fdccb3…62e9`). Cache en `cache/spi_monthly_santiago.parquet`
  (~700 KB, keyed al mtime de CHIRPS daily).
- **Tests**: `tests/test_precipitation_spi.py` (13 tests, todos OK)
  cubre schema, drought metrics bounded, SPI_means ≈ 0,
  `san_pedro_driest_trend`, `_spi_for_commune` con sintético,
  `compute_drought_metrics` con sequías de 8 meses consecutivos.
- **Modo monitor** (`--monitor`): fetcha los últimos 90 días desde
  Open-Meteo, compara con baseline CHIRPS, imprime tabla de anomalía.
  No escribe archivos.
- **Modo histórico** (`--history`): imprime resumen año-a-año desde
  CHIRPS cached + top 10 comunas más afectadas. No hace llamadas a
  red.
