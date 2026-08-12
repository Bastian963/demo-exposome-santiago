# PM2.5 crónico de alta resolución — metodología (ACAG vía GEE)

## Por qué esta capa

El material particulado fino **PM2.5** es la exposición ambiental con la
asociación más replicada con **deterioro cognitivo y demencia** (Livingston et
al., *Lancet Commission on dementia prevention*, 2024). Para envejecimiento
cerebral la ventana relevante es la **exposición crónica** (años), no un solo
año, por lo que esta capa usa una **media multi-anual**.

El repositorio ya estimaba NO₂ de superficie a ~3.5 km (Sentinel-5P), pero su
único PM2.5 venía del reanálisis **CAMS legacy (~11 km)**, que agrupa ~20 comunas
en el mismo valor y borra el gradiente intra-urbano. Esta capa lo reemplaza por
PM2.5 satelital a **~1 km**, recuperando el contraste poniente/centro vs oriente
—el mismo problema de resolución que el proyecto ya había corregido para NO₂—.

## Fuente

- **Producto:** ACAG / van Donkelaar *surface PM2.5* (Atmospheric Composition
  Analysis Group, Washington University in St. Louis). Combina profundidad
  óptica de aerosoles (AOD) de MODIS, MISR, SeaWiFS y VIIRS con el modelo de
  transporte químico GEOS-Chem y una red neuronal residual calibrada contra
  monitores en tierra.
- **Acceso:** *asset* de Google Earth Engine del awesome-gee-community-catalog
  (sat-io): `projects/sat-io/open-datasets/GLOBAL-SATELLITE-PM25/ANNUAL`
  (mensual disponible en `.../MONTHLY`). Se reusa el pipeline GEE ya autenticado
  del repo (`init_gee("exposome-api")`), sin API key adicional.
- **Versión/resolución:** V6.GL.02, 0.01° (~1 km), unidades **µg/m³**, medias
  anuales 2000–2022.

## Procesamiento

1. **Ventana crónica.** Se filtra la colección anual a **2015–2022** y se promedia
   (`ImageCollection.filterDate(...).mean()`). Es la última ventana de 8 años
   disponible y representa exposición de largo plazo.
2. **Banda.** El catálogo no documenta el nombre de banda; el código selecciona
   la banda 0 (`band: "auto"`) y la renombra a `pm25`, quedando agnóstico al
   nombre. Confirmar con `ee.Image(...).bandNames().getInfo()` y fijarla en
   `config/cities/santiago.yaml` si se desea.
3. **Estadística zonal comunal.** `reduceRegions` (media) sobre las 52 comunas
   (`src/exposome/gee.py:image_to_stats`), reusando los límites ya procesados
   (no se re-descarga OSM).
4. **Media ponderada por población.** `sum(pm25·pop)/sum(pop)` con el ráster
   **WorldPop** (el mismo de la capa ALAN); la exposición poblacional es lo
   epidemiológicamente relevante. Fallback a la media areal si una comuna pequeña
   no intersecta el ráster.
5. **Razón WHO 2021.** `pm25_who_ratio = pm25_mean / 5.0 µg/m³` (guía de
   `air_quality.who_guidelines.pm25`).

## Salidas (`data/processed/santiago_pm25_acag_2015_2022.*`)

| Columna | Significado |
|---|---|
| `pm25_mean` | PM2.5 crónico medio areal de la comuna [µg/m³] |
| `pm25_pop_weighted` | PM2.5 crónico ponderado por población [µg/m³] |
| `pm25_who_ratio` | Veces sobre la guía WHO 2021 (5 µg/m³) |

Se integra al master como spec `air_quality_pm25` y pasa a ser el `pm25_*`
canónico (el PM2.5 grueso de CAMS se retira del master, conservando el CSV/figura
legacy para la comparación documentada CAMS vs satélite).

## Validación

- **Validez aparente (gradiente conocido):** las comunas poniente/centro (Cerro
  Navia, Pudahuel, Independencia, Santiago) deben superar a las del oriente
  (Las Condes, Lo Barnechea, Vitacura). `plot_pm25_map.py` lo expone en el ranking.
- **Validez de constructo:** correlación de Spearman con el NO₂ de superficie
  (co-exposición de combustión urbana), siempre disponible.
- **Verdad de terreno (opcional):** si se deja un CSV con la media anual de
  PM2.5 por estación SINCA en `data/raw/stations_sinca/sinca_pm25_annual.csv`
  (columnas `station, lat, lon, pm25`), la figura calcula la concordancia
  ACAG–SINCA por comuna (ρ de Spearman y sesgo medio). Se omite con elegancia si
  el archivo no existe.

## Limitaciones

- Indicador **ecológico/comunal**: no reemplaza la exposición residencial
  individual.
- ACAG es un producto modelado (AOD + transporte químico + ML); a ~1 km suaviza
  micro-gradientes (calles con alto tráfico) que un modelo de uso de suelo (LUR)
  o el **Plan B** (calibración AOD×SINCA) capturarían mejor. Queda como mejora
  futura del gradiente fino.
- La ventana 2015–2022 no cubre el año en curso; es deliberado (exposición
  crónica y disponibilidad del producto).

## Referencias

- Livingston G. et al. *Dementia prevention, intervention, and care: 2024 report
  of the Lancet standing Commission.* Lancet, 2024.
- van Donkelaar A. et al. *Monthly Global Estimates of Fine Particulate Matter
  and Their Uncertainty.* Environ. Sci. Technol., 2021 (ACAG V5/V6).
