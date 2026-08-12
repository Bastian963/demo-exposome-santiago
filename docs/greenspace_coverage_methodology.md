# Metodologia de areas verdes - cobertura satelital (Landsat-8/9)

## Proposito

Esta capa entrega indicadores de cobertura verde a nivel comunal en Santiago usando
imagenes satelitales Landsat-8/9 procesadas en Google Earth Engine (GEE). Complementa la
capa `greenspace_access` (OSM) capturando vegetacion que no aparece mapeada en
OpenStreetMap, como parques privados, arboles en veredas y areas verdes informales.

## Fuente

- Proveedor: Google Earth Engine (GEE), colecciones USGS Landsat.
- Colecciones:
  - `LANDSAT/LC08/C02/T1_L2` (Landsat 8, OLI/TIRS, Collection 2 Level 2)
  - `LANDSAT/LC09/C02/T1_L2` (Landsat 9, OLI-2/TIRS-2, Collection 2 Level 2)
- Proyecto GEE: `exposome-api`.
- Resolucion espacial: 30 m (resolucion nativa de las bandas opticas de Landsat).
- Unidad geografica de salida: comuna, 52 comunas esperadas.

## Configuracion

La config en `config/cities/santiago.yaml` (seccion `greenspace.satellite`) define:

- `years: [2024]`
- `season_months: [10, 11, 12, 1, 2, 3]` — primavera-verano austral, maxima vegetacion y
  minima nubosidad.
- `ndvi_threshold: 0.20`
- `evi_threshold: 0.15`
- `scale_meters: 30`

## Metodo

`scripts/run_greenspace_coverage.py` llama a `src/exposome/greenspace_satellite.py`.
Requiere autenticacion GEE activa (`earthengine authenticate`).

### Preprocesamiento de imagenes

1. Se cargan las imagenes LC08 y LC09 del periodo indicado, filtradas por el bounding box
   de las 52 comunas.
2. Se aplica la escala y offset de reflectancia superficial de Landsat C02:
   `SR = DN * 2.75e-5 - 0.2` sobre las bandas opticas (`SR_B2`, `SR_B4`, `SR_B5`).
3. Se enmascaran nubes y sombras de nube usando el bit 3 (cloud), bit 4 (cloud shadow) y
   bit 5 (snow) de la banda `QA_PIXEL`, mas el bit 0 (fill).
4. Se aplica un filtro de mes para conservar solo imagenes del periodo estacional.

### Calculo de indices

- **NDVI**: `(SR_B5 - SR_B4) / (SR_B5 + SR_B4)`, rango teorico [-1, 1].
- **EVI**: `2.5 * ((NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1))`, rango teorico [-1, 1].
  Los pixeles EVI fuera del rango [-1, 1] se enmascaran antes de reducir (fix de
  inestabilidad del denominador cuando este es cercano a cero).

### Composite

Se calcula la mediana pixel a pixel sobre la coleccion enmascarada (imagenes de ambos
sensores mezclados). La mediana es robusta ante nubes residuales y outliers.

### Estadisticas zonales

Se usa `ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)` en una sola
llamada `reduceRegions` con `scale=30`, `crs=EPSG:4326`, `tileScale=4`. Esto devuelve
para cada banda (NDVI, EVI, green_ndvi, green_evi) el valor medio y maximo por comuna.

- `green_cover_pct_ndvi`: fraccion de pixeles con `NDVI >= 0.20`, convertida a porcentaje.
- `green_cover_pct_evi`: fraccion de pixeles no enmascarados con `EVI >= 0.15`, convertida
  a porcentaje. El denominador excluye los pixeles EVI enmascarados.

## Columnas

- `name`: nombre normalizado de comuna.
- `area_km2`: area comunal en km².
- `ndvi_mean`: NDVI medio sobre el composite, rango [-1, 1].
- `ndvi_max`: NDVI maximo sobre el composite, rango [-1, 1].
- `evi_mean`: EVI medio sobre pixeles validos del composite, rango [-1, 1].
- `evi_max`: EVI maximo sobre pixeles validos del composite, rango [-1, 1].
- `green_cover_pct_ndvi`: porcentaje de pixeles con NDVI >= 0.20, rango [0, 100].
- `green_cover_pct_evi`: porcentaje de pixeles no enmascarados con EVI >= 0.15, rango [0, 100].

## Outputs

- `data/processed/santiago_greenspace_coverage.csv`
- `data/processed/santiago_greenspace_coverage.geojson`
- `data/processed/santiago_greenspace_coverage_metadata.json`
- `figures/greenspace_coverage_santiago_2panel.png`

## Integracion al master

`scripts/build_master_exposome.py` incluye `greenspace_coverage` como capa requerida.
Las columnas `ndvi_mean`, `ndvi_max`, `evi_mean`, `evi_max`, `green_cover_pct_ndvi` y
`green_cover_pct_evi` entran al master sin renombrar.

## Limitaciones

- Resolucion de 30 m es mas gruesa que Sentinel-2 (10 m); parques urbanos pequenos pueden
  perderse. Se eligio Landsat para evitar timeouts de GEE al procesar Sentinel-2 a escala
  regional.
- `green_cover_pct_evi` usa como denominador solo los pixeles EVI no enmascarados; en
  comunas con muchos pixeles anomalos el porcentaje puede no ser comparable.
- El composite cubre solo los meses estacionales del ano configurado (2024); no captura
  variabilidad interanual.
- No hay validacion contra un producto NDVI independiente (p. ej. MOD13A3).
- La capa `greenspace_cv` valida cuanto del verde detectado por vision computacional
  queda fuera del mapeo OSM, lo que complementa la cobertura satelital.
