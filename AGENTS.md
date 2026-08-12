# AGENTS.md — BrainLat Exposome Demo

High-signal guidance for agents working in this repo.

## Environment (critical)

**One environment: `.venv`, managed by `uv`, Python 3.12.** `pyproject.toml` is the
single source of truth for dependencies (`uv.lock` pins the resolution). There is
no conda/mamba environment anymore — the old `.conda/envs/exposome` and the
deprecated `.conda/envs/brainlat` (Python 3.11) were retired in favor of this one,
because running two parallel environments let real dependencies (e.g. `xlrd`)
get installed ad-hoc into conda without ever being declared anywhere, which then
broke on a fresh checkout.

```bash
# Create/sync if missing or after a dependency change
uv sync --all-extras

# Activate
source .venv/bin/activate

# Verify GEE
python -c "import ee; ee.Initialize(project='exposome-api'); print('GEE OK')"
```

`uv sync` is exact: requesting only one extra removes packages that belong to
other extras. Always use `--all-extras` for this single shared environment, and
never synchronize `.venv` while a long-running Python process is active.

If GEE auth fails, run `earthengine authenticate` inside the activated env and
complete OAuth in browser.

`climate_lst_ecostress` (ECOSTRESS) is the one layer that does **not** go
through GEE — Earth Engine hosts `ECO_L2T_LSTE` but has ingested only Los
Angeles tiles, so Latin American cities must come from NASA Earthdata. It needs
a second credential, from a free Earthdata Login account
(<https://urs.earthdata.nasa.gov>). Note that **`earthaccess` ships no CLI** —
there is no `earthaccess login` command. Authenticate once with:

```bash
.venv/bin/python -c "import earthaccess; earthaccess.login(strategy='interactive', persist=True)"
```

That prompts for username/password and persists them to `~/.netrc`.
Alternatively export `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD`, or
`EARTHDATA_TOKEN`. It is interactive, so a human runs it — never an agent.
Declare the `earthdata` capability when preflighting that layer. See
`docs/evaluacion_fuentes_nasa.md`.

When you add a new import, add the package to `pyproject.toml`'s `dependencies`
(or the `dev` extra for test/lint-only tools) and run `uv sync --all-extras` —
never `pip install` directly into `.venv`, or the dependency silently stops
being reproducible for the next checkout.

## Project Structure & Execution

- **Run everything from repo root** — commands resolve study paths under `data/`, `cache/` and `webapp/public/data/`.
- `cache/`, `tmp/`, `.conda/` are gitignored. Do not commit them.
- `src/exposome/` + `exposome run/publish` are the active compute and publication interfaces.
- Settings compose as `config/layers/` → `config/countries/` → location → study.
  Do not add a city-to-city `legacy_city_config` dependency.
- Versioned spatial references live in `data/reference/<iso2>/<city>/<study>/`;
  raw downloads are provider/version-scoped under `data/raw/`.
- A normalized layer directory contains `manifest.json`; integrated study
  outputs contain `release_manifest.json` beside the master.
- Canonical runtime accepts only schema-v2 Layer bundles and Study releases.
  Bare CSVs and v1 manifests require the explicit local migrator under
  `scripts/migrations/`; run/resume/master/publish never adopt them implicitly.
- Durable provider payloads live in immutable, manifested
  `data/raw/<provider>/<dataset>/<version>/` snapshots. `cache/` is evictable
  operation state and never a source of record.
- `scripts/build_master_exposome.py` remains a Santiago compatibility adapter while studies migrate to canonical paths.

## Long-running data collection — assistants DO NOT RUN

**Policy: AI assistants never execute data-collection scripts.** These hit GEE,
Open-Meteo, OSM/Overpass, or Esri tile servers and can run for tens of minutes to
hours; running them burns tokens for no reason since the assistant just waits.
Instead, an assistant prepares the exact command(s) and hands them to the human,
who runs them overnight. This applies to every `scripts/run_*.py` / `fetch_*.py`
below — reading their code, editing them, or running a fast unit test against
them is fine; invoking them against real data is not.

Every long-running script must satisfy three requirements:

1. **Progress bar** (`tqdm`) over the main loop (years / communes / tiles) so
   the human can see it's alive during an overnight run.
2. **Incremental checkpoint** — persist to `cache/` after each unit of work
   (each year, each commune), not once at the end of the loop. A script that
   only writes its cache after the whole loop finishes is **not** crash-safe: a
   Ctrl-C mid-loop loses every unit fetched in that run. Save after each
   iteration instead.
3. **Resume / skip-if-cached** — on re-run, diff the requested keys (years,
   communes, tiles) against what's already in the `cache/` file and only fetch
   what's missing. Most modules already do this half of the contract via a
   `.exists()` guard; see `src/exposome/walkability.py`'s `build_walkability_layer`
   (per-commune checkpoint), `src/exposome/healthcare.py`'s
   `fetch_healthcare_osm` (per-tag checkpoint), or `src/exposome/wildfire.py`'s
   `fetch_annual_metrics` (per-year checkpoint) for reference implementations —
   there is no single shared helper, each module implements this inline.

Scripts by provider group (⚠️ = does not yet meet all three requirements):

| Group | Scripts | Notes |
|---|---|---|
| GEE (year/commune loops) | `run_air_quality_satellite.py`, `run_pm25.py`, `run_alan.py`, `run_precipitation.py`, `run_precipitation_spi.py`, `run_precipitation_annual.py` ⚠️, `run_wildfire.py`, `run_wind.py`, `run_greenspace_coverage.py`, `run_greenspace_multisource.py`, `run_climate_lst.py`, `run_climate_heat.py`, `run_climate_metrics.py` ⚠️, `run_climate_fetch.py` | Per-year/per-step `cache/<city>_<layer>_*.csv`; skip-if-cached. `run_wildfire.py` was the original tqdm+per-year reference; `run_pm25.py`, `run_alan.py`, `run_wind.py`, `run_air_quality_satellite.py` (step-bar over each cached GEE call), `run_greenspace_coverage.py`/`run_greenspace_multisource.py` (added a zonal-stats CSV cache + step-bar — previously a single uncached `reduceRegions` call), `run_precipitation.py`/`run_climate_lst.py`/`run_climate_fetch.py` (year-bar; `run_climate_fetch.py`'s ERA5-Land also gets a nested month-bar, no new per-month checkpoint — CPU-cheap to redo within a year) now match the contract too. `run_precipitation_annual.py` and `run_climate_metrics.py` (climate_openmeteo layer) are untouched, still ⚠️. `run_precipitation_spi.py`'s main path is 100% local compute over already-cached CHIRPS (no progress bar needed); only its `--monitor` mode (live Open-Meteo per-commune loop) got a step-bar, plus a portability fix — it hardcoded Chile's `EPSG:32719` for centroid projection instead of the study's own `cfg["crs"]["metric"]`. |
| **`run_climate_heat.py` gating fix** | `src/exposome/climate/build_layer.py::build_climate_heat_layer` | The importable runner (`src/exposome/runners.py`) calls this function directly, bypassing this script's `--fetch-missing` pre-step entirely. Until now that made `build_climate_heat_layer` crash with `FileNotFoundError` on any city with no pre-existing `climate_heat_grid_daily_<year>.csv` (e.g. a first CDMX run) — the cache-first docstring was true only via the subprocess wrapper. `build_climate_heat_layer` now calls `ensure_grid_daily` itself before `load_daily` when `source="openmeteo"`, so the importable runner path is resume-safe too; this script's own pre-fetch becomes a no-op once the cache exists. |
| Open-Meteo HTTP (rate-limited) | `run_climate_openmeteo.py`, `run_climate_heat_annual.py`, `run_air_quality.py` (legacy CAMS/Open-Meteo Air Quality API — not GEE despite the name; see line ~180 below, historically stale) | 429 backoff already implemented; per-commune/per-year cache files; `run_air_quality.py` checkpoints per 40-point chunk to a `.partial` cache |
| OSM / Overpass (osmnx) | `run_greenspace_access.py`, `run_healthcare.py`, `run_walkability.py`, `run_public_transport.py`, `run_social_infrastructure.py`, `run_food_environment.py` | osmnx caches raw HTTP responses in `cache/` automatically; layer-level checkpoint is still per-script |
| Esri tiles | `run_greenspace_cv.py` | Per-tile jpg cache in `cache/`, plus a scene-level tqdm bar over the sample-point loop; explicitly documented as "intended for overnight runs" |
| Local files (fast, not gated by this policy) | `fetch_indec_population.py`, `run_demography.py`, `run_heavy_metals.py`, `run_socioeconomic.py`, `run_pobreza_sae.py`, `run_food_insecurity.py`, `run_community_safety.py`, `run_argentina_outcomes.py`, `run_neuro_mortality.py`, `run_neuro_hospitalizations.py`, `run_noise.py` | Read pre-downloaded local/GitHub-raw CSVs; no meaningful rate limit or long loop |

### Exposome Status & Review Tracking

- `docs/exposome_status.csv` is the editable tracking table for layer review state.
- `docs/exposome_status.md` is the human-readable dashboard generated from the CSV.
- `scripts/audit_exposome_status.py` regenerates and checks the dashboard from `LAYER_SPECS`, processed outputs, metadata, methodology docs, figures, and prompts.
- `docs/review_prompts/<layer_id>.md` contains one prompt per layer for separate Codex/Claude/OpenCode review sessions; `_template.md` documents the shared checklist.
- The status table currently tracks 21 master layers plus validation/comparator rows (`greenspace_cv`, `neuro_mortality`, `neuro_hospitalizations`).
- Manual review fields are preserved when regenerating: `review_status`, `review_tool`, `review_date`, `review_doc`, `blockers`, `next_action`, `final_check`.
- Do not set `final_check=true` unless the layer has valid 52-commune output, required columns, reproducibility notes, methodology/limitations, visual diagnostic where applicable, and master integration when applicable.

Regenerate after adding/changing layers:
```bash
PYTHONPYCACHEPREFIX=/tmp python3 scripts/audit_exposome_status.py --write
PYTHONPYCACHEPREFIX=/tmp python3 scripts/audit_exposome_status.py --check
```

Run tests with the project environment:
```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest discover -s tests
```

### Study Execution

Use `config/studies/<study>.yaml` as the source of truth:

```bash
exposome run --study santiago_communes --dry-run
exposome run --study santiago_communes --resume
exposome publish --study santiago_communes --study caba_native
exposome verify --study santiago_communes
```

Country-specific layers remain explicitly unavailable when their provider does
not cover the selected country; they must not silently reuse Santiago data.

## Webapp — Resolución espacial por exposoma

La autoridad es `manifest.json.spatial_indicators` de **cada bundle publicado**
(`schema_version: 3`), no `palette.json` ni el flag legacy `has_fine_layer`.
Una ciudad puede tener PM2.5 nativo y otra sólo agregado administrativo; el
catálogo global no puede decidir el soporte del mapa.

**No todos los exposomas de todas las ciudades están publicados a resolución de
origen.** Procesar una fuente sobre su grilla nativa no equivale a publicar sus
píxeles: si `detail` es `null`, el producto web es administrativo.

Cada indicador separa cuatro conceptos:

- `downloaded`: producto o grilla obtenida;
- `observation`: huella física de una observación;
- `analysis`: soporte donde se calculó el valor;
- `rendered`: geometría que la app muestra realmente.

`detail: null` implica mapa administrativo. Un detalle COG sólo se anuncia si
el descriptor y su sidecar prueban `canonical_resolution_verified: true`, la
misma `source_native_resolution_m` y `source_support_preserved: true`. Verde
usa GeoJSON sólo con `grid_alignment: study_aoi_metric_grid`. Ruido España usa
MVT sólo con descriptor `vector_contours`, hashes de fuente, validación de área
por banda y presupuestos de tesela; al ser vectorial no declara resolución en
metros. El frontend vuelve a administrativo si falta cualquiera de esas pruebas.

| Exposoma | Fuente/observación | Detalle permitido |
|---|---|---|
| PM2.5 | ACAG 0,01° (≈1.113 m) | COG ACAG canónico |
| NO₂ | grilla S5P 1.113 m; huella TROPOMI ≈3,5 × 5,5–7 km | COG de columna troposférica en `mol/m²` |
| ALAN | VIIRS DNB 463,83 m | COG canónico; un TIFF histórico a 500 m no se publica |
| Viento | ERA5-Land 11.132 m | COG de banda velocidad; un TIFF ERA5 a 9 km no se publica |
| Verde | Dynamic World 10 m; estimador por celda estable de 1 km muestreado a 30 m | GeoJSON real reanudable |
| Ruido España | polígonos MER/SICA Lden 2022 en EPSG:3035 | MVT categórico `vector_contours`, zooms 11--15, sin resolución raster inventada |
| Calor/lluvia/incendios/OSM/administrativos | soporte propio de cada fuente | administrativo hasta publicar un activo verificable específico |

**Reglas:**

- La UI etiqueta el `rendered`; FUENTE/DESCARGAR pueden informar además el
  producto original como «fuente», nunca como «Mapa».
- Los límites administrativos son máscara, consulta o agregación; no crean
  píxeles ni aumentan resolución. `mask_only` se reserva a detalle nativo;
  `analysis_unit` identifica un resumen zonal; `source_unit`, una fuente que ya
  era administrativa; `component_specific`, un compuesto sin escala única.
- Las fuentes vectoriales OSM no reciben una falsa resolución raster. Salud e
  infraestructura social sí tienen grilla analítica de 1 km; caminabilidad,
  comida y acceso verde se publican administrativamente.
- `resolution_warning` puede ser correcto cuando la fuente es más gruesa que la
  unidad. Nunca se elimina sobremuestreando.
- Cambiar colección, banda, escala o periodo debe invalidar el caché mediante
  su namespace. `--force` no sustituye esa garantía.
- Antes de desplegar: `exposome spatial-audit --all --strict`.
- Los cuatro modos de mapa (polígono administrativo, grilla GeoJSON, COG y
  contornos vectoriales MVT)
  comparten un único tooltip: nombre de unidad, métrica, valor/unidad y soporte
  realmente renderizado. La leyenda usa un ancho instrumental fijo de 320 px;
  nombres largos se envuelven sin cambiar el largo de la barra de color.

Decisión: `docs/adr/0004-published-spatial-support-contract.md`. Procedimiento e
incidentes: `docs/knowledge/runbooks/publicar-resolucion-espacial.md`. Inventario
vigente e historia: `docs/resolution_manifest.md`.

**Series temporales (selector de año):**
- `manifest.temporal_indicators` es el contrato moderno. Un año sólo puede
  activar `years.<año>.detail` si su `temporal_support.year` coincide. Nunca se
  reutiliza un COG estático o promedio para una cosecha anual.
- Para series con `spatial_target.required_for_production: true`, la publicación
  exige detalle verificable para **todos** los `expected_years`. Si falta uno,
  producción falla y la app oculta el selector completo; no cambia
  silenciosamente a polígonos administrativos. Esto aplica a COG raster y a
  grillas analíticas GeoJSON.
- Sólo las series cuyo método es administrativo, encuesta, snapshot OSM o
  compuesto sin escala única pueden mantener detalle anual no exigible.
- Los COG de una misma serie deben tener contenido distinto, hashes fuente
  verificables y un único `color_domain` robusto compartido. Así, un cambio de
  color entre años representa un cambio de valor y no una reescala de leyenda.
- `has_annual: true` (solo pm25) → slider con Play que carga GeoJSONs anuales
  (`/data/annual/pm25_<año>.geojson`); es compatibilidad legacy, no autoridad
  sobre el detalle raster.
- `year_columns: {"<año>": "<columna>", ...}` → las cosechas viajan como columnas del
  `master.geojson` y el selector solo intercambia la columna (sin archivos extra).
  La UI se elige por cantidad: **≤4 años → sub-pestañas** (food_insecurity CASEN
  2020/2022; poverty_income MDSF SAE 2017/2020/2022/2024; poverty_multi 2017/2022/2024);
  **>4 años → el mismo slider con Play en modo columnas** (calor y lluvia
  2015-2024). Ver `renderTimeSlider()` en `webapp/src/main.js`.
- `default_year` fija la cosecha inicial (calor: "2024" = columna canónica sin sufijo).
  Sin `default_year`, el default es la columna agregada de `column` y el slider gana un
  stop "Prom." (lluvia: promedio CHIRPS 2015-2024).
- En la leyenda, `period` es el prefijo corto de fuente compuesto con el año activo
  ("CHIRPS 2019"); `period_avg` es el sufijo del agregado ("CHIRPS 2015-2024").
- Los índices compuestos (`heat_exposure_index`, `precip_extremes_index`) **no** llevan
  años: son z-scores del período completo y un valor "anual" sería engañoso.
- Series por año: `scripts/run_climate_heat_annual.py` (mismo pipeline canónico por año;
  grilla Open-Meteo cacheada en `cache/climate_heat_grid_daily_<año>.csv`) y
  `scripts/run_precipitation_annual.py` (CHIRPS diario en disco).

Decisión transversal: `docs/adr/0007-annual-spatial-support-is-atomic.md`.

## Webapp — Panel ANALYTICS (comparación de distribuciones entre ciudades)

Panel accesible solo desde la vista LATAM (`webapp/src/panels/analytics-compare.js`,
botón en `states/latam.js`): histograma + eCDF superpuestos por ciudad, con mediana,
banda robusta doble-MAD asimétrica, KS y Anderson-Darling k-muestral. Todo el cómputo
estadístico vive en `src/exposome/distributions.py` y se materializa vía
`scripts/export_webapp_distributions.py` en
`webapp/public/data/v1/analytics/distributions.json` — el webapp solo renderiza ese
JSON, nunca recalcula un test client-side. Metodología completa (por qué doble-MAD,
por qué scipy y no una reimplementación en JS, la advertencia de autocorrelación
espacial en grilla fina) en `docs/analytics_distribution_comparison.md`. Regenerar
el artefacto tras publicar un estudio nuevo: `python scripts/export_webapp_distributions.py`.

Interfaz v3 (pantalla completa bajo el header): el selector **es el catálogo de
exposomas del picker** (`getPalette().exposomes` agrupado por `entorno`/`sociedad`/
`resultados`, mismos sprites `icon-<id>`, grupos Calor/Lluvia colapsados que
despliegan a sus hijos — reutiliza el patrón de `city-overview.js`). El panel no
inventa taxonomía: empata el dato por `exposome_id` y muestra en gris los
exposomas sin dato comparable. Además: chips de ciudad, veredicto KS/AD en prosa
con medidor visual de D, pestaña METODO, y toggle de escala log en el histograma.

El exporter exporta **una distribución por exposoma a su máxima resolución
comparable** (grilla fina sólo si al menos dos ciudades publican un detalle
verificado por el manifest v3; si no, la columna principal admin) y **descarta las ~160
columnas derivadas** que el picker no muestra (`master.csv` sigue siendo la
fuente completa). El join columna→exposoma vive una sola vez en
`registry_by_column` (salta `status:group` para que la columna compartida
resuelva al hijo, no al padre); cada indicador del JSON lleva `exposome_id`,
`category`, `unit`/`unit_long` y `column` **del catálogo** (sin inferencia), más
`log` (bins log10 vía `shared_histogram_log`) cuando el mínimo agrupado es > 0.
La comparación es cross-city: solo se exporta lo presente en ≥2 ciudades, así
que hoy el riel es disperso (entorno 15, sociedad 3, resultados 0) y crece al
sumar ciudades.

Al agregar un nuevo exposoma al webapp, verificar la resolución en el `*_metadata.json`
de su fuente y que su `column`/`category` en `palette.json` sean correctos.

## Hardcoded Santiago Assumptions

- Region query: `"Región Metropolitana de Santiago, Chile"`
- Admin level: `8` (comunas)
- Expected units: **52 communes** (validated strictly in master builder)
- CRS metric: `EPSG:32719` (UTM 19S — Chile-specific)
- CRS geographic: `EPSG:4326`
- Legacy notebook outputs contain `rm_santiago`; new config-driven layers use `<city>_<layer>{_<suffix>}.{csv,geojson}`.

**Any generalization to other cities must modify these.** The master builder will throw if the row count ≠ 52 or if any `name` duplicates or missing values exist.

## Google Earth Engine

- Project ID: `exposome-api`
- Initialized with: `ee.Initialize(project='exposome-api')`
- `earthengine-api` and `geemap` are installed via pip inside the `exposome` env.
- GEE is **required** for `scripts/run_air_quality_satellite.py` (Plan A+ satellite pipeline: Sentinel-5P NO2 + MODIS AOD with ERA5 BLH conversion), `scripts/run_alan.py` (VIIRS DNB night-time lights + WorldPop weighting), `scripts/run_precipitation.py` (CHIRPS daily rainfall), and `scripts/run_wildfire.py` (MODIS MCD64A1 burned area + FIRMS active fire).
  `scripts/run_air_quality.py` is a *different*, older layer (`air_quality`, not
  `air_quality_satellite`) — despite the similar name it does NOT use GEE; it
  hits the CAMS/Open-Meteo Air Quality API directly. README.md's "Plan A+"
  narrative still describes `run_air_quality.py` as the GEE script, which is
  stale since this split — treat README's air-quality section as describing
  `run_air_quality_satellite.py`'s actual behavior when in doubt.
- If GEE auth fails, run `earthengine authenticate` inside the activated env.

## Data Flow

### Legacy (notebooks)
```
APIs (Open-Meteo, OSM, GitHub raw CSVs)
    → notebooks (one per exposome layer)
    → data/processed/*_exposome_rm_santiago.{csv,geojson}
    → scripts/build_master_exposome.py
    → data/processed/santiago_exposome_master.{csv,geojson,json}
```

### New — config-driven pipeline
```
config/cities/<city>.yaml
    → src/exposome/config.py
    → src/exposome/boundaries.py  (reuse existing GeoJSONs)
    → src/exposome/air_quality.py  (GEE satellite)
    → scripts/run_air_quality.py
    → data/processed/<city>_air_quality_satellite_YYYY.{csv,geojson}
```

Precipitation follows the same config-driven pattern with CHIRPS daily rainfall:

```
config/cities/<city>.yaml
    → src/exposome/precipitation.py  (GEE CHIRPS)
    → scripts/run_precipitation.py
    → data/processed/<city>_precipitation_chirps_YYYY_YYYY.{csv,geojson,json}
```

Wildfire (the "climate disasters" factor) follows the same pattern, combining
two GEE satellite sources and an optional local CONAF/itrend CSV:

```
config/cities/<city>.yaml  (wildfire: block)
    → src/exposome/wildfire.py  (GEE: MODIS MCD64A1 burned area + FIRMS active fire)
    → scripts/run_wildfire.py
    → data/processed/<city>_wildfire_YYYY_YYYY.{csv,geojson,json}
```

- Caches per-year satellite metrics in `cache/<city>_wildfire_annual_YYYY_YYYY.csv`
  (safe to interrupt; only missing years are re-fetched).
- Official enrichment is opt-in: drop a CSV at the path in `wildfire.official.path`
  (default `data/raw/conaf_incendios_comuna.csv`) to add `fire_official_*` columns;
  it is skipped gracefully when absent, so the layer is reproducible from satellite alone.
- Reuses `demography.normalize_comuna_name()` to match official commune names to the boundaries.

Healthcare access follows the same pattern, but combines OpenStreetMap with the
official MINSAL/DEIS facility registry when available:

```
config/cities/<city>.yaml
    → src/exposome/healthcare.py
        → src/exposome/healthcare_official.py  (MINSAL/DEIS)
        → OpenStreetMap amenities via osmnx
        → conflation (official wins within 150 m buffer)
    → scripts/run_healthcare.py
    → data/processed/<city>_healthcare_access.{csv,geojson,json}
```

Run with official data (default):
```bash
python scripts/run_healthcare.py
```

Run with OSM only:
```bash
python scripts/run_healthcare.py --no-official
```

Force re-download of the official DEIS CSV:
```bash
python scripts/run_healthcare.py --refresh-official
```

Compute street-network distances (slower, more realistic):
```bash
python scripts/run_healthcare.py --use-network
```

Generate choropleth maps:
```bash
python scripts/plot_healthcare_maps.py
```

By default it reads ``data/processed/santiago_exposome_master.geojson`` and
also emits population-adjusted ratio maps (e.g. inhabitants per primary-care
facility). To plot only the standalone healthcare layer:

```bash
python scripts/plot_healthcare_maps.py --geojson data/processed/santiago_healthcare_access.geojson
```

Categories currently emitted:
- `n_hospital` — hospitals
- `n_clinic` — clinics / private clinics
- `n_primary_care` — CESFAM, SAPU, SAR, CGU, CGR, PSR, CECOSF, SUR
- `n_pharmacy` — pharmacies (OSM only; DEIS does not publish pharmacies)
- `n_laboratory` — clinical laboratories
- `n_dental` — dental clinics
- `n_mental_health` — community mental health centres (COSAM)
- `n_total` — all health facilities matched by the OSM tags or present in DEIS

Each DEIS-derived category is also split by administrative sector:
- `n_<category>_public` — public / SNSS / municipal / Servicio de Salud / FFAA
- `n_<category>_private` — private providers

Compare the official and OSM inventories:
```bash
python scripts/compare_healthcare_sources.py
```
This writes `data/processed/healthcare_source_comparison_by_commune.csv` and
`data/processed/healthcare_unmatched_facilities.csv`.

### Demography (Censo 2017)

Population counts by commune are extracted from the INE Censo 2017 manzana
microdata and added as a separate layer:

```bash
python scripts/run_demography.py
```

Outputs `data/processed/<city>_demography.csv` with columns such as
`pop_total`, `pop_male`, `pop_female`, `pop_0_14`, `pop_15_64`, `pop_65_plus`
and the corresponding percentages.

`scripts/build_master_exposome.py` merges demography and computes derived
ratios like `health_inhabitants_per_primary_care`.

### Greenspace

The greenspace layer has been split into three reproducible, config-driven
pipelines:

```
config/cities/<city>.yaml
    → src/exposome/greenspace_satellite.py   # Landsat-8/9 NDVI/EVI
    → scripts/run_greenspace_coverage.py
    → data/processed/<city>_greenspace_coverage.{csv,geojson,json}

config/cities/<city>.yaml
    → src/exposome/greenspace_access.py      # OSM parks + distance/buffers
    → scripts/run_greenspace_access.py
    → data/processed/<city>_greenspace_access.{csv,geojson,json}

config/cities/<city>.yaml
    → src/exposome/greenspace_cv.py          # Esri World Imagery + ExG/SAM
    → scripts/run_greenspace_cv.py
    → data/processed/<city>_greenspace_cv_sample.{csv,geojson,json}
    → data/processed/<city>_greenspace_cv_commune.csv
```

Run them with:

```bash
python scripts/run_greenspace_coverage.py
python scripts/run_greenspace_access.py
python scripts/run_greenspace_cv.py --method exg --samples-per-commune 5
```

Notes:
- `run_greenspace_coverage.py` uses **Landsat-8/9 Collection 2** at 30 m because
  Sentinel-2 at 10 m triggers GEE computation/download limits for the whole
  Región Metropolitana. The composite is built for the Oct–Mar growing season.
- `run_greenspace_access.py` computes OSM-based green area plus Euclidean
  distance to the nearest park and green area/count within 300/500/1000 m
  buffers. Distances are capped at `99999` m for communes with no mapped parks.
- `run_greenspace_cv.py --method exg` samples random tiles per commune from
  Esri World Imagery and detects vegetation with Excess Green + Otsu. It
  demonstrates that OSM under-maps private/tree-line greenness (~90% of detected
  vegetation falls outside OSM polygons in sampled tiles).
- `run_greenspace_cv.py --method sam` is reserved for future GPU/overnight runs
  using Segment Anything; it is not implemented yet.

The master builder merges both `greenspace_access` (renamed to legacy
`green_km2`, `green_pct`, `n_green`) and `greenspace_coverage` (NDVI/EVI
metrics) into the master table.

## Current Refactor Direction

The project is moving from monolithic notebooks to a **config-driven pipeline**:
- New code belongs in `src/exposome/` as importable modules.
- City configs go in `config/cities/<city>.yaml`.
- CLI scripts go in `scripts/run_<layer>.py`.
- Preserve existing notebooks as reference; do not delete them.

When adding new modules, prefer `typer` for CLI entrypoints and `pyyaml` for config loading.

## Obsidian Knowledge Vault

- Open the repository root as the vault; shared knowledge lives in
  `docs/knowledge/`.
- Do not manually edit `docs/knowledge/generated/`. Regenerate it with
  `PYTHONPYCACHEPREFIX=/tmp .venv/bin/python scripts/build_obsidian_knowledge.py --write`
  and verify with `--check` after layer, study or status changes.
- Keep `local-notes/` private. It contains personal drafts and raw meeting
  transcripts and must never be committed.
- Publish only reviewed meeting minutes under `docs/knowledge/meetings/YYYY/`;
  remove credentials, personal data and sensitive discussion first.
- Methodology documents in `docs/` remain canonical. Every audited layer must
  link to an existing methodology; declared sharing is allowed for closely
  related layers.
- Shared notes use relative Markdown links. Do not introduce Obsidian MCPs or
  community plugins without an explicit request.

<!-- OPENWIKI:START -->

## OpenWiki

This repository uses OpenWiki for recurring code documentation. Start with `openwiki/quickstart.md`, then follow its links to architecture, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->

> **Correction, deliberately outside the block above** (OpenWiki rewrites
> everything between its markers on every `--update`, so a fix placed inside
> would not survive): there is **no** OpenWiki CI in this repo. The wiki is
> refreshed by hand with `openwiki code --update` after structural changes —
> a new layer, a new study, a refactor of the execution seam. OpenWiki
> regenerates `.github/workflows/openwiki-update.yml` on every run; it is
> gitignored on purpose, since it targets OpenRouter with a secret that does
> not exist and would fail daily.
