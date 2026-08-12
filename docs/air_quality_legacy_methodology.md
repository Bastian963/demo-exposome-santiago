# Calidad del aire legacy (CAMS/Open-Meteo) — metodología y rol actual

## Rol de esta capa

`air_quality` se conserva como una capa **legacy/comparativa**. No es la fuente
canónica de PM2.5 del exposoma:

- El PM2.5 canónico del master proviene de `air_quality_pm25`
  (`santiago_pm25_acag_2015_2022.*`).
- La capa más robusta para NO2/AOD/BLH satelital proviene de
  `air_quality_satellite` (`santiago_air_quality_satellite_2024.*`).
- `air_quality` se mantiene para dos fines concretos:
  - comparación histórica CAMS vs satélite;
  - fuente de `no2_mean`, `n_grid` y `no2_who_ratio` en
    `santiago_exposome_master.csv`.

El PM2.5 legacy (`pm25_mean`, `pm25_who_ratio`) se conserva en el CSV y en la
figura comparativa, pero **no se integra al master**.

## Fuente y escala

- API: Open-Meteo Air Quality (`https://air-quality-api.open-meteo.com/v1/air-quality`)
- Dataset subyacente: reanálisis CAMS
- Ventana: año 2024 completo
- Variables descargadas: `pm2_5`, `nitrogen_dioxide`
- Grilla: paso `0.1°` sobre la Región Metropolitana, aproximadamente `11 km`

La resolución es demasiado gruesa para capturar bien el gradiente intraurbano
fino. Por eso la capa sirve como referencia histórica, pero no como mejor
estimador espacial disponible para PM2.5 crónico ni para NO2 satelital.

## Procesamiento

1. Se construye una grilla fija sobre el bbox configurado en
   `config/cities/santiago.yaml`.
2. Se descarga la serie horaria 2024 por punto y se resume a media anual por
   variable.
3. Los puntos se guardan en `cache/air_quality_grid_2024.csv`; si ese archivo
   existe, el CLI legacy lo reutiliza y no vuelve a consultar Open-Meteo.
4. Cada comuna recibe la media de los puntos CAMS que caen **dentro** de su
   polígono.
5. Cuando una comuna no contiene puntos interiores por la resolución gruesa de
   CAMS, se usa el **punto más cercano al centroide** y `n_grid` queda en `0`.
6. Se calculan razones respecto de las guías OMS 2021:
   - `pm25_who_ratio = pm25_mean / 5.0`
   - `no2_who_ratio = no2_mean / 10.0`

## Outputs y reproducibilidad

CLI reproducible desde la raíz del repo:

```bash
.conda/envs/exposome/bin/python scripts/run_air_quality.py
```

Salidas esperadas:

- `data/processed/air_quality_exposome_rm_santiago.csv`
- `data/processed/air_quality_exposome_rm_santiago.geojson`
- `data/processed/air_quality_exposome_rm_santiago_metadata.json`

El CLI legacy no requiere GEE. Solo necesita conectividad a Open-Meteo si falta
el cache local `cache/air_quality_grid_2024.csv`.

## Integración al master

`scripts/build_master_exposome.py` importa solo:

- `no2_mean`
- `n_grid`
- `no2_who_ratio`

No importa `pm25_mean` ni `pm25_who_ratio` desde esta capa. El master obtiene
`pm25_*` desde `air_quality_pm25`.

## Limitaciones

- Resolución gruesa (`~11 km`): varias comunas vecinas comparten exactamente el
  mismo valor CAMS.
- `n_grid=0` es frecuente en comunas pequeñas; el fallback por centroide evita
  faltantes, pero confirma que esta capa no tiene resolución adecuada para
  comparaciones finas dentro de la ciudad.
- Indicador ecológico anual: no representa exposición individual.
- El PM2.5 legacy ya fue superado metodológicamente por ACAG (`air_quality_pm25`).

## Diagnóstico visual asociado

`figures/air_quality_before_after_satellite.png` compara el NO2 legacy CAMS con
la capa satelital nueva y sirve para mostrar la pérdida de detalle espacial de
la grilla gruesa.
