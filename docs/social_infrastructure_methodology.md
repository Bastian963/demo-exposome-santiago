# Infraestructura social-cognitiva — metodología (OpenStreetMap)

## Por qué esta capa

El **aislamiento social** es uno de los 14 factores modificables de riesgo
de demencia según la *Lancet Commission 2024* (Livingston et al.). Chile
no publica indicadores comunales directos de aislamiento social o
composición de hogares (ver `docs/social_isolation_methodology.md` para
el análisis de la brecha).

Esta capa es un **proxy ecológico** de oportunidad de participación
social, estimulación cognitiva y actividad comunitaria, construido a
partir de la densidad y accesibilidad de infraestructura
social-cognitiva mapeada en OpenStreetMap. **No mide aislamiento
social, soledad, ni uso individual de servicios** — mide oferta
espacial de lugares que facilitan interacción social, cognitiva y
física.

## Lo que captura la capa

Seis categorías de POIs (puntos de interés) OpenStreetMap, agregadas
por comuna:

| Categoría | OSM tags típicos | Relevancia brain health |
|---|---|---|
| **library** | `amenity=library` | Estimulación cognitiva, lectura, aprendizaje permanente |
| **cultural** | `amenity=theatre`/`arts_centre`/`cinema`; `tourism=museum`/`gallery` | Participación cultural, enriquecimiento cognitivo |
| **community** | `amenity=community_centre`; `community_centre=*` | Reunión vecinal, capital social, sentido de pertenencia |
| **senior** | `amenity=social_facility` con `social_facility:for=senior` | Espacios específicos para adultos mayores |
| **sports** | `leisure=sports_centre`/`stadium`/`fitness_centre` (curated) | Actividad física → BDNF, vascular health |
| **public_space** | `leisure=park`/`garden`/`playground`/`recreation_ground`; `place=square` | Encuentro incidental, recreación al aire libre |

A diferencia de la capa `greenspace_access` (que se enfoca en áreas
verdes urbanas), esta capa incluye equipamiento cívico-cultural,
bibliotecas, centros comunitarios y centros para adultos mayores.

## Fuente y procesamiento

1. **Descarga OSM** vía Overpass directo (sin API key), por cada grupo
   de tags definido en `config/cities/santiago.yaml →
   social_infrastructure.osm_tag_groups`. Reusa la cache de
   `greenspace_osm.geojson` para `public_space`. Cache local en
   `cache/santiago_social_infrastructure_osm_*.geojson`.
2. **Clasificación**: cada feature se asigna a 0+ categorías según
   reglas tag-value declaradas en config. Features sin categoría se
   descartan.
3. **Curación (clave)**: el inventario curado excluye features con
   `access=private|customers|no|permit` (clubes privados, canchas con
   pago, etc.) y restringe las categorías deportivas a las que
   ofrecen acceso público real (`sports_centre`, `stadium`,
   `fitness_centre` — excluye `pitch`, `swimming_pool` que típicamente
   son privados o de pago). Para `public_space` se usan reglas
   conservadoras (recreation_ground, park, garden, dog_park,
   playground, square).
4. **Geometría → puntos representativos** en `EPSG:32719` (UTM 19S).
5. **Deduplicación por cluster** (radio 50 m): un polígono OSM con
   múltiples POIs en la misma manzana → un solo punto representativo.
6. **Conteo por comuna** (spatial join).
7. **Distancias** sobre grilla 1 km × 1 km (idéntica al patrón
   `healthcare_access` y `public_transport`): distancia euclidiana al
   POI curado más cercano, con cap a 99,999 m para comunas sin
   cobertura.
8. **Coverage 500 m / 1000 m**: fracción de la grilla comunal a
   distancia ≤ umbral.
9. **Tres sub-índices** (z-score → rescale 0-100):
   - **civic_index**: media de `z(log1p(social_civic_points_per_10k))`
     y `z(social_civic_diversity)`.
   - **access_index**: media de `z(social_coverage_1000m)` y
     `-z(social_mean_nearest_m)` (más cerca = mejor).
   - **recreation_index**: `z(log1p(winsorized p90 social_recreation_points_per_10k))`.
10. **social_index = 0.45 × civic + 0.35 × access + 0.20 × recreation**.

## Período cubierto

- **Snapshot OSM único** (~Junio 2026). OSM es un contrib-edit
  colaborativo; el "año" de la capa es la fecha mediana de las
  ediciones OSM incorporadas, no un período crónico.
- A diferencia de capas satelitales (PM2.5, ALAN, NDVI), esta capa
  **no es una exposición crónica multi-año**: es una instantánea de
  oferta espacial. Para análisis de cohorte longitudinal se
  recomienda combinar con variables temporales (apertura/cierre de
  equipamientos críticos).

## Salidas (`data/processed/santiago_social_infrastructure.*`)

| Columna | Significado |
|---|---|
| `social_n_total` | POIs curados (post-acceso) por comuna |
| `social_n_total_raw` | POIs crudos (incluye privados y pagos) |
| `social_n_{library,cultural,community,senior,sports,public_space}` | Conteos curados por categoría |
| `social_n_sports_raw`, `social_n_public_space_raw` | Conteos crudos (referencia) |
| `social_private_or_customer_excluded_n` | POIs excluidos por acceso restringido |
| `social_category_diversity` | # categorías no-cero (0-6) |
| `social_civic_diversity` | # categorías cívicas no-cero (library/cultural/community/senior, 0-4) |
| `social_density_per_km2` | `social_n_total / área_comuna` |
| `social_points_per_10k` | POIs curados por 10k habitantes |
| `social_civic_points_per_10k` | POIs cívicos por 10k habitantes |
| `social_recreation_points_per_10k` | POIs recreación por 10k habitantes |
| `social_mean_nearest_m` | Distancia media al POI más cercano (grilla 1 km) |
| `social_median_nearest_m` | Distancia mediana |
| `social_p90_nearest_m` | Percentil 90 de distancia |
| `social_coverage_500m` | Fracción de la grilla a ≤500 m |
| `social_coverage_1000m` | Fracción de la grilla a ≤1 km |
| `social_n_access_grid` | # puntos de la grilla 1 km en la comuna |
| `social_civic_index` | 0-100, sub-índ. cívico |
| `social_access_index` | 0-100, sub-índ. accesibilidad |
| `social_recreation_index` | 0-100, sub-índ. recreación |
| `social_index` | 0-100, índice compuesto (0.45/0.35/0.20) |

## Hallazgos de validez de constructo

- **38,212 features OSM raw → 8,398 POIs curados**: la curación
  reduce ~78 % de los puntos, principalmente por acceso restringido y
  duplicación cluster.
- **Top 5 (más acceso)**: Providencia, Vitacura, Santiago, Macul, La
  Reina — todas comunas centrales con mapeo OSM exhaustivo, alto NSE
  y/o inversión municipal.
- **Bottom 5 (menos acceso)**: San Pedro, María Pinto, San José de
  Maipo, Melipilla, Alhué — todas rurales/peri-urbanas, baja densidad
  de mapeo OSM y oferta real de servicios limitada.
- **Sesgo de mapeo**: OSM tiene **cobertura heterogénea**: comunas
  centrales con mapeo ciudadano denso vs. rurales con gaps
  sistemáticos. La capa debe interpretarse como **oferta mapatada**, no
  oferta total.
- **Asimetría raw vs curado**: la razón `social_n_total_raw /
  social_n_total` promedia 6.5×, pero llega a >50× en comunas
  turísticas (ej. centro de Santiago) con muchos POIs privados.

## Limitaciones

- **No es aislamiento social medido**: es un proxy de oportunidad
  espacial. Estudios individuales (CASEN, ENUT, cohortes
  BrainLat) deben suplementar para estimar el constructo real.
- **Sesgo de mapeo OSM**: las comunas con más voluntarios OSM tienen
  conteos inflados. Validación cruzada con catastro municipal
  pendiente.
- **Sin componente temporal**: snapshot único, no hay serie de
  apertura/cierre.
- **Sin acceso real**: la curación es por tag `access`, no por
  verificación presencial. Algunos lugares "públicos" pueden estar
  cerrados en la práctica.
- **Sin aforo ni calidad**: la capa no distingue entre un centro
  comunitario grande y una sede vecinal pequeña.
- **Cobertura heterogénea**: 4 comunas tienen < 10 POIs curados,
  lo que genera varianza alta en los z-scores.

## Relevancia para salud cerebral (BrainLat)

La evidencia epidemiológica respalda la asociación entre oferta
espacial de infraestructura social y outcomes cognitivos:

- **Reserva cognitiva**: frecuencia de uso de bibliotecas, centros
  culturales y espacios comunitarios se asocia con menor riesgo de
  demencia incidente (Stern, *Lancet Neurology* 2012).
- **Cohorte BrainLat**: la RM tiene alta heterogeneidad de oferta
  social-cognitiva (Providencia 93.9 vs San Pedro 25.6 en el
  `social_index`). La capa permite testar si esta heterogeneidad
  media la asociación entre NSE y cognición, independientemente de
  PM2.5, ALAN y green space.
- **Modificación de la carga térmica**: la presencia de centros
  comunitarios con aire acondicionado modera el efecto del calor
  extremo en adultos mayores (Mora et al., *Epidemiology* 2017).
- **Walkability + social + dementia**: la combinación de
  `walkability`, `social_infrastructure` y `greenspace_access`
  conforma el eje "entorno construido amigable para認知症" en el
  marco de la WHO ICF.

## Reproducibilidad

- **Cache**: `cache/santiago_social_infrastructure_osm_*.geojson`
  (~50-100 MB). Si están presentes, el script corre offline.
- **Tiempo de cómputo**: ~30-60 s desde caché. ~5-10 min si hay
  re-descargar desde Overpass.
- **Idempotencia**: re-ejecutar
  `python scripts/run_social_infrastructure.py` produce un CSV
  **byte-idéntico** al de la corrida anterior (md5
  `4f60cd…8a99`). Solo `created_utc` cambia en la metadata.
- **Test de regresión**: `tests/test_social_infrastructure.py`
  (20 tests) cubre schema, índice compuesto, contraste
  urbano/rural, jerarquía curated ≤ raw, y validaciones de cobertura
  y distancia.
- **Validación de coherencia interna**: el output exige 52 comunas,
  sin NaN, sin duplicados de `name`, `social_index` en [0, 100].

## Key data anchors (52 comunas, snapshot 2026)

- **Más alto `social_index`**: Providencia (93.9), Vitacura (88.0),
  Santiago (84.9), Macul (83.7), La Reina (81.9).
- **Más bajo `social_index`**: San Pedro (25.6), María Pinto (43.2),
  San José de Maipo (46.9), Melipilla (47.1), Alhué (48.9).
- **Mayor `social_mean_nearest_m` (más lejos del POI más cercano)**:
  Alhué (9,600 m), Til-Til (8,800 m), San Pedro (7,500 m). Estas
  comunas tienen oferta efectivamente cero dentro de un radio
  razonable.
- **Mayor `social_coverage_1000m` (fracción de grilla cubierta)**:
  Santiago (1.0), Providencia (1.0), Ñuñoa (1.0), Independencia
  (0.99), Recoleta (0.99). Centro y pericentro prácticamente
  saturados.
- **Contraste NSE vs social_index**: Spearman ρ ≈ +0.56 (p ≈ 1.6e-5);
  la correlación es robusta y captura el patrón "NSE alto → más
  oferta mapeada" que también refleja el sesgo de mapeo OSM
  (voluntarios más activos en zonas de mayor NSE).
