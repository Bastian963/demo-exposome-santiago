# Metodología de `climate_heat` — exposición térmica ERA5-Land

## Propósito

Esta capa caracteriza la exposición térmica anual de cada unidad
administrativa. El producto principal del master representa 2024; las tablas
anuales opcionales cubren 2015–2024. El calor se interpreta como exposición
ambiental y no como una medición clínica individual.

## Fuente canónica

- **Producto:** ECMWF ERA5-Land Daily Aggregated, colección de Google Earth
  Engine `ECMWF/ERA5_LAND/DAILY_AGGR`.
- **Bandas:** `temperature_2m`, `temperature_2m_min`,
  `temperature_2m_max`, `dewpoint_temperature_2m` y
  `total_precipitation_sum`.
- **Resolución:** píxel nativo nominal de aproximadamente 11.132 km. No se
  sobremuestrea a una grilla fina ni se publica un detalle subadministrativo
  artificial.
- **Unidades:** temperaturas Kelvin y precipitación en metros se convierten a
  °C y mm durante la extracción.

Open-Meteo fue la fuente de una versión histórica de Santiago y se conserva
como capa/comparador separado (`climate_openmeteo`). No es una fuente válida
para reconstruir ni publicar `climate_heat` bajo la configuración vigente.

## Flujo espacial y temporal

1. Se disuelven los límites del estudio para definir un AOI independiente de
   la partición administrativa.
2. Se muestrean los píxeles ERA5-Land que cubren los límites del AOI. La
   extracción se divide por año, mes y ventanas de fechas para respetar los
   límites de GEE.
3. Las métricas diarias y anuales se calculan primero por píxel.
4. Se construye la huella de cada píxel nativo y se intersecta con los
   polígonos administrativos en el CRS métrico configurado por el estudio.
5. Cada indicador administrativo es una media ponderada por el área de
   intersección. Si una unidad terrestre no intersecta ningún píxel observado
   por la máscara de costa, se usa el centro del píxel ERA5-Land observado más
   cercano sólo cuando está a menos de una separación nativa (11.132 m). El
   resultado registra la distancia, `used_nearest_fallback=true` y
   `n_area_grid_points=0`; distancias mayores detienen la construcción. No se
   usan centroides ni puntos representativos de la unidad.

Este orden evita que un cambio de límites altere qué observaciones originales
se descargan y permite que unidades pequeñas reciban todos sus píxeles
intersectantes. El fallback acotado evita perder unidades costeras pequeñas
sin ocultar la extrapolación espacial que implica.

## Indicadores

| Columna | Unidad | Definición |
|---|---:|---|
| `tmean_annual_c` | °C | Media anual de temperatura media diaria |
| `tmax_mean_annual_c` | °C | Media anual de temperatura máxima diaria |
| `summer_tmax_mean_c` | °C | Media de Tmax en diciembre, enero y febrero |
| `tmax_p95_c` | °C | Percentil 95 de Tmax diaria |
| `tmax_abs_c` | °C | Máximo anual de Tmax |
| `apparent_tmax_mean_c` | °C | Media anual de temperatura aparente máxima derivada |
| `hot_days_30c` | días | Días con Tmax ≥ 30 °C |
| `hot_days_35c` | días | Días con Tmax ≥ 35 °C |
| `apparent_hot_days_35c` | días | Días con temperatura aparente máxima ≥ 35 °C |
| `tropical_nights_20c` | días | Días con Tmin ≥ 20 °C |
| `precip_annual_mm` | mm | Precipitación anual acumulada |
| `n_days` | días | Observaciones diarias efectivamente utilizadas |

ERA5-Land no entrega temperatura aparente. Se aproxima mediante la fórmula de
Steadman usando temperatura, punto de rocío y un viento residencial constante
de 1 m/s. Por ello, las métricas aparentes son aproximaciones y no deben
interpretarse como observaciones independientes.

`heat_exposure_index` es la media de z-scores de cinco componentes térmicos y
es relativo a las unidades de la misma ciudad. `urban_heat_anomaly_c` es la
diferencia de `summer_tmax_mean_c` respecto de la mediana de la ciudad; no es
una isla de calor física medida con LST. Ninguno de estos dos índices se
publica como serie anual, porque cambiaría su referencia entre años.

Las series 2015–2024 publican sólo métricas observables:
`summer_tmax_mean_c`, `hot_days_30c` y `tropical_nights_20c`. Cada producto
anual conserva todos los `spatial_id`, el año, checksum y procedencia. Los
archivos permanecen separados del master y el bundle los declara mediante
`temporal_indicators`.

## Reproducibilidad

La descarga real es una tarea nocturna ejecutada por una persona. El fetcher
guarda un checkpoint completo por año y omite años válidos al reanudarse.

```bash
source .venv/bin/activate

# Ejemplo: poblar el cache canónico de 2024 para un estudio.
python scripts/run_climate_fetch.py \
  --city <study> --years 2024 \
  --cache-dir cache/<country>/<location>/<study>/climate_heat \
  --out-dir data/processed/<country>/<location>/<study>/climate_heat

# Construcción local, cache-first, de la capa administrativa.
exposome run --study <study> --layers climate_heat --force --no-build-master
```

El cache anual se llama `<study>_era5land_grid_<año>.csv`. Si existe pero no
contiene todas las bandas y meses requeridos se mueve a un archivo
`*.invalid_<timestamp>.csv` y se vuelve a descargar; no se acepta como un
checkpoint válido.

El sidecar resultante debe declarar `source: era5land`, tamaño de píxel,
método de agregación, número de píxeles y número de filas diarias. La
publicación rechaza un sidecar cuya fuente contradiga la configuración
resuelta del estudio.

## Interpretación y limitaciones

1. La grilla de ~11 km no resuelve cañones urbanos, parques, materiales de
   superficie ni gradientes de barrio. La capa sólo se interpreta al soporte
   administrativo publicado.
2. ERA5-Land es un reanálisis: sus valores modelados pueden diferir de
   estaciones meteorológicas y de otros reanálisis, especialmente en valles y
   topografía compleja.
3. La temperatura aparente supone viento constante; no incorpora la capa de
   viento anual de GEMMA dentro de esa fórmula.
4. Los meses de verano son meses calendario del mismo año, por lo que el
   verano austral queda dividido entre años consecutivos.
5. Los umbrales absolutos facilitan comparación descriptiva, pero el índice
   compuesto y la anomalía son relativos dentro de cada ciudad y no deben
   compararse directamente entre ciudades.
6. `climate_heat` no sustituye una capa satelital de temperatura superficial
   ni una validación con estaciones locales.
7. Las unidades sin intersección usan un píxel terrestre cercano y por ello
   comparten su señal regional; la bandera y distancia publicadas deben
   consultarse antes de interpretar diferencias locales.

## Referencia

Muñoz-Sabater, J. et al. (2021). *ERA5-Land: a state-of-the-art global
reanalysis dataset for land applications*. Earth System Science Data, 13,
4349–4383. DOI: `10.5194/essd-13-4349-2021`.
