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
