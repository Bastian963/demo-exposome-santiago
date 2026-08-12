# Sleep-circadian context layer

This note documents the commune-level sleep-circadian context layer for the
Región Metropolitana de Santiago. The layer is designed for exposome modelling:
it summarizes environmental and social conditions plausibly linked to worse
sleep, but it is **not** a direct estimate of sleep duration, sleep quality,
insomnia, sleep apnea, or any clinical sleep disorder.

## Why include sleep context

Sleep is a key pathway between urban exposures and brain health. Artificial
light at night can disrupt circadian timing and melatonin secretion; warm nights
can reduce sleep comfort and recovery; and social vulnerability can shape both
exposure and resilience. The layer therefore complements ALAN, heat and
socioeconomic indicators already present in the Santiago exposome.

Direct sleep survey data are kept as regional context:

- MINSAL Encuesta Nacional de Salud (ENS) databases:
  https://epi.minsal.cl/bases-de-datos/
- INE Encuesta Nacional sobre Uso del Tiempo (ENUT):
  https://www.ine.gob.cl/estadisticas/sociales/genero/uso-del-tiempo/enut
- ENUT 2023 main report:
  https://www.ine.gob.cl/docs/default-source/uso-del-tiempo-tiempo-libre/publicaciones-y-anuarios/ii-enut/informe-de-principales-resultados-ii-enut-2023.pdf
- ENS sleep substudy in Región Metropolitana:
  https://www.scielo.cl/scielo.php?pid=S0034-98872020000700895&script=sci_arttext

These sources can quantify sleep at national/regional or study-sample level,
but they are not used here to impute commune-level sleep outcomes.

## Regional reference values

These values are useful for interpretation and external validation, but they do
not replace the commune-level proxy:

- ENUT 2023 reports average time spent sleeping in Chile as 07:11 on weekdays
  and 07:35 on weekends among people aged 12+. Women report 07:14 on weekdays
  and 07:37 on weekends; men report 07:07 and 07:32, respectively.
- The ENS 2016/17 sleep substudy in Región Metropolitana reports, in the RM
  sample, frequent sleep-related symptoms such as habitual snoring, witnessed
  apneas, daytime sleepiness, insomnia, hypnotic use and non-restorative sleep.
- Expanded estimates in the RM adult sample include non-restorative sleep around
  44%, excessive daytime sleepiness around 21%, insomnia around 7.5% and
  hypnotic use around 13%.

## Inputs

Implemented in `src/exposome/sleep_context.py`, using
`data/processed/santiago_exposome_master.csv` as the input table.

Required columns:

- `alan_radiance_pop_weighted` from VIIRS DNB + WorldPop.
- `om_tropical_nights_20c` and `om_tmin_mean_summer_c` from the Open-Meteo
  climate metrics layer.
- `hacinamiento_phh`, `nse_index` and `demo_pct_pop_65_plus` from the
  socioeconomic and demography layers.

## Method

The layer first creates direct interpretable columns:

- `sleep_alan_log = log1p(alan_radiance_pop_weighted)`.
- `sleep_tropical_nights_20c = om_tropical_nights_20c`.
- `sleep_summer_tmin_c = om_tmin_mean_summer_c`.

Then all components are converted to 0-100 percentile ranks, where higher means
higher sleep-circadian risk.

Exposure index:

```text
sleep_exposure_index =
  mean(percentile(log ALAN),
       percentile(tropical nights),
       percentile(summer Tmin))
```

Vulnerability index:

```text
sleep_vulnerability_index =
  mean(percentile(overcrowding),
       percentile(population aged 65+),
       percentile(-NSE index))
```

Final context index:

```text
sleep_context_index =
  0.70 * sleep_exposure_index + 0.30 * sleep_vulnerability_index
```

## How to run

```bash
mamba activate /Users/bastianayalainostroza/Dropbox/Brainlat/.conda/envs/exposome
python scripts/build_master_exposome.py
python scripts/run_sleep_context.py
python scripts/build_master_exposome.py
python scripts/plot_sleep_context.py
```

Outputs:

- `data/processed/santiago_sleep_context.csv`
- `data/processed/santiago_sleep_context.geojson`
- `data/processed/santiago_sleep_context_metadata.json`
- `figures/sleep_context_santiago.png`

## Validation and limitations

The pipeline validates 52 commune rows, unique names, complete inputs, and a
bounded 0-100 final index. The figure checks whether high-index communes are
driven by expected co-exposures: high night-time light, warm nights and social
vulnerability.

Limitations:

- Ecological, commune-level proxy only; no individual sleep measurement.
- Does not use noise exposure yet, which is an important sleep determinant.
- Uses equal component weights within exposure/vulnerability groups and fixed
  70/30 exposure/vulnerability weights for v1.
- Direct sleep data from ENS/ENUT should be reported as external context, not
  as commune-level ground truth.

## Relevance for brain health (BrainLat)

The sleep-circadian context index is built on the well-established evidence
that disrupted sleep is a **modifiable risk factor for cognitive decline**:

- **Sleep disruption and dementia**: short sleep duration, fragmented sleep,
  and circadian misalignment are independent risk factors for all-cause
  dementia and Alzheimer's disease (Sabia et al., *Nature Communications
  2021*; Livingston et al., *Lancet Commission 2024* lists sleep as one of
  14 modifiable risk factors).
- **Vías biológicas plausibles**: menor consolidación de memoria durante
  sueño profundo, menor aclaramiento glifático de β-amiloide y tau,
  disregulación del eje HPA y mayor inflamación sistémica.
- **Urban exposure pathways**: ALAN suprime melatonina → desincronización
  circadiana; noches cálidas reducen el sueño de onda lenta; la
  vulnerabilidad social (hacinamiento, NSE bajo) amplifica el impacto de
  estas exposiciones al reducir el margen de recuperación.
- **Aplicación BrainLat**: esta capa permite testar si la co-exposición
  sueño-circadiana media la asociación entre exposiciones urbanas
  (PM2.5, ruido, calor) y outcomes neurocognitivos en la cohorte
  BrainLat. Es complementaria al ALAN y al climate_metrics del master.

## Reproducibilidad

- **Inputs requeridos:** `data/processed/santiago_exposome_master.csv`
  y `santiago_exposome_master.geojson` (deben existir; re-correr
  `scripts/build_master_exposome.py` si faltan).
- **Tiempo de cómputo:** <1 s (no hay red ni cómputo pesado; agregación
  in-memory de 52 comunas).
- **Idempotencia:** re-ejecutar `python scripts/run_sleep_context.py`
  produce un CSV **byte-idéntico** al de la corrida anterior (md5
  `9190b1…712c`); solo `created_utc` cambia en la metadata.
- **Test de regresión:** `tests/test_sleep_context.py` (14 tests)
  cubre schema, índices en [0,100], composición 0.70/0.30, transform
  log1p, contraste urbano/rural, e invariantes de percentile rank.
- **Validación de coherencia interna:** el input `master` exige 52
  comunas, columnas requeridas completas y nombres únicos; el output
  exige índice en [0,100] y sin NaN.

## Key data anchors (52 comunas)

Para facilitar la lectura del mapa, los extremos del índice
`sleep_context_index` (rango 23.07 – 78.69):

- **Más alto (mayor riesgo sueño-circadiano)**: San Joaquín (78.69),
  La Granja (77.78), San Ramón (74.90), San Miguel (73.46), Vitacura
  (71.24). Cuatro de los cinco son comunas de alta densidad y NSE
  bajo-medio; Vitacura es la excepción (alto NSE pero Tmin=17.2 C y
  20 noches tropicales la ponen en el quintil más alto de exposición).
- **Más bajo (menor riesgo)**: Buin (23.07), El Monte (25.92), María
  Pinto (26.67), Peñaflor (26.73), Talagante (28.10). Todas rurales
  del sur, con 0 noches tropicales y Tmin<13 C.
- **Hallazgo contraintuitivo**: Santiago y Providencia tienen índices
  **moderados** (57.09 y 64.48) pese a su ALAN altísimo, porque su NSE
  alto reduce la vulnerabilidad. La capa captura co-exposición, no
  exposición única.
