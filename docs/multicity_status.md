# Checklist multiciudad de la cohorte

Tablero de avance por ciudad, priorizado por dónde vive realmente la cohorte
según la entrega de residencia de participantes
(`data/raw/zipcodes/2026-07/`, ver su README). La entrega es **city-level**
(sin códigos postales), lo que acota el **linkage con la cohorte** al
municipio/comuna/localidad oficial de cada país.

**Filosofía de resolución**: la resolución de la cohorte NO baja la resolución
de los productos del exposoma. Cada capa se genera y conserva a la máxima
resolución que su fuente/método permita (rásters nativos, grilla fina, patrón
`caba_native`); la agregación a unidades administrativas es un producto
derivado que se calcula recién al cruzar con la cohorte u otro outcome de
menor resolución. Si mañana llega un outcome más fino (zipcode real,
coordenadas), los productos ya lo soportan sin recomputar. Auditoría
capa-por-capa (fuente, resolución nativa, escala usada, producto fino
existente o hueco) en `docs/resolution_manifest.md`.

Números regenerables con
`python3 scripts/summarize_participant_locations.py --write`
(total cohorte: 3.874 participantes; corte 2026-07).
Estados reutilizan el vocabulario de `docs/exposome_status.md`
(`not_started`, `partial`, `checked`, `blocked`).

## Metros priorizados (n ≥ 50 → 79,8 % de la cohorte)

| # | Metro | País | n | % | Location | Polígonos ref. | Study | Capas corridas | Webapp | Estado | Siguiente acción |
|---|---|---|---:|---:|---|---|---|---|---|---|---|
| 1 | Lima Metropolitana | PE | 645 | 16,6 | `pe/lima` | ✓ 50 distritos (43 Lima + 7 Callao) | `lima_distritos` visible + `lima_native` oculto | 14/14 + master/release; 20/83 productos anuales locales | ✓ 50 perfiles | partial | Calor y viento ya usan ERA5-Land. Reprocesar ALAN a 463,83 m y completar PM2.5/NO₂/ALAN/viento nativos; luego republicar |
| 2 | Bogotá D.C. | CO | 587 | 15,2 | `co/bogota` | ✓ 20 localidades (SDP/IDECA vía espejo CAR) | `bogota_localidades` **publicada** (tier `preview`) + `bogota_native` oculto | 14/14 + master/release; 8/9 productos anuales locales (`greenspace_multisource`/`green`: excepción documentada Los Mártires/2019, ver [ADR 0008](adr/0008-excepciones-temporales-documentadas.md)) | ✓ 20 perfiles | partial | Publicada en el catálogo del webapp: `spatial-audit --strict` y `resolution-coverage` (12/13 indicadores requeridos, sólo `green` falta) pasan limpio, sin issues de proveniencia agregada. El único pendiente es estructural, no de esta ciudad: `green` permanece en `preview` porque su hueco de fuente es permanente (no hay reprocesamiento que lo cierre); graduar a `production` requeriría relajar esa exigencia, no volver a correr datos |
| 3 | Valle de Aburrá (Medellín) | CO | 508 | 13,1 | `co/valle_aburra`, `co/medellin` | ✓ 10 municipios (AMVA) + ✓ 21 comunas/corregimientos (DAP) | `valle_aburra_municipios` + `medellin_comunas` visibles; acompañantes nativos ocultos | 14/14 en ambos + masters/releases; 20/83 productos anuales locales por estudio | ✓ Medellín (21 perfiles); Valle pendiente | partial | Medellín agregado ya está limpio y publicado; completar su detalle nativo. En Valle reprocesar ALAN/calor/viento, correr detalle nativo y publicar 10 perfiles |
| 4 | Santiago (RM) | CL | 461 | 11,9 | `cl/santiago` | ✓ CUT 52 comunas | `santiago_communes` + `santiago_native` oculto | 25/25; auditoría espacial v3 aprobada | ✓ | partial | La app oculta correctamente ALAN/viento nativos históricos no canónicos; reprocesar ALAN/calor/viento agregado y ALAN/viento nativo antes de restaurar ese detalle |
| 5 | Valle de México (ZMVM) | MX | 351 | 9,1 | `mx/cdmx` | ✓ 16 alcaldías | `cdmx_alcaldias` **publicada** (tier `preview`) + `cdmx_native` oculto | 14/14 agregado + master/release; 83/83 anuales completos (2026-08-02); 11 COG de detalle reconstruidos y 16 perfiles regenerados | ✓ 16 perfiles | partial | Publicada en el catálogo del webapp: `verify` (108+46 assets), `spatial-audit --strict` (0 issues) y `resolution-coverage` (12/13 indicadores requeridos) pasan limpio. El único pendiente es estructural, no de esta ciudad: `green` (`greenspace_multisource`) permanece en `preview` por el mismo hueco permanente de Dynamic World que Bogotá ([ADR 0008](adr/0008-excepciones-temporales-documentadas.md)) — graduar a `production` requeriría relajar esa exigencia, no volver a correr datos |
| 6 | San Juan (Gran San Juan + prov.) | AR | 195 | 5,0 | `ar/san_juan` | ✓ 19 departamentos (IGN, `in1 LIKE '70%'`) | `san_juan_departamentos` config-completo, sin correr | 0/14 | — | not_started | Decisión resuelta: provincia completa a nivel departamento, no solo Gran San Juan (los 195 participantes tienen `City`=departamento en el CSV de cohorte, spanning ~13 de 19 deptos, no solo los 6 del metro). `exposome audit` y `exposome run --dry-run` pasan limpio (19/19 unidades, 14/14 capas ready). Falta correr `exposome run --study san_juan_departamentos --resume` (GEE/Open-Meteo/OSM, humano). Las 4 capas AR-only (`community_safety`/`community_violence`/`suicide_mortality`/`road_traffic_mortality`) quedan afuera: están hardcodeadas en código a `buenos_aires_amba`, no es config — follow-up aparte |
| 7 | São Paulo (município) | BR | 143 | 3,7 | `br/sao_paulo` | ✓ 96 distritos (GeoSampa WFS `distrito_municipal`) | `sao_paulo_distritos` visible + `sao_paulo_native` oculto | 14/14 + master/release; 20/83 productos anuales locales | — | partial | Reprocesar sólo viento agregado con ERA5-Land, correr PM2.5/NO₂/ALAN/viento nativos, reconstruir, exportar 96 perfiles y publicar. Scope: município, no RMSP |
| 8 | Buenos Aires (CABA+AMBA) | AR | 75 | 1,9 | `ar/buenos_aires`, `ar/buenos_aires_amba` | ✓ 15 comunas + 55 unidades AMBA | `buenos_aires_amba` (+ estudios ocultos) | 20/21 AMBA; se añadió `greenspace_multisource` para uniformar las 14 portables; detalle nativo PM2.5/NO₂/ALAN/verde/viento verificado | ✓ | partial | Correr la nueva capa verde agregada y su serie; reprocesar ALAN/calor/viento agregado para alinear procedencia; luego republicar y exigir gate `production` |
| 9 | Santa Marta | CO | 74 | 1,9 | — | — | — | 0 | — | not_started | **Corrección**: la nota anterior ("misma fuente DANE") era incorrecta — DANE solo llega a nivel municipio (mismo hallazgo que bloqueó IDECA para Bogotá), no a comunas. Confirmadas 9 comunas urbanas (María Eugenia-Pando, Central, Pescaito, Polideportivo-El Jardín, Santafé-Bastidas, Mamatoco-11 de Noviembre, Gaira-Rodadero, Pozos Colorados-Don Jaca, Parque-Bureche, agrupadas en 3 localidades) + 4 corregimientos rurales (fuera de alcance). **Bloqueado**: no se encontró fuente descargable de los límites de comuna tras revisar Alcaldía (403), IGAC/ICDE, ArcGIS Hub, HDX (COD-AB solo a municipio) y Catastro Multipropósito Santa Marta (sin geoportal público visible). Siguiente acción: contactar directamente `catastromultiproposito@santamarta.gov.co` o revisar el anexo cartográfico del POT (`01_EXPEDIENTE_STM.pdf`) |
| 10 | Belo Horizonte (RMBH aprox.) | BR | 52 | 1,3 | — | — | — | 0 | — | not_started | Municípios RMBH (IBGE); evaluar junto a RMSP |

## Cola (n < 50)

Arequipa (31), Cartagena (31), Pasto (30), Barranquilla (29), Cali (25),
Chiclayo (15), Cuernavaca ZM (14), Talca (6). Umbral de inclusión pendiente de
decisión; con n≈30 la variación intra-ciudad es poco estimable, probablemente
solo perfil de exposición puntual (estilo `caba_native`) y no estudio agregado.

Colas residuales por país (no asignables a un metro): CO 391 (10,1 %; 144
strings de ciudad distintos — la cola larga colombiana es el mayor hueco de
cobertura), PE 92, CL 51, MX 35, AR 10, BR 2. Fuera de LatAm o sin país: ~25
participantes (EEUU 10, España 2, otros 1 c/u, 4 sin país).

## Qué puede correrse en cada ciudad nueva

Según `config/layers.yaml` (`category` y `pilot_layers`):

- **Portables a cualquier metro LatAm (14 capas comunes)**: `air_quality_pm25`
  (ACAG), `air_quality_satellite` (Sentinel-5P/MODIS/ERA5), `alan` (VIIRS),
  `greenspace_coverage` y `greenspace_multisource`
  (Dynamic World/GEE), `precipitation` (+`precipitation_spi`, CHIRPS),
  `climate_heat` (ERA5-Land), `wind`, `wildfire` (MODIS/FIRMS), y las
  OSM: `greenspace_access`, `walkability`, `social_infrastructure`,
  `food_environment`, `healthcare`. Caveat OSM: cobertura variable por país
  (el gap de `food_environment` ya documentado en Chile aplica con más razón
  fuera).
- **Solo Chile** (`category: CL`): `socioeconomic`/NSE, `pobreza_sae`,
  `food_insecurity` (CASEN), `heavy_metals` (RETC), `noise` (MMA),
  comparadores DEIS (`neuro_mortality`, `neuro_hospitalizations`).
- **Solo Argentina** (`countries: [AR]`): `community_safety`,
  `community_violence`, `suicide_mortality`, `road_traffic_mortality`.
  Equivalentes oficiales para CO/PE/MX/BR: por investigar al abrir cada país.

## Checklist por ciudad (plantilla)

Para graduar una ciudad de `not_started` a `checked`:

- [ ] `config/locations/<iso2>/<ciudad>.yaml` (bbox, timezone, CRS)
- [ ] Polígonos de referencia con fuente y licencia documentadas
      (`data/reference/<iso2>/<ciudad>/<estudio>/spatial_units.geojson`)
- [ ] `config/studies/<estudio>.yaml` (unidades esperadas, periodo, capas)
- [ ] Capas portables corridas (`exposome run --study <id>`)
- [ ] **Estudio native compañero declarado y corrido.** No basta con «conservar
      productos finos»: las series anuales *no* cuentan para esto. Son cinco
      pasos verificables, y saltárselos publica la ciudad pintando unidades
      administrativas planas:
      - [ ] `detail: {native_study: <ciudad>_native}` en el YAML del agregado
      - [ ] AOI: `python3 scripts/migrations/build_native_aoi.py --study <id>
            --native-study <ciudad>_native` (disuelve las unidades ya validadas;
            comprobar el área contra la superficie oficial)
      - [ ] `config/studies/<ciudad>_native.yaml` calcado de
            `pais_vasco_native.yaml` (7 capas ráster, `hidden: true`)
      - [ ] `exposome run --study <ciudad>_native --resume`
      - [ ] `exposome detail --study <id> --resume` → 11 COG en `detail/`
- [ ] `publication_tier: production` en el manifest publicado. Ojo: `production`
      con `required_indicators: 0` **no** prueba cobertura — significa que no
      había capas ráster publicadas que exigir (ADR 0011).
- [ ] Master + `release_manifest.json` (`exposome verify --study <id>`)
- [ ] Export webapp (`scripts/export_webapp_cities.py` y afines)
- [ ] Revisión metodológica por capa (tabla estilo `exposome_status`)

La corrida común se prepara e inspecciona con:

```bash
.venv/bin/python scripts/run_multicity_overnight.py --city <id> --dry-run
```

El comando humano, su presupuesto horario, logs, reanudación y gates se
documentan en
[`docs/knowledge/runbooks/recoleccion-overnight.md`](knowledge/runbooks/recoleccion-overnight.md).

## Pendientes transversales

- [ ] Crosswalk oficial ciudad→código (DANE, UBIGEO, INEGI, IBGE, IGN-AR)
      para reemplazar la agrupación aproximada de
      `scripts/summarize_participant_locations.py`.
- [ ] Decidir umbral de inclusión de metros (propuesta: n ≥ 50).
- [ ] Decidir estudio Gran San Juan (hallazgo clave de la entrega 2026-07).
- [ ] Pedir al consorcio una re-entrega con ID de participante + municipio
      codificado (o zipcode real) si el linkage individual llega a necesitarse.
