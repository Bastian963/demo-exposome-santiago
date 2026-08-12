# Metodologia de la capa `healthcare` — Acceso a salud (Santiago)

## Proposito

Caracterizar la accesibilidad a servicios de salud en las 52 comunas de la
Region Metropolitana de Santiago, Chile, como factor de exposoma urbano para el
estudio del envejecimiento cerebral y la demencia. La capa entrega, por comuna:

- Conteo agregado de establecimientos de salud por categoria y por sector
  (publico / privado).
- Densidad de establecimientos por km^2.
- Distancia (euclideana) al establecimiento de salud, hospital y atencion
  primaria mas cercano, calculada sobre una grilla regular dentro del poligono
  comunal.
- Derivados de razon habitantes / establecimiento cuando se cruza con la capa
  `demography` (master exposome).

La capa alimenta el master exposome (`scripts/build_master_exposome.py`,
seccion `LAYER_SPECS["healthcare"]`) y se renombra como prefijo `health_*` al
integrarse.

## Fuentes

### 1. MINSAL/DEIS — Establecimientos de salud vigentes

- Publicador: Departamento de Estadisticas e Informacion de Salud (DEIS) del
  Ministerio de Salud de Chile, en datos.gob.cl.
- Recurso: "Establecimientos de Salud Vigentes" (CKAN
  `establecimientos-de-salud-vigentes`).
- Descubrimiento de URL: API CKAN `package_show` (config
  `healthcare.official_source.ckan_package_url`) con fallback explicito a
  `csv_url`.
- Formato CSV: separador `;`, codificacion por defecto (latin-1 en el archivo
  original), columnas segun `healthcare.official_source.columns`.
- Cache local: `cache/establecimientos_deis.csv` (descargado una vez; se reusa
  salvo que se invoque el script con `--refresh-official`).
- Filtros aplicados:
  - `RegionGlosa` contiene `Metropolitana de Santiago` (case-insensitive).
  - `EstadoFuncionamiento` contiene `Vigente` (case-insensitive). Conserva
    asi establecimientos en operacion habitual y los transitorios.
  - Coordenadas validas y dentro del bounding box de la RM definido en
    `config/cities/santiago.yaml` (descarta errores groseros de coordenada).
- Clasificacion por tipo (`healthcare.official_source.type_mapping`):
  - `hospital` — "Hospital".
  - `clinic` — "Clinica".
  - `primary_care` — CESFAM, SAPU, SAR, CGU, CGR, PSR, CECOSF, SUR.
  - `laboratory` — "Laboratorio Clinico".
  - `dental` — "Clinica Dental".
  - `mental_health` — COSAM (Centro Comunitario de Salud Mental).
- Clasificacion por sector (`healthcare_official._classify_sector`):
  - Publico si `TipoSistemaSaludGlosa == "Publico"`, o si
    `DependenciaAdministrativa` indica municipal, Servicio de Salud, SEREMI,
    FFAA/Carabineros/PDI, o pertenencia al SNSS.
  - Privado si `TipoSistemaSaludGlosa == "Privado"` o `DependenciaAdministrativa
    == "Privado"`.
  - Default conservador: `publico` cuando no se resuelve.

### 2. OpenStreetMap (complemento)

- Proveedor: colaboradores de OpenStreetMap (ODbL).
- Descarga: `osmnx.features_from_place` con los tags configurados en
  `healthcare.osm_tags` (descargas por clave para mantener el query pequeno y
  reintentar ante fallos transitorios de Overpass).
- Categorias mapeadas (`config/cities/santiago.yaml`,
  `healthcare.osm_tags`):
  - `amenity`: hospital, clinic, pharmacy, doctors, health_post, dentist.
  - `healthcare`: hospital, clinic, centre, doctor, pharmacy, dentist,
    laboratory.
- Cache local: `cache/santiago_healthcare_osm.geojson`.
- OSM se conserva como complemento: aporta farmacias (que DEIS no publica),
  dentistas, psicoterapeutas, y registros informales no incorporados al
  registro oficial. La columna `source` registra el origen de cada
  establecimiento (`"deis"`, `"osm"`, o `"both"` si fueron conflacionados).

## Categorias normalizadas

Cada establecimiento (DEIS o OSM) se asigna a una o varias categorias booleanas
mutuamente compatibles segun las reglas de
`config/cities/santiago.yaml`:

| Categoria       | Reglas de inclusion (cualquiera)                                               |
| --------------- | ------------------------------------------------------------------------------ |
| `hospital`      | `amenity=hospital` o `healthcare=hospital`                                      |
| `clinic`        | `amenity=clinic` o `healthcare=clinic`                                          |
| `primary_care`  | `amenity` in `{doctors, health_post}` o `healthcare` in `{centre, doctor}`      |
| `pharmacy`      | `amenity=pharmacy` o `healthcare=pharmacy`                                      |
| `laboratory`    | `healthcare=laboratory`                                                         |
| `dental`        | `amenity=dentist` o `healthcare=dentist`                                        |
| `mental_health` | `healthcare=psychotherapist`                                                    |
| `all_health`    | el establecimiento matchea cualquier tag del universo OSM consultado            |

`n_total` suma todos los establecimientos con `is_all_health=True`; equivale a
la union DEIS+OSM sin duplicados.

## Conflacion DEIS / OSM

Implementada en `src/exposome/healthcare.py::conflate_sources`:

1. Ambos GeoDataFrames se proyectan al CRS metrico (`EPSG:32719`).
2. Para cada punto OSM se busca el DEIS mas cercano con `scipy.spatial.cKDTree`.
3. Un punto OSM se considera duplicado de un DEIS si:
   - esta a menos de `strict_buffer_m` (50 m) del DEIS, o
   - esta a menos de `buffer_m` (150 m) **y** el nombre normalizado coincide
     con `difflib.SequenceMatcher` >= `name_match_threshold` (0.5).
4. El registro oficial gana: se conserva el DEIS, y los OSM duplicados se
   descartan. El campo `source` se etiqueta como `"both"` cuando hay match.
5. Los puntos OSM sin match se conservan como cobertura complementaria (caso
   tipico: farmacias).
6. Las columnas booleanas de sector (`is_<cat>_public`, `is_<cat>_private`)
   quedan `False` para OSM (OSM no distingue sector).

## Metricas y unidades

### Conteos por comuna (int)

`n_total`, `n_public_total`, `n_private_total`, `n_hospital`,
`n_hospital_public`, `n_hospital_private`, `n_clinic`, `n_clinic_public`,
`n_clinic_private`, `n_primary_care`, `n_primary_care_public`,
`n_primary_care_private`, `n_pharmacy`, `n_laboratory`, `n_laboratory_public`,
`n_laboratory_private`, `n_dental`, `n_dental_public`, `n_dental_private`,
`n_mental_health`, `n_mental_health_public`, `n_mental_health_private`.

Asignacion espacial: `gpd.sjoin(..., predicate="within")` en `EPSG:32719`. Un
establecimiento se asigna a la comuna que contiene su punto representativo
(poligonos OSM colapsan a `representative_point()` en CRS metrico para evitar
centrides geodesicos mal ubicados en areas extensas).

### Densidad

`density_per_km2 = n_total / area_km2` (float, 4 decimales).

### Grilla de acceso y distancias (metros, enteros)

- `grid_spacing_m = 1000` (config): se genera una grilla regular 1 km x 1 km
  en `EPSG:32719` recortada al poligono de cada comuna. Si una comuna no
  contiene ningun punto de grilla (caso extremo), se usa su `representative
  point()`.
- Para cada punto de grilla se calcula la distancia euclideana al
  establecimiento mas cercano por categoria:
  - `all_facilities` (todos los establecimientos con `is_all_health=True`).
  - `hospital_facilities` (`is_hospital=True`).
  - `primary_care_facilities` (`is_primary_care=True`).
- Se resume por comuna en `mean_*_m`, `median_*_m`, `p90_*_m`
  (`_m` indica metros enteros). El calculo usa `gpd.sjoin_nearest` por
  defecto; existe la opcion `use_ckdtree=True` (CLI `--use-ckdtree`) que
  acelera el query con `scipy.spatial.cKDTree`.
- `n_access_grid` = numero de puntos de grilla dentro de la comuna (proxy
  del area efectivamente muestreada).
- `distance_metric = "euclidean_straight_line"`. La capa actual **no** usa
  red vial; la opcion `--use-network` permanece disponible y archivada
  (`network.enabled = false` por defecto) para corridas que requieran
  distancia por red de calles.

### Derivados en el master

`scripts/build_master_exposome.py` calcula razones poblacionales cuando la
capa `demography` esta disponible:

- `health_inhabitants_per_hospital` = `demo_pop_total / health_n_hospital`.
- `health_inhabitants_per_primary_care`.
- `health_inhabitants_per_clinic`.
- `health_inhabitants_per_public_facility`.
- `health_inhabitants_per_private_facility`.
- `health_inhabitants_per_facility`.

Valores `NaN` cuando la comuna no tiene establecimientos de esa categoria
(undefined); el chequeo de integridad del master excluye explicitamente
estas columnas de razon.

## Reproducibilidad

- Script principal: `python scripts/run_healthcare.py` (cache-first, DEIS+OSM,
  distancia euclideana, sin red vial).
- Flags opcionales:
  - `--no-official`: desactiva DEIS (solo OSM).
  - `--refresh-official`: fuerza re-descarga del CSV DEIS.
  - `--use-network`: activa distancia por red vial (costoso; no usado en la
    corrida de revision).
  - `--use-ckdtree`: acelera el calculo de distancias.
- Cache disponible localmente: `cache/santiago_communes.geojson`,
  `cache/santiago_healthcare_osm.geojson`, `cache/establecimientos_deis.csv`.
  La corrida cache-first reusa todos los insumos y solo recomputa los
  indicadores por comuna.
- `config/cities/santiago.yaml` documenta todas las reglas de filtrado, tags
  y umbrales.
- `data/processed/santiago_healthcare_access_metadata.json` registra
  `n_facilities_*`, `distance_metric`, `use_official_source`, `use_network` y
  la lista de columnas — es la fuente canonica para auditoria.
- Comparacion DEIS vs OSM: `python scripts/compare_healthcare_sources.py`
  produce `data/processed/healthcare_source_comparison_by_commune.csv` y
  `data/processed/healthcare_unmatched_facilities.csv` (establecimientos DEIS
  sin equivalente OSM dentro de 150 m, y viceversa).
- Mapas coropleticos: `python scripts/plot_healthcare_maps.py` (lee el master
  GeoJSON) emite 11 mapas en `figures/` que incluyen razones poblacionales.

## Outputs principales

- `data/processed/santiago_healthcare_access.csv` (52 filas x 35 columnas).
- `data/processed/santiago_healthcare_access.geojson` (mismo contenido con
  geometria comunal).
- `data/processed/santiago_healthcare_access_metadata.json` (metadata con
  contadores por fuente/categoria, configuracion usada y fecha UTC).
- `data/processed/santiago_exposome_master.csv` (filas `health_*`,
  razones `health_inhabitants_per_*`).
- `figures/healthcare_n_primary_care_map.png`, `healthcare_n_hospital_map.png`,
  `healthcare_n_total_map.png`, `healthcare_mean_*_distance_map.png`,
  `healthcare_ratio_inhabitants_per_*_map.png` (11 mapas).
- `figures/healthcare_access_santiago.png` (resumen legacy 2-panel, conserva
  el archivo original de la primera corrida).

## Verificacion de la corrida de revision (auditoria opencode, 2026-06-29)

- `santiago_healthcare_access.csv`: 52 comunas, `name` sin duplicados ni
  nulos, 35 columnas (incluye los conteos y las distancias euclideanas).
- `use_official_source=true`, `distance_metric=euclidean_straight_line`,
  `use_network=false` en metadata.
- Conteos totales: `n_facilities_total=2754`, `n_facilities_osm=1690`,
  `n_facilities_official=1064` (post-conflacion).
- `santiago_exposome_master.csv`: contiene las 30 columnas `health_*`
  (24 conteos + 1 densidad + 5 razones poblacionales) y las 9 columnas
  `mean/median/p90_nearest_*_m` (euclideanas, sin sufijo `network`).
- Comparacion DEIS vs OSM: 169 DEIS sin match OSM, 1194 OSM sin match DEIS
  (principalmente farmacias y dentistas que DEIS no publica).
- Tests: `python -m unittest discover -s tests` (toda la suite exposome) en
  verde.
- Auditoria: `scripts/audit_exposome_status.py --check` en verde despues de
  registrar este documento y aplicar `--write`.

## Limitaciones

1. **Distancia euclideana.** No considera red vial, topografia ni transporte
   publico. Sobre-estima accesibilidad en comunas con barreras fisicas
   (cerros, autopistas) y sub-estima el tiempo real de viaje. La opcion
   `--use-network` entrega distancia por red de calles (cache de grafo en
   `cache/santiago_walk_graph.graphml`) y queda archivada para corridas que
   prioricen fidelidad sobre velocidad.
2. **Grilla 1 km.** Puede perder variabilidad intra-comunal fina (manzanas).
   Es un compromiso estandar para 52 comunas y ~15 000 puntos en la RM.
3. **DEIS no publica farmacias.** Por construccion, las 1124 farmacias de la
   capa provienen solo de OSM. La categoria `n_pharmacy` no se desglosa en
   `public`/`private`.
4. **OSM no distingue sector.** Las razones publicas/privadas se aplican
   solo a los establecimientos DEIS conflacionados.
5. **Mapeo OSM heterogeneo.** El inventario de clinicas privadas y dentistas
   en OSM es desigual entre comunas; las comunas con mayor densidad de
   voluntarios OSM pueden mostrar sobre-conteo. La comparacion con DEIS
   cuantifica esta diferencia.
6. **Cobertura espacial.** `sjoin(..., predicate="within")` asigna cada
   punto a una sola comuna; establecimientos ubicados exactamente sobre un
   limite comunal se asignan al poligono que contenga el punto
   representativo.
7. **Categorias excluyentes pero no exhaustivas.** El universo OSM
   consultado excluye deliberadamente nodos con tags no canonicos (p.ej.
   `healthcare=yes` sin subtipo). Un analisis cualitativo podria ampliar
   este universo.
8. **Validacion externa oficial.** El contraste con el registro DEIS ya
   cubre hospitales, APS, clinicas, laboratorios, dentales y salud mental
   (COSAM). No hay validacion contra fuentes terciarias (Superintendencia
   de Salud, Fonasa, etc.); queda como mejora futura no bloqueante.

## Interpretacion para brain health / exposoma

- `health_n_primary_care` y `health_inhabitants_per_primary_care` son
  indicadores directos de acceso a atencion primaria, componente central
  del continuo de cuidados para hipertension, diabetes y demencia
  (Livingston et al., Lancet Commission on Dementia Prevention 2024).
- `mean_nearest_primary_care_m` complementa al conteo: comunas rurales
  con 1 CESFAM pueden mostrar alta distancia media por baja densidad de
  poblacion.
- El desglose `*_public` vs `*_private` permite estudiar inequidad en el
  mix de provision: en Chile el sector publico (SNSS) cubre ~80% de la
  poblacion via APS, por lo que razones publicas bajas relativas al
  privado en una comuna sugieren dependencia de prestadores privados.
- La capa se cruza en el master con `pm25_pop_weighted`, `no2_surface_ug_m3`,
  `noise_combined_pct`, `green_cover_pct_ndvi`, `nse_index` y
  `demo_pct_pop_65_plus`, habilitando analisis de exposoma multiple y
  modelos de demanda de servicios por comuna.
- Los ratios `health_inhabitants_per_*` ya excluyen automaticamente las
  comunas sin oferta (`NaN`), evitando division por cero y reflejando
  limites estructurales de acceso.
