# ADR 0004: El manifest del bundle gobierna el soporte espacial publicado

Fecha: 2026-07-19

## Contexto

Una resolución de fuente no implica que esa resolución esté disponible en el
mapa. El incidente que motivó esta decisión combinó cuatro problemas:

1. Lima y Medellín sólo habían publicado valores por unidad administrativa,
   pero la interfaz heredaba de `palette.json` la etiqueta global de PM2.5
   «≈1 km».
2. La mera existencia de un GeoTIFF permitía reutilizar detalles históricos de
   ALAN a 500 m y viento a 9 km, aunque la configuración canónica ya exigía
   463,83 m y 11.132 m.
3. `--force` reconstruía outputs, pero algunos cachés no estaban ligados a la
   colección o escala. ALAN podía reutilizar un caché de 500 m y escribir
   metadata nueva de 463,83 m.
4. Analytics elegía la muestra fina por presencia del ráster, no por la
   publicación verificada de ese activo.

También se confundían conceptos físicamente distintos: resolución de descarga,
huella observacional, escala de análisis y soporte efectivamente renderizado.
TROPOMI es el ejemplo principal: la grilla L3 puede estar almacenada a 1.113 m,
pero una observación tiene una huella aproximada de 3,5 × 5,5–7 km.

## Decisión

1. La única autoridad para la resolución que muestra una ciudad es
   `manifest.json.spatial_indicators` del bundle publicado, con
   `schema_version: 3`. `palette.json` conserva catálogo y compatibilidad, pero
   no demuestra que una ciudad tenga detalle fino.
2. Cada indicador declara por separado `downloaded`, `observation`, `analysis`
   y `rendered`. La UI muestra `rendered`; la pestaña de descarga puede informar
   además la fuente sin confundirla con el mapa.
3. `detail: null` significa choropleth administrativo. Un `detail` sólo puede
   ser `cog`, `geojson` o `vector_contours` cuando el activo existe y su
   procedencia fue verificada. `vector_contours` se reserva a polígonos fuente
   categóricos servidos como MVT y nunca declara resolución raster en metros.
4. Todo COG debe declarar `canonical_resolution_verified: true`,
   `source_native_resolution_m` y un sidecar con la misma escala,
   `source_support_preserved: true` y la `source_grid` inspeccionada. La grilla
   real debe coincidir con el CRS y paso canónicos del producto; una etiqueta
   nominal en metros no valida un TIFF que Earth Engine redujo a su fallback de
   1°. Si falla una condición, publicación, auditoría y frontend lo ocultan.
5. El rol del polígono se declara como `mask_only`, `analysis_unit`,
   `source_unit` o `component_specific`. Sólo `mask_only` significa que el
   límite recorta un detalle nativo sin definir sus valores. Los polígonos
   nunca crean píxeles ni aumentan la resolución de la fuente. Está prohibido
   sobremuestrear para aparentar detalle.
6. Las capas vectoriales no reciben una falsa resolución raster. Se distinguen
   fuente vectorial, grilla analítica —si realmente existe— y mapa publicado.
7. La publicación del agregado se bloquea cuando la metadata contradice la
   colección o escala configurada (actualmente ALAN, calor y viento).
8. Todo caché cuyo contenido dependa de proveedor, producto, banda, escala o
   periodo debe incluir esos parámetros en su namespace. `--force` por sí solo
   no es prueba de que el caché haya sido invalidado.
9. Analytics usa grilla fina sólo si al menos dos ciudades publican el mismo
   tipo de detalle verificado. En caso contrario compara la columna principal
   administrativa común.
10. Un `resolution_warning` del preflight es informativo: puede indicar que la
    fuente es legítimamente más gruesa que la unidad administrativa. No autoriza
    remuestreo ni constituye por sí mismo un fallo del pipeline.
11. Cada indicador puede añadir una disponibilidad por estudio. `available`
    significa que la capa forma parte de la release; `country_not_supported`,
    `not_enabled_by_study`, `not_published_by_study` y `coming_soon` explican
    por qué no existe. Un indicador no disponible declara `rendered.kind:
    unavailable`, nunca un polígono administrativo ficticio.

## Alternativas consideradas

- **Usar `has_fine_layer` global:** descartado porque una capa puede estar
  publicada en Santiago y ausente en Lima.
- **Detectar cualquier ráster existente:** descartado porque no demuestra
  colección, escala, unidad, vigencia ni inclusión en el bundle.
- **Forzar todas las fuentes a una grilla de 1 km:** descartado porque inventa
  detalle para ERA5-Land, CHIRPS y otras fuentes gruesas.
- **Mostrar siempre la resolución nativa de la fuente:** descartado porque
  confunde disponibilidad científica con el producto realmente descargable.

## Consecuencias

- Una ciudad puede mostrar honestamente «Mapa: distrito; fuente: ACAG 0,01°»
  hasta que publique el COG nativo.
- Agregar una ciudad requiere un manifest propio; copiar flags de otra ciudad
  deja de ser suficiente.
- Cambiar proveedor o escala obliga a regenerar caché, metadata, release,
  detalle, bundle y Analytics.
- Los activos históricos pueden permanecer en disco sin reaparecer en la app:
  sólo vuelven a anunciarse después de pasar las puertas canónicas.
- El catálogo puede conservar una capa globalmente visible y, a la vez,
  explicar que sólo está soportada en determinados países; la ausencia no se
  confunde con una deuda de resolución.
- La operación obligatoria se documenta en
  [`../knowledge/runbooks/publicar-resolucion-espacial.md`](../knowledge/runbooks/publicar-resolucion-espacial.md),
  y el inventario capa-ciudad vive en
  [`../resolution_manifest.md`](../resolution_manifest.md).

## Capas y estudios afectados

Todas las capas publicadas y todos los estudios web. Las puertas específicas
actuales cubren PM2.5, NO₂, ALAN, viento, componentes físicos de calor y lluvia,
dosel y verde para detalle. Todo COG se contrasta contra su grilla canónica
inspeccionada, no sólo contra una resolución nominal.
