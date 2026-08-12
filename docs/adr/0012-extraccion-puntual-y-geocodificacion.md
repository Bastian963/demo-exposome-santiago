# ADR 0012: la extracción puntual entrega promedios de bloque, no valores en el punto

- Estado: aceptado
- Fecha: 2026-08-12
- Alcance: la pestaña de descarga de GEMMA, `exposome extract-points` y todo
  consumo de exposomas por coordenada
- Enmienda: [ADR 0004](0004-published-spatial-support-contract.md)

## Contexto

[ADR 0004](0004-published-spatial-support-contract.md) §2 ya anticipó esta
superficie: «la UI muestra `rendered`; **la pestaña de descarga** puede informar
además la fuente sin confundirla con el mapa».
`docs/resolution_manifest.md:63` la vuelve a mencionar. Nunca se construyó.

Ahora se pide: pegar una lista de direcciones o coordenadas y descargar sus
valores de exposoma. El pedido es razonable y los datos existen —7 ciudades
publican 11 COGs de detalle más 94 cortes anuales cada una, ~80 pares ciudad ×
exposoma— pero la formulación natural de la respuesta viola el contrato.

«El valor de PM2.5 en Manuel Rodríguez 1085» sugiere una medición en esa esquina.
No existe tal cosa. El píxel ACAG que contiene esa esquina es un promedio sobre
0,01° ≈ 1,1 km; la observación TROPOMI que sostiene el NO₂ cubre 3,5 × 5,5–7 km.
Entregar un número por dirección sin decir sobre qué región es el promedio es
exactamente el «sobremuestrear para aparentar detalle» que ADR 0004 §5 prohíbe,
sólo que en formato tabla en vez de mapa.

### Tres formas concretas de equivocarse, medidas

**1. Anclar la compuerta de radio en la resolución equivocada.**
`INDICATOR_SUPPORT["no2"]` declara `downloaded` = 1113,2 m pero `observation` =
3500 × 5500–7000 m. Un buffer de 500 m sobre NO₂ está un orden de magnitud dentro
de la huella de medición: no promedia nada, devuelve el mismo valor que `r=0` con
apariencia de haber promediado.

**2. Leer `storage_grid` como si fueran metros de terreno.** Los COGs se guardan
en EPSG:3857, cuyos metros no son metros de terreno: a latitud φ, 1 m-Mercator =
`cos φ` m de terreno. Medido en `santiago_communes/annual/detail/pm25_2020.tif`:

```
storage_grid.resolution        1192,4 m-Mercator
  × cos(−33,45°)             =   994,9 m de terreno
source_native_resolution_m     1113,0 m
                            → sobredeclaración del 10,6 %
```

O sea: usar el número que está más a mano afirma **más** resolución de la que la
fuente sostiene.

**3. Preguntarle a `palette.json` qué hay disponible.** Medido sobre
`webapp/public/palette.json` (47 exposomas) contra el bundle:

```
has_fine_layer = true   →  4   (pm25, no2, alan, green)
COGs detail/*.tif       → 11
has_annual = true       →  1   (pm25)
capas con serie anual   → 10
```

Está mal en las dos direcciones a la vez: esconde 7 capas finas que existen y
anuncia una (`green`) que **no tiene `green.tif`** —su detalle es
`subcomuna/green.geojson`— así que iterar por esa bandera produce un 404. Es el
mismo error que ADR 0004 §1 registró para Lima y Medellín, sobrevivido en otro
archivo.

### El problema de fondo: no hay un estimando declarado

Los tres errores comparten causa. Nadie escribió **qué cantidad** devuelve una
consulta por coordenada. Sin estimando declarado, cada consumidor improvisa uno,
y las improvisaciones son sistemáticamente optimistas: toman la resolución más
fina disponible, el buffer más chico que el usuario pidió, y la bandera más
accesible.

## Decisión

### 1. El estimando es un promedio de bloque sobre una vecindad explícita

Una consulta por coordenada devuelve, por definición:

> el promedio del indicador sobre **B(x, r)**: la celda que lo contiene cuando
> `r = 0`, o el disco de radio `r`.

No se interpola. Sin bilineal, sin kriging, sin *area-to-point*, sin downscaling.
`docs/plan_b_downscaling.md` sigue siendo la ruta —no implementada— hacia un PM2.5
genuinamente más fino; **la extracción puntual no es una puerta trasera hacia
ella**.

El estimador para un ráster con celdas `cᵢ` de valor `vᵢ` es la media ponderada
por área, `wᵢ = área(cᵢ ∩ B(x, r))`, y no «celdas cuyo centroide cae dentro», que
se sesga cuando `r` es comparable al tamaño de celda.

### 2. La compuerta de radio se calcula contra `observation`

```
2r ≥ observation_res  →  radius_status = "resolved"
2r <  observation_res  →  radius_status = "sub_observation"
```

Se entrega igual, marcado. Para huellas anisotrópicas se usa la dimensión mayor:
NO₂ → 7000 m, así que **todo radio ≤ 3500 m queda `sub_observation`**. Las
resoluciones declaradas en grados se convierten a la latitud del punto.

`support_m = max(2r, observation_res)` — **nunca menor que la huella de
observación**, y siempre derivado de `source_native_resolution_m` o de
`INDICATOR_SUPPORT`, jamás de `storage_grid`, que sólo sirve para indexar píxeles.

### 3. Los indicadores administrativos no se promedian entre unidades

Para los registros `_admin`, `_vector` y `_composite` —cuya nota dice
literalmente «no se infiere variación intraunidad»— un buffer que cruce un límite
comunal produciría un número que no existe en ninguna unidad. Se devuelve **el
valor de la unidad contenedora**, con `radius_m = null`. La fragilidad de borde se
expone como diagnóstico separado (`units_touched`, `distance_to_boundary_m`),
nunca como valor mezclado.

Consecuencia de alcance: como `_vector` sólo publica el resumen administrativo,
«POIs dentro de 500 m» **no está disponible** para estudios agregados. Sí lo está
contra los `.gpkg` nativos, por CLI.

### 4. `sd_within_buffer` se suprime cuando el radio no resuelve

La SD ponderada dentro del buffer es la mejor medida honesta de cuánto depende el
valor de la ubicación exacta —es decir, de cuánto importa el error de
geocodificación. Pero bajo `sub_observation` **todas** las celdas contribuyentes
caen dentro de una sola huella de observación, así que la SD tiende a 0 y se
leería como *alta confianza* justo donde el dato es menos informativo. NO₂ está en
ese régimen en todos los radios ofrecidos.

Por eso se emite `null` salvo cuando `radius_status = resolved`. La heterogeneidad
local se comunica por `radius_status` y `support_m`.

### 5. La disponibilidad sale del manifest

`manifest.temporal_indicators` y `spatial_indicators` son la autoridad, con
*fallback* a los assets declarados para los 3 estudios publicados sin
`spatial_completion` (`buenos_aires_amba`, `buenos_aires_comunas`, `caba_native`)
— indexar sólo por esa llave descarta en silencio los 4 COGs reales de AMBA.
`palette.json` se usa **sólo** para etiquetas, unidades, colores, umbrales y la
taxonomía `category`.

### 6. Una sola fuente canónica para los dos caminos

Python leyendo `data/processed` (EPSG:4326 y varios UTM/Sinusoidal) y la webapp
leyendo `detail/*.tif` (reproyectado por `build_cog` con `WarpedVRT` nearest a
EPSG:3857) son **teselados distintos**: con `r=0` casi siempre coinciden pero
pueden diferir una celda cerca de bordes, y con buffers los pesos de área difieren
por construcción. La misma dirección devolvería dos números según por dónde se
pidió.

**Para un estudio publicado, el COG publicado es la fuente canónica de ambos.**
La lectura nativa queda como modo aparte y etiquetado del CLI (`--source native`),
para estudios sin publicar, y su diferencia se documenta cuantificada en vez de
ocurrir en silencio.

### 7. Enmienda: la webapp sí geocodifica direcciones, bajo condiciones

`scripts/export_webapp_zipcodes.py:3-5` declara «The webapp never geocodes ZIP
codes online. It only resolves codes from local, reproducible reference files».
El pedido de geocodificar direcciones en línea la contradice, así que se enmienda
explícitamente y no por omisión.

La política que la reemplaza:

1. La geocodificación vive en un **adaptador separado**, nunca dentro del
   muestreador. `scripts/query_exposome.py:1-5` («ZIP/address geocoding is kept
   outside the exposure sampler because a postal area is not a unique point»)
   **se mantiene intacta**.
2. Requiere **consentimiento explícito** nombrando el proveedor antes del primer
   request. Las direcciones son PII.
3. `lat/lon` es un modo de primera clase y no transmite nada. El CLI sobre
   `data/processed` tampoco.
4. Throttle de 1 req/s, tope de lote en la UI, caché por hash de consulta.
   Proveedor por defecto Nominatim/OSM, con interfaz agnóstica.
5. Los **códigos postales** siguen resolviéndose sólo desde archivos de
   referencia locales y reproducibles — esa mitad de la política no se toca. Como
   hoy no existe ninguno para los 7 países del repo, el resolutor devuelve
   `unsupported_country` en vez de inventar un centroide.

Cada valor entregado lleva su `geocode_precision` y `geocode_accuracy_m` junto a
`support_m`, y se deriva `geocode_material = geocode_accuracy_m > 0,5 · support_m`
— porque con superficies de ≥463 m un error de 50–100 m es inmaterial para casi
todo, y material para `canopy` y para la proximidad a bordes.

## Alternativas consideradas

- **Devolver el valor del píxel y ya.** Es lo que hace hoy
  `scripts/query_exposome.py` y es defendible para `r=0`. Descartado como única
  opción porque no responde la pregunta epidemiológica —la exposición no se vive
  en un punto— y porque no da ninguna señal de cuánto depende el número de la
  precisión del geocodificador.
- **Interpolar bilinealmente para suavizar.** Descartado por ADR 0004 §5: un
  suavizado no es información, y produce valores que no están en ninguna celda.
- **Ofrecer la escalera HELIX completa (100/300/500/1000/1500 m).** Descartado:
  la mayoría de esos radios queda bajo el soporte de casi todas las capas y genera
  columnas sin significado. Se ofrece `0/300/500/1000` y se marca lo que no
  resuelve.
- **Un kernel de decaimiento gaussiano en vez del buffer duro.** Mejor justificado
  para exposiciones que decaen con la distancia (ruido, tráfico), pero el buffer
  duro es el estándar de la literatura y es comparable entre estudios. Queda
  anotado en la metodología como extensión, no en v1.
- **Prohibir la geocodificación y aceptar sólo coordenadas.** Respeta la política
  vigente sin enmendarla, pero traslada el problema al usuario, que lo resolverá
  con un geocodificador peor y sin registrar la precisión. Descartado: es más
  honesto geocodificar con consentimiento y **medir** el error que empujarlo fuera
  de vista.

## Consecuencias

- Una descarga puede decir honestamente «PM2.5 = 18,4 µg/m³, promedio sobre 1113
  m, radio 300 m no resoluble» en vez de un número desnudo.
- El formato «código postal» que se pidió **no funciona para ninguna ciudad** hasta
  que se vendorice una referencia postal. No existe ninguna en el repo, y Chile
  —donde vive la dirección del ejemplo— no tiene conjunto nacional usable. El
  candidato más fuerte es México/SEPOMEX, porque allá el código postal sí es
  geografía real y `cdmx_alcaldias` ya está publicada.
- `scripts/query_exposome.py` deja de ser el muestreador y pasa a ser un
  envoltorio de `src/exposome/point_query.py`. En la mudanza se arreglan cinco
  defectos suyos, de los cuales el que devuelve nulos silenciosos —asumir EPSG:4326
  y dejar que `boundless=True, masked=True` convierta un índice fuera de grilla en
  `None`— afecta a `greenspace_multisource` en 8 ciudades, `greenspace_coverage` en
  5 y `wildfire` en todas.
- Agregar un indicador nuevo obliga a declarar su `estimand_kind`; un test recorre
  `INDICATOR_SUPPORT` y falla si alguno no mapea a exactamente una clase.
- El conflicto de `canopy` queda expuesto y hay que resolverlo:
  `DETAIL_NATIVE_RESOLUTION_M` dice 1,0 m, `DETAIL_SOURCE_GRID` dice 3857 @ 30 m y
  `layers.yaml` dice 10 m. Una grilla de 30 m no sostiene una afirmación de 1 m.
- El seguimiento operativo vive en
  [`../planning/point_download_tab.md`](../planning/point_download_tab.md) y la
  justificación estadística completa en
  [`../point_extraction_methodology.md`](../point_extraction_methodology.md).
