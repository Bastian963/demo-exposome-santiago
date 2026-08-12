# Manifiesto de resolución por capa

Este documento responde una pregunta concreta: **¿cada exposoma se genera a la
máxima resolución que su fuente y metodología permiten, o se está perdiendo
detalle intra-unidad innecesariamente?** Es la contraparte auditable de la
"Filosofía de resolución" declarada en `CLAUDE.md` y en
`docs/multicity_status.md` § Filosofía de resolución: nunca degradar la
resolución de un producto para igualarla a la de la unidad administrativa; la
agregación por comuna/alcaldía es un derivado, no el producto primario.

La historia de auditoría de 2026-07-16 se conserva más abajo. **El contrato
vigente desde 2026-07-19** es `schema_version: 3` de `webapp/public/data/v1/<país>/<ciudad>/<study>/manifest.json`:
el visor toma el soporte espacial, unidad y activo de detalle exclusivamente
desde `spatial_indicators`, no desde un flag global de `palette.json`.
La decisión estable vive en
[`adr/0004-published-spatial-support-contract.md`](adr/0004-published-spatial-support-contract.md)
y su checklist operativo en
[`knowledge/runbooks/publicar-resolucion-espacial.md`](knowledge/runbooks/publicar-resolucion-espacial.md).

## Respuesta corta: no todos los mapas están a resolución de origen

El pipeline evita degradar silenciosamente la fuente, pero eso no significa que
cada ciudad ya publique todos los píxeles originales. Coexisten dos productos:

1. el producto nativo, cuando el estudio acompañante lo materializó y el bundle
   publica un detalle verificado;
2. el resumen por comuna/distrito/municipio usado por perfiles y choropleth.

Si sólo existe el segundo, la fuente pudo haberse evaluado sobre su grilla
nativa durante la reducción zonal, pero el mapa disponible sigue siendo
administrativo. No debe llamarse «mapa de 1 km».

Los límites administrativos tienen roles explícitos:

| `boundary_role` | Papel del límite | Variación intraunidad publicada |
|---|---|---|
| `mask_only` | Recorta/delimita un detalle nativo; no define píxeles ni valores | Sí, mediante COG/GeoJSON/MVT verificado |
| `analysis_unit` | Define el grupo sobre el cual se calcula y reporta un resumen | No |
| `source_unit` | La fuente original ya viene en esa unidad administrativa | No y no debe inferirse |
| `component_specific` | Índice con componentes de soportes diferentes | No hay una resolución única |

Por tanto, «las comunas sólo delimitan» es correcto únicamente para un activo
nativo con `mask_only`. En un choropleth agregado, las comunas son
`analysis_unit`; en CASEN, SAE u otras fuentes administrativas pueden ser
`source_unit`.

## Contrato vigente de visualización

- Una unidad administrativa es solo máscara/consulta. Nunca define el origen
  de la grilla, el valor de un píxel ni una conversión de unidades.
- Un raster nativo publicado se convierte localmente a **COG en EPSG:3857** y
  se renderiza con remuestreo `nearest`. El COG conserva su grilla nativa; no
  se vectoriza ni se inventa una malla de 1 km.
- Una fuente vectorial categórica puede conservar sus polígonos mediante MVT.
  No recibe resolución en metros: la auditoría verifica procedencia, área por
  categoría, topología, zooms y presupuestos de transferencia.
- La resolución nominal no basta: el sidecar conserva la `source_grid`
  inspeccionada y debe coincidir con el CRS/paso canónico del indicador. Un
  reductor de Earth Engine que cae a 1° se bloquea antes de descargar y vuelve
  a comprobarse sobre el TIFF escrito.
- Si el manifiesto no publica un activo de detalle para un indicador, el visor
  muestra y etiqueta solo el resumen administrativo, aunque la fuente original
  sea fina. La pestaña de descarga separa explícitamente «Mapa» de «fuente».
- Un detalle con `temporal_support.kind: year` sólo puede mostrarse durante esa
  cosecha. Las series raster exigidas deben publicar detalle para todos sus
  años; no se mezcla ERA5-Land anual con columnas comunales Open-Meteo.
- NO₂ fino se entrega como columna troposférica Sentinel-5P en `mol/m²`. La
  concentración comunal derivada con BLH no se aplica píxel a píxel.
- Las fuentes administrativas permanecen como tales. Para indicadores
  compuestos, cada componente conserva su soporte; no se les asigna una falsa
  resolución común.
- La LST de ECOSTRESS (70 m) **no** reemplaza el calor de ERA5-Land (11.132 km):
  son cantidades físicas distintas — temperatura radiativa de superficie contra
  temperatura del aire a 2 m — y conviven como capas separadas. Un producto más
  fino no autoriza a retirar el más grueso cuando no miden lo mismo. Ver
  `docs/lst_ecostress_methodology.md`.

| Indicador publicado | Soporte analítico | Detalle v3 |
|---|---:|---|
| PM2.5 | ≈1.113 km | COG nativo, si existe el estudio nativo |
| NO₂ | ≈1.113 km | COG de columna S5P (`mol/m²`), si existe el estudio nativo |
| ALAN | 463.83 m | COG nativo, si existe el estudio nativo |
| Viento ERA5-Land | 11.132 km | COG nativo, banda de velocidad, si existe el estudio nativo |
| Verde Dynamic World | fuente 10 m; estimador publicado 1 km a 30 m | GeoJSON de grilla común al AOI, solo después de corrida real reanudable |
| Calor físico ERA5-Land | ≈11.132 km (0,1°) | COG por métrica física, si su grilla inspeccionada es canónica |
| LST ECOSTRESS | 70 m | COG por ventana solar (media, máximo, conteo de observaciones), una vez corrida la capa. **Aún no producido para ningún estudio.** |
| Lluvia física CHIRPS | ≈5.566 km (0,05°) | COG por métrica física, si su grilla inspeccionada es canónica |
| Ruido España MER/SICA | polígonos Lden 2022 en EPSG:3035 | MVT categórico `vector_contours`, zooms 11--15, sin resolución raster |
| SPI, índices compuestos de calor/lluvia, incendios, OSM y administrativos | según fuente o unidad de origen | solo resumen hasta publicar un activo que cumpla el mismo contrato |

Para series raster anuales, el detalle vive por cosecha en
`temporal_indicators.<id>.years.<año>.detail`; el COG agregado del período no se
reutiliza en el slider. La publicación exige hashes distintos y aplica un solo
dominio cromático robusto a todos los años. Si falta un raster anual, el valor
no se publica como serie de producción y la app oculta el selector incompleto.

Los modos administrativo, grilla GeoJSON, COG y contornos MVT comparten tooltip
(unidad, métrica, valor/unidad y soporte renderizado) y una leyenda de 320 px.
Estas son reglas transversales de la app, no excepciones visuales de Santiago.

Auditoría España actualizada el 2026-08-10:

- `barcelona_districts_noise` es el gate del detalle Lden; el rollout a
  `cataluna_comarques` y `pais_vasco_provincias` usa exactamente el mismo
  constructor y contrato.
- Los contornos sólo cubren la huella modelada de las aglomeraciones MER. El
  mapa administrativo permanece atenuado fuera de ella para dar contexto sin
  inventar exposición.
- `barcelones_noise_pilot` conserva su condición parcial: aunque publique MVT,
  no representa las doce aglomeraciones de la release catalana completa.
- La decisión y presupuestos verificables están en
  [ADR 0010](adr/0010-noise-spain-mvt-vector-contours.md).

Auditoría multiciudad actualizada el 2026-07-20:

- Una inspección del TIFF descubrió que los COG de Santiago para PM2.5, NO₂,
  calor físico, lluvia física y viento eran rásteres 3×3 sobre una grilla de
  1°, aunque sus sidecars repetían la resolución nominal configurada. La
  publicación segura los oculta y deja el estudio en tier `preview` hasta su
  reexportación. ALAN, verde, dosel y salud conservan detalle verificado.
- AMBA conserva sus COG canónicos. El contrato nuevo se aplica por indicador y
  ciudad, por lo que un activo válido de otra ciudad no puede rehabilitar uno
  defectuoso de Santiago.
- CDMX ya conserva los rasters nativos en `cdmx_native`; el posproceso local
  `exposome detail` enlazó PM2.5 y NO₂ al estudio agregado, todavía no publicado.
- Bogotá (`bogota_localidades`, 14 capas configuradas) publica en tier
  `preview`, no `production`: `resolution-coverage` reporta 12/13 indicadores
  espaciales requeridos completos, con `green` (`greenspace_multisource`)
  como único faltante — declara una excepción temporal documentada para Los
  Mártires/2019 (Dynamic World sin píxeles válidos, determinista, ver
  `docs/greenspace_multisource_methodology.md#limitations` y
  [ADR 0008](adr/0008-excepciones-temporales-documentadas.md)). Los otros 12
  indicadores requeridos y sus COG/grillas de detalle están verificados;
  `green` sigue visible como coropleta del promedio del período, sólo su
  selector temporal se oculta.
- Lima y Medellín conservan solo reducciones zonales, por lo que anunciar
  «≈1 km» como resolución del mapa era incorrecto. Hasta materializar sus
  estudios nativos, el visor declara distrito/comuna como soporte renderizado
  y mantiene 0,01° únicamente como resolución de la fuente.
- El control encontró además rasters históricos de ALAN a 500 m y viento a
  9 km en Santiago/CDMX. Deben regenerarse a las escalas canónicas vigentes
  (463,83 m y 11.132 m) antes de volver a publicar esos detalles.
- Las fuentes OSM son vectoriales. Salud e infraestructura social calculan
  acceso en grilla de 1 km; caminabilidad, comida y acceso verde publican un
  indicador administrativo. El manifest ya no les asigna a todas una falsa
  grilla común de 1 km.
- Los reductores nativos de ACAG, S5P, ERA5-Land y CHIRPS preservan ahora la
  proyección de la imagen fuente. El exportador usa el `crs_transform` real,
  valida la grilla antes y después de la descarga, y la puerta canónica evita
  que un fallback de 1° vuelva a anunciarse como píxel nativo.

El comando local `exposome detail --study <aggregate>` prepara los COG desde
artefactos nativos ya existentes; no consulta proveedores. Para AMBA se agregó
`buenos_aires_amba_native`, que cubre todo el AOI de 55 unidades y debe correr
por los pipelines normales antes de poder publicar detalle.

Antes de desplegar, ejecutar la auditoría local sobre el bundle publicado:

```bash
exposome spatial-audit --bundle webapp/public/data/v1/cl/santiago/santiago_communes
```

La auditoría exige cobertura para cada tarjeta de `palette.json`, un contrato
v3, activos de detalle existentes y metadata COG; para verde exige además la
grilla común `study_aoi_metric_grid`.

La tabla y hallazgos siguientes son el registro histórico previo al contrato
v2; sus rutas `webapp/public/data/subcomuna/*.geojson`, la conversión fina de
NO₂ con BLH comunal y las cifras de 9 km para ERA5-Land no describen el
comportamiento vigente.

## Cómo leer la tabla

- **Resolución nativa**: la del producto fuente (tamaño de píxel del sensor o
  reanálisis), tomada de `config/layers.yaml` (`native_resolution_m`) y
  `config/cities/santiago.yaml` / `config/layers/*.yaml` (`scale_meters`).
- **Escala usada en reducción zonal**: el `scale` pasado a
  `reduceRegions`/`image_to_stats` al calcular el estadístico por
  comuna/alcaldía. Cuando coincide con la nativa, la comuna no pierde
  resolución en el agregado — el número por comuna es tan bueno como el
  píxel lo permite.
- **Producto fino materializado**: si existe una salida que preserva
  variación intra-comuna (webapp `subcomuna/*.geojson`, patrón `caba_native`)
  o si solo existe el agregado por unidad.

## Capas raster globales (GEE) — resolución fuente

| Capa | Fuente | Resolución nativa | Escala zonal usada | Producto fino | Patrón nativo (`caba_native`) |
|---|---|---:|---:|---|---|
| `pm25` (air_quality_pm25) | ACAG/van Donkelaar V6, awesome-gee-community-catalog | ~1113 m | 1113 m (coincide) | ✓ `webapp/public/data/subcomuna/pm25.geojson` (real, 14.971 celdas, reemplaza el placeholder sintético v0.6), `has_fine_layer: true` | ✓ GeoTIFF nativo |
| `alan` | VIIRS DNB monthly (VCMSLCFG) | 500 m | 500 m (coincide) | ✓ `subcomuna/alan.geojson`, `has_fine_layer: true` (real, sin cambios en esta fase) | ✓ GeoTIFF nativo |
| `greenspace_coverage` | Landsat 8/9 C2 (NDVI/EVI) | 30 m | 30 m (coincide) | ✗ ninguno | ✓ GeoTIFF nativo (CABA y Santiago) — ver Hallazgo 3b sobre el fix de tiling que hizo falta para Santiago |
| `greenspace_multisource` — Dynamic World | Dynamic World V1 | 10 m | 30 m (`commune_scale_meters` en `config/layers/greenspace.yaml:46`) — **evaluado y confirmado correcto**, ver Hallazgo 4 | ✓ `subcomuna/green.geojson` — grilla de celdas de 1 km (`scripts/export_webapp_green_subcomuna.py`), cada celda muestreada a 30 m (`fine_scale_meters`, no 10 m: ~1000 muestras/celda hacen la media estadísticamente igual a 10 m, misma justificación que Hallazgo 4, evita timeout de GEE), no reutiliza el agregado comunal, `has_fine_layer: true` | ✗ no está en `NATIVE_LAYER_SPECS` |
| `greenspace_multisource` — canopy | Meta/WRI Global Canopy Height | 1 m | 30 m (`sample_scale_meters`) — **es la escala de uso confiable del producto**, no un compromiso, ver Hallazgo 4 | ✗ ninguno | ✗ no está en `NATIVE_LAYER_SPECS` |
| `precipitation` | CHIRPS Daily | 5566 m (~0.05°) | 5566 m (coincide) | ✗ ninguno | ✓ GeoTIFF nativo |
| `precipitation_spi` | Derivado de CHIRPS (cómputo local) | heredada de CHIRPS | heredada | ✗ ninguno | ✗ (deriva de `precipitation`, que sí es nativo) |
| `climate_heat` | ERA5-Land Daily Aggregated | 11132 m (~0.1°) | 11132 m; métricas por píxel y agregación posterior ponderada por área de intersección | ✗ ninguno (solo agregado administrativo; sin fallback a punto representativo) | ✓ grilla nativa |
| `wind` | ERA5-Land hourly | 11132 m | 11132 m (coincide) | ✗ ninguno | ✓ GeoTIFF nativo |
| `wildfire` — burned_area | MODIS MCD64A1 | 500 m | 500 m (coincide) | ✗ ninguno | ✓ **NUEVO (aclarado)** — `NATIVE_LAYER_SPECS["wildfire"]` exporta el GeoTIFF nativo a esta escala (`native.py:186`, `block["burned_area"]["scale_meters"]`) |
| `wildfire` — active_fire | FIRMS | 1000 m | 1000 m (coincide) | ✗ ninguno | ✗ no se exporta como GeoTIFF propio — solo alimenta el agregado por comuna. `config/layers.yaml`'s `native_resolution_m: 1000` usa este valor (el más grueso de los 2) para el warning de resolución agregada — ver comentario en el YAML |
| `air_quality_satellite` — NO2 | Sentinel-5P TROPOMI | 1113 m (~3.5 km efectivo, swath) | 1113 m (coincide) | ✓ `subcomuna/no2.geojson` (real, 14.971 celdas, conversión a superficie vía BLH comunal), `has_fine_layer: true` | ✓ **NUEVO** — `NATIVE_LAYER_SPECS["air_quality_satellite"]` (banda NO2 sola, 1113 m). Corrida y verificada en `caba_native` y `santiago_native` (GeoTIFF descargado en ambas) |
| `air_quality_satellite` — O3 | Sentinel-5P TROPOMI | 7000 m | 7000 m (coincide) | ✗ ninguno | ✗ fast-follow explícito, ver Hallazgo 3 |
| `air_quality_satellite` — AOD/Angstrom | MODIS MCD19A2 | 3000 m | 3000 m (coincide) | ✗ ninguno | ✗ fast-follow explícito, ver Hallazgo 3 |
| `air_quality_satellite` — BLH (insumo NO2 superficie) | ERA5 hourly | 30000 m | 30000 m (coincide) | — (insumo, no exposoma final) | ✗ |
| `air_quality` (legacy CAMS) | CAMS vía Open-Meteo Air Quality API | 11000 m | 11000 m (coincide) | ✗ | ✗ |
| `greenspace_cv` | Esri World Imagery (zoom 17, ExG+Otsu) | ~1 m (comparador puntual, no censal) | — (muestreo puntual, no zonal) | n/a (es en sí mismo el producto de mayor detalle disponible) | ✗ |

## Capas OSM / vectoriales (sin concepto de "píxel")

`greenspace_access`, `healthcare`, `walkability`, `social_infrastructure`,
`food_environment`, `public_transport`: la fuente es vectorial (features OSM),
así que no hay downgrade de resolución posible en el sentido raster — el
agregado por comuna (conteos, distancias, densidades) ya usa la geometría
exacta de cada feature. Las 5 primeras están en `NATIVE_LAYER_SPECS`
(`caba_native` cachea los features OSM crudos dentro del AOI, sin agregar; las
métricas derivadas — distancia, conteo — se calculan al consultar por
coordenada, no en el momento de descarga).

## Capas administrativas / socioeconómicas (Chile-only, sin fuente fina)

`socioeconomic`, `heavy_metals`, `demography`, `food_insecurity`,
`pobreza_sae`, `noise`, `community_safety`, `community_violence`,
`suicide_mortality`, `road_traffic_mortality`: la fuente original ya es
administrativa (CASEN, censo por manzana agregado a comuna, SNIC por
departamento, mapa de ruido MMA a nivel de manzana pero publicado agregado).
No hay una versión "más fina" disponible sin volver a la fuente cruda (p. ej.
demografía sí tiene microdato por manzana en `demography.py`, pero el
producto público de INE no permite reconstruir manzanas individuales de forma
confiable fuera de ese pipeline). Correctamente marcadas `has_fine_layer:
false` en `palette.json`.

## Hallazgos (auditoría inicial → estado final tras el plan de cierre)

1. **RESUELTO — subcomuna PM2.5 y NO2 eran sintéticos, no un archivo
   huérfano.** La causa real era más grave que "el flag no se activó": tanto
   `subcomuna/pm25.geojson` (marcado `has_fine_layer: true`, mostrado como
   dato real) como `subcomuna/no2.geojson` (marcado `false`) resultaron ser
   el mismo placeholder sintético v0.6 (media comunal + ruido gaussiano,
   mismo seed) — ninguno de los dos tuvo nunca su reemplazo v0.7 con datos
   GEE reales, a diferencia de `alan`/`green`. Se escribieron
   `scripts/export_webapp_pm25_subcomuna.py` y
   `scripts/export_webapp_no2_subcomuna.py` (mismo patrón que
   `export_webapp_alan_subcomuna.py`; NO2 reutiliza el BLH comunal ya
   cacheado para la conversión a superficie — ver docstring del script) y se
   retiró `scripts/export_webapp_subcomuna.py` (el generador sintético
   legacy, sin consumidores tras este cambio). Cubierto por
   `tests/test_export_webapp_pm25_subcomuna.py` y
   `tests/test_export_webapp_no2_subcomuna.py` (11 tests, offline). Mientras
   se esperaba la corrida real se bajó `pm25.has_fine_layer` a `false` en
   `palette.json` (estaba en `true` mostrando el placeholder como si fuera
   real — más honesto no mostrar nada que mostrar datos falsos como reales).
   **2026-07-16: el usuario corrió ambos scripts contra Santiago** — 14.971
   celdas cada uno, `is_synthetic: false`, PM2.5 13.4–29.1 µg/m³ y NO2
   0.5–37.5 µg/m³ (ambos rangos plausibles, verificados antes de activar los
   flags). Ambos flags (`pm25` y `no2`) ya están en `true` en `palette.json`.
2. **RESUELTO — `palette.json`'s `no2.resolution` decía "≈11 km"** (copy del
   `air_quality` legacy/CAMS, desactualizado desde la migración a Plan A++).
   Corregido a "≈1.1 km (S5P)", consistente con `air_quality_satellite`'s
   `scale_meters: 1113` real.
3. **RESUELTO (NO2) / fast-follow explícito (O3/AOD) — `air_quality_satellite`
   no estaba en `NATIVE_LAYER_SPECS`.** NO2 a 1113 m es más fino que `wind`
   (9000 m) o `wildfire` (1000 m), que sí tenían patrón nativo. Se agregó
   `air_quality_satellite` a `NATIVE_LAYER_SPECS` (`src/exposome/native.py`)
   **solo con la banda NO2** — bundlear O3 (7000 m)/AOD (3000 m) en el mismo
   GeoTIFF forzaría una escala común y sobremuestrearía las bandas más
   gruesas, lo que viola la política de CLAUDE.md de nunca fingir detalle por
   sobremuestreo. Habilitado en `caba_native.yaml` (Buenos Aires) y en el
   nuevo `santiago_native.yaml` (ver más abajo). O3/AOD quedan como
   fast-follow con el mismo patrón (entrada propia, su propia escala) si se
   necesitan más adelante. Cubierto por 2 tests nuevos en
   `tests/test_native_pipeline.py`.

   **`santiago_native` (nuevo estudio)**: hasta este cierre, agregar NO2 a
   `NATIVE_LAYER_SPECS` solo tenía efecto en Buenos Aires — Santiago no tenía
   ningún estudio en modo `native`. Se creó `config/studies/santiago_native.yaml`
   (espejo de `caba_native.yaml`, oculto del picker), con AOI en
   `data/reference/cl/santiago/santiago_native/aoi.geojson` — un dissolve
   local de los 52 polígonos comunales de `santiago_communes` (geometría
   pura, sin tocar proveedores), en vez de geocodificar un límite nuevo.
   `exposome audit`/`--dry-run` confirman `ready` para ambos estudios
   (`caba_native` y `santiago_native`). **2026-07-16: corrida real del
   usuario** — `air_quality_pm25`, `alan`, `precipitation`, `climate_heat`,
   `wind`, `wildfire` y `air_quality_satellite` (NO2) descargaron
   correctamente para `santiago_native`; `air_quality_satellite` también se
   corrió y confirmó para `caba_native` (antes solo tenía las 12 capas
   originales). Ver Hallazgo 3b para el problema que apareció con
   `greenspace_coverage` en esa misma corrida, y su cierre.

   **Hallazgo 3b — RESUELTO — `greenspace_coverage` excedía el límite
   síncrono de GEE sobre Gran Santiago.** `export_gee_native_layer` usaba
   `geemap.ee_export_image` (descarga síncrona, tope ~48 MB de GEE). El
   composite NDVI/EVI de 4 bandas a 30 m sobre el AOI disuelto completo
   (~180×150 km, incluye comunas rurales andinas como San José de Maipo)
   pidió ~1,17 GB — ~23x el límite. CABA nunca lo tocó por tener un AOI
   mucho más chico. El preflight/dry-run no lo detecta porque depende del
   tamaño real de la respuesta de GEE, no de nada verificable offline.

   Se encontró además un bug real independiente: `geemap.ee_export_image`
   imprimía el error de descarga pero no lanzaba excepción, así que
   `export_gee_native_layer` seguía y escribía `metadata.json`/`manifest.json`
   como si la exportación hubiera funcionado, con un `.tif` que nunca se
   creó — habría roto `exposome verify` más adelante, lejos de la causa
   real.

   Cierre: se cambió `export_gee_native_layer` a `geemap.download_ee_image`
   (misma librería `geemap`, agrega `geedim` como dependencia nueva en
   `pyproject.toml`) — tilea y reensambla automáticamente cuando la imagen
   excede el límite, y descarga directo cuando no (sin cambio de
   comportamiento para las 5 capas chicas que ya funcionaban). Se mantuvo
   el guard `tif.exists()` como defensa adicional aunque `download_ee_image`
   ya lanza excepción por su cuenta en vez de solo imprimir. Cubierto por
   2 tests offline en `tests/test_native_pipeline.py` (descarga exitosa +
   fallo silencioso). `greenspace_coverage` está de vuelta en
   `santiago_native.yaml`; verificación real (que GEE efectivamente tilee
   ~1,17 GB sin error) pendiente de que el usuario corra
   `exposome run --study santiago_native --resume`.
4. **RESUELTO — Dynamic World y canopy usan 30 m en el agregado por comuna
   por decisión correcta, no por un hueco pendiente.** Se evaluó bajar
   `commune_scale_meters`/`sample_scale_meters` a la resolución nativa
   (10 m Dynamic World, 1 m canopy) y se descartó:
   - `_zonal_means` (`src/exposome/greenspace_multisource.py`) resuelve vía
     `reduceRegions(...).getInfo()` — una llamada **síncrona e interactiva**,
     sin ruta de `Export.table.toDrive` de respaldo. `config/layers/
     greenspace.yaml:40-44` ya documenta que reducir el stack estacional de
     Dynamic World (85 imágenes) a 10 m sobre comunas grandes (San José de
     Maipo, ~5000 km²) agota ese presupuesto interactivo de GEE y hace
     timeout — no es un ahorro gratuito, es un riesgo real de romper una capa
     que hoy corre limpia.
   - La media comunal a 30 m ya es estadísticamente insesgada como estimador
     de cobertura — subir a 10 m no cambia el estadístico, solo el costo.
   - Canopy a 30 m no es un compromiso de costo: es la escala de uso
     confiable documentada del producto (`greenspace.yaml:52-54`,
     `docs/greenspace_multisource_methodology.md:73-77`) — altura de canopy
     a 1 m agregada sobre comunas de cientos de km² no tiene un beneficio
     estadístico que justifique el costo, aun si el presupuesto lo permitiera.
   - El export fino del webapp (`green.geojson`) ya recalcula a 10 m nativo
     por separado vía `scripts/export_webapp_green_subcomuna.py`, así que el
     detalle no se pierde para el usuario final — el agregado por comuna en
     30 m y el producto fino en 10 m son dos productos correctos a distinta
     escala, no una degradación.
   
   Si en el futuro se quiere 10 m también en el agregado, el prerequisito es
   migrar `_zonal_means` a `Export.table.toDrive` (o chunking por comuna) para
   eliminar el riesgo de timeout — no un simple cambio de config.

## Auditoría 2026-08-11: los estudios españoles publicaban sin detalle nativo

Detectado al revisar España en GEMMA: País Vasco pintaba 3 provincias planas.
La regla ya estaba en este documento y aun así se incumplió; lo que faltaba era
algo que la hiciera cumplir.

### Estado medido

| estudio | tier | exigidos | completos | faltan |
|---|---|---:|---:|---:|
| `santiago_communes`, `lima_distritos`, `medellin_comunas`, `valle_aburra_municipios` | production | 13 | 13 | 0 |
| `cdmx_alcaldias`, `bogota_localidades` | preview | 13 | 12 | 1 (`green`) |
| **`pais_vasco_provincias`** | **preview** | **14** | **1** | **13** |
| `cataluna_comarques` | production* | 0 | 0 | 0 |

\* falso positivo, ver más abajo.

Los 47 indicadores de País Vasco resolvían a `boundary_role: analysis_unit`: la
provincia **definía** el valor pintado en vez de sólo recortarlo, que es
exactamente lo que la tabla de `boundary_role` de este documento reserva para
`mask_only`.

### Cadena causal

1. `config/studies/pais_vasco_provincias.yaml` no declaraba bloque `detail:`.
   Santiago, CDMX y Bogotá sí: `detail.native_study: <ciudad>_native`.
2. No existía `config/studies/pais_vasco_native.yaml`. Había nueve estudios
   native en el repo y ninguno español.
3. Sin productos nativos, `exposome detail` (`cli.py:101`) no tiene qué
   convertir — es post-proceso local que nunca contacta un proveedor.
4. Sin `detail/*.tif`, `spatial_coverage` marca cada indicador ráster como
   `missing` → `status: partial` → `publication_tier: preview`.

`spatial_plan.py:113` ya emitía el prerrequisito exacto («declare
detail.native_study with a validated dissolved AOI»), pero nada lo consultaba
en la ruta de publicación.

### El hueco del gate: se aprueba publicando menos

`spatial_coverage.py:93` — `base_required = required_for_production and available`.
Un indicador **sólo se exige si su capa está publicada**.

Por eso `cataluna_comarques` figuraba en `production / complete / 0 required`:
se publicó con `noise_spain` sola, así que el gate no tenía ningún indicador
ráster que exigir. Al republicarse con sus 14 capas cae a `preview / partial`
con los mismos 13 faltantes que País Vasco.

**Un estudio mejora su tier publicando menos capas.** Ése es el defecto de
fondo, y es la razón de que esto pasara desapercibido pese a estar escrito
aquí: el tier no mide cobertura espacial, mide cobertura espacial *de lo que se
decidió publicar*.

La decisión de cerrarlo con un test de configuración en vez de cambiar la
fórmula del tier —y por qué— está en
[ADR 0011](adr/0011-companion-native-study-is-a-config-gate.md). Mientras no se
cambie, **la lectura correcta de cobertura es `missing_indicators`, no
`publication_tier`.**

### Qué arregla el mapa y qué arregla la etiqueta

Conviene no confundirlos:

- El visor resuelve el detalle **por indicador**, desde
  `spatial_indicators[<id>].detail` (`webapp/src/data-repository.js:218,272`).
  Cada COG que exista se pinta a resolución nativa aunque el tier siga en
  `preview`.
- `publication_tier` sólo alimenta un rótulo del selector de ciudad
  («vista previa: faltan detalles espaciales»,
  `webapp/src/states/latam.js:327`).

O sea: los COGs arreglan el mapa; llegar a `production` arregla además la
etiqueta. CDMX y Bogotá llevan un año en `preview` por un solo indicador
(`green`) y sus mapas sí son nativos.

### Contrato operativo

> Todo estudio agregado visible en el selector declara `detail.native_study` y
> publica los COGs de sus indicadores ráster exigidos. Si no los publica, no es
> una entrega: es una vista previa, y debe decirlo.

Checklist de ejecución en
[`knowledge/runbooks/publicar-resolucion-espacial.md`](knowledge/runbooks/publicar-resolucion-espacial.md).
La guarda que faltaba es `tests/test_native_detail_contract.py`, que recorre los
estudios agregados no ocultos y exige la declaración. Los pilotos de una sola
capa vectorial (`barcelona_districts_noise`, `barcelones_noise_pilot`) están
exceptuados con motivo: su detalle es MVT `vector_contours`, no ráster nativo.

### Lo que salió al ejecutarlo (2026-08-11)

**`noise_lden` de País Vasco: resuelto.** 219 teselas, bandas disjuntas,
geometría válida y dentro del AOI; el descriptor pasa la puerta de publicación.
Es el primero de los 13 indicadores que faltaban, y el único que no dependía de
la corrida native.

**Bug encontrado al hacerlo: la validez geométrica no sobrevive a un cambio de
CRS.** `_simplify` la comprueba en EPSG:3035 y esa puerta se cumplía, pero el
pipeline de teselas cruza a EPSG:3857 y vuelve, y ninguno de los dos cruces
revalidaba. Medido para `pais_vasco_provincias`: **13 de 9.052 partes válidas en
3035 volvían inválidas en 3857**, y GEOS moría con `TopologyException: side
location conflict at -334844.01 5356803.54` — un mensaje que nombra una
coordenada pero ni la banda, ni la aglomeración, ni el CRS, y que mandó la
primera hipótesis a los contornos fuente, donde todo estaba limpio.

Arreglado con `_repair_after_reprojection` en las dos costuras
(`noise_spain_tiles.py`), con tests de regresión en
`tests/test_noise_spain_tiles.py`. La reparación está acotada por la puerta de
área que ya existía: la pérdida medida es de **0,006 % en el peor caso**
(banda 70-74). Barcelona nunca lo disparó; el test de round-trip de la suite
**sí lo disparaba** sin que fuera fatal, o sea que estaba latente.

**Nota operativa.** El payload crudo de MITECO (2,7 GB) vive fuera del repo bajo
`$GEMMA_RAW_PAYLOAD_ROOT`, como documenta
`data/raw/miteco/sica-mer-agglomerations/4f-2022/README.md`. La variable no está
exportada en ningún perfil, así que el paso falla con un `FileNotFoundError` que
parece pérdida de datos y no lo es. `resolucion_nativa_pais_vasco.sh` la deriva
del destino del symlink `cache` y avisa si no la encuentra.

### AOI reproducible

Los AOI de `santiago_native` y `cdmx_native` se hicieron a mano. El de
`pais_vasco_native` sale de `scripts/migrations/build_native_aoi.py`, que
disuelve las unidades ya validadas del estudio agregado:

```bash
python3 scripts/migrations/build_native_aoi.py \
  --study pais_vasco_provincias --native-study pais_vasco_native
```

Medido: 7.225,2 km² en 3 partes con 2 huecos interiores — coincide exactamente
con la suma de las 3 provincias y con los 7.234 km² oficiales dentro de la
generalización de GISCO. Los huecos (Condado de Treviño) y las partes sueltas
se conservan a propósito: rellenarlos extendería cada ráster sobre territorio
que el estudio no cubre.

## Follow-ups (fuera de esta fase, decisión del usuario)

- **Grillas finas faltantes restantes**: NDVI/EVI 30 m (`greenspace_coverage`)
  y CHIRPS 5.5 km (`precipitation`) siguen sin export sub-comuna en el
  webapp — solo agregado. Mismo patrón que `pm25`/`alan`/`green`/`no2`
  (`scripts/export_webapp_*_subcomuna.py`) se puede replicar si se necesita
  el detalle intra-comuna para estas dos.
- **O3/AOD en `NATIVE_LAYER_SPECS`**: mismo patrón usado para NO2 (entrada
  propia, su propia escala — 7000 m y 3000 m respectivamente), no bundleadas
  en un solo GeoTIFF. Pendiente de que se necesiten fuera de un contexto de
  ranking relativo (ver limitación de O3 superficie en `air_quality.py`).
- **`cdmx_native`**: espejo de `caba_native`/`santiago_native` para Ciudad de
  México — la arquitectura (`src/exposome/native.py`, `NATIVE_LAYER_SPECS`,
  ahora con 13 capas incluyendo NO2) ya lo soporta sin cambios de código;
  solo requiere un `config/studies/cdmx_native.yaml` y un AOI (dissolve de
  `cdmx_alcaldias`'s `spatial_units.geojson`, mismo método usado para
  `santiago_native`, o geocodificar como se hizo para CABA).
