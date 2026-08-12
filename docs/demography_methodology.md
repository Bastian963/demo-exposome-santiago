# Metodologia de demografia Censo 2017

## Proposito

Esta capa entrega una base poblacional comunal para Santiago usando el Censo
2017 de INE Chile. Se usa como denominador e insumo de vulnerabilidad en el
master exposome, por ejemplo para `demo_pop_total`,
`demo_pct_pop_65_plus` y los ratios de habitantes por establecimiento de salud.

## Fuente

- Proveedor: Instituto Nacional de Estadisticas de Chile (INE).
- Dataset: Censo 2017, microdato publico agregado a manzana.
- Archivo descargado: `Censo2017_ManzanaEntidad_CSV.rar`.
- URL: `https://redatam-ine.ine.cl/tab/Censo2017_ManzanaEntidad_CSV.rar`.
- Tabla principal: `Censo2017_Manzanas.csv`.
- Tabla de nombres/codigos de comuna:
  `Censo2017_Identificación_Geográfica/Microdato_Censo2017-Comunas.csv`.
- Region usada: `13`, Region Metropolitana de Santiago.
- Unidad geografica de salida: comuna, 52 comunas esperadas.

## Metodo

`scripts/run_demography.py` llama a `src/exposome/demography.py` desde la raiz
del repositorio. El pipeline descarga el RAR si no existe en `cache/`, extrae
los CSV requeridos y filtra las filas de manzana con `REGION == 13`.

Las filas se agrupan por `COMUNA` y luego se unen a la tabla de nombres de
comuna del Censo. Los nombres se normalizan con `normalize_comuna_name()` para
calzar con las geometria comunales ya usadas por el proyecto.

El archivo publico de manzanas usa `*` para celdas pequenas suprimidas. Esas
celdas se convierten a nulas antes de agregar. Como la supresion afecta
componentes por sexo y edad, los componentes comunales se reescalan contra el
total oficial `PERSONAS` usando redondeo entero por mayores residuos. Esto
garantiza que:

- `pop_total == pop_male + pop_female`
- `pop_total == pop_0_14 + pop_15_64 + pop_65_plus`

Los grupos etarios son:

- `pop_0_14`: `EDAD_0A5 + EDAD_6A14`
- `pop_15_64`: `EDAD_15A64`
- `pop_65_plus`: `EDAD_65YMAS`

Los porcentajes se calculan como `100 * grupo / pop_total` y se redondean a
dos decimales.

## Columnas

- `name`: nombre normalizado de comuna.
- `comuna_code`: codigo INE/CUT de comuna.
- `pop_total`: personas, total Censo 2017.
- `pop_male`: personas, hombres ajustados por supresion.
- `pop_female`: personas, mujeres ajustadas por supresion.
- `pop_0_14`: personas de 0 a 14 anos.
- `pop_15_64`: personas de 15 a 64 anos.
- `pop_65_plus`: personas de 65 anos y mas.
- `pct_pop_0_14`: porcentaje comunal de 0 a 14 anos.
- `pct_pop_15_64`: porcentaje comunal de 15 a 64 anos.
- `pct_pop_65_plus`: porcentaje comunal de 65 anos y mas.

## Outputs

- `data/processed/santiago_demography.csv`
- `data/processed/santiago_demography.geojson`
- `data/processed/santiago_demography_metadata.json`
- `figures/demography_santiago_2panel.png`

El GeoJSON reutiliza geometria comunal local de capas procesadas existentes y
se escribe en `EPSG:4326`.

## Integracion al master

`scripts/build_master_exposome.py` trata `demography` como capa requerida. Las
columnas poblacionales se renombran con prefijo `demo_`, mientras
`comuna_code` queda sin prefijo. `demo_pop_total` alimenta los indicadores
derivados `health_inhabitants_per_*`.

## Limitaciones

- La fecha de referencia es Censo 2017; no es un denominador intercensal ni una
  estimacion actual.
- La salida es comunal y no conserva heterogeneidad intra-comunal.
- La supresion de celdas pequenas en el microdato publico obliga a reescalar
  componentes por sexo y edad a nivel comunal.
- El ajuste conserva el total oficial comunal, pero no recupera la distribucion
  exacta de las celdas suprimidas.
