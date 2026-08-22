# Incidentes multiciudad

Este registro conserva lecciones operativas revisadas. Los logs crudos y
`incident_candidates.md` se generan bajo `cache/multicity_runs/`, no se
versionan y pueden contener respuestas de proveedores. Nunca copies tokens,
URLs firmadas, datos personales ni payloads completos a este documento.

## Flujo de triaje

1. Identifica la primera tarea `failed` en `summary.md`; las tareas `blocked`
   suelen ser consecuencias y no causas.
2. Confirma si el fallo es transitorio (429/5xx, timeout, Overpass saturado) o
   determinista (config, esquema, cobertura, checksum, resolución).
3. Localiza el último checkpoint válido y verifica que reanudar no vuelva a
   descargar unidades completas.
4. Corrige código/config si corresponde y añade una prueba que reproduzca la
   clase de error.
5. Repite el mismo comando nocturno. No uses `--force` para esconder un
   fingerprint o cache namespace incorrecto.
6. Registra abajo únicamente la causa raíz y la prevención reutilizable.

## Plantilla

### AAAA-MM-DD — proveedor/capa — síntoma corto

- Estudios afectados:
- Síntoma observable:
- Causa raíz:
- Artefactos que deben invalidarse:
- Checkpoint seguro desde el cual reanudar:
- Corrección:
- Prueba o gate preventivo:
- Comando de recuperación:

## Incidentes registrados

### 2026-08-19 — healthcare/Overpass — mirrors agotados en Cartagena

- Estudios afectados: `cartagena_urban` (observado); cualquier estudio nuevo
  que dependa de Overpass puede mostrar el mismo patrón.
- Síntoma observable: la primera etiqueta `amenity` permanece en `0/2`; cada
  mirror agota dos intentos. Se observaron `ConnectionError` en `.de`,
  `ResponseStatusCodeError` en `.fr` y timeout por intento en `.ch`.
- Causa raíz: indisponibilidad o saturación transitoria de los mirrors, no una
  configuración inválida de Cartagena.
- Artefactos que deben invalidarse: ninguno. El runner conserva bundles
  exitosos y no reemplaza master/release ante el fallo de la capa.
- Checkpoint seguro desde el cual reanudar: caches por tag existentes; en este
  caso `amenity` no terminó y se reintentará íntegra, mientras cualquier tag
  ya guardado se omite.
- Corrección: no hacer bucles inmediatos. Ejecutar las capas no-OSM pendientes,
  esperar seis horas y reintentar solo la capa OSM con `--resume`, en serie.
  Tras tres ciclos, dejar `needs_review` y continuar otra ciudad.
- Prueba o gate preventivo: los tests de fallback de `osm_fetch` cubren la
  rotación y el límite por endpoint; el supervisor
  `scripts/run_osm_recovery_week.py --dry-run` verifica la cola antes de una
  pasada humana.
- Comando de recuperación: `nohup .venv/bin/python
  scripts/run_osm_recovery_week.py --duration-hours 168 >
  logs/osm_recovery_week.log 2>&1 &`.

### 2026-08-20 — OSM Colombia — fallback reproducible a extracto Geofabrik

- Estudios afectados: `cartagena_urban`, `pasto_urban` y sus companions
  native, tras fallos repetidos de la etiqueta `amenity` en los tres mirrors
  Overpass.
- Diagnóstico: que `.de`, `.fr` y `.ch` fallen tras sus plazos no invalida los
  bundles ni es motivo para aumentar el paralelismo. Los mensajes `loading
  tile checkpoint` son lecturas locales, no descargas nuevas.
- Corrección durable: usar el extracto OSM PBF fechado de Colombia en vez de
  consultas HTTP para `greenspace_access`, `food_environment`, `healthcare` y
  `social_infrastructure`. **No** usar los archivos `-free.shp.zip` ni
  `-free.gpkg.zip`: no preservan los tags OSM que filtran estas capas.
- Ubicación canónica en Joaco:
  `data/raw/geofabrik/colombia/<YYMMDD>/colombia.osm.pbf`. El payload no se
  versiona en Git ni se deja en Dropbox/una unidad NTFS; el
  `source_manifest.json` y el SHA-256 sí son el registro reproducible.
- Ingesta, después de una descarga humana y verificación de tamaño/hash:
  `PYTHONPYCACHEPREFIX=/tmp .venv/bin/python
  scripts/migrations/ingest_geofabrik_extract.py --source
  data/raw/geofabrik/colombia/<YYMMDD>/colombia.osm.pbf --region colombia
  --version <YYMMDD> --source-path south-america`.
- Configuración posterior: declarar el mismo `osm_extract` bajo
  `layer_overrides` de las cinco capas para cada estudio afectado y reanudar
  con `--resume`. `walkability` consume `lines/highway` del extracto y arma el
  grafo de calles localmente.
- Regla operativa: no cambiar a este origen a mitad de una tarea activa. Dejar
  que el supervisor registre `needs_review`, validar el snapshot y recién
  entonces cambiar la configuración y reiniciar la recuperación.

### 2026-08-20 — OSM LATAM — inventario de snapshots reutilizables

- Estudios afectados: ciudades nuevas o reintentos de la cohorte LATAM que
  usan capas OSM por tags.
- Prevención: consultar `config/operations/geofabrik_latam_cohort.yaml` antes
  de una corrida. El mismo PBF fechado se reutiliza para todas las ciudades de
  una región; no se descarga uno por ciudad ni se usa `latest`.
- Gate preventivo: `PYTHONPYCACHEPREFIX=/tmp .venv/bin/python
  scripts/check_geofabrik_latam_cohort.py --require-payload --verify-hash`.
  Verifica el hash sin red y falla si falta un snapshot requerido.
- Límite histórico superado: `walkability` ahora consume `lines/highway` y
  construye el grafo local. Las publicaciones existentes no se recalculan
  retrospectivamente sólo para cambiar el backend.

Los siete siguientes salieron al habilitar **Lima** y correr **Bogotá**
(2026-07-22/25). Los siete tienen **fix en código con test**, así que una ciudad
nueva los hereda ya corregidos: se documentan para reconocer el síntoma rápido y
para no re-introducirlos en un refactor. Los tres primeros aparecen la **primera
vez que corre un estudio de una ciudad nueva**; los dos últimos comparten una
misma causa (el runner no replicaba post-procesos de `config.load_config`).

### 2026-07-22 — climate_heat (agregado) — `TypeError: unhashable type: 'list'`

- Estudios afectados: cualquier estudio agregado nuevo (visto en `lima_distritos`).
- Síntoma observable: `climate_heat` agregado revienta cuando la fuente ERA5-Land
  (11.132 m) es más gruesa que la escala de la unidad y dispara el
  `resolution_warning`. Bloquea el keystone materialize→master→publish.
- Causa raíz: `load_communes` leía la caché con el nombre de ciudad, pero
  `prepare_boundary_cache` la siembra con `<study_id>_communes.geojson` → cache
  miss → ruta de descarga OSM → una lista (`region_query`) usada como miembro de
  set.
- Corrección: `src/exposome/climate/build_layer.py` (`load_communes` lee la caché
  sembrada por study_id).
- Prueba o gate preventivo: `tests/test_climate_heat.py::LoadCommunesStudyScopedCacheTest`.

### 2026-07-22 — greenspace_coverage (nativo) — grilla de 111.320 m

- Estudios afectados: cualquier estudio nativo nuevo con verde satelital.
- Síntoma observable: `ValueError: resolved to a 111320 m grid, expected ~30 m`
  (grilla del fallback de 1° de Earth Engine).
- Causa raíz: `build_landsat_composite().median()` descarta la proyección de 30 m;
  sin fijarla, EE cae al fallback de 1°.
- Corrección: `landsat_source_projection()` en
  `src/exposome/greenspace_satellite.py` + `.setDefaultProjection(...)` en el
  export nativo (`src/exposome/native.py`).
- Prueba o gate preventivo: `tests/test_native_pipeline.py::test_greenspace_coverage_pins_source_projection`
  y el chequeo `native._validate_export_grid` (tolerancia 5 %).

### 2026-07-22 — wildfire (nativo) — componentes con grillas distintas

- Estudios afectados: cualquier estudio nativo nuevo con wildfire.
- Síntoma observable: `ValueError: combines source components with different
  native grids` (burned_area 463,31 m vs active_fire 926,63 m).
- Causa raíz: el export intentaba combinar los dos componentes MODIS/FIRMS en una
  sola grilla; además `scale_meters` (500/1000, etiqueta nominal del reducer
  agregado) ≠ `nominalScale` real de GEE (463,31/926,63), 7,3 % de diferencia que
  reprobaba `_validate_export_grid`.
- Corrección: exportar cada componente por separado en su propia grilla
  (`src/exposome/native.py`, `_gee_component_images`) + `native_scale_meters` real
  en `config/layers/wildfire.yaml`. **Regla para capas nuevas**: toda capa GEE con
  offset sub-nominal (MODIS, VIIRS/alan) debe declarar `native_scale_meters` real,
  no la etiqueta nominal.
- Prueba o gate preventivo: `tests/test_native_pipeline.py` (`test_wildfire_exports_each_component_on_its_own_grid`,
  `test_wildfire_component_scales_match_earth_engine_grid`).

### 2026-07-22 — social_infrastructure — `materialize` no lo verifica como v2

- Estudios afectados: cualquier estudio agregado nuevo (visto en `lima_distritos`;
  Santiago no lo sufre porque su bundle es de un builder viejo sin ese diagnóstico).
- Síntoma observable: `Cannot materialize a Study release; ... not verified v2
  artifacts: social_infrastructure` → 11 tareas de publish bloqueadas.
- Causa raíz: `collect_legacy_assets` elegía `primary_table` solo por
  `master.required_columns`; el diagnóstico `diagnostics/*_low_access.csv` (slice
  `nsmallest(10)` **sin `spatial_id`**) ordena antes que el CSV real y satisface
  esas columnas → se robaba el rol → `_validate_primary_columns` (que exige
  `spatial_id`) fallaba.
- Corrección: en `src/exposome/runners.py`, todo archivo bajo un subdirectorio
  `diagnostics/` recibe rol `diagnostic`, nunca primary (honra la convención de
  `normalize_layer_outputs`).
- Prueba o gate preventivo: `tests/test_layer_catalog.py::test_legacy_collector_ignores_diagnostic_subset_without_join_key`.
- Comando de recuperación: `--resume` re-corre el bundle corrupto solo (no
  verifica → `complete=False`), no hace falta `--force`.

### 2026-07-23 — GEE Restricted Mode — descargas multi-tile `Exceeded concurrency limit`

- Estudios afectados: cualquier estudio con capas GEE multi-tile cuando el
  proyecto está en Restricted Mode (cuota noncommercial agotada).
- Síntoma observable: `Too Many Requests: Exceeded Earth Engine concurrency limit`
  siempre a los mismos ~17/84 tiles. **Señal de triaje**: las capas GEE de **un
  solo tile pasan** y solo fallan las **multi-tile** → es concurrencia, no cuota
  diaria; esperar el reset no lo arregla si el patrón es ese.
- Causa raíz: `geemap.download_ee_image` → `geedim` usa `max_requests=32` por
  defecto; Restricted Mode sirve pocos requests concurrentes.
- Corrección: constantes `EE_DOWNLOAD_NUM_THREADS=1` / `EE_DOWNLOAD_MAX_REQUESTS=1`
  en `src/exposome/gee.py`, pasadas a los 3 sitios de descarga (`native.py`,
  `annual_spatial_detail.py`, `pm25.py`). `build_cog` reusa el `.tif` local y
  `export_webapp_green_subcomuna.py` es secuencial → no necesitan el cap.
- Prueba o gate preventivo: `tests/test_native_pipeline.py::test_success_calls_download_ee_image_and_writes_metadata`
  asercia `num_threads==1` y `max_requests==1`.

### 2026-07-23 — greenspace_access/Overpass — Bogotá detenido aparentemente en `0/20`

- Estudios afectados: estudios con polígonos rurales grandes divididos en
  teselas; observado en `bogota_localidades`.
- Síntoma observable: el log repite `greenspace_access OSM regions: 0/20`
  durante más de una hora, con CPU casi nula. El caché mostraba 18 localidades
  completas; sólo faltaban Usme (16 teselas) y Sumapaz (64).
- Causa raíz: OSMnx 2.1 reintenta recursivamente HTTP 429/504 y el estado
  `Currently`, sin respetar el número de intentos del fallback exterior.
  `requests_timeout` limita una petición, no la recursión completa. Las
  teselas se acumulaban en memoria y sólo se guardaban al completar la
  localidad, por lo que Ctrl-C perdía el trabajo parcial de Usme/Sumapaz.
- Artefactos que deben invalidarse: ninguno de los 18 GeoJSON por localidad.
  Una tesela sólo es reutilizable desde el nuevo directorio de checkpoint
  cuyo namespace coincide con bbox, tags y tamaño de grilla.
- Checkpoint seguro desde el cual reanudar: los 18 archivos bajo
  `cache/co/bogota/bogota_localidades/greenspace_access/`
  `bogota_localidades_greenspace_osm_by_region/`.
- Corrección: plazo duro por intento de endpoint en
  `src/exposome/osm_fetch.py`, logs de endpoint/tesela, escritura atómica por
  tesela y progreso inicial `18/20` con la lista de pendientes.
- Prueba o gate preventivo:
  `tests/test_osm_fetch.py::CallWithOverpassFallbackTests::test_attempt_deadline_rotates_away_from_stalled_endpoint`
  y
  `TiledBboxFetchTests::test_partial_tile_checkpoints_resume_without_repeating_finished_tiles`.
- Comando de recuperación:
  `caffeinate -dimsu .venv/bin/python scripts/run_multicity_overnight.py --city bogota --max-hours 10`.

### 2026-07-25 — greenspace_access (agregado) — el tiling por-unidad nunca engancha en el runner

- Estudios afectados: **todo** estudio agregado multi-localidad. Visible solo
  cuando una unidad rural es demasiado grande para una consulta Overpass única:
  `bogota_localidades` (Usme, Sumapaz). Lima pasó **de casualidad** (50 distritos
  chicos, cada uno cabe en `features_from_place`). Amenaza a SP/Medellín/CDMX con
  unidades rurales grandes.
- Síntoma observable: `greenspace_access` agregado falla 3 noches seguidas con
  `ConnectionError: Failed to download OSM green areas for 2 of 20 region(s)` en las
  dos localidades más grandes; ambas revientan a los 120 s de deadline en los dos
  mirrors. Bloquea `materialize base` → 11 tareas de publish/verify/validate
  `blocked`. **Señal de triaje decisiva**: `0` subdirectorios `*_tiles` en el caché
  (`..._by_region/`) de Bogotá **y** Lima → el tiling nunca corrió en ningún estudio
  multi-localidad; las urbanas pasan por `features_from_place`, las rurales gigantes
  no.
- Causa raíz (más profunda que el incidente 2026-07-23 de arriba, que arregló el
  *mecanismo* de teselas pero asumió que enganchaba): el camino de teselas
  (`fetch_features_from_bbox_tiled`, diseñado justo para Sumapaz/Usme) sólo se toma
  si `cfg["spatial_units"]` es `dict` (`greenspace_access._download_osm_green`,
  `bbox is not None`). El runner inyecta la config vía
  `StudyContext.resolved_config`, que **no emitía ese dict** — sí lo emite el camino
  directo `config.load_config` (config.py). Sin el dict → `units=None` →
  `query_bbox=None` para las 20 → fallback a `features_from_place` sin teselas → las
  2 unidades grandes exceden 120 s. Verificado offline: con el dict, Usme resuelve a
  16 teselas y Sumapaz a 64.
- Artefactos que deben invalidarse: ninguno de los 18 GeoJSON por localidad; sólo
  faltan Usme y Sumapaz.
- Checkpoint seguro desde el cual reanudar: los 18 archivos bajo
  `cache/co/bogota/bogota_localidades/greenspace_access/`
  `bogota_localidades_greenspace_osm_by_region/`.
- Corrección: `StudyContext.resolved_config` (`src/exposome/studies.py`) ahora emite
  `cfg["spatial_units"]` (path/layer/id_column/name_column/unit_type/expected_units/
  source), a la par de `config.py`. Enciende el tiling en `greenspace_access` y la
  consulta AOI compacta en `healthcare`; `walkability` sin cambio (corto-circuito por
  caché). Santiago intacto (los cachés cortan a todos los lectores; su
  `region_query` es una sola cadena).
- Prueba o gate preventivo:
  `tests/test_spatial_contract.py::SpatialContractTest::test_loads_geojson_and_estimates_southern_utm`
  asercia que `resolved_config` emite el dict `spatial_units`.
- Comando de recuperación: reanudar la corrida nocturna con el mismo comando;
  `--resume` re-corre sólo Usme y Sumapaz, ahora por teselas. **Regla para capas
  nuevas**: toda capa que resuelva geometría por-unidad debe leerla de
  `cfg["spatial_units"]` (dict), no geocodificar nombres de lugar; el runner ya lo
  provee. Cualquier cosa que `config.load_config` ponga en el cfg debe ponerlo
  también `resolved_config`, o el runner degrada en silencio.

### 2026-07-25 — pm25/alan — `pop_weighted` degenerado (== media de área) fuera de Chile

- Estudios afectados: **toda** ciudad no-chilena (agregado y nativo). Confirmado
  degenerado en Lima (ya publicada) y Bogotá; Santiago real (`max|media−popw| = 2,68`).
- Síntoma observable: en el log, `filled pop-weighted ... with area mean` para todas
  las unidades; `pm25_pop_weighted` (columna **requerida** del master) y las
  `*_pop_weighted` de alan quedan idénticas a la media simple. **No falla la capa**
  (no bloquea) → se publica en silencio como si fuera ponderación poblacional.
- Causa raíz: **misma brecha que el incidente greenspace_access de arriba**.
  `config.load_config` fija `alan.population.country`/`pm25.population.country` al país
  del estudio (config.py); `StudyContext.resolved_config` (camino del runner) no lo
  hacía → quedaba el default de capa `country: CHL` (`config/layers/alan.yaml`).
  `WorldPop/GP/100m/pop` es por-país: la imagen CHL no cubre Perú/Colombia → peso nulo
  sobre el AOI → fallback a media de área. Viola el aislamiento por país (proxy chileno
  silencioso).
- Corrección: `resolved_config` (`src/exposome/studies.py`) aplica el mismo
  post-proceso portable que `config.load_config`, vía
  `_apply_runner_portable_postprocess` en **ambas** ramas (agregado **y** nativo —
  la rama nativa retornaba antes y quedaba en `CHL`). Verificado: Bogotá→COL,
  Lima→PER, Santiago→CHL. Un `diff` clave-por-clave `config.load_config` vs
  `resolved_config` reveló que la **misma brecha** producía otras dos divergencias
  que aún no habían salido como incidentes pero iban a: `climate.seasons.summer`
  quedaba en `[12,1,2]` (verano austral) para ciudades del hemisferio norte como
  Bogotá (`[6,7,8]` correcto), y `healthcare.output_base`/`graph_cache` quedaban con
  el nombre de Santiago para toda otra ciudad. Las cuatro se cierran de una.
- Artefactos que deben invalidarse: los bundles `pm25`/`alan` (población),
  `climate_heat`/`climate` (estación) y `healthcare` (rutas), agregado **y** nativo,
  de **todas** las ciudades no-chilenas ya corridas. El código nuevo sólo corrige al
  re-correr esas capas con `--force` (ya están cacheadas como completas); Lima
  publicada requiere re-correr + re-publicar. **Alcance a decidir por el humano**, no
  bloquea la corrida en curso.
- Prueba o gate preventivo (cierra la **clase**, no sólo el síntoma):
  `tests/test_study_context_runtime.py::StudyContextRuntimeTests::test_resolved_config_matches_load_config_on_portable_keys`
  compara `resolved_config` con `config.load_config` clave-por-clave (estudio no-nativo
  y nativo) y falla si **cualquier** clave portable diverge — captura una futura
  divergencia sin esperar a que salga como incidente.

## Lecciones vigentes

### 2026-08-22 — ciudades metropolitanas — no confundir RM con “Colar” o municipio central

- Estudios afectados: ciudades cuya residencia de cohorte se etiqueta como
  región metropolitana, empezando por `belo_horizonte_rmbh`.
- Riesgo: usar sólo el municipio central reduce la cobertura; sumar el Colar
  Metropolitano por proximidad la amplía sin sustento. Ambos resultados rompen
  la correspondencia entre la etiqueta de cohorte, unidad espacial y release.
- Prevención: la referencia debe cruzar una lista oficial de membresía de la
  región metropolitana con la malla municipal oficial. El migrador de RMBH
  exige 34 `CD_MUN` únicos y escribe hashes de ambas fuentes; si el total
  cambia, falla antes de crear o reemplazar la referencia.
- Operación: no se agrega la ciudad a `cohort_latam_ready.yaml` ni se inicia
  una corrida semanal hasta que existan referencia, manifiesto crudo y dos
  preflights limpios. Para OSM, declarar un PBF local en los cinco layers,
  incluido `walkability`, evita repetir el incidente de Overpass/PBF vacío.

### 2026-08-22 — São Paulo / caminabilidad PBF — falso éxito de red vacía

- Estudios afectados: cualquier estudio con `walkability.osm_extract`.
- Síntoma observable: el log dice `reading highway lines from <extracto>.osm.pbf`,
  seguido de `sparse/empty network` para **todas** las unidades y de un
  `walkability: executed`. El CSV termina con `walk_n_nodes=0` y métricas cero
  para toda la ciudad.
- Causa raíz: se buscaba `highway` sólo en `other_tags` de la capa GDAL `lines`.
  Los PBF Geofabrik estándar promueven esa clave a su propia columna, por lo
  que el filtro devolvía un GeoDataFrame vacío.
- Corrección: `fetch_highway_lines_from_local_extract` lee la columna directa y
  usa `other_tags` únicamente como fallback. `build_walkability_layer` rechaza
  explícitamente un inventario local vacío y los checkpoints PBF se separan de
  los de Overpass. El algoritmo de `walkability` se versionó para invalidar el
  bundle creado antes de la corrección.
- Prueba o gate preventivo:
  `tests/test_osm_fetch.py::LocalExtractFetchTests::test_highway_lines_use_one_local_pbf_query_with_bbox`,
  más las tres señales del log documentadas en
  [Extractos OSM locales](../../osm_local_extract.md#gate-obligatorio-nunca-aceptar-un-éxito-con-red-vacía).
- Recuperación: actualizar código, ejecutar únicamente
  `exposome run --study <agregado> --layers walkability --force --no-build-master`,
  verificar `highway lines: N` y unidades `ok`, y sólo después reanudar native
  y el supervisor semanal. No eliminar PBFs ni checkpoints de capas sanas.

### 2026-08-22 — São Paulo native / caminabilidad PBF — CRS `auto` no resoluble

- Estudios afectados: estudios native cuya ubicación declara `crs.metric: auto`.
- Síntoma observable: los cuatro exports PBF por tags terminan `executed`, pero
  `walkability` falla con `CRSError: Invalid projection: auto`.
- Causa raíz: el estudio agregado resuelve `auto` desde sus unidades espaciales;
  el companion native tiene sólo un AOI y la primera ruta PBF le pasó la cadena
  literal `auto` a PyProj/OSMnx.
- Corrección: `export_native_osm` resuelve el CRS métrico desde el AOI native
  mediante `resolve_metric_crs` antes de construir el grafo. La prueba
  `test_native_walkability_resolves_an_auto_metric_crs_from_its_aoi` cubre esta
  rama.
- Recuperación: actualizar código y reanudar solamente
  `exposome run --study <native> --layers walkability --resume --no-build-master`.
  Los cuatro layers nativos PBF que ya terminaron válidos se conservan.

### 2026-08-22 — San Juan / Dynamic World y Overpass — no dejar una provincia completa en una sola consulta

- Estudios afectados: ciudades con unidades administrativas extensas, en
  particular `san_juan_departamentos` (19 departamentos y ~88 554 km²).
- Síntomas observables: Dynamic World falla con `EEException: Computation
  timed out` tras un único `reduceRegions`; después, acceso verde comienza
  `OSM region checkpoints: 0/19` y consume varios minutos por departamento en
  mirrors Overpass aunque ya existe un PBF argentino congelado.
- Causa raíz: la reducción GEE para todas las geometrías se hacía en una sola
  petición sin checkpoint intermedio; además faltaba declarar el extracto
  argentino en los cinco layers OSM del estudio agregado.
- Corrección: `greenspace_multisource` reduce y guarda cada unidad por
  separado en un cache validado parcial; al reintentar procesa sólo los nombres
  faltantes. San Juan declara
  `data/raw/geofabrik/argentina/260819/argentina.osm.pbf` para acceso verde,
  caminabilidad, infraestructura social, alimentación y salud.
- Recuperación: detener el supervisor que esté ejecutando consultas Overpass,
  actualizar configuración/código, recuperar primero
  `greenspace_multisource` y `greenspace_access` con `--resume`, y recién
  después reiniciar la semana con `--reset-state`. No borrar el PBF ni capas
  válidas; el checkpoint de una unidad OSM ya terminada también se conserva.

- La resolución se valida en el bundle publicado, no en `palette.json`. Un
  TIFF existente no se publica si su sidecar no prueba grilla, resolución y
  soporte preservado. Véase
  [Publicar resolución espacial](publicar-resolucion-espacial.md).
- **Una ciudad por corrida nocturna.** El `RunLock` (`cache/.multicity_overnight.lock`,
  fcntl) es de una sola corrida a propósito: dos ciudades en paralelo parten la
  cuota GEE y fallan las dos. Si el lock rechaza una corrida, verificá que su
  `pid=` no esté vivo (`ps -p <pid>`) antes de asumir que quedó viejo; **no lo
  borres si el proceso corre**.
- **Front-cargar GEE tras el reset diario** (00:00 America/Los_Angeles). Las fases
  `layers`/`temporal`/`resolution` son GEE-pesadas; arrancar con cuota agotada
  desperdicia la noche. El cap de concurrencia (arriba) ayuda pero no reemplaza la
  cuota real.
- **El publish gatilla el sellado del nativo.** En el DAG,
  `final release → verify → publish` exige `resolution:detail → seal-native →
  TODAS las nativas`. Una ciudad no publica (ni entra al picker) hasta que su
  estudio nativo sella; el catálogo la gradúa sola al pasar los gates.
- Un estudio nativo nuevo (`bogota_native`, etc.) preflighta con `--dry-run`
  antes de gastar una noche; los tres bugs de "primera corrida" de arriba ya están
  cubiertos por tests, pero un síntoma nuevo se arregla con test antes de repetir.
- Los inputs de Study deben llamarse exactamente igual que el parámetro del
  runner importable; una discrepancia puede activar un default de otra ciudad.
  La historia y otras generalizaciones corregidas están en
  [Pipeline multiciudad](../../multicity_pipeline.md#errores-de-generalización-encontrados-al-habilitar-capas-fuera-de-santiago).
- **`resolved_config` (runner) debe emitir lo mismo que `config.load_config`.** El
  runner inyecta `StudyContext.resolved_config`; el camino directo usa
  `config.load_config`. Una sola clave presente en un camino y no en el otro degradó
  en silencio (sin fallar) **cuatro** cosas a la vez: `spatial_units` (tiling OSM),
  `population.country` (proxy chileno), `climate.seasons.summer` (estación del
  hemisferio equivocado) y las rutas de `healthcare`. Al agregar cualquier
  post-proceso portable a un camino, replicarlo en el otro (o en el helper compartido
  `_apply_runner_portable_postprocess`). El gate que lo obliga es el test de paridad
  clave-por-clave `test_resolved_config_matches_load_config_on_portable_keys`; no
  arreglar la divergencia por síntoma, correr ese `diff` y cerrar la clase.
- Una respuesta parcial de proveedor es cache, no fuente de registro. Solo un
  bundle con manifest y checksums puede hacer que `--resume` declare una capa
  completa.
- Las tareas OSM se ejecutan secuencialmente. Aumentar concurrencia después de
  un 429 o límite por IP empeora la recuperación.
