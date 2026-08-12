# Metodologia de areas verdes - acceso (OpenStreetMap)

## Proposito

Esta capa entrega indicadores de accesibilidad a areas verdes por comuna en Santiago,
basados en poligonos de parques, jardines y zonas de recreacion extraidos de
OpenStreetMap (OSM). Se usa como medida de exposicion ambiental en el master exposome.

## Fuente

- Proveedor: OpenStreetMap (datos de contribuidores bajo licencia ODbL).
- Metodo de descarga: `osmnx.features_from_place` con los tags definidos en
  `config/cities/santiago.yaml` (secciones `greenspace.access.osm_tags`).
- Cache local: `cache/santiago_greenspace_osm.geojson` (6 835 poligonos, presentes al
  momento de la revision). Las corridas posteriores cargan este cache sin llamar a la API
  de Nominatim/Overpass si el archivo existe y no esta vacio.
- Unidad geografica de salida: comuna, 52 comunas esperadas.

## Metodo

`scripts/run_greenspace_access.py` llama a `src/exposome/greenspace_access.py` desde la
raiz del repositorio.

### Obtencion de poligonos OSM

Se descargan poligonos con los tags de vegetacion/recreacion de la config (leisure y
landuse). Se filtran geometrias no poligonales y se reparan invalidas con `buffer(0)`. Los
poligonos se guardan en cache para reproducibilidad.

### Cobertura OSM (`green_osm_km2`, `green_osm_pct`)

Se proyecta la union de todos los poligonos verdes al CRS metrico de la ciudad
(`EPSG:32719`) y se calcula la interseccion con cada poligono comunal. Eso evita doble
conteo donde los poligonos OSM se solapan. El area se divide por el area comunal para
obtener el porcentaje.

### Conteo de poligonos (`green_osm_n`)

Se usa el punto representativo de cada poligono verde (no su centroide) para asignarlo a
una sola comuna mediante un `sjoin`. Esto garantiza que cada poligono cuenta una sola vez
aunque cruce limites comunales.

### Distancia al parque mas cercano (`dist_to_nearest_park_m`)

Se calcula la distancia en linea recta desde el centroide del poligono comunal al punto
representativo del poligono verde mas cercano usando `gpd.sjoin_nearest`. Las comunas sin
areas verdes OSM reciben el valor centinela `99999` m (documentado en metadata).

### Metricas de buffer (`green_area_within_{300,500,1000}m_km2`, `green_count_within_{300,500,1000}m`)

Se genera un buffer de la geometria comunal completa (no un buffer del centroide). Los
poligonos cuyo punto representativo cae dentro del buffer se contabilizan y su area se
suma. El metodo `whole_polygon_by_repr_point` es mas rapido que el recorte exacto pero
puede sobre- o sub-estimar en los margenes.

## Columnas

- `name`: nombre normalizado de comuna.
- `area_km2`: area comunal en km².
- `green_osm_km2`: km² de areas verdes OSM dentro de la comuna (interseccion exacta, sin solapamiento).
- `green_osm_pct`: 100 * green_osm_km2 / area_km2.
- `green_osm_n`: numero de poligonos OSM cuyo punto representativo cae en la comuna.
- `dist_to_nearest_park_m`: distancia en metros desde el centroide comunal al parque mas cercano (99999 si no hay ninguno).
- `green_area_within_300m_km2`, `green_area_within_500m_km2`, `green_area_within_1000m_km2`: km² dentro del buffer.
- `green_count_within_300m`, `green_count_within_500m`, `green_count_within_1000m`: conteo de poligonos dentro del buffer.

## Outputs

- `data/processed/santiago_greenspace_access.csv`
- `data/processed/santiago_greenspace_access.geojson`
- `data/processed/santiago_greenspace_access_metadata.json`
- `figures/greenspace_access_santiago_2panel.png`

## Integracion al master

`scripts/build_master_exposome.py` incluye `greenspace_access` como capa requerida.
Las columnas `green_osm_km2`, `green_osm_pct`, `green_osm_n`, `dist_to_nearest_park_m`
y las metricas de buffer entran directamente sin renombrar.

## Limitaciones

- El mapeo OSM es heterogeneo entre comunas: comunas con menos contribuidores pueden
  tener sub-mapeo de areas verdes. La capa `greenspace_cv` valida este sesgo comparando
  OSM con deteccion por vision computacional en imagenes de calle.
- La distancia es linea recta desde el centroide comunal, no ponderada por poblacion ni
  basada en red vial.
- Los buffers usan el poligono comunal completo y contabilizan poligonos por punto
  representativo; no es un recorte exacto al buffer.
- Las tags OSM no cubren vegetacion privada ni patios interiores.
