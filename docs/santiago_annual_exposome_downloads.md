# Descarga anual de exposomas faltantes — Santiago

**Estudio:** `santiago_communes`  
**Ventana objetivo:** 2015–2024  
**Producto:** archivo de exposiciones por comuna y año  
**Fuera de alcance:** análisis hospitalario, MCMC, master y webapp

## Qué hace el script

`scripts/run_missing_annual_exposomes.py --study santiago_communes` revisa todas las capas
habilitadas del estudio, calcula la intersección entre el período 2015–2024 y
la cobertura válida de cada proveedor, y descarga únicamente los años que no
tienen un manifiesto anual válido. Cada unidad de reanudación es una
combinación exposición–año.

No ejecuta `run_hospitalization_exposome_analysis.py`, no modifica el protocolo
de inferencia, no reconstruye `master.csv` y no copia datos a
`webapp/public/`. Las salidas se mantienen aisladas en:

```text
data/processed/cl/santiago/santiago_communes/temporal_exposomes/
  coverage.csv
  manifest.json
  <layer>/<year>/annual.csv
  <layer>/<year>/manifest.json
```

Los caches de proveedor quedan bajo
`cache/cl/santiago/santiago_communes/temporal_exposomes/` y no se versionan.
El script histórico `run_santiago_missing_annual_exposomes.py` es un wrapper
compatible del comando genérico.

## Cobertura solicitada

| Producto anual | Años objetivo | Fuente | Observación |
|---|---:|---|---|
| PM2.5 | 2015–2022 | ACAG V6.GL.02 | La colección configurada termina en 2022. |
| Calidad del aire satelital | 2019–2024 | Sentinel-5P, MODIS MAIAC y ERA5 | 2018 se excluye por no ser un año completo de Sentinel-5P. |
| ALAN | 2015–2024 | VIIRS DNB VCMSLCFG | Radiancia comunal y ponderada por población. |
| Verde Landsat | 2015–2024 | Landsat 8/9 C2 L2 | Compuesto Oct–Mar con filtro de meses discontinuos. |
| Verde Dynamic World | 2016–2024 | Dynamic World V1 | 2015 se excluye por cobertura parcial; canopy sigue estático. |
| Calor | 2015–2024 | ERA5-Land Daily | Píxeles nativos antes de agregar por comuna. |
| Clima Open-Meteo | 2015–2024 | Historical Weather API | Producto centrodial separado del calor canónico ERA5-Land. |
| Viento | 2015–2024 | ERA5-Land hourly | Anual, invierno y verano austral. |
| Precipitación | 2015–2024 | CHIRPS Daily | Ya disponible localmente; se materializa sin descargar de nuevo. |
| Incendios | 2015–2024 | MODIS MCD64A1 + FIRMS | Ya disponible localmente; se materializa sin descargar de nuevo. |
| Metales | 2015–2024 | RETC | Incluye las cosechas 2023 y 2024 que faltaban en la capa agregada. |

Los rangos están declarados en los bloques `settings.temporal` de las capas.
El script no consulta “el último año” dinámicamente: esto evita que una nueva
cosecha del proveedor cambie silenciosamente una corrida reproducible.

## Capas que no se temporalizan

- Ruido: mapa oficial único de 2023.
- Caminabilidad, transporte, áreas verdes OSM, infraestructura social, entorno
  alimentario y parte de salud: snapshots actuales de OSM, sin archivo anual
  comparable.
- NSE, demografía, pobreza e inseguridad alimentaria: censos, encuestas o
  cosechas administrativas seleccionadas, no observaciones anuales homogéneas.
- Sueño contextual y SPI: productos derivados; no tienen una descarga de
  proveedor independiente.
- Mortalidad y hospitalizaciones: desenlaces, no exposomas.

Todas estas capas aparecen en `--dry-run` con la razón de exclusión; ninguna se
omite silenciosamente ni se rellena con datos contemporáneos.

## Preparación

Desde la raíz del repositorio:

```bash
source .venv/bin/activate
uv sync --all-extras
python -c "import ee; ee.Initialize(project='exposome-api'); print('GEE OK')"
```

Si falla la autenticación:

```bash
earthengine authenticate
```

## Secuencia recomendada

Primero inspeccionar sin escribir ni descargar:

```bash
.venv/bin/python scripts/run_santiago_missing_annual_exposomes.py --status
```

Para ver las 103 combinaciones y la clasificación de las capas estáticas:

```bash
.venv/bin/python scripts/run_santiago_missing_annual_exposomes.py --dry-run
```

Después, ejecutar la recopilación completa. Es una tarea para el humano y se
recomienda dejarla durante la noche:

```bash
mkdir -p logs
caffeinate -i .venv/bin/python scripts/run_santiago_missing_annual_exposomes.py \
  --resume 2>&1 | tee logs/santiago_annual_exposomes.log
```

Para una sola fuente, `--layer` puede repetirse:

```bash
.venv/bin/python scripts/run_santiago_missing_annual_exposomes.py \
  --layer pm25 \
  --layer alan \
  --resume
```

Los identificadores aceptados son los de la primera columna de la tabla de
cobertura. Un identificador estático se rechaza en vez de ejecutar otro
pipeline por accidente.

## Interrupciones y fallos

- Cada año validado tiene `annual.csv` y `manifest.json` con SHA-256.
- Una repetición con `--resume` omite los manifiestos válidos.
- Los builders conservan sus caches por año, mes, comuna o componente según el
  proveedor; los archivos incompletos usan sufijo `.partial`.
- Si una fuente falla, se escribe `<layer>/<year>/failure.json`, continúa el
  resto del lote y el proceso termina con código distinto de cero.
- Para recuperarse se ejecuta exactamente el mismo comando. No se deben borrar
  caches ni usar `--no-resume` salvo durante una prueba controlada.

`coverage.csv` distingue `complete`, `source_cached` y `pending`. En el estado
local auditado el 18 de julio de 2026 había 20 años `source_cached`
(precipitación e incendios) y 83 pendientes de proveedor. El tiempo real
depende de las cuotas de GEE/Open-Meteo; debe presupuestarse una o más noches,
especialmente por viento y ERA5-Land.

## Validación del producto

Un año sólo se marca completo si:

- contiene exactamente 52 `spatial_id` únicos del estudio;
- incluye `spatial_name`, `year` y al menos una variable numérica finita;
- no contiene valores faltantes en las variables de exposición;
- su SHA-256 coincide con el manifiesto.

Los archivos originales producidos por cada builder se conservan bajo
`<layer>/<year>/builder/` para auditoría. `annual.csv` es la tabla normalizada
común; no implica que los indicadores de fuentes diferentes sean causalmente
comparables.
