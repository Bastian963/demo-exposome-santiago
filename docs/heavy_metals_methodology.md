# Metales pesados industriales — metodología (RETC vía MMA)

## Por qué esta capa

El pilar de **toxinas industriales** estaba ausente del exposome. Las capas
existentes capturan contaminación de **fondo urbano** (PM2.5 ACAG ~1 km,
NO₂ Sentinel-5P ~3.5 km), pero no **emisiones puntuales industriales**,
que representan un perfil de riesgo neurológico distinto:

- **Plomo (Pb):** neurotóxico #1; reduce volumen hipocampal y acelera
  deterioro cognitivo de manera dosis-respuesta (Livingston et al., *Lancet
  Commission 2024*; Lanphear et al., *Lancet Public Health 2018*).
- **Arsénico (As):** neuropatía periférica, estrés oxidativo en SNC,
  asociación emergente con demencia.
- **Mercurio (Hg):** neurotóxico clásico (Minamata); fuentes escasas en RM.
- **Manganeso (Mn) y Cadmio (Cd):** ausentes del RETC RM — sus fuentes
  industriales principales están en otras regiones (Atacama, Maule).

Construcción del caso para correlación con BrainLat: si el modelo de carga
acumulada (PM2.5 + Pb/As industrial + ruido + calor) explica más varianza en
el outcome neurológico que PM2.5 solo, esta capa es necesaria.

## Fuente

- **RETC** — *Registro de Emisiones y Transferencias de Contaminantes*,
  Ministerio del Medio Ambiente de Chile.
- Sub-registro: **Emisiones al aire de fuentes puntuales** (fuentes
  industriales con declaración obligatoria).
- Portal: `datosretc.mma.gob.cl`, dataset ID
  `2733b0f0-428a-4594-afeb-17780c8d47c1`.
- Cobertura: 2005–2024; licencia CC-BY.
- **Sin API key.** Descarga directa de CSV/XLSX (2015–2019: CSV semicolón
  latin-1; 2019–2020: CSV semicolón utf-8-sig; 2021–2022: XLSX).

## Procesamiento

1. **Descarga y caché.** Años 2015–2022, uno por uno. Los archivos
   se guardan en `cache/retc_efp_YYYY.{csv,xlsx}`.
2. **Filtro región.** Se mantienen solo las filas con `region` = "Metropolitana".
3. **Clasificación de metales.** El campo `contaminante` (o `contaminantes`
   según el año) se compara con palabras clave en español: `plomo`, `arsénico`,
   `cadmio`, `manganeso`, `mercurio`.
4. **Conversión de unidades.** Las columnas `emision_primario`,
   `emision_secundario` y `emision_materia_prima` se suman y convierten a
   kg/año según el campo `unidad` (ton/año → ×1000; kg/año → ×1).
5. **Geocodificación.** `latitud`/`longitud` en formato español (coma decimal)
   → float; puntos fuera de cualquier polígono comunal → asignados a la comuna
   más cercana (≤50 casos, generalmente bordes).
6. **Agregación comunal.** `sjoin` punto-en-polígono + media anual de la suma
   de emisiones por establecimiento × año. Resultado: una fila por comuna.
7. **Columnas derivadas:**
   - `hm_pb_log = log1p(hm_pb_kg)` — escala log para modelos de regresión
     (la relación Pb-cognición es log-lineal).
   - `hm_as_log = log1p(hm_as_kg)` — ídem para As.
   - `hm_index` — z-score ponderado de Pb(0.35) + Mn(0.30) + As(0.20) +
     Cd(0.10); para RM, Mn=Cd=0, así que el índice refleja principalmente Pb.

## Salidas (`data/processed/santiago_heavy_metals_retc_2015_2022.*`)

| Columna | Significado |
|---|---|
| `hm_pb_kg` | Media anual de emisiones de Pb al aire [kg/yr] |
| `hm_mn_kg` | Media anual de emisiones de Mn al aire [kg/yr] (=0 en RM) |
| `hm_as_kg` | Media anual de emisiones de As al aire [kg/yr] |
| `hm_cd_kg` | Media anual de emisiones de Cd al aire [kg/yr] (=0 en RM) |
| `hm_hg_kg` | Media anual de emisiones de Hg al aire [kg/yr] |
| `hm_pb_log` | log1p(hm_pb_kg) — para regresión lineal |
| `hm_as_log` | log1p(hm_as_kg) — para regresión lineal |
| `n_sources` | N° establecimientos únicos con declaraciones de metales pesados |
| `hm_index` | Índice compuesto (z-score ponderado) |

## Hallazgos de validez de constructo

- **Tiltil como outlier:** la comuna de Tiltil concentra ~10,629 kg/yr de Pb
  (~99.6 % del total RM). Esto corresponde a instalaciones industriales
  conocidas en esa zona (cementera, reciclaje de baterías). Es un hallazgo
  real, no un error.
- **Pb vs PM2.5:** Spearman ρ ≈ −0.15 (p ≈ 0.30) → **no correlacionan**.
  Esto confirma que las fuentes puntuales industriales y la contaminación
  de fondo de combustión son **exposiciones distintas**. La capa RETC aporta
  información independiente al master.
- **Pb vs NSE:** ρ ≈ 0.22 (p ≈ 0.11) → gradiente socioeconómico débil.
  Tiltil es semi-rural y no es la zona más pobre del RM, lo que explica
  el patrón distinto al de PM2.5.

## Limitaciones

- **Declaración voluntaria / umbral de reporte:** el RETC exige declaración
  solo a establecimientos sobre umbrales de capacidad/emisión. Fuentes
  menores (talleres, microempresas) no aparecen.
- **Solo fuentes puntuales:** no captura exposición difusa (pintura con Pb
  en viviendas antiguas, suelo contaminado históricamente).
- **Tiltil como driver:** el índice compuesto está dominado por Tiltil.
  Usar `hm_pb_log` o analizar por cuartiles mitiga el efecto outlier.
- **Mn y Cd = 0 en RM:** legítimo, no faltante. Las regiones mineras y de
  fundición (Atacama, Coquimbo) serían el escenario correcto para esos metales.

## Referencias

- Livingston G. et al. *Dementia prevention, intervention, and care: 2024
  report of the Lancet standing Commission.* Lancet, 2024.
- Lanphear B.P. et al. *Low-level lead exposure and mortality in US adults.*
  Lancet Public Health, 2018.
- MMA Chile. *Informe Consolidado de Emisiones y Transferencias de
  Contaminantes del RETC 2014–2023.* Santiago, 2024.
