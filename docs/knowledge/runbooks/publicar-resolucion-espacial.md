# Publicar y verificar resolución espacial

Este runbook evita confundir la resolución de una fuente con la resolución que
la app realmente puede mostrar. La decisión permanente está en
[ADR 0004](../../adr/0004-published-spatial-support-contract.md); el inventario
por capa y ciudad está en [resolution_manifest.md](../../resolution_manifest.md).

## Vocabulario obligatorio

| Campo v3 | Pregunta que responde | Ejemplo PM2.5 |
|---|---|---|
| `downloaded` | ¿Qué producto/grilla se obtuvo? | ACAG 0,01° |
| `observation` | ¿Qué huella física representa una observación? | huella ACAG 0,01° |
| `analysis` | ¿Sobre qué soporte se calculó el valor? | píxel ACAG o polígono agregado |
| `rendered` | ¿Qué geometría ve el usuario en esta ciudad? | COG nativo o distrito |
| `detail` | ¿Qué activo fino verificable carga el navegador? | `cog`, `geojson`, `vector_contours` o `null` |

Nunca uses «resolución nativa» sin aclarar si describe fuente, observación,
análisis o mapa. En la interfaz, `rendered` manda.

Tampoco afirmes que las comunas «sólo delimitan» sin revisar `boundary_role`:

| Rol | Uso correcto |
|---|---|
| `mask_only` | AOI de un detalle nativo; el límite no crea el valor |
| `analysis_unit` | reducción zonal o resumen cuyo valor depende de la unidad |
| `source_unit` | dato originalmente publicado en esa unidad |
| `component_specific` | compuesto sin soporte espacial único |

Un ráster procesado a escala nativa pero publicado sólo como promedio comunal
no es un mapa nativo: es un producto administrativo derivado.

## Antes de recopilar datos

1. Confirma en `config/layers/` la colección, banda, escala y periodo canónicos.
2. Confirma que el estudio agregado declara `spatial.unit_type` y
   `expected_units`.
3. Confirma que declara `detail.native_study`. **No es condicional**: todo
   estudio agregado visible en el selector con indicadores ráster lo necesita,
   porque sin él no existe estudio native, `exposome detail` no tiene qué
   convertir, y la ciudad se publica pintando unidades administrativas planas.
   La única excepción son los pilotos de una sola capa vectorial
   (`barcelona_districts_noise`, `barcelones_noise_pilot`), cuyo detalle es MVT
   `vector_contours` y no ráster nativo.

   El 2026-08-11 esta línea decía «cuando corresponde» y tres estudios
   —`pais_vasco_provincias`, `cataluna_comarques`, `san_juan_departamentos`—
   pasaron sin declararlo. `tests/test_native_detail_contract.py` lo comprueba
   ahora en tiempo de config; para verificarlo a mano:

   ```bash
   PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest tests.test_native_detail_contract
   ```

   Si falta, el compañero se crea con
   `scripts/migrations/build_native_aoi.py` (AOI por disolución de las unidades
   ya validadas) más un `config/studies/<ciudad>_native.yaml` calcado de
   `pais_vasco_native.yaml`.
4. Ejecuta sólo el preflight local:

   ```bash
   exposome run --study <aggregate> --dry-run
   exposome run --study <native> --dry-run
   ```

5. Un `resolution_warning` puede ser correcto. Documenta que la fuente es más
   gruesa; no cambies la escala para eliminar el warning.
6. Revisa que el nombre del caché dependa de cada parámetro que cambia valores.
   Si un cambio de colección/escala reutiliza el mismo archivo, corrige el
   namespace antes de la corrida. No confíes sólo en `--force`.

Para obtener el lote exacto por ciudad sin iniciar ninguna descarga:

```bash
exposome resolution-plan --all
# o una ciudad publicada:
exposome resolution-plan --bundle webapp/public/data/v1/<iso2>/<city>/<study>
# por id de estudio: reutiliza su bundle si ya existe; sólo construye el
# escenario pre-publicación cuando no hay manifest en --output/--version:
exposome resolution-plan --study <aggregate>
```

El plan separa la exportación nativa, el cálculo agregado, el detalle local y
la publicación. Sus comandos son instrucciones para una persona: no son parte
de un chequeo automático del asistente. `assessment_source` indica si el
diagnóstico vino de `published_bundle` o de `configured_study`; un manifest
existente pero corrupto detiene el comando en vez de inventar faltantes.

## Después de la corrida humana

Inspecciona antes de reconstruir el master:

- cantidad exacta de `spatial_id` y ausencia de duplicados;
- valores finitos y unidades correctas;
- colección y escala efectivas en `*_metadata.json`;
- rango de fechas y checksum;
- número y distancia de fallbacks espaciales, cuando existan;
- que ningún caché pertenezca a otra ciudad o configuración.

La publicación debe detenerse si ALAN no usa 463,83 m, calor no usa ERA5-Land
o viento no usa `ECMWF/ERA5_LAND/HOURLY` bajo la configuración vigente.

## Materializar y publicar detalle

La recolección del estudio nativo la ejecuta el humano. Después, el posproceso
es local:

```bash
exposome detail --study <aggregate> --indicators pm25,no2,alan,wind
exposome run --study <aggregate> --resume
exposome verify --study <aggregate>
python scripts/export_study_profiles.py --study <aggregate>
exposome publish --study <aggregate>
python scripts/export_webapp_distributions.py
```

Cuando la corrida nativa también materializó métricas físicas de calor o
lluvia, publica cada métrica en su propio COG —no la banda de un índice
relativo— con:

```bash
exposome run --study <native> --layers climate_heat,precipitation --resume
exposome detail --study <aggregate> \
  --indicators heat_summer_tmax,heat_hot_days,heat_tropical_nights,rain_annual,rain_dry_spell,rain_heavy
```

El exportador nativo de calor usa los meses estivales de la ubicación
(diciembre--febrero al sur del ecuador; junio--agosto al norte, salvo una
configuración local explícita). Los grupos `heat`/`rain` y sus índices no
reciben COG: son combinaciones de z-scores o percentiles dentro del estudio y
no existen como píxeles observados.

`exposome run --study <aggregate> --layers healthcare --resume` materializa
además `subcomuna/healthcare.geojson`: celdas estables de 1 km con la distancia
real al establecimiento más cercano. La media que llega al master es un resumen
ponderado de esas celdas; no se replica sobre ellas. El índice de
infraestructura social sigue administrativo porque combina conteos, población,
cobertura y z-scores del estudio.

Para dosel, primero materializa el producto nativo y luego su COG:

```bash
exposome run --study <native> --layers greenspace_multisource --resume
exposome detail --study <aggregate> --indicators canopy --resume
```

El detalle resultante es una fracción de dosel calculada en celdas de 30 m; la
fuente Meta/WRI de 1 m se conserva como procedencia, pero no se afirma como
resolución fiable del mapa.

Para `green`, el detalle correcto es el porcentaje Dynamic World por celda
estable de 1 km, no una imagen de clase 10 m ni una repetición del promedio
comunal. Tras completar la capa de verdes, la persona ejecuta:

```bash
python scripts/export_webapp_green_subcomuna.py --study <aggregate>
```

El script consulta GEE, deja checkpoint por lote y escribe
`subcomuna/green.geojson` con `grid_alignment: study_aoi_metric_grid`; por eso
no se ejecuta automáticamente por un asistente.

Para ruido MER/SICA de España, el posproceso también es local y reanudable. No
instala herramientas de sistema ni consulta al proveedor:

```bash
python scripts/build_noise_vector_tiles.py --study barcelona_districts_noise --resume
exposome materialize --study barcelona_districts_noise
exposome verify --study barcelona_districts_noise
exposome publish --study barcelona_districts_noise
exposome spatial-audit \
  --bundle webapp/public/data/v1/es/barcelona/barcelona_districts_noise --strict
```

El gate de Barcelona debe pasar antes de repetir el constructor para
`cataluna_comarques` y `pais_vasco_provincias`. El descriptor
`noise_lden.vector_contours.json` y su informe enlazado prueban zooms 11--15,
hashes del snapshot, topología, solape crudo→resuelto registrado y variación de
área resuelta→simplificada→MVT <=0,5 % por banda, teselas
<=500 kB comprimidas y carga inicial <=2 MB. No se escribe una resolución en
metros: la fuente y el mapa son polígonos categóricos.

SPI permanece administrativo: su implementación vigente ajusta la distribución
sólo después de agregar la serie diaria CHIRPS por unidad. No se debe rasterizar
esa tabla. Una futura versión deberá conservar la serie temporal por píxel y
validar el mismo ajuste SPI antes de que la auditoría pueda exigir detalle.

`exposome detail` no fabrica datos: convierte a COG activos nativos ya
materializados. Verde usa su exportador reanudable de grilla estable y sólo se
publica cuando el GeoJSON declara `grid_alignment: study_aoi_metric_grid`.

Para recuperar ALAN ciudad por ciudad, incluidos los pares de estudio nativo y
agregado y la verificación de la grilla VIIRS de 15 arc-segundos, sigue
[recuperar-alan-nativo.md](recuperar-alan-nativo.md).

## Puertas de aceptación

```bash
exposome spatial-audit --bundle webapp/public/data/v1/<iso2>/<city>/<study> --strict
exposome spatial-audit --all --strict
exposome resolution-coverage --all --tier preview
exposome resolution-coverage --all --tier production
python scripts/validate_webapp_info.py --registry --bundles
cd webapp
npm test
npm run build
```

`spatial-audit` responde si el manifest es honesto: una ciudad puede declarar
correctamente que todavía sólo muestra polígonos administrativos. En cambio,
`resolution-coverage` compara cada capa disponible con el máximo soporte que
su método puede publicar. Un resultado `preview` es visible con la etiqueta
**VISTA PREVIA**, pero no se puede promover a producción hasta que el comando
con `--tier production` pase o la capa tenga una excepción administrativa o de
componentes documentada.

Para ALAN, la puerta canónica exige además una grilla fuente VIIRS de 15
arc-segundos (463,83 m nominales) registrada desde el TIFF inspeccionado. Un
archivo a 500 m, aunque contenga variación intra-comuna, permanece oculto hasta
que sea regenerado.

El sidecar de todo COG nuevo debe incluir `source_sha256`, `source_band`,
`source_grid` y `storage_grid`. `exposome detail --resume` verifica el hash y
la banda antes de reutilizarlo; si cambia el TIFF fuente, reconstruye el COG.

En navegador verifica al menos:

1. Una ciudad sin detalle dice «Mapa: distrito/comuna/...», aunque la fuente
   sea de 1 km.
2. Una ciudad con COG dice «Celda» y la resolución del `rendered` del manifest.
3. FUENTE y DESCARGAR distinguen «Mapa» de «fuente».
4. No hay 404 al cambiar ciudad, indicador, perfil ni descarga.
5. El selector temporal sólo aparece si el manifest publica años válidos.
6. Analytics no usa detalle fino de una única ciudad ni activos no verificados.
7. Al pasar por un COG, popup, indicador y monitor muestran el mismo valor y la
   misma unidad; al salir se restaura el valor y dominio de la unidad
   seleccionada. Si el detalle usa otra métrica —NO₂ columna en `mol/m²` frente
   al proxy comunal— también debe cambiar la etiqueta y nunca ubicar el valor
   comunal sobre la leyenda del ráster.
8. Polígono, grilla GeoJSON y COG usan el mismo tooltip: nombre de unidad,
   métrica, valor/unidad y soporte activo. El nombre se obtiene de la capa de
   límites bajo el cursor, incluso cuando el valor viene de un píxel.
9. La leyenda mantiene una barra de 320 px en todos los exposomas; los nombres
   largos ocupan como máximo dos líneas y no cambian el ancho del colorbar.
10. Un contorno MVT dice «Banda Lden modelada: 55--59 dB(A)», muestra cinco
    categorías y deja visible, atenuado, el contexto administrativo fuera de la
    huella modelada; nunca lo presenta como una medición puntual.

## Incidentes conocidos y prevención

| Síntoma | Causa observada | Prevención automática |
|---|---|---|
| Lima/Medellín mostraban PM2.5 «≈1 km» sin píxeles | etiqueta heredada del catálogo global | `spatial_indicators.rendered` por bundle |
| ALAN/viento históricos reaparecían como detalle | existencia del TIFF tomada como prueba | escala canónica + sidecar + `canonical_resolution_verified` |
| `--force` podía conservar ALAN a 500 m | caché sin colección/escala en su clave | namespace hash de proveedor, banda, escala y población |
| Analytics usaba un ráster obsoleto | buscaba archivos en `data/processed` | sólo detalle publicado v3 y compartido por ≥2 ciudades |
| NO₂ parecía tener precisión física de 1,1 km | grilla L3 confundida con huella TROPOMI | `downloaded` separado de `observation` |
| Todas las capas OSM parecían grillas de 1 km | fuente vectorial confundida con soporte analítico | contratos vector/admin específicos por capa |
| Calor de Lima perdió distritos costeros | polígonos sin intersección con centros ERA5-Land | fallback al píxel más cercano acotado a una celda nativa y registrado |
| Viento decía ERA5 aunque la config pedía ERA5-Land | metadata histórica no bloqueaba publicación | `aggregate_provenance_issues` |
| Viento de Santa Marta falló con `wind_u_mean` | reducción directa no devolvió centros de píxel ERA5-Land en borde costero | píxeles nativos + intersección por área; fallback observado <= una celda |
| Calor de Cartagena no obtuvo ERA5-Land mensual | la consulta no alcanzaba píxeles cuyos centros quedaban fuera del AOI | anillo de una celda nativa y namespace de caché nuevo |
| Salud de Santa Marta no tenía `n_access_grid` | caché parcial OSM y categoría explícita ausente | caché identificado por AOI/tags/buffer; sin proxy ni sentinel si falta salud/hospital/primaria |
| `verify`/`publish` rechaza `release_manifest.json` después de un `run --layers` | una recuperación parcial actualiza capas pero, por diseño, no reemplaza el master ni la release completa; los estudios históricos además pueden conservar manifest v1 | ejecutar el cierre local del plan: migrador v1/v2 explícito, perfiles, `exposome materialize`, `verify` y recién `publish` |
| `Image.reduceResolution` rechaza canopy sin proyección | el mosaico Meta/WRI perdió la proyección predeterminada de sus teselas | conservar la proyección de una tesela fuente con `setDefaultProjection()` antes de calcular la fracción a 30 m |
| CHIRPS nativo falla al mezclar años bisiestos | Earth Engine tipa CDD como `Short<0,365>` o `Short<0,366>` según el año | convertir los componentes anuales a `Float` antes de calcular la media 2015--2024 |
| `climate_heat` falla porque falta `*_era5land_grid_<año>.csv` | el runner importable saltaba la etapa que crea o reanuda el caché ERA5-Land | `build_climate_heat_layer()` llama a `ensure_era5land_daily()` antes de leerlo; una corrida normal recupera sólo el año faltante |
| Un runner configurado por Study falla con `KeyError: 'region_query'` | `resolved_config()` omitía claves de ubicación que todavía requieren adaptadores legacy | la configuración inyectada conserva `location_id`, país, zona horaria y un `region_query` derivado de la ubicación |
| Salud falla con `float() argument must be a string or a real number, not 'Series'` | `sjoin_nearest` puede conservar índices duplicados en celdas limítrofes/equidistantes; seleccionar un cuantil con `.loc` devuelve varias filas | cuantiles de distancia ordenados y seleccionados por posición; prueba explícita con índices duplicados |
| ALAN se publica como mapa administrativo pese a declarar 463,83 m | el promedio anual VIIRS perdió su proyección predeterminada y el exportador obtuvo una grilla nominal de 1° | conservar la proyección de una imagen mensual VIIRS con `setDefaultProjection()`; exigir la grilla fuente de 15 arc-segundos en la auditoría |
| PM2.5, NO₂, ERA5-Land o CHIRPS forman bloques enormes aunque la etiqueta dice 0,01°/0,05°/0,1° | `ImageCollection.mean()` u otro reductor perdió la proyección fuente y Earth Engine asignó su grilla fallback de 1°; el antiguo sidecar sólo repetía la escala configurada | restaurar la proyección de la primera imagen fuente con `setDefaultProjection()`, exportar con su `crs_transform`, inspeccionar el TIFF descargado y rechazar automáticamente cualquier grilla fuera de tolerancia antes de crear el COG |
| El cursor cambia el mapa pero el monitor conserva la intensidad o unidad comunal | el COG reemplazaba globalmente el dominio del estudio y el preview transportaba sólo un número | transportar por hover `{value, domain, unit, metricLabel}`; normalizar con el `color_domain` del COG y restaurar el contexto base de la comuna al salir o al recibir nodata |
| `resolution-plan --study` pide reconstruir una publicación completa | la ruta por estudio generaba siempre un manifest sintético vacío, aunque el bundle existiera | resolver primero `webapp/public/data/<version>/<país>/<ciudad>/<estudio>` y auditar su manifest; usar el escenario sintético sólo antes de la primera publicación |
| El selector decía `Open-Meteo 2024` mientras mostraba píxeles ERA5-Land, y reutilizaba ese COG en años anteriores | el detalle espacial no declaraba su cosecha temporal y la UI activaba cualquier COG disponible para todos los años | todo COG anual declara `detail.temporal_support`; para series raster exigidas, cada año tiene su propio COG o la publicación se bloquea y el selector se oculta |
| PM2.5 cambiaba numéricamente entre años pero el patrón de píxeles parecía inmóvil | la tabla anual sí cambiaba, pero el mapa superponía siempre el COG ACAG promedio 2015--2022 | publicar un COG ACAG por cosecha bajo `temporal_indicators`, exigir año y hash distintos, usar un dominio común y bloquear la serie incompleta |
| El hover mostraba un cuadro blanco distinto según el tipo de mapa | polígono, GeoJSON fino y COG construían popups independientes; el COG tampoco resolvía la comuna bajo el píxel | un único renderer de tooltip consulta `communes-fill` y presenta siempre unidad, métrica, valor/unidad y soporte renderizado |
| El colorbar cambiaba de largo entre exposomas | la leyenda crecía según el nombre de la métrica | ancho fijo de 320 px, título limitado a dos líneas y período truncado sin alterar la barra |
| El migrador v2 fallaba con `Study release settings fingerprint is stale` aunque se usara `--allow-stale-settings` | `load_release()` comprobaba el fingerprint antes de permitir que el migrador aplicara su rebind explícito | `load_release(..., allow_stale_settings=True)` existe sólo para recuperación local; verificación y publicación conservan el modo estricto por defecto, con prueba de regresión |
| `publish` aborta con «Annual spatial publication is incomplete for required series» y el año faltante es un hueco de fuente permanente, no una corrida pendiente | `_write_temporal_assets()` no distinguía un hueco transitorio de uno confirmado y reproducido (Dynamic World sin píxeles válidos para Bogotá/Los Mártires/2019) | declarar `temporal_exceptions` en el estudio (ADR 0008): resta el año del chequeo bloqueante sin tocar `expected_years`, así que `resolution-coverage` sigue exigiendo la serie completa y el estudio permanece en `preview` |
| Una ciudad pinta unidades administrativas planas pese a tener todas sus capas ráster corridas y sus series anuales completas | el estudio agregado no declara `detail.native_study`, así que no existe estudio native, `exposome detail` no tiene rásters que convertir y ningún indicador publica COG. Medido el 2026-08-11: `pais_vasco_provincias` con 14/14 capas y 83/83 anuales publicaba `preview` con **1 de 14** indicadores espaciales | `tests/test_native_detail_contract.py` exige la declaración para todo agregado no oculto, valida que el native exista y que su AOI sea legible |
| Un estudio figura `production / complete` con `required_indicators: 0` y aun así no tiene ningún detalle nativo | `spatial_coverage.py:93` — `base_required = required_for_production and available` — sólo exige un indicador si **su capa está publicada**, de modo que publicar menos capas mejora el tier. `cataluna_comarques` leía `production` por haberse publicado con `noise_spain` sola | la misma guarda de config; y el tier deja de tratarse como prueba suficiente de cobertura espacial (ADR 0011) |
| Los tiles vectoriales de ruido mueren con `TopologyException: side location conflict at <x> <y>`, una coordenada que no nombra banda ni aglomeración | la validez geométrica no sobrevive a un cambio de CRS: `_simplify` la comprueba en EPSG:3035, pero el pipeline cruza a EPSG:3857 para teselar y vuelve al decodificar, y ninguno de los dos cruces revalidaba. Medido: 13 de 9.052 partes válidas en 3035 volvían inválidas en 3857 | `_repair_after_reprojection` en las dos costuras de CRS, acotado por la puerta de área ya existente (pérdida medida: 0,006 % peor caso); regresión en `tests/test_noise_spain_tiles.py` |
| Cualquier paso que lea el snapshot SICA/MER falla con `FileNotFoundError` sobre un `.zip` que parece perdido | el payload crudo (2,7 GB) vive fuera del repo bajo `$GEMMA_RAW_PAYLOAD_ROOT` por diseño, pero la variable no está exportada en ningún perfil de shell | `resolucion_nativa.sh` la deriva del destino del symlink `cache` y aborta con el `export` exacto si no la encuentra |

### Detalle espacial limitado a un año

Un COG anual no representa automáticamente toda la serie temporal del master.
Su descriptor público debe declarar, como mínimo:

```json
"temporal_support": {
  "kind": "year",
  "year": "2024",
  "source_label": "ERA5-Land"
}
```

Para una serie raster exigida en producción, todos sus años deben mostrar el
COG correspondiente. No se admite que 2024 muestre ERA5-Land y 2015--2023
vuelvan a coropletas administrativas. Al cambiar de año cambian juntos el
activo, la leyenda, el popup y el texto `Celda`/`Mapa`.

Para una serie raster completa, cada año vive además en
`temporal_indicators.<id>.years.<año>.detail`. La auditoría estricta exige que
el año coincida, que los hashes fuente sean distintos y que todos los detalles
usen el `color_domain` común de la serie. Un COG de período (`kind: period`) es
válido sólo para la vista base o promedio.

Si `spatial_target.required_for_production` es verdadero y falta cualquier
`expected_year`, `publish`, `spatial-audit --strict` y
`resolution-coverage --tier production` bloquean el cierre. La app oculta el
selector incompleto y un estado obsoleto devuelve «cosecha espacial no
publicada», nunca un fallback comunal silencioso.

## Cierre de una recuperación parcial

Un comando parcial como `exposome run --study X --layers alan --resume` puede
recolectar una capa correctamente, pero no debe publicar por sí mismo: todavía
no existe una release consistente que enlace todas las capas, el master y los
activos de detalle. Después de completar las capas que indica
`exposome resolution-plan`, ejecuta este cierre, en este orden:

```bash
# Sólo local: conserva backups *.v1.json y convierte los artefactos históricos.
# --allow-stale-settings exige que primero se hayan re-ejecutado las capas
# afectadas por cambios de configuración, tal como aparece en el plan.
python scripts/migrations/upgrade_artifact_manifests_v2.py \
  --study <study> --write --allow-stale-settings

python scripts/export_study_profiles.py --study <study>
exposome materialize --study <study>
exposome verify --study <study>
exposome publish --study <study>
```

`materialize` no consulta GEE, OSM, Open-Meteo ni otro proveedor: reconstruye
el master y la release schema-v2 únicamente si cada capa habilitada ya tiene un
bundle v2 verificable. Por eso falla de forma segura si falta una capa o si se
intentó saltar la migración. No edites a mano `release_manifest.json`.

## Huecos permanentes de fuente: `temporal_exceptions`

Un año faltante en una serie anual requerida normalmente bloquea `publish` y
`spatial-audit --strict` (ADR 0007) — así debe ser: la mayoría de los huecos
son transitorios y se resuelven corriendo `run_missing_annual_exposomes.py`.
Pero algunos son permanentes: la fuente no tiene observación válida para esa
celda espacio-temporal específica, confirmado y reproducido, no una corrida
pendiente. `bogota_localidades`/`greenspace_multisource` es el primer caso:
Dynamic World no devuelve píxeles válidos para Los Mártires en 2019
(`docs/greenspace_multisource_methodology.md#limitations`).

Para ese caso, declara la excepción en el estudio en vez de editar el chequeo
o rellenar el dato ([ADR 0008](../../adr/0008-excepciones-temporales-documentadas.md)):

```yaml
# config/studies/<id>.yaml
temporal_exceptions:
  - layer_id: <capa>
    indicator: <indicador>
    years: [<año>]
    reason: >-
      Motivo verificable y reproducido, con referencia a la metodología.
    doc: docs/<metodologia>.md#seccion
```

`layer_id` debe estar habilitado por el estudio; `reason` y `doc` son
obligatorios. La excepción resta ese año del chequeo que bloquea `publish`
para esa capa, pero **no** toca `expected_years` en el manifest publicado, así
que:

- `spatial-audit --strict` sigue pasando (verifica que la excepción sea
  subconjunto de `expected_years` y tenga motivo documentado).
- `resolution-coverage` **no** cambia — sigue exigiendo la serie completa para
  `production`. El estudio queda en `preview` a propósito.
- El supervisor nocturno detecta una excepción documentada y usa
  `resolution-coverage --tier preview` tanto en staging como al validar la
  publicación. Esto permite publicar el estudio restante, pero no promueve su
  bundle a producción ni permite huecos que no estén declarados.
- La app oculta el selector temporal de ese indicador (serie declarada
  incompleta), pero el indicador sigue visible con su soporte espacial
  habitual — grilla fina o COG si los publica, no un choropleth
  administrativo forzado. El bloqueo retira sólo el eje de años, nunca la
  capa. Verificado en vivo para `bogota_localidades`/`green`: la grilla fina
  de 1.861 celdas se sigue renderizando, sólo desaparece el selector.

No declares una excepción para un hueco que todavía no confirmaste como
permanente: primero corré `run_missing_annual_exposomes.py --resume` al menos
una vez y documentá la reproducción en la metodología de la capa.

## Qué actualizar cuando cambia una fuente

- configuración canónica y metodología;
- namespace del caché si cambia el contenido;
- metadata y manifest de capa;
- master y `release_manifest.json`;
- sidecar y descriptor del detalle;
- bundle, catálogo y distribuciones;
- [resolution_manifest.md](../../resolution_manifest.md) y, si cambia una
  decisión estable, un ADR nuevo. No reescribas este ADR como historial mutable.
