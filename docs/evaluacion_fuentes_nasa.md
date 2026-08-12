# Evaluación de fuentes de datos NASA para el exposoma

Este documento responde una pregunta concreta que se repite: **¿las herramientas
de acceso a datos de la NASA (Worldview, Earthdata Search, AppEEARS,
`earthaccess`, NASA POWER) son más ricas que las fuentes que ya usa el pipeline,
y agregan información?**

Se escribe para que la pregunta no se vuelva a litigar cada vez que alguien
descubre el catálogo de la NASA. El veredicto tiene fecha: **2026-08-02**.

## Respuesta corta: casi todo ya lo consumimos, por un camino mejor

El pipeline **ya usa productos NASA**: MODIS MCD64A1, MODIS MCD19A2, FIRMS,
VIIRS DNB y Landsat 8/9. Todos entran por **Google Earth Engine**, que resuelve
del lado del servidor el mosaico, la reproyección, el enmascarado por banda de
calidad y la estadística zonal. Descargar los mismos granulos en HDF/NetCDF por
Earthdata Search o AppEEARS obligaría a reimplementar ese trabajo dentro del
repo: es un camino más lento hacia el mismo dato, con más superficie de error.

**La excepción real es ECOSTRESS** (LST a 70 m), que GEE no sirve para América
Latina. Ese caso sí justifica abrir un camino NASA-directo y está desarrollado
más abajo.

## Veredicto por herramienta

| Herramienta | Veredicto | Razón |
|---|---|---|
| **NASA Worldview** | No es una fuente | Es un visor. Sirve para QA visual (mirar un día de humo, verificar una anomalía antes de debuggear código), no para alimentar el pipeline. |
| **NASA Earthdata Search** | Rechazado para lo que ya tenemos | Navegador sobre el catálogo CMR. Para MODIS/VIIRS/Landsat es un camino **peor** que GEE: entrega granulos crudos y nos deja reproyección, máscara QA, mosaico y zonal stats por implementar. Su valor es de descubrimiento, no de producción. |
| **AppEEARS** | Solo ante un hueco de GEE | Recorta por polígono y entrega series listas, lo cual es genuinamente cómodo. Pero opera por cola y con espera; choca con la reproducibilidad de `exposome run`, que es config-driven y reejecutable. Se justifica únicamente para productos que GEE no tiene. |
| **`earthaccess`** | Correcto **si** hay hueco | Es la biblioteca adecuada para acceso NASA-directo (maneja Earthdata Login, CMR y el acceso en nube). Hoy no está en `pyproject.toml`. Se adopta por ECOSTRESS, no por los demás productos. |
| **NASA POWER** | **Rechazado por resolución** | Entrega en grilla MERRA-2, 0,5°×0,625° (~55 km). Ya está en producción ERA5-Land a **11.132 m** (`climate_heat`, `wind`) y el archivo horario de Open-Meteo sobre ERA5. Adoptar POWER sería degradar un producto vigente, lo que la filosofía de máxima resolución de `CLAUDE.md` prohíbe explícitamente. |

## Qué productos NASA ya entran, y por dónde

Asset IDs verificados contra `config/layers/` y `src/exposome/`.

| Producto NASA | Asset en GEE | Capa | Resolución nativa | Estado |
|---|---|---|---:|---|
| MODIS MCD64A1 (área quemada) | `MODIS/061/MCD64A1` | `wildfire` | 463,31 m | En producción |
| NASA FIRMS (fuego activo) | `FIRMS` | `wildfire` | 926,63 m | En producción |
| MODIS MCD19A2 MAIAC (AOD, FMF) | `MODIS/061/MCD19A2_GRANULES` | `air_quality_satellite` | 3.000 m | En producción |
| VIIRS DNB (luces nocturnas) | `NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG` | `alan` | 463,83 m | En producción |
| Landsat 8/9 C2 L2 (NDVI/EVI) | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | `greenspace_coverage` | 30 m | En producción |
| MODIS MOD11A1 / MYD11A1 (LST) | `MODIS/061/MOD11A1`, `MODIS/061/MYD11A1` | — | 1.000 m | **Código existe, sin productizar** |
| Landsat C2 L2 térmico (`ST_B10`) | `LANDSAT/LC08/C02/T1_L2` | — | 30 m | Módulo existe, sin CLI |

No-NASA, para contexto: Sentinel-5P (ESA) en `air_quality_satellite`, CHIRPS
(UCSB) en `precipitation`, ERA5-Land (ECMWF) en `climate_heat`/`wind`, Dynamic
World (Google) y canopy Meta/WRI en `greenspace_multisource`, ACAG PM2.5.

**Antes de esta evaluación había cero apariciones en el repo** de
`earthaccess`, `power.larc.nasa.gov`, `appeears`, `earthdata`, `LAADS` o
`ECOSTRESS`: no había ninguna biblioteca cliente NASA instalada y todo NASA
pasaba por GEE. Eso cambió solo para ECOSTRESS (ver abajo): `earthaccess` es
ahora dependencia y `src/exposome/climate/fetch_ecostress.py` lo usa. Ningún
otro producto NASA cambió de canal.

## El hallazgo: ECOSTRESS a 70 m

ECOSTRESS (`ECO_L2T_LSTE`) entrega temperatura superficial a **70 m** desde un
instrumento montado en la Estación Espacial Internacional, entre 52°N y 52°S.

**Está en el catálogo de GEE, pero no sirve para nosotros.** La propia ficha de
Google ([`NASA/ECOSTRESS/L2T_LSTE/V2`](https://developers.google.com/earth-engine/datasets/catalog/NASA_ECOSTRESS_L2T_LSTE_V2))
dice: *"Currently, only tiles covering the Los Angeles metro area have been
ingested into Earth Engine. We plan to expand coverage in the future."* Para
Santiago, Bogotá, Lima o São Paulo, GEE no tiene el dato y `earthaccess` pasa a
ser el único camino.

Por qué importa: `climate_heat` se publica a **11.132 m**, la capa "fina" más
gruesa del bundle. ECOSTRESS son 70 m. Y por la órbita precesante de la ISS
muestrea **distintas horas del día** — incluida la tarde de máximo calor y la
madrugada —, algo que ningún sensor heliosincrónico puede dar: MODIS pasa
siempre a 10:30/13:30, Landsat a ~10:00.

### Cobertura verificada contra CMR

Conteos de granulos `ECO_L2T_LSTE` obtenidos del endpoint público de CMR
(sin autenticación):

| Ciudad | 2023 | 2024 |
|---|---:|---:|
| Santiago | 756 | 324 |
| Bogotá | 834 | 301 |
| Lima | 150 | 76 |
| São Paulo | 323 | 138 |

Son conteos de **granulos** (tesela × adquisición), no de pasadas: Santiago cae
en dos teselas MGRS (19HCC, 19HCD), así que hay que dividir por ~2. El muestreo
de enero 2023 sobre Santiago da 63 granulos = **18 días distintos de
adquisición** en un mes.

Santiago por año: 2019: 329 · 2020: 403 · 2021: 497 · 2022: 507 · 2023: 756 ·
2024: 324 · 2025: 510 · 2026: 825. La serie parte en **2019** (el instrumento se
lanzó en julio de 2018), no en 2015 como el resto de las series climáticas.

Es cobertura de sobra para Santiago, Bogotá y São Paulo. **Lima es el caso
dudoso**: 150/76 son 5-10× menos que Santiago, y son granulos *antes* de
enmascarar nubes. Bajo la garúa del Pacífico la estratocúmulo marina persiste
buena parte del año, así que 76 granulos podrían dejar adquisiciones utilizables
de un dígito en 2024. Lima puede terminar siendo un hueco permanente para esta
capa; sería un resultado válido, no un bug que perseguir (precedente: el hueco
de Dynamic World en Bogotá, ADR 0008).

### Advertencia que manda sobre el diseño de la capa

**LST no es temperatura del aire y no reemplaza `climate_heat`.** ERA5-Land
entrega T2M, temperatura del aire a 2 m; ECOSTRESS entrega temperatura
radiativa de piel. Son cantidades físicas distintas y durante el día difieren
varios kelvin. La capa se suma como indicador de ambiente térmico superficial e
isla de calor, no como sustituto.

## Candidatos registrados, no implementados

Dos mejoras reales que salieron de esta evaluación y que **no** están en el
alcance actual. Se dejan escritas para que no se pierdan.

**VNP46A2 Black Marble** (`NASA/VIIRS/002/VNP46A2`) — luces nocturnas diarias a
500 m, corregidas por BRDF lunar y atmósfera, con relleno de huecos. El `alan`
actual usa el compuesto **mensual** de NOAA (`VCMSLCFG`) a la misma resolución
efectiva. Misma resolución, mejor corrección, cadencia diaria, **ya está en
GEE** — sin camino de acceso nuevo ni credencial nueva. `ROADMAP.md` ya pide
compuestos ALAN sub-anuales. Es el candidato con mejor relación esfuerzo/valor
de los tres.

**MODIS MOD11A1 / MYD11A1 a 1 km** — LST día y noche desde Terra y Aqua, 11×
más fino que ERA5-Land. Ya está en GEE y `src/exposome/climate/fetch_modis_lst.py`
ya existe. **Ojo con asumir que es gratis**: ese fetcher está sobre el patrón
legacy (`config.load_config(city)` + `boundaries.get_communes`, previo a la
migración a locations/studies) y hace **solo estadística zonal**, sin export
raster nativo. Productizarlo significa portarlo al contexto de `studies.py`,
agregar entrada en `config/layers.yaml`, spec en `NATIVE_LAYER_SPECS` y export
COG — una capa nueva normal, no un cableado.

## GRDI v1: por qué un índice de privación global no es una capa del exposoma

Veredicto con fecha: **2026-08-05**.

Aparece cada tanto la idea de que SEDAC resuelve el hueco socioeconómico del
catálogo, que es real: fuera de Chile (`socioeconomic`, `pobreza_sae`) y
Argentina (`community_safety`, `community_violence`) **no hay ninguna capa
socioeconómica**. Lima, Bogotá, CDMX, São Paulo y Medellín no tienen ninguna.
El candidato obvio es el **Global Gridded Relative Deprivation Index (GRDI),
v1 (2010-2020)** de CIESIN/SEDAC. Se evaluó contra datos y **se descarta**.

### Qué es

Ocho GeoTIFF globales a 30 arc-sec (~1 km), WGS84, 43178×16580, float32,
nodata −9999: el índice compuesto `povmap-grdi-v1.tif`, seis componentes y un
raster de conteo de relleno. Escala 0–100, donde **100 = máxima privación**.
Los componentes son CDR (razón de dependencia infantil), IMR (mortalidad
infantil), SHDI (IDH subnacional), BUILT (superficie construida), VNL-2020 y
VNL-slope (luces nocturnas). Licencia **CC BY 4.0**, DOI
`10.7927/3xxe-ap97`, 228 países. La licencia y la cobertura son buenas; el
problema es otro.

### Dentro de ciudad ordena denso vs. rural, no rico vs. pobre

Zonal stats de las 52 comunas de Santiago contra el `master.csv` validado:

| Comuna | Realidad | GRDI |
|---|---|---|
| Lo Espejo | de las más pobres de Chile | **11** (poco privada) |
| La Pintana | la más pobre del Gran Santiago | **16** |
| Providencia / Vitacura | las de mayor `nse_index` del país | **21 / 18** |
| San José de Maipo | rural, ingreso medio | **64** (máxima privación) |

El patrón se repite en las 12 geografías del repo sin excepción: el mínimo es
siempre el centro denso y el máximo siempre la periferia rural (Bogotá:
Candelaria→Sumapaz; CDMX: Benito Juárez→Milpa Alta; São Paulo:
Cambuci→Marsilac; Medellín: Santa Cruz→Palmitas).

La prueba decisiva es restringir a las **34 comunas urbanas** (>1.000 hab/km²),
que es donde vive la cohorte. La correlación con todo lo socioeconómico se cae
a cero:

| ρ Spearman (GRDI vs.) | 52 comunas | 34 urbanas |
|---|---:|---:|
| `nse_index` | −0,54* | −0,13 |
| `ingreso` | −0,48* | −0,30 |
| `escolaridad` | −0,42* | −0,09 |
| `pobreza_pct` | +0,28* | +0,06 |
| `pobreza_multi_pct` | +0,42* | −0,03 |
| `viv_materialidad_deficitaria_pct` | +0,59* | +0,08 |
| `hacinamiento_phh` | +0,27 | +0,31 |

(*p<0,05; ninguna de la columna urbana es significativa.) La más fuerte del set
completo, `viv_materialidad_deficitaria_pct`, es la que más se derrumba.
`hacinamiento_phh` es la única que no cae, y nunca fue significativa. El −0,54
aparente del set completo era enteramente el contraste urbano/rural.

Lo que GRDI sí mide: ρ(GRDI, `alan_radiance_mean`) = **−0,87** y
ρ(GRDI, densidad poblacional) = **−0,83**. Es un índice de urbanicidad, y mide
lo que la capa `alan` ya mide mejor.

### La causa: la resolución socioeconómica es falsa

La documentación de SEDAC lo dice. Sobre el índice (p. 12): *"owing to the use
of built-up areas and nighttime lights, the GRDIv1 **may not fully capture
intra-urban differentials in deprivation**"*. Y sobre CDR (p. 4): *"calculated
at the level of administrative (or census) units, and the result is **applied
to all grid cells within those units**"*.

Verificado contando valores de píxel distintos dentro de cada comuna:

| Componente | Valores distintos (mediana) | sd intra-comuna | % comunas constantes |
|---|---:|---:|---:|
| SHDI | 1 | 0,00 | **79 %** |
| CDR | 2 | 0,35 | **27 %** |
| IMR | 5 | 0,71 | 0 % |
| BUILT | 112 | 36,05 | 3 % |
| VNL-2020 | 91 | 24,36 | 6 % |

Solo BUILT y VNL son grillados de verdad, y son justamente los que miden
urbanicidad. Los tres componentes socioeconómicos son valores de unidad
administrativa pintados sobre la grilla: "1 km" nominal, resolución efectiva
admin-1 (SHDI) o de la unidad administrativa que en Chile coincide
aproximadamente con la comuna (CDR). Adoptarlo sería exactamente lo que
prohíbe la filosofía de máxima resolución de `CLAUDE.md`: **sobremuestrear un
producto grueso para fingir detalle**.

### Tampoco se rescata por componente

CDR es el único que correlaciona fuerte y en la dirección correcta en el corte
urbano (ρ = −0,82 con `ingreso`, +0,89 con `hacinamiento_phh`). Pero da
**ρ = 0,94 contra la CDR calculada del Censo 2017 vía `demography`**
(`demo_pop_0_14`/`demo_pop_15_64`) en esas 34 comunas: reproduce lo que el
pipeline ya tiene, con vintage 2010 (GPWv4 BDCv4.11) en vez de 2017 y sin
aportar ningún detalle espacial. Fuera de Chile el nivel administrativo es
"best-available" y queda sin verificar. BUILT y VNL duplican `alan` (VIIRS DNB
a 463,83 m, más fino).

**Límite de la validación:** el contraste contra verdad de terreno es solo
Santiago, porque `socioeconomic`/`pobreza_sae` son CL-only y es el único
estudio con master SES validado. El patrón centro→periferia sí se replica en
las 12 geografías, y el mecanismo lo documenta SEDAC.

### Tampoco sirve para comparar ciudades entre sí

Comparar promedios por unidad entre ciudades mide la geometría de las unidades,
no privación: las comarques catalanas son rurales y las alcaldías son urbanas,
así que Cataluña "sale" en 48,8 y CDMX en 21,5. Enmascarando a píxeles urbanos
(**BUILT ≤ 20**, misma grilla, sin datos nuevos) Cataluña cae a **10,5** y el
orden se da vuelta: la comparación cruda era un artefacto.

El ranking corregido tampoco es creíble. Deja a **CABA como la más privada
(25,7)**, por encima de Lima (16,0) y Bogotá (15,1), y a CDMX (11,4) como menos
privada que Santiago (18,4). Se cita como ilustración y no como orden
defendible: se corrió un solo umbral y la fracción de píxeles retenidos va de
11 % (Cataluña) a 97 % (CABA), así que el nivel exacto es sensible al corte.
Alcanza para descartar el uso, no para afirmar un orden.

El único componente que ordena regiones de forma sensata es **SHDI** (País
Vasco 3,0 y Cataluña 5,9 abajo; Medellín 34,6 y São Paulo 30,3 arriba). Pero
SHDI es el Subnational HDI del **Global Data Lab**, que se baja directo de la
fuente: no hace falta un raster NASA de 429 MB para obtenerlo, y GRDI lo
entrega degradado (winsorizado, indexado 0–100 y con peso 0,1 dentro de un
compuesto).

### Qué queda

El hueco socioeconómico portable sigue abierto y hay que llenarlo con otra
cosa. Si alguna vez se necesita señal socioeconómica a escala **admin-1 o entre
países** — la escala del crosswalk `Exposome_Global`, no la de GEMMA — el
camino es **SHDI de Global Data Lab directo**, no GRDI.

## Descartados explícitamente

- **GRDI v1 (CIESIN/SEDAC)**: 1 km nominal, pero sus componentes
  socioeconómicos son valores administrativos repintados en grilla. Dentro de
  ciudad ordena denso vs. rural (ρ = −0,87 con `alan`), no rico vs. pobre;
  entre ciudades tampoco da un orden creíble. Si se necesita señal admin-1,
  SHDI se baja directo de Global Data Lab. Detalle arriba.
- **NASA POWER**: ~55 km contra 11.132 m ya en producción. Degradación.
- **MOD13Q1 NDVI (250 m)**: peor que Landsat a 30 m y Dynamic World a 10 m, ya
  en uso.
- **TEMPO**: contaminantes horarios, pero cobertura **solo Norteamérica**. No
  aplica a ninguna ciudad de la cohorte.
- **GPM IMERG**: 11 km contra CHIRPS a 5.566 m ya en producción. Solo tendría
  sentido si apareciera una demanda concreta por extremos sub-diarios, que hoy
  no existe.
