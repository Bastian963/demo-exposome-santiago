# Extractos OSM locales para capas de tags

## Qué resuelve

Las cinco capas OSM del set portable consultan Overpass. Para áreas
metropolitanas eso funciona: Bogotá (1.634 km²) resolvió `greenspace_access`
en 80 tiles. Para estudios de escala regional no escala.

Medido el 2026-08-10 sobre `cataluna_comarques` (43 comarques, 32.105 km²):

| | Overpass | Extracto local |
|---|---|---|
| Consultas | 1.786 tiles | 1 lectura |
| Tiempo de `greenspace_access` | **69 h** (a 2,31 min/tile medidos) | **99 s** |

El troceado no es una decisión de diseño reversible por configuración: existe
porque Overpass rechaza consultas grandes de polígonos. `GREEN_TAG_MAX_TILE_SPAN_DEG`
está en 0,08° y su comentario documenta por qué no se puede subir — las
unidades rurales con cobertura natural densa expiran antes que las urbanas del
mismo tamaño angular. Leyendo un archivo en disco ese límite desaparece.

Hay un segundo motivo, independiente de la velocidad: **reproducibilidad**. Una
consulta a Overpass depende del estado de OSM y del servidor en ese instante y
no se puede repetir. Un extracto fechado y checksumeado sí.

## Cómo funciona

Geofabrik publica cortes diarios de la base de OSM por región. Se baja **a
mano desde la página** (ver `data/raw/geofabrik/README.md`), se congela con
`scripts/migrations/ingest_geofabrik_extract.py` y el estudio lo declara en
`layer_overrides.<layer>.osm_extract` (para `greenspace_access`, en
`layer_overrides.greenspace.access.osm_extract`).

**Va en `layer_overrides`, no en `layer_inputs`**, aunque `noise_spain` use lo
segundo: estas cuatro capas corren por el camino heredado de runner que recibe
`--city`, así que sólo ven el `cfg` resuelto y nunca los `layer_inputs` del
estudio. De yapa entra en `layer_execution_identity` vía `layer_settings`, de
modo que declararlo —o cambiar el corte— invalida el `--resume` de esas capas
por sí solo, sin tocar las demás.

La lectura la hace `fetch_features_from_local_extract` en
`src/exposome/osm_fetch.py`, que devuelve **el mismo contrato de GeoDataFrame**
que la ruta Overpass (`element`, `id`, `name`, una columna por clave de tag,
`geometry`), de modo que las capas no distinguen el origen.

El driver OSM de GDAL —disponible vía `pyogrio`, sin dependencias nuevas—
expone cinco capas y promueve un conjunto fijo de claves a columnas reales:

- `multipolygons` promueve `leisure`, `landuse`, `natural`, `amenity`, `shop`,
  `tourism` y otras. El filtrado usa `where "clave IN (…)"`, que es barato.
- `points` promueve muchas menos; `shop`, `amenity` y `healthcare` viven en el
  campo `other_tags`, en formato hstore `"k"=>"v"`. Ahí el filtrado usa
  `other_tags LIKE` y luego se parsea a columnas.

**El filtro se empuja a GDAL en una sola pasada.** Leer por bbox de cada unidad
cuesta 119 s *por unidad* porque el driver OSM no tiene índice espacial y
reescanea el archivo entero; una pasada con `where` sobre toda la región cuesta
99 s en total. La asignación por unidad se hace después, en memoria.

## Validación contra Overpass

Se comparó contra los 196 tiles de Álava que Overpass alcanzó a cachear antes
de que su corrida muriera, **recortando ambos lados al límite real de País
Vasco**:

| | Overpass | Extracto |
|---|---|---|
| Features dentro de País Vasco | 606 | 7.961 |
| De esos 606, presentes en el extracto | — | **603 (99,5 %)** |

### El recorte regional explica casi toda la diferencia cruda

Sin recortar, 619 features de Overpass no aparecían en el extracto. **616
estaban fuera de la comunidad** — en Burgos, La Rioja y Navarra. Overpass
tileaba el *bbox* de Álava, que se sale de sus límites; el extracto de
Geofabrik viene recortado a la región.

No es una pérdida: `greenspace_access` descarta esos features igual al cruzarlos
contra los polígonos de unidad. Pero **es la trampa a vigilar** al comparar los
dos caminos: hay que recortar al límite real antes de sacar conclusiones.

Los 3 restantes eran nodos, ausentes por leer sólo `multipolygons`.

### Los "extra" del extracto son reales, pero el 13× no es lo que parece

Tres de los features que sólo tenía el extracto se verificaron contra la API de
OSM: los tres existen con `leisure=park`, uno es «Florida parkea» en
Vitoria-Gasteiz.

Ahora bien, **ese 13× no demuestra que Overpass sea sistemáticamente
incompleto**. La corrida de País Vasco murió sin terminar: 150 de los 196 tiles
de Álava volvieron vacíos y Gipuzkoa quedó a medias. 606 no es la respuesta
final de Overpass, es una parcial. No se puede extrapolar a Bogotá, Santiago o
CDMX, cuyas corridas sí cerraron, sin repetir la comparación en cada una.

Lo que sí queda establecido es lo que hacía falta: **el camino local no pierde
nada de lo que Overpass encuentra dentro de la región**.

## Alcance

| Capa | Ruta | Lecturas del `.pbf` | Motivo |
|---|---|---|---|
| `greenspace_access` | extracto | 1 | polígonos por tag |
| `food_environment` | extracto | 1 por categoría (5) | POIs por tag; sólo usa geometría |
| `healthcare` | extracto | 1 | POIs por tag |
| `social_infrastructure` | extracto | 1 | POIs por tag |
| `walkability` | **Overpass** | — | construye un grafo de calles con `ox.graph_from_polygon`; osmnx no lee `.pbf` directo |

Las capas sin `osm_extract` declarado siguen usando Overpass sin cambios, así
que ciudades como Bogotá o Santiago no se ven afectadas.

### Una sola pasada, no una por clave de tag

`healthcare` y `social_infrastructure` consultan Overpass **troceado por clave
de tag** (o por grupo de tags) para que cada consulta sea chica. Contra el
extracto ese troceo no sólo es innecesario: **cuesta exactitud**.

Overpass devuelve *todos* los tags de un feature, sin importar cuál lo
encontró. El extracto materializa **sólo las claves pedidas**. Entonces:

- `healthcare` leyendo por clave dejaría un centro con `amenity=hospital` +
  `healthcare=clinic` con una de las dos columnas vacía, y la deduplicación por
  `(element, id)` se queda con la copia que llegó primero — moviéndolo de
  categoría en silencio. Verificado en País Vasco: en una sola pasada,
  `amenity` queda poblado en 1.730 de 1.741 features y `healthcare` en 1.424.
- `social_infrastructure` leyendo por grupo daría a cada copia sólo las
  columnas de su grupo, y `_classify_features` asignaría una categoría en vez
  de dos a un local que es a la vez `amenity=community_centre` y
  `leisure=sports_centre`.

`food_environment` sí lee por categoría: sólo usa geometría
(`_geometry_only_cache_frame`), no hay semántica cruzada que preservar.

### `extra_keys`: columnas que no se filtran

`social_infrastructure` **filtra por un tag que nunca consulta**: excluye del
indicador curado los locales con `access` en private/customers/no/permit
(`social_infrastructure.py`, `curated_access_allowed`). Con Overpass la columna
venía gratis; con el extracto no existiría, y el filtro admitiría todo.

No es hipotético. En el extracto de País Vasco, de 12.659 features de
infraestructura social, **1.637 (13 %) tienen un `access` excluible**. Sin la
columna, esos 1.637 entraban al conteo curado e inflaban `social_n_total` y
cada `social_n_<categoría>` **contra todas las demás ciudades del repo** — una
ruptura de comparabilidad, que en un proyecto comparativo es peor que una
corrida lenta.

Por eso `fetch_features_from_local_extract` acepta `extra_keys`: claves que se
materializan como columna **sin sumar cláusula al `where`**. La columna existe
aunque venga vacía, para que un `.get("access")` devuelva una Series real y no
el fallback silencioso.

Regla general al cablear una capa nueva: **diferenciar el conjunto de claves
que se le pasan al fetch contra el conjunto de columnas de tag que lee el
código aguas abajo.** Toda clave que sólo esté en el segundo conjunto va en
`extra_keys`.

## Limitaciones

- **Fecha del corte.** El extracto es una foto, no una serie. Da igual para
  estas capas: ninguna genera serie anual — son snapshots por diseño, y el
  catálogo no las marca `annual_downloadable`.
- **Borde de región.** Elementos que cruzan el límite pueden quedar partidos.
  Irrelevante para unidades interiores.
- **Geometrías.** GDAL emite avisos de anillos no cerrados en algunos
  multipolígonos de OSM. Los ensambla igual; el efecto sobre áreas agregadas no
  se ha cuantificado y conviene medirlo si alguna unidad da un valor extremo.
