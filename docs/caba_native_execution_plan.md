# Ejecución nativa de exposomas para CABA

Este documento define el flujo operativo para Buenos Aires. La arquitectura
mantiene dos modos explícitos:

- `aggregate`: requiere polígonos de unidades (comunas, barrios o ZIPs) y
  produce una fila por unidad. Es el modo actual de Santiago.
- `native`: requiere únicamente un AOI de la ciudad, conserva la resolución de
  cada proveedor y consulta después por coordenadas.

## Estado inicial

El estudio `caba_native` está en `config/studies/caba_native.yaml`. Su AOI
actual es `data/raw/ar/buenos_aires/caba_native/aoi/caba_boundary.geojson`,
una geometría administrativa de CABA obtenida de OpenStreetMap. El archivo
`caba_bbox.geojson` se conserva como fallback y referencia del bbox original.
Antes de publicar resultados se debe revisar la atribución ODbL.

No se deben crear polígonos de códigos postales para iniciar las descargas.
Un ZIP o una dirección se convierten primero en coordenadas mediante una fuente
de geocodificación documentada. El valor consultado corresponde al píxel,
nodo, POI o red fuente más cercano; no se interpola una fuente gruesa.

## Comandos

Ejecutar desde la raíz y usando el entorno `exposome`:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python \
  scripts/run_exposome.py --study caba_native --dry-run --no-build-master
```

La salida debe mostrar las capas habilitadas como `ready`. La opción `dry-run`
no contacta proveedores.

Para ejecutar una capa o un subconjunto:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python \
  scripts/run_exposome.py --study caba_native \
  --layers greenspace_coverage,climate_heat --no-build-master
```

El orquestador traduce cada capa nativa a `scripts/run_native_layer.py`; los
wrappers históricos (`run_pm25.py`, `run_wind.py`, etc.) siguen reservados para
el modo agregado y no deben ejecutarse directamente para CABA.

La ejecución nativa no genera `master.csv`: guarda productos en
`data/processed/ar/buenos_aires/caba_native/<layer>/` y metadata en cada
directorio. `--resume` reutiliza productos nativos completos.

## Productos y resolución

| Capa | Producto nativo | Resolución aproximada |
|---|---|---:|
| `air_quality_pm25` | GeoTIFF ACAG | 1.1 km |
| `alan` | GeoTIFF VIIRS | 500 m |
| `greenspace_coverage` | GeoTIFF NDVI/EVI Landsat | 30 m |
| `precipitation` | GeoTIFF CHIRPS | 5.6 km |
| `climate_heat` | puntos diarios Open-Meteo | 0.10 grados |
| `wind` | GeoTIFF ERA5-Land | 11.132 km |
| `wildfire` | GeoTIFF MODIS/FIRMS | 500 m/1 km |
| capas OSM | GeoPackage de polígonos, POIs o red | fuente OSM |

PM2.5 debe declarar en metadata el máximo temporal disponible de ACAG. Las
capas de salud, alimentos, infraestructura y verde OSM son inventarios de
OpenStreetMap y no deben presentarse como registros oficiales argentinos.

## Consulta por punto

Para un punto:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python \
  scripts/query_exposome.py --study caba_native \
  --lon -58.437 --lat -34.603 \
  --layers air_quality_pm25,greenspace_coverage,climate_heat
```

Para varios puntos, el CSV debe contener `id`, `lon` y `lat`:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python \
  scripts/query_exposome.py --study caba_native \
  --input data/raw/ar/buenos_aires/caba_native/query_points.csv \
  --output data/processed/ar/buenos_aires/caba_native/queries/points.csv
```

Los puntos fuera del AOI se rechazan. Para raster se toma el píxel nativo más
cercano; para clima se informa el nodo más cercano y se resumen sus valores
diarios; para OSM se conserva el total del AOI, el conteo dentro de 500 m y la
distancia al feature más cercano.

## Agregación posterior

Si después se dispone de comunas, barrios o ZIPs con un ID estable:

```bash
PYTHONPYCACHEPREFIX=/tmp .conda/envs/exposome/bin/python \
  scripts/aggregate_exposome.py --study caba_native \
  --polygons data/raw/ar/buenos_aires/units.geojson \
  --id-column id --layers air_quality_pm25,greenspace_coverage
```

Este comando produce una tabla derivada y no modifica los GeoTIFF, GeoPackages
ni puntos nativos.

## Orden de ejecución

1. Verificar la geometría administrativa de CABA, su atribución ODbL y la fecha
   de descarga.
2. Ejecutar el `dry-run` y verificar que no aparezcan `missing_input` ni
   `unavailable`.
3. Confirmar GEE con `ee.Initialize(project='exposome-api')` y conectividad de
   OpenStreetMap/Open-Meteo.
4. Ejecutar primero `greenspace_coverage`, `climate_heat`, `air_quality_pm25`
   y una capa OSM como smoke test.
5. Revisar los GeoTIFF/GeoPackage, metadata, cobertura y resolución.
6. Ejecutar las capas restantes con `--resume`.
7. Crear consultas por coordenadas; solo después generar agregados territoriales.

## Límites deliberados

Las capas chilenas (`socioeconomic`, `demography`, `heavy_metals`, `noise`,
`food_insecurity`, `pobreza_sae` y enriquecimiento DEIS) no se ejecutan para
Argentina. Para incorporarlas se requiere un proveedor argentino explícito y
una metodología propia; no se deben activar cambiando únicamente el nombre de
la ciudad.
