# Pipeline multi-ciudad y multi-país

## Objetivo y alcance

La arquitectura nueva permite ejecutar exposomas para una combinación de país,
ciudad y polígonos de estudio sin copiar scripts por ciudad. La unidad espacial
puede ser una comuna, código postal, radio censal u otro polígono; internamente
siempre se normaliza a `spatial_id` y `spatial_name`.

La portabilidad se decide por **capacidad de la fuente**, no por el nombre de la
unidad espacial. Las capas globales y de OpenStreetMap pueden ser candidatas para
otra ciudad. Las fuentes oficiales chilenas siguen siendo válidas, pero se
declaran como específicas de Chile en vez de aplicar proxies silenciosos fuera
del país. El pipeline legacy de Santiago y sus archivos planos se conservan
durante la migración.

`santiago_communes` usa CUT de cinco dígitos como `spatial_id` desde el reference
versionado `data/reference/cl/santiago/santiago_communes/`. El crosswalk conserva
`legacy_name` y `slug` para no invalidar caches, joins o perfiles web durante la
transición. Los archivos planos siguen disponibles como adapter hasta que los
gates de paridad de v3.0 estén completos.

## Componentes de configuración

- `config/layers/<layer_id>.yaml`: defaults científicos y de proveedor. Los
  overrides nacionales viven en `config/countries/<iso2>.yaml`; la precedencia
  fija es capa → país → ubicación → estudio.
- `config/locations/<iso2>/<ciudad>.yaml`: nombre, códigos de país, zona horaria,
  `bbox` y CRS de una ciudad. `crs.metric: auto` selecciona una proyección UTM
  local a partir de los polígonos.
- `config/studies/<estudio>.yaml`: ubicación, archivo de polígonos, columnas de
  identificación, tipo de unidad, periodo y capas habilitadas.
- `config/layers.yaml`: catálogo declarativo de proveedores, portabilidad,
  resolución, requisitos, comando y contrato de integración de cada capa.
- `src/exposome/studies.py` y `src/exposome/spatial.py`: resolución del estudio,
  rutas canónicas y validación geográfica.
- `src/exposome/layers.py`: preflight, plan de ejecución, normalización de outputs
  y metadatos del estudio.
- `src/exposome/master.py`: unión uno-a-uno por `spatial_id` y reporte de cobertura.

Los estudios iniciales son `santiago_communes` y
`buenos_aires_zipcodes`. El segundo es una plantilla y no puede ejecutarse hasta
ubicar los polígonos aportados por el usuario en la ruta declarada.

Para el flujo operativo actual de Buenos Aires debe usarse `caba_native`,
documentado en `docs/caba_native_execution_plan.md`. Ese estudio no requiere
códigos postales: conserva productos en la resolución nativa dentro de un AOI y
permite consultas posteriores por coordenadas. `buenos_aires_zipcodes` queda
reservado para una agregación derivada cuando existan polígonos postales
válidos. La entrega de residencia de la cohorte (2026-07,
`data/raw/zipcodes/`) resultó ser city-level —sin códigos postales—, así que
esa agregación queda descartada salvo una re-entrega con mayor resolución; la
priorización de ciudades derivada de esa data vive en
`docs/multicity_status.md`.

En la primera versión portable, `period.start_date` y `period.end_date` deben
cubrir años calendario completos. El loader traduce esa ventana a cada capa:
CHIRPS, clima e incendios usan todos los años; ALAN, viento, calor y verde usan
el `reference_year` (por defecto, el último); PM2.5 recorta la ventana a la
disponibilidad ACAG 2000-2022 y falla si no existe intersección.

## Contrato de polígonos

El bloque `spatial` del estudio debe declarar, como mínimo:

```yaml
spatial:
  path: data/raw/ar/buenos_aires/buenos_aires_zipcodes/buenos_aires_zipcodes.geojson
  id_column: postal_code
  name_column: postal_code
  unit_type: postal_code
  source: user_provided
  license: document_before_execution
```

Requisitos del archivo:

1. Formato GeoJSON (`.geojson`/`.json`) o GeoPackage (`.gpkg`); un GeoPackage con
   varias capas también debe declarar `spatial.layer`.
2. CRS de origen definido y transformable al CRS geográfico de la ubicación.
3. Solo geometrías `Polygon` o `MultiPolygon`, no vacías y válidas. La reparación
   de geometrías debe ser una acción explícita y revisada.
4. `id_column` sin nulos, blancos ni duplicados. Los IDs se convierten a texto y
   se publican como `spatial_id`.
5. `name_column` es opcional; si falta, se usa `spatial_id`. Nombres vacíos
   individuales también reciben el ID como fallback.
6. Los polígonos deben solaparse con el `bbox` de la ubicación. Las unidades
   fuera del bbox se contabilizan en los atributos de validación.
7. `expected_units` es opcional. Debe fijarse cuando el número oficial es
   conocido; si se omite, la cantidad se obtiene del archivo sin imponer `52`.
8. `source` y `license` deben documentarse antes de publicar resultados.

El loader calcula `area_km2`, conserva los atributos de origen y devuelve primero
`spatial_id`, `spatial_name`, `area_km2` y `geometry`. No se debe unir una capa al
master mediante nombres libres de ciudad o comuna.

## Rutas y outputs

Para `<país>/<ciudad>/<estudio>`, las rutas se resuelven así:

```text
data/reference/<iso2>/<ciudad>/<estudio>/
data/raw/<provider>/<dataset>/<version>/
data/interim/<iso2>/<ciudad>/<estudio>/
data/processed/<iso2>/<ciudad>/<estudio>/
cache/<iso2>/<ciudad>/<estudio>/
```

Cada capa escribe bajo `data/processed/.../<layer_id>/` y usa su directorio
equivalente en `cache/`. El orquestador normaliza los CSV/GeoJSON a las claves
espaciales comunes, añade contexto de estudio/ubicación y escribe un
`manifest.json` con checksums y assets principales. Tras integrar el master se
escribe `release_manifest.json` para enlazar capas, configuración y outputs.

El master se escribe en la raíz procesada del estudio:

- `master.csv`
- `master.geojson`
- `master_coverage.csv`
- `master_metadata.json`

`master_coverage.csv` registra por capa IDs esperados, encontrados, faltantes y
extra, además de cobertura de datos. Una capa requerida ausente bloquea el master
en modo estricto; no se rellena como si tuviera cobertura completa.

## Portabilidad de capas

El catálogo usa cinco categorías:

| Categoría | Regla de uso | Ejemplos |
|---|---|---|
| `global` | Fuente con cobertura internacional; puede requerir GEE o red | PM2.5 ACAG, VIIRS ALAN, Landsat, CHIRPS, calor, viento, incendios |
| `OSM` | Extracción reproducible desde OpenStreetMap, con cobertura local variable | áreas verdes, caminabilidad, infraestructura social, entorno alimentario, salud |
| `CL` | Fuente o interpretación oficial válida solo para Chile | CASEN, INE, DEIS, RETC, ruido MMA, inseguridad alimentaria |
| `derived` | Depende de capas ya procesadas o inputs adicionales del estudio | contexto de sueño, SPI, métricas climáticas derivadas |
| `comparator` | Validación o desenlace externo; no entra al master como exposoma | CV de vegetación, mortalidad y hospitalizaciones neurológicas |

El piloto portable contiene 12 capas: siete globales
(`air_quality_pm25`, `alan`, `greenspace_coverage`, `precipitation`,
`climate_heat`, `wind`, `wildfire`) y cinco OSM (`greenspace_access`,
`walkability`, `social_infrastructure`, `food_environment`, `healthcare`). En
salud, Chile puede enriquecer OSM con DEIS; otros países ejecutan el proveedor
OSM sin presentar ese inventario como oficial.

## Preflight y ejecución

Trabajar siempre desde la raíz con el entorno `exposome`:

```bash
# Resolver configuración, expected_units y rutas, sin descargar datos
exposome audit --study santiago_communes

# Validar el estudio y mostrar comandos sin crear archivos ni contactar proveedores
exposome run --study santiago_communes --dry-run

# Probar un subconjunto portable
exposome run --study santiago_communes \
  --layers air_quality_pm25,greenspace_coverage --no-build-master

# Reanudar el conjunto habilitado y construir el master al finalizar
exposome run --study santiago_communes --resume

# Validar una release materializada
exposome verify --study santiago_communes
```

`--force` obliga a ejecutar las capas seleccionadas aunque exista un output
normalizado; no debe combinarse con `--resume`. El master se construye por
defecto y puede desactivarse con `--no-build-master`.

Un dry-run con capas bloqueadas imprime el plan completo y termina con código
`2`; esto permite usarlo como control de CI. Una ejecución selectiva construye
un master diagnóstico parcial, mientras una ejecución del estudio completo
mantiene validación estricta de sus capas requeridas.

El preflight informa uno de cuatro estados por capa:

- `ready`: requisitos estáticos satisfechos.
- `unavailable`: la capa no está habilitada, no tiene runner o no aplica al país.
- `missing_input`: falta el archivo espacial, una dependencia, un input local o
  una capacidad solicitada.
- `resolution_warning`: la fuente es más gruesa que la escala nominal declarada
  para las unidades; permite continuar, pero exige interpretar la limitación.

El preflight es estático y offline. Un `ready` no sustituye autenticación de GEE,
disponibilidad de red ni control de calidad del proveedor. Del mismo modo, el
informe `audit_exposome_status.py --study` resuelve rutas y cuenta features
GeoJSON, pero la validación completa de geometrías ocurre al cargar las unidades
con el contrato espacial durante la ejecución.

## Incorporar una ciudad o conjunto de códigos postales

1. Obtener polígonos con ID estable y documentar fuente, licencia, fecha y nivel
   administrativo. No derivar polígonos postales a partir de puntos de dirección.
2. Añadir `config/locations/<iso2>/<ciudad>.yaml` con bbox, zona horaria y
   `crs.metric: auto`, salvo que exista una proyección oficial preferida.
3. Crear `config/studies/<estudio>.yaml` y habilitar solo capas pertinentes. Una
   ciudad puede tener varios estudios, por ejemplo comunas y códigos postales.
4. Ejecutar `audit_exposome_status.py --study <estudio>` y corregir el contrato
   espacial antes de cualquier descarga.
5. Ejecutar `run_exposome.py --study <estudio> --dry-run`. Resolver primero
   `unavailable` y `missing_input`; revisar cada `resolution_warning`.
6. Hacer un smoke test con 1-2 capas portables y `--no-build-master`; inspeccionar
   CSV, GeoJSON, metadatos, geometría y cobertura.
7. Ejecutar el conjunto portable con `--resume`, construir el master y revisar
   `master_coverage.csv` antes de incorporar análisis posteriores.
8. Para una fuente nacional nueva, añadir un proveedor acotado por país y una
   metodología propia. No extender una capa `CL` cambiando solo el nombre de la
   ciudad.

## Errores de generalización encontrados al habilitar capas fuera de Santiago

`config/cities/santiago.yaml` fue durante años la única ruta de código
realmente ejercitada. Buenos Aires AMBA es la segunda ciudad llevada a través
del pipeline completo, y habilitar capas más allá de las 12 del piloto portable
sacó a la luz varios supuestos de un solo país agazapados en capas marcadas
como `global`/`derived` (es decir, en teoría ya portables). Quedan documentados
acá para que no se repitan al incorporar la tercera, cuarta, etc. ciudad.

**1. `cfg["bbox"]` no existía para ciudades sin `config/cities/<city>.yaml`.**
Síntoma: `Configuration error: 'bbox'` al correr `air_quality` (CAMS legacy).
Causa: hay dos implementaciones de "legacy mapping" — `StudyContext.config` en
`studies.py` (sí arma `bbox`) y `ResolvedSettings.legacy_mapping()` en
`settings.py` (no lo armaba), y `config.load_config()` usa la segunda para
cualquier ciudad sin archivo legacy propio. **Arreglado de forma general**: se
agregó `bbox` (con el esquema legacy `lat_min/lat_max/lon_min/lon_max`,
derivado de `context.location.bbox`) al `cfg.update(...)` de
`src/exposome/config.py`, en las dos ramas (nativa y agregada). Esto queda
disponible automáticamente para cualquier ciudad futura — no requiere tocar
`config/locations/<iso2>/<ciudad>.yaml` ni la capa que lo consume.

**2. Nombre de parámetro de `layer_inputs` no coincidía con la firma real de
la función.** Síntoma: `precipitation_spi` corría igual pero leía
`santiago_precipitation_chirps_daily_2015_2024.csv` (el archivo de Santiago,
no el de la ciudad pedida) sin avisar. Causa: `config/layers.yaml` declara
`study_inputs: [chirps_daily_csv]`, pero `build_precipitation_spi_layer(...)`
aceptaba un parámetro llamado `daily_csv`. El wiring dinámico de
`src/exposome/runners.py` (`run_importable_layer`) empareja `layer_inputs` por
**nombre exacto de parámetro** vía `inspect.signature` — si el nombre no
coincide, el valor se descarta en silencio y la función cae a su default
hardcodeado. **Arreglado**: se renombró el parámetro a `chirps_daily_csv` en
`src/exposome/precipitation_spi.py` para que coincida.
Lección para nuevas capas: antes de agregar `layer_inputs.<capa>.<clave>` a un
`config/studies/<estudio>.yaml`, verificar que `<clave>` sea exactamente el
nombre del parámetro en la función registrada en `_RUNNERS` de `runners.py`
— no alcanza con que coincida con `study_inputs` en `layers.yaml`.

**3. Dependencias instaladas a mano en el entorno conda viejo, nunca
declaradas en ningún archivo.** `xlrd` (lectura de `.xls` de fuentes
DNEC/INDEC), `esda` + `libpysal` + `scikit-learn` (`scripts/bivariate_lisa.py`,
`spatial_autocorrelation.py`, `cluster_communes.py`), `pyarrow` (cache parquet
de SPI en `precipitation_spi.py`, y usado también por `master.py` y
`socioeconomic.py`). Ninguna apareció hasta que el código real las ejercitó por
primera vez fuera de Santiago. **Arregladas**: las cuatro están ahora en
`pyproject.toml`; el entorno quedó consolidado en un único `.venv` (`uv sync`)
en vez de un conda `exposome` con paquetes acumulados ad-hoc durante meses.
Antes de habilitar una capa para una ciudad nueva, correr un import-check
rápido de `src/exposome/` completo detecta esta clase de gap sin gastar una
corrida real:
```bash
.venv/bin/python -c "
import sys, importlib, pkgutil
sys.path.insert(0, 'src')
import exposome
for mod in pkgutil.walk_packages(exposome.__path__, prefix='exposome.'):
    try:
        importlib.import_module(mod.name)
    except Exception as e:
        print(f'{mod.name}: {type(e).__name__}: {e}')
"
```

**4. Reintentos de OSM sin espera entre intentos.** `healthcare.py`
(`_download_osm_tag`) y `greenspace_access.py` (`_download_osm_green`)
reintentaban 3 veces sin ningún `sleep` entre intentos — inútil contra un
corte o rate-limit transitorio de Overpass, porque los 3 intentos fallan
igual de rápido. **Arreglado**: ambas funciones ahora esperan 20s entre
reintentos y lo imprimen (antes el log iba a `ox.utils.log()`, silenciado por
`ox.settings.log_console = False`). `food_environment.py` y
`social_infrastructure.py` ya tenían este patrón correcto (`_RETRY_SLEEP_S`) y
sirvieron de referencia para el fix.

**5. Documentación desactualizada tras un rename.** `scripts/run_air_quality.py`
dejó de ser el pipeline GEE Plan A+ (Sentinel-5P + ERA5 BLH) hace tiempo —
ese código ahora vive en `scripts/run_air_quality_satellite.py` (capa
`air_quality_satellite`). `run_air_quality.py` quedó como una capa `air_quality`
distinta y más simple (CAMS vía Open-Meteo Air Quality API, sin GEE), pero
AGENTS.md y la sección "Plan A+" de README.md seguían describiendo el
comportamiento viejo. Corregido en AGENTS.md; la narrativa larga de README.md
queda pendiente de una revisión más grande (no es solo texto: describe una
metodología completa) y no se tocó en esta pasada.

**6. `wildfire.py` guardaba el cache recién al final del loop de años.**
`fetch_annual_metrics` acumulaba los años nuevos en memoria y escribía el
cache una sola vez después del `for year in todo` completo — un corte a
mitad de una corrida perdía todo el progreso de esa ejecución, al revés de lo
que decía su propio comentario. **Arreglado**: ahora escribe el CSV tras cada
año (mismo patrón que `walkability.py`) y tiene barra `tqdm`. Era el último
gap de checkpoint pendiente de la lista original; los cinco módulos OSM más
el fetch de Open-Meteo y wildfire ya cumplen los tres requisitos de la
política de scripts largos en AGENTS.md. Los demás scripts GEE por año
(`pm25`, `alan`, `wind`, `climate_heat`, `greenspace_coverage`,
`air_quality_satellite`, `climate_metrics`) ya resumen por año vía
`.exists()` pero todavía no tienen barra de progreso — pendiente para una
próxima pasada si hace falta.

**7. Overpass podía quedar recursivo dentro de una tesela y perder la localidad
parcial.** La corrida de Bogotá llegó a 18/20 localidades de
`greenspace_access`, pero permaneció más de una hora aparentemente en `0/20`.
Las pendientes reales eran Usme (16 teselas) y Sumapaz (64). OSMnx 2.1 vuelve a
llamar recursivamente su request ante HTTP 429/504 y también repite el endpoint
de estado mientras informa `Currently`; ese bucle interno no devolvía el
control al fallback de mirrors. Además, el código sólo guardaba al terminar la
localidad completa, de modo que interrumpir una de estas unidades rurales
perdía todas sus teselas ya obtenidas. **Arreglado**:
`call_with_overpass_fallback` aplica un plazo POSIX por intento y rota de
endpoint al vencerlo; `fetch_features_from_bbox_tiled` escribe cada tesela
atómicamente bajo un namespace derivado de bbox+tags+grilla; y
`greenspace_access` comienza mostrando el conteo real de checkpoints y las
localidades pendientes. Repetir `--resume` conserva las 18 localidades y
continúa desde la tesela faltante, sin aceptar una localidad parcial como
completa.

## Resolución y comparabilidad

La agregación a polígonos no aumenta la resolución nativa. Un raster de 11.1 km
resumido por código postal sigue siendo una observación de aproximadamente 11.1 km;
varios códigos pueden compartir el mismo píxel. Está prohibido sobremuestrear una
fuente gruesa para aparentar detalle subcomunal.

El manifest v3 de cada bundle —no el catálogo global ni la presencia de un
archivo— gobierna el soporte que la app puede anunciar. Ver
[`adr/0004-published-spatial-support-contract.md`](adr/0004-published-spatial-support-contract.md)
y el
[`runbook de publicación espacial`](knowledge/runbooks/publicar-resolucion-espacial.md).

Antes de comparar ciudades o escalas:

- registrar resolución nativa, periodo, método de agregación y ponderación;
- cuantificar cobertura y unidades que comparten señal cuando corresponda;
- separar valores observados de proxies heredados desde una unidad mayor;
- no comparar índices normalizados dentro de cada ciudad como niveles absolutos
  entre ciudades sin una estrategia de armonización explícita;
- tratar diferencias de cobertura OSM como posible sesgo de medición.

Los outputs son exposiciones ecológicas asociadas a áreas, no exposición
individual ni evidencia causal. El código postal tampoco es una unidad
geográfica homogénea entre países.

## Compatibilidad legacy

Los `scripts/run_<layer>.py`, `config/cities/santiago.yaml` y archivos planos de
`data/processed/` son adaptadores de baseline, no interfaces operativas. El
pipeline activo usa `exposome run`, `config/studies/`, manifests y claves
`spatial_*`. El tablero de revisión también se genera desde la release canónica:

```bash
python scripts/audit_exposome_status.py --write
python scripts/audit_exposome_status.py --check
exposome verify --study santiago_communes
```

El retiro físico de cada adaptador se rige por
[`architecture/v3_retirement_gates.md`](architecture/v3_retirement_gates.md).
