# Metodologia de validacion CV de vegetacion (greenspace_cv)

## Proposito

Esta capa valida cuanto verde es visible a nivel de veredas y calles — y cuanto de ese
verde esta fuera del mapeo OSM. Es una **capa de validacion**, no una capa del master.
Complementa `greenspace_access` (OSM) y `greenspace_coverage` (Landsat) documentando el
sesgo de sub-mapeo de OSM en areas verdes urbanas.

La metrica clave es `cv_outside_osm_pct_mean`: en Santiago su valor es ~88% (promedio por
comuna), lo que indica que la gran mayoria del verde visible desde la calle no esta
registrado en OpenStreetMap.

## Fuente de imagenes

- **Proveedor**: Esri World Imagery (imagenes aereas/satelitales de alta resolucion)
- **Acceso**: Tiles XYZ publicos vía ArcGIS tile server
- **Zoom**: 17 (~1 m/pixel en latitudes de Santiago)
- **Mosaico**: 3×3 tiles = ~768×768 pixeles por muestra
- **Cache local**: `cache/cv_tiles/<z>_<x>_<y>.jpg` (evita re-descargas)

## Metodo: Excess Green (ExG) con umbral Otsu

Referencia principal: Woebbecke et al. (1995), *Color indices for weed identification*.

### Formula ExG

```
s = R + G + B + 1e-6
ExG = 2*(G/s) - (R/s) - (B/s)
```

Donde R, G, B son valores de pixel [0-255]. La normalizacion cromatica (`/s`) hace el
indice robusto a cambios de iluminacion.

### Umbral automatico (Otsu 1979)

El umbral se calcula por maximizacion de varianza entre clases (metodo de Otsu) aplicado
sobre el histograma ExG de cada imagen. Se aplica un umbral minimo de seguridad de 0.05
para evitar que imagenes muy uniformes clasifiquen todo como verde.

### Filtro de dominancia verde

Un pixel clasificado como verde debe ademas cumplir `G >= R` Y `G >= B`. Este filtro
elimina falsas alarmas frecuentes: techos, pavimento húmedo, agua.

### Limpieza morfologica

- Opening binario con kernel 3×3 (elimina ruido puntual)
- Minimo de blob: 10 pixeles conectados (elimina manchas aisladas)

## Diseno de muestreo

- `samples_per_commune`: 5 puntos aleatorios dentro de cada poligono comunal (semilla 42)
- Los puntos se generan en CRS metrico (EPSG:32719) y se convierten a WGS84 para la
  descarga de tiles
- Para cada punto se descarga el mosaico 3×3 tiles centrado en ese punto

## Comparacion OSM

Los poligonos OSM cacheados (`cache/santiago_greenspace_osm.geojson`) se rasterizan sobre
la grilla de pixeles de cada mosaico para calcular:

- `cv_inside_osm_pct`: % del verde CV que cae dentro de poligonos OSM
- `cv_outside_osm_pct`: % del verde CV que cae fuera de OSM (sesgo de sub-mapeo)

## Columnas

### CSV de nivel muestra (`santiago_greenspace_cv_sample.csv`)

- `name`: nombre de comuna
- `sample_id`: id de muestra
- `cv_green_pct`: % de pixeles clasificados como verdes por ExG
- `osm_green_pct`: % de pixeles cubiertos por poligonos OSM
- `cv_inside_osm_pct`: % del verde CV dentro de OSM
- `cv_outside_osm_pct`: % del verde CV fuera de OSM
- `method`: metodo usado (`exg`)
- `zoom`: nivel de zoom de tiles (17)
- `exg_threshold`: umbral Otsu calculado para esta muestra

### CSV agregado por comuna (`santiago_greenspace_cv_commune.csv`)

- `name`: nombre de comuna
- `cv_green_pct_mean`: media de cv_green_pct entre las 5 muestras
- `cv_green_pct_std`: desviacion estandar de cv_green_pct (0 si n_samples=1)
- `osm_green_pct_mean`: media de osm_green_pct
- `cv_outside_osm_pct_mean`: media de cv_outside_osm_pct (indicador principal de sub-mapeo)
- `n_samples`: numero de muestras validas por comuna (esperado: 5)

## Outputs

- `data/processed/santiago_greenspace_cv_sample.csv`
- `data/processed/santiago_greenspace_cv_sample.geojson` (bounding boxes de cada mosaico)
- `data/processed/santiago_greenspace_cv_commune.csv`
- `data/processed/santiago_greenspace_cv_sample_metadata.json`
- `figures/greenspace_cv_santiago.png`
- `scripts/run_greenspace_cv.py` (detalle metodologico y visualizaciones)

## Reproducibilidad

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/run_greenspace_cv.py \
  --method exg --samples-per-commune 5 --seed 42
```

La primera corrida descarga ~2340 tiles Esri (~2 min con paralelismo). Las corridas
siguientes son instantaneas si los tiles estan cacheados.

## Limitaciones

- Cada comuna esta representada por 5 puntos aleatorios, no por una cobertura exhaustiva.
  La variabilidad intra-comunal puede ser alta en comunas grandes o heterogeneas.
- Esri World Imagery no tiene fecha garantizada por tile; los tiles pueden mezclar fechas
  distintas dentro de una misma comuna.
- ExG puede confundir cesped artificial intensamente verde con vegetacion real.
- La comparacion con OSM usa los mismos poligonos que `greenspace_access`; el sesgo OSM
  puede ser diferente segun la actividad de contribuidores por zona.
- Esta capa NO entra al master exposome; es solo un validador del sesgo de sub-mapeo OSM.

## Referencias

- Woebbecke, D. M., et al. (1995). Color indices for weed identification under various
  soil, residue, and lighting conditions. *Transactions of the ASAE*, 38(1), 259-269.
- Otsu, N. (1979). A threshold selection method from gray-level histograms. *IEEE
  Transactions on Systems, Man, and Cybernetics*, 9(1), 62-66.
