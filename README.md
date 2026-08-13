# Santiago Urban Exposome Demo

Proyecto demostrativo para una postulación a **Data Scientist in Brain Health and Exposome Data Analysis**.

El objetivo es mostrar un flujo reproducible para construir indicadores comunales del **exposoma urbano** en la Región Metropolitana de Santiago, usando fuentes abiertas, geoprocesamiento en Python y salidas listas para integrarse con datos clínicos, cognitivos o epidemiológicos.

## Qué Demuestra

- Identificación y descarga de datos abiertos geoespaciales.
- Harmonización de indicadores en una unidad común: las 52 comunas de la RM.
- Construcción de capas ambientales, sociales e infraestructurales del exposoma.
- Exportación en formatos tabulares y GIS (`CSV`, `GeoJSON`, mapas `PNG/HTML`).
- Integración final en una tabla maestra lista para modelamiento estadístico.

## Pipeline Multi-Ciudad (En Migración)

Santiago sigue siendo el caso validado, pero el pipeline nuevo separa
**ubicación**, **estudio espacial** y **capacidad de cada capa**. Esto permite usar
comunas, códigos postales u otros polígonos sin duplicar scripts ni asumir que
todas las fuentes chilenas aplican fuera de Chile.

```bash
# Revisar polígonos, expected_units y rutas resueltas
exposome audit --study santiago_communes

# Preflight offline: muestra disponibilidad, advertencias y comandos
exposome run --study santiago_communes --dry-run

# Ejecutar/reanudar las capas habilitadas y construir el master del estudio
exposome run --study santiago_communes --resume

# Validar checksums de una entrega ya materializada
exposome verify --study santiago_communes
```

> **Scripts de recopilación de datos (`scripts/run_*.py`, `fetch_*.py`):** los
> asistentes de IA no los ejecutan — el humano los corre de noche. Deben tener
> barra de progreso, checkpoint incremental y resumen (skip-if-cached). Ver la
> política completa en [`AGENTS.md`](AGENTS.md#long-running-data-collection--assistants-do-not-run).

La configuración vive en `config/layers/` (defaults de proveedor),
`config/countries/` (overrides nacionales), `config/locations/`,
`config/studies/` y el catálogo `config/layers.yaml`. La precedencia es
layer → país → ubicación → estudio; ninguna ciudad hereda la configuración de
otra. La guía completa, incluido el contrato de polígonos y las limitaciones de
resolución, está en
[`docs/multicity_pipeline.md`](docs/multicity_pipeline.md).
La resolución que la app puede mostrar se rige por el manifest v3 de cada
bundle; ver la [decisión arquitectónica](docs/adr/0004-published-spatial-support-contract.md)
y el [runbook de publicación espacial](docs/knowledge/runbooks/publicar-resolucion-espacial.md).
La política de datos y artefactos está en [`data/README.md`](data/README.md), y
los gates para retirar los adaptadores históricos en
[`docs/architecture/v3_retirement_gates.md`](docs/architecture/v3_retirement_gates.md).

Las recolecciones largas también pueden ejecutarse en nodos auxiliares sin
convertirlos en repositorios paralelos. El primer nodo es WSL `BrainLat`,
asignado a Santa Marta, Cartagena y Pasto. Su
[runbook operativo](docs/knowledge/runbooks/nodo-wsl-descargas.md) y la
[arquitectura de handoff](docs/architecture/distributed-collection-nodes.md)
definen qué permanece local, qué se entrega y cómo se verificará antes de una
integración futura. La promoción por ciudad hasta preview y producción de GEMMA
se detalla en el
[runbook de integración](docs/knowledge/runbooks/integrar-nodo-wsl-en-gemma.md).

Para Buenos Aires, el flujo nativo y la consulta posterior por coordenadas están
documentados en
[`docs/caba_native_execution_plan.md`](docs/caba_native_execution_plan.md).

## Capas Del Exposoma

| Script | Factor | Indicadores principales | Fuente |
|---|---|---|---|
| **`scripts/run_air_quality.py`** | **Calidad del aire (Plan A+)** | **NO₂ columna + superficie [µg/m³], AOD** | **GEE: Sentinel-5P + MODIS + ERA5** |
| **`scripts/run_pm25.py`** | **PM₂.₅ crónico (alta resolución)** | **PM₂.₅ medio y ponderado por población [µg/m³], razón WHO** | **GEE: ACAG/van Donkelaar ~1 km (media 2015–2022)** |
| **`scripts/run_alan.py`** | **Luz artificial nocturna (ALAN)** | **radiancia media/mediana/sd/máx y ponderada por población [nW/cm²/sr]** | **GEE: VIIRS DNB + WorldPop** |
| **`scripts/run_precipitation.py`** | **Precipitación** | **lluvia anual, días húmedos/intensos, RX1/RX5, rachas secas/húmedas, anomalía 2024** | **GEE: CHIRPS diario** |
| **`scripts/run_sleep_context.py`** | **Contexto sueño-circadiano** | **índice ambiental 0-100 basado en ALAN, noches cálidas y vulnerabilidad** | **Capas procesadas + ENS/ENUT como contexto regional** |
| **`scripts/run_wildfire.py`** | **Desastres climáticos — incendios forestales** | **área quemada km²/%, recurrencia, focos activos, índice de exposición 0-100** | **GEE: MODIS MCD64A1 + FIRMS (+ CONAF opcional)** |
| **`scripts/run_heavy_metals.py`** | **Metales pesados industriales (RETC)** | **Pb, As, Hg en kg/yr; log(Pb+1); índice compuesto; n fuentes** | **MMA RETC — fuentes puntuales 2015–2022** |
| **`scripts/run_neuro_mortality.py`** | **Comparador sanitario — mortalidad neurológica** | **tasas comunales de demencia, Alzheimer, ACV y parkinsonismo** | **DEIS defunciones** |
| **`scripts/run_neuro_hospitalizations.py`** | **Comparador sanitario — egresos neuropsiquiátricos** | **tasas comunales de hospitalización mental, ACV, demencia, ánimo, psicosis, sustancias** | **DEIS egresos hospitalarios** |
| `scripts/run_air_quality.py` | Calidad del aire | NO₂ columna + superficie [µg/m³], AOD | GEE: Sentinel-5P + MODIS + ERA5 |
| `scripts/run_greenspace_access.py` | Áreas verdes | % área verde, km2, número de polígonos | OpenStreetMap |
| `scripts/run_healthcare.py` | Acceso a salud | conteos, densidad, distancia media/mediana/P90 a salud y hospital | OpenStreetMap |
| `scripts/run_socioeconomic.py` | Nivel socioeconómico | pobreza, ingreso, escolaridad, índice NSE | CASEN/SAE vía datos abiertos |
| `scripts/run_climate_heat.py` | Clima/calor urbano | Tmax verano, días >=30/35 C, noches cálidas, índice de calor | Open-Meteo Historical |

## Mejora de calidad del aire — Plan A+ (satélite + conversión física)

Identificamos que la fuente CAMS usada en el notebook original tiene **resolución ~11 km**, lo que agrupa ~20 comunas en el mismo valor y oculta el gradiente intra-urbano.

Implementamos un **pipeline configurable** que integra satélites de mayor resolución y los convierte a unidades epidemiológicamente interpretables:

```bash
# Requiere entorno 'exposome' con GEE autenticado
python scripts/run_air_quality.py
```

**Qué hace:**
1. Lee la configuración de ciudad desde `config/cities/santiago.yaml`.
2. Usa los límites comunales ya procesados (evita re-descargar de OSM).
3. Extrae **NO₂ troposférico** de **Sentinel-5P TROPOMI** (~3.5 km) vía Google Earth Engine.
4. Extrae **AOD** (profundidad óptica de aerosoles) de **MODIS MCD19A2** (~3 km).
5. Extrae **altura de capa de mezcla** (BLH) de **ERA5** para convertir NO₂ columna → **concentración superficial en µg/m³**.
6. Calcula estadísticas zonales por comuna y exporta `data/processed/santiago_air_quality_satellite_2024.{csv,geojson}`.

**Figura evolutiva de tres paneles:**

![CAMS 11 km vs satélite columna vs satélite µg/m³](figures/air_quality_plan_a_plus_3panel.png)

> **Panel A:** CAMS legacy (~11 km) en µg/m³. **Panel B:** Sentinel-5P columna (mol/m²) — más detalle espacial pero unidades no comparables. **Panel C:** Plan A+ — mismo detalle espacial pero convertido a µg/m³ mediante BLH de ERA5, directamente comparable con guías WHO.

**Metodología completa:** `docs/plan_a_plus_methodology.md` explica la física de la conversión, los supuestos, las limitaciones y las referencias.

**Plan B (futuro):**  Documentado en `docs/plan_b_downscaling.md`.  Consiste en un modelo de ML espacial (Random Forest / XGBoost) que calibra el proxy satelital con estaciones SINCA para llegar a **~1 km de resolución** y estimar PM₂.₅ y NO₂ de superficie.

## Luz artificial nocturna (ALAN) — VIIRS DNB

Nueva capa del exposoma urbano, especialmente relevante para salud cerebral (disrupción circadiana, supresión de melatonina, sueño → deterioro cognitivo, demencia, depresión, ACV). Se construye con la banda Día/Noche de VIIRS vía GEE y se pondera por población (WorldPop).

```bash
# Requiere entorno 'exposome' con GEE autenticado
python scripts/run_alan.py        # capa comunal santiago_alan_viirs_2024.{csv,geojson}
python scripts/plot_alan_map.py   # figura de 4 paneles
```

![ALAN — coropleta ponderada por población, ranking y validez de constructo](figures/alan_santiago_4panel.png)

> **A)** Radiancia ponderada por población (escala log): centro denso brillante, periferia rural oscura. **B)** Ranking de las 52 comunas. **C)** Validez de constructo vs NO₂ de superficie (Spearman ρ≈+0.87). **D)** Gradiente socioeconómico de la exposición a luz.

**Metodología completa:** `docs/alan_methodology.md`.

## PM₂.₅ crónico de alta resolución — ACAG vía GEE

PM₂.₅ es la exposición ambiental #1 ligada a demencia (Lancet Commission 2024).
El repo ya estimaba NO₂ de superficie a ~3.5 km, pero su único PM₂.₅ venía del
CAMS legacy (~11 km), que agrupa ~20 comunas en el mismo valor. Esta capa lo
reemplaza por PM₂.₅ satelital **ACAG/van Donkelaar a ~1 km**, promediado en una
ventana **crónica 2015–2022** (la ventana de exposición correcta para
envejecimiento cerebral), accedido como *asset* del mismo Google Earth Engine que
ya usa el proyecto (sin API key adicional) y ponderado por población (WorldPop).

```bash
# Requiere entorno 'exposome' con GEE autenticado
python scripts/run_pm25.py          # santiago_pm25_acag_2015_2022.{csv,geojson,json}
python scripts/build_master_exposome.py  # PM₂.₅ pasa a ser el pm25_* canónico del master
python scripts/plot_pm25_map.py     # figura de 4 paneles (mapa, ranking, validación, NSE)
```

Indicadores: `pm25_mean`, `pm25_pop_weighted`, `pm25_who_ratio`. La validación
contra estaciones SINCA es opcional (deja `data/raw/stations_sinca/sinca_pm25_annual.csv`
con `station, lat, lon, pm25`); sin ese archivo la figura cae a validez de
constructo vs NO₂. El PM₂.₅ grueso de CAMS se retira del master pero se conserva
el CSV/figura legacy para la comparación CAMS-vs-satélite.

**Metodología completa:** `docs/pm25_methodology.md`.

## Precipitación — CHIRPS diario

Nueva capa comunal de precipitación para vigilar humedad, sequía y eventos de
lluvia intensa como exposiciones ambientales candidatas para análisis
cerebro-exposoma. La capa usa CHIRPS diario vía Google Earth Engine y resume
2015-2024 por comuna.

```bash
# Requiere entorno 'exposome' con GEE autenticado
python scripts/run_precipitation.py       # santiago_precipitation_chirps_2015_2024.{csv,geojson,json}
python scripts/plot_precipitation_maps.py # figura de 4 paneles
```

Indicadores principales: precipitación anual media, variabilidad interanual,
días húmedos, días con lluvia >=10/20 mm, RX1day, RX5day, rachas secas/húmedas,
lluvia de invierno/verano, anomalía del año más reciente e índice de extremos
0-100. La capa queda integrada al master como exposición exploratoria lista
para cruzarse con cohortes, neuropsicología, biomarcadores o neuroimagen.

**Metodología completa:** `docs/precipitation_methodology.md`.

## Contexto sueño-circadiano

Nueva capa comunal que resume condiciones urbanas asociadas a peor sueño, sin
estimar horas de sueño ni prevalencia clínica por comuna. Combina luz artificial
nocturna ponderada por población, noches tropicales, temperatura mínima de
verano y vulnerabilidad social en un índice 0-100.

```bash
python scripts/build_master_exposome.py  # asegura insumos integrados
python scripts/run_sleep_context.py      # data/processed/santiago_sleep_context.{csv,geojson}
python scripts/build_master_exposome.py  # incorpora sleep_* al master
python scripts/plot_sleep_context.py     # figura diagnóstica opcional
```

La ENS/ENUT se usa como evidencia y validación regional, no como imputación
comunal. **Metodología completa:** `docs/sleep_context_methodology.md`.

## Metales pesados industriales — RETC (MMA)

Nueva capa de **toxinas industriales** para investigación en salud cerebral.
El Plomo (Pb) es el neurotóxico #1 de la Lancet Commission 2024; el Arsénico
(As) y el Mercurio (Hg) tienen evidencia emergente de daño al SNC.

```bash
python scripts/run_heavy_metals.py   # santiago_heavy_metals_retc_2015_2022.{csv,geojson,json}
python scripts/plot_heavy_metals_map.py  # figura de 4 paneles
```

Fuente: **RETC MMA** (`datosretc.mma.gob.cl`), emisiones al aire de fuentes
puntuales 2015–2022, licencia CC-BY, sin API key. Geocodificación por
punto-en-polígono comunal con fallback a comuna más cercana.

Hallazgos clave:
- **Tiltil** concentra ~99.6% de las emisiones de Pb del RM (~10,629 kg/yr),
  correspondiente a un complejo industrial conocido.
- **Mn y Cd = 0 en RM**: sus fuentes industriales están en otras regiones
  (Atacama, Maule) — hallazgo real, no error.
- **Pb vs PM₂.₅**: ρ = −0.15 (p = 0.30, n.s.) — las fuentes industriales
  y la combustión de fondo **no co-localizan**, confirmando que RETC añade
  información exposómica independiente.

Indicadores: `hm_pb_kg`, `hm_as_kg`, `hm_hg_kg`, `hm_pb_log`, `hm_as_log`,
`n_sources`, `hm_index` (z-score ponderado). **Metodología completa:**
`docs/heavy_metals_methodology.md`.

## Comparadores Sanitarios DEIS

Los archivos de defunciones y egresos hospitalarios se usan como desenlaces
ecológicos externos, no como capas del exposoma. Los CSV crudos grandes viven en
`data/raw/deis/` y no se versionan en git.

```bash
python scripts/run_neuro_mortality.py
python scripts/compare_neuro_mortality_exposome.py

python scripts/run_neuro_hospitalizations.py
python scripts/compare_neuro_hospitalizations_exposome.py
```

La mortalidad sirve mejor para desenlaces neurológicos duros (demencia,
Alzheimer, ACV, parkinsonismo). Los egresos hospitalarios son la fuente más útil
para morbilidad mental no fatal (trastornos del ánimo, psicosis, sustancias,
ansiedad/estrés). **Metodología completa:** `docs/neuro_outcomes_methodology.md`.

La inferencia exposoma–hospitalizaciones orientada a publicación tiene un CLI
separado, no reprocesa microdatos y persiste cada modelo MCMC de forma reanudable.
Es un análisis offline: no entra al master, la API, los exportadores ni la app,
y finalizar la inferencia no publica ningún artefacto web:

```bash
uv sync --all-extras
.venv/bin/python scripts/run_hospitalization_inference.py --mode classical
.venv/bin/python scripts/run_hospitalization_inference.py --mode publication --phase status
.venv/bin/python scripts/run_hospitalization_inference.py --mode publication --phase primary --resume
```

Las fases restantes, el control negativo obligatorio y los criterios de
aceptación están documentados en
[`docs/hospitalization_inference_protocol.md`](docs/hospitalization_inference_protocol.md).
La cobertura histórica disponible, los años aún no materializados y su prioridad
están inventariados en
[`docs/hospitalization_exposure_temporal_coverage.md`](docs/hospitalization_exposure_temporal_coverage.md).
El descargador reanudable de exposomas anuales de Santiago, que no ejecuta
ningún análisis ni publica en la app, está documentado en
[`docs/santiago_annual_exposome_downloads.md`](docs/santiago_annual_exposome_downloads.md).

---

## Salida Principal

La salida integrada canónica de Santiago está en
`data/processed/cl/santiago/santiago_communes/`:

- `master.csv`: tabla integrada con `spatial_id` (CUT) como clave y `name` como
  alias de compatibilidad.
- `master.geojson`: la misma tabla con geometría comunal.
- `master_metadata.json` y `master_coverage.csv`: procedencia y cobertura.
- `release_manifest.json`: checksums de capas, figuras y master.

Cada capa tiene su propio directorio y `manifest.json`; los datos no se
versionan en Git. Materializa o regenera una release y compruébala antes de
usarla:

```bash
exposome run --study santiago_communes --resume
exposome verify --study santiago_communes
```

## Estructura Del Repositorio

```text
config/          ubicaciones, estudios espaciales y catálogo de capas
src/exposome/    contratos y módulos importables del pipeline
notebooks/       análisis reproducibles con outputs agregados y seguros
data/reference/  contratos espaciales pequeños, versionados
data/processed/  releases canónicas por país/ciudad/estudio (no versionadas)
figures/         artefactos históricos; figuras activas viajan con cada capa
webapp/           aplicación y bundles publicados (generados)
docs/            documentos auxiliares de postulación
scripts/         utilidades reproducibles, incluida la integración maestra
```

## Vault de conocimiento (Obsidian)

La raíz del repositorio puede abrirse directamente como un vault de Obsidian.
La portada compartida está en
[`docs/knowledge/00-inicio.md`](docs/knowledge/00-inicio.md) y conecta capas,
metodologías, estudios, ADR, runbooks y minutas de reuniones.

Las fichas bajo `docs/knowledge/generated/` se regeneran desde el estado y los
YAML canónicos:

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/build_obsidian_knowledge.py --write
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/build_obsidian_knowledge.py --check
```

Las transcripciones crudas y notas personales se guardan en `local-notes/`, que
está ignorado por Git. No se requiere MCP ni plugins comunitarios.

## Outputs Relevantes

| Ruta canónica | Contenido |
|---|---|
| `.../master.csv` | exposoma comunal integrado |
| `.../air_quality_pm25/manifest.json` | PM₂.₅ ACAG y sus assets |
| `.../alan/manifest.json` | luz artificial nocturna y figura diagnóstica |
| `.../precipitation/manifest.json` | precipitación CHIRPS y serie diaria de entrada |
| `.../neuro_mortality/manifest.json` | comparador comunal DEIS |
| `.../release_manifest.json` | inventario verificable de la release |

En la tabla, `...` es `data/processed/cl/santiago/santiago_communes`. Los
archivos planos con `rm_santiago` son solamente baseline de migración y no
deben ser consumidos por código nuevo.

## Reproducibilidad

### Entorno de desarrollo (`.venv` con `uv`, Python 3.12)

El proyecto usa un único entorno virtual gestionado con **`uv`**, Python 3.12, configurado para soportar Google Earth Engine, OpenAQ y el stack geoespacial completo. `pyproject.toml`/`uv.lock` son la única fuente de verdad de dependencias — no hay entorno Conda.

```bash
# Crear/sincronizar (crea .venv si no existe)
uv sync --all-extras

# Activar
source .venv/bin/activate

# Verificar
python -c "import ee; ee.Initialize(project='exposome-api'); print('GEE OK')"
```

`uv sync` elimina los extras no solicitados. En esta instalación compartida se
usa siempre `--all-extras`, y no se sincroniza `.venv` mientras haya una corrida
larga de Python activa.

> Al agregar un import nuevo, agregá el paquete a `pyproject.toml` y corré `uv sync --all-extras` de nuevo — instalar con `pip install` directo en `.venv` no queda registrado y se pierde en el próximo `uv sync`.

Orden reproducible recomendado: `exposome run --study <study>` (o el runner
específico documentado en `config/layers.yaml`), luego `exposome publish
--study <study>`. Las rutas de datos y cachés se resuelven desde el estudio;
no se requieren notebooks ni mapas HTML generados.

> **Google Earth Engine:** El entorno `exposome` está preconfigurado con GEE y el proyecto `exposome-api`. Si necesitas reautenticar, ejecuta `earthengine authenticate` dentro del entorno activado.

## Decisiones Metodológicas

Las siguientes decisiones describen el caso legacy validado de Santiago. Los
nuevos estudios obtienen unidad espacial, conteo esperado y CRS desde su YAML y
normalizan las claves a `spatial_id`/`spatial_name`.

- Unidad geográfica común: comuna (`name`).
- CRS métrico para áreas/distancias: `EPSG:32719`.
- CRS de exportación GIS: WGS84 (`EPSG:4326`).
- Acceso a salud: distancias calculadas sobre grilla intra-comunal de 1 km.
- Calor urbano: proxy residencial = media de la **banda baja (valle poblado, ≤300 m sobre el punto más bajo)** de cada comuna, excluyendo píxeles de alta cordillera que sesgarían a las comunas precordilleranas grandes (San José de Maipo, Lo Barnechea); punto representativo como fallback para comunas pequeñas sin grilla interior.
- Precipitación: medias areales comunales de CHIRPS diario 2015-2024; los indicadores resumen lluvia crónica, extremos y anomalía 2024 como exposiciones candidatas, no como outcome cerebral.
- Tabla maestra: merge `one_to_one` por nombre de comuna y validación estricta de 52 filas sin missing.

## Limitaciones

- Los indicadores son ecológicos/comunales; no reemplazan exposición individual residencial exacta.
- OpenStreetMap puede tener subregistro diferencial por comuna.
- Las capas climáticas y de aire provienen de reanálisis/grillas, no de micro-sensores intraurbanos.
- El apéndice Google Earth Engine en clima/verde es opcional y requiere autenticación externa.

## Relevancia Para Investigación En Exposoma

Este proyecto traduce una necesidad de investigación en exposoma urbano a un prototipo funcional: toma fuentes abiertas, genera indicadores ambientales/sociales/infraestructurales, los harmoniza en una unidad común y produce una base lista para cruzarse con cohortes, datos cognitivos, biomarcadores o neuroimagen.
