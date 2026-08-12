# Series temporales multi-ciudad

## Contrato

La recopilación anual es común a cualquier estudio agregado y vive en
`src/exposome/temporal_exposomes.py`. El comando principal es:

```bash
.venv/bin/python scripts/run_missing_annual_exposomes.py --study <study> --status
```

`scripts/run_santiago_missing_annual_exposomes.py` se conserva como wrapper
compatible. Los archivos locales sólo se descubren bajo las rutas canónicas del
estudio y con su `study_id`; el fallback histórico de incendios de Santiago sólo
se permite para `santiago_communes`.

Cada producto completo contiene `annual.csv`, sus detalles espaciales exigidos
y `manifest.json`, con todos los `spatial_id`, año, valores finitos y SHA-256.
`--local-only` sólo completa métodos administrativos; una tabla local de lluvia
permanece `source_cached` hasta producir sus COG CHIRPS anuales.

Las nueve parejas aggregate/native publicables están declaradas en
`config/operations/multicity_14.yaml`. El inventario incluye Santiago, Lima,
Bogotá, Valle de Aburrá, Medellín, CDMX, São Paulo, AMBA y comunas de Buenos
Aires. La fase temporal descubre los métodos habilitados por estudio, no una
lista codificada por ciudad.

## Lima y Medellín

Cada estudio declara 83 productos capa-año para 2015–2024:

- 20 completos localmente: 10 de precipitación y 10 de incendios;
- 63 remotos: PM2.5, calidad del aire satelital, ALAN, dos productos de verde,
  calor y viento.

Estado de sólo lectura:

```bash
.venv/bin/python scripts/run_missing_annual_exposomes.py --study lima_distritos --status
.venv/bin/python scripts/run_missing_annual_exposomes.py --study medellin_comunas --status
```

Recopilación remota nocturna (la ejecuta una persona):

```bash
caffeinate -i .venv/bin/python scripts/run_missing_annual_exposomes.py \
  --study lima_distritos --resume
caffeinate -i .venv/bin/python scripts/run_missing_annual_exposomes.py \
  --study medellin_comunas --resume
```

No se generan series para snapshots OSM ni para el dosel Meta estático. Tampoco
se publican como anuales los índices compuestos de calor o lluvia; se exponen sus
métricas observables.

## Publicación web

`exposome publish` transforma cada `annual.csv` validado en JSON tabular bajo
`annual/`, sin repetir las geometrías. El `manifest.json` del bundle declara
`temporal_indicators`, que asocia exposoma, columna, años, archivo, checksum y
procedencia, además del COG o GeoJSON específico de cada cosecha cuando el
método ofrece detalle. El navegador une los registros al master por
`spatial_id`, pero renderiza el detalle anual como geometría de valores.

El selector anual usa primero este contrato. Para bundles antiguos conserva la
compatibilidad con `has_annual` y `year_columns`. Los perfiles territoriales
incluyen los mismos valores bajo `profile.timeseries`. Si una serie marcada
`required_for_production` está incompleta, publicación y selector se bloquean;
no hay fallback comunal por año.

Plan nocturno reanudable para todas las ciudades (lo ejecuta una persona):

```bash
caffeinate -i .venv/bin/python scripts/run_multicity_overnight.py \
  --phase temporal --max-hours 10
```

El mismo comando se repite hasta que no queden tareas diferidas. Para una sola
ciudad se añade `--city santiago` o el `study_id` agregado.

## Gate de procedencia y secuencia de publicación

Los artefactos actuales requieren una corrida humana antes de publicar: calor
de Lima debe pasar de Open-Meteo a ERA5-Land y viento 2024 debe regenerarse en
ambas ciudades con la colección ERA5-Land vigente. La publicación rechaza un
sidecar cuya fuente contradiga la configuración resuelta.

```bash
# Recopilación remota: ejecutar por una persona
.venv/bin/python scripts/run_climate_fetch.py \
  --city lima_distritos --years 2024 \
  --cache-dir cache/pe/lima/lima_distritos/climate_heat \
  --out-dir data/processed/pe/lima/lima_distritos/climate_heat
.venv/bin/exposome run --study lima_distritos \
  --layers climate_heat,wind --force --no-build-master
.venv/bin/exposome run --study medellin_comunas \
  --layers wind --force --no-build-master

# Reconstrucción local y verificación
.venv/bin/exposome run --study lima_distritos --resume
.venv/bin/exposome run --study medellin_comunas --resume
.venv/bin/exposome verify --study lima_distritos
.venv/bin/exposome verify --study medellin_comunas

# Perfiles, bundles y derivados web
.venv/bin/python scripts/export_study_profiles.py \
  --study lima_distritos --study medellin_comunas
.venv/bin/exposome publish --study lima_distritos --study medellin_comunas
.venv/bin/python scripts/export_webapp_distributions.py
```

Después se validan los paneles informativos por bundle y la aplicación real en
navegador. Un selector raster temporal sólo aparece si el bundle declara y
verifica **todos** sus `expected_years`.
