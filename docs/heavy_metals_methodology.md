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

## Relevancia para salud cerebral (BrainLat)

La exposición crónica a metales pesados neurotóxicos tiene efectos bien
caracterizados sobre la estructura y función cerebral:

- **Pb y atrofia hipocampal**: concentraciones óseas de Pb en adultos
  mayores se asocian inversamente con volumen hipocampal y desempeño en
  pruebas de memoria ejecutiva (Reuben et al., *Lancet Public Health
  2020*; el efecto es log-lineal, lo que justifica el uso de `hm_pb_log`
  en los modelos).
- **As y deterioro cognitivo**: estudios poblacionales en Chile (Arica,
  Antofagasta) han mostrado asociación entre As en agua y reducciones
  en CI y funciones ejecutivas en adultos mayores.
- **Vías de exposición**: las emisiones RETC son **inhalación** (vía
  respiratoria directa a SNC vía mucosa olfatoria) y deposición en
  suelo/vegetación (vía ingestión incidental). Esta capa captura la
  vía inhalatoria industrial; para exposición dietética del suelo se
  requieren datos adicionales.
- **Sinergia con PM2.5**: el Pb y As particulado (PM₂.₅ industrial)
  entran al organismo junto al resto de la contaminación de fondo, así
  que el modelo combinado (PM2.5 + RETC) es más informativo que cada
  capa por separado.

## Período cubierto

- **8 años crónicos: 2015–2022** (alineado con PM2.5, ALAN, climate).
- Se promedian los 8 años de declaración por comuna para obtener
  exposición crónica (ventana relevante para outcomes neurodegenerativos
  de lenta evolución).
- En promedio, **5,253 establecimientos únicos** declaran emisiones de
  metales pesados en la RM en este período (5253 / 52 ≈ 101 fuentes
  promedio por comuna).

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
- **Distribución por comuna de fuentes industriales** (n_sources):
  - 45/52 comunas tienen al menos 1 fuente que declara Pb.
  - 47/52 comunas declaran As (>0 kg/yr).
  - 48/52 declaran Hg (mercurio).
  - 0/52 declaran Mn o Cd → ver sentinel abajo.
  - Quilicura (229 fuentes) y Lampa (114) son las comunas con mayor
    número de establecimientos después de Tiltil (24 fuentes pero
    muy intensivas).
- **Pb vs PM2.5:** Spearman ρ ≈ −0.15 (p ≈ 0.30) → **no correlacionan**.
  Esto confirma que las fuentes puntuales industriales y la contaminación
  de fondo de combustión son **exposiciones distintas**. La capa RETC aporta
  información independiente al master.
- **Pb vs NSE:** ρ ≈ 0.22 (p ≈ 0.11) → gradiente socioeconómico débil.
  Tiltil es semi-rural y no es la zona más pobre del RM, lo que explica
  el patrón distinto al de PM2.5.

## Sentinel: Mn y Cd = 0 en todas las comunas

**Hallazgo estructural, no dato faltante.** El RETC no registra **ninguna**
emisión de Mn o Cd en las 52 comunas de la RM:

- Las fuentes industriales de **Mn** (siderurgia, ferroaleaciones) se
  concentran en Atacama y la zona de Ventanas (Quintero-Puchuncaví).
- Las fuentes de **Cd** (fundición de zinc) están en Atacama, Coquimbo y
  el cordón industrial de Ventanas.

Por lo tanto `hm_mn_kg` y `hm_cd_kg` son **0.0 legítimos**, no NaN. Esto
tiene tres consecuencias explícitas:

1. **El índice compuesto `hm_index`** (z-score ponderado Pb+Mn+As+Cd)
   reduce su peso efectivo: solo Pb (0.35) y As (0.20) tienen señal
   real. La media ≈ 0 porque los términos Mn y Cd aportan
   `-w * mean/std` y ambas medias son 0 → aporte exactamente 0.
2. **Los modelos de correlación con neuro_outcomes** deben usar
   `hm_pb_log` o `hm_pb_kg` directamente, no `hm_index` (que pierde
   contraste cuando 2 de 4 componentes son cero).
3. **Para incluir Mn/Cd** en el análisis, se debe ampliar la zona de
   estudio a otras regiones mineras del norte de Chile, lo cual escapa
   al alcance de este exposome urbano de Santiago.

Este sentinel está testeado en `tests/test_heavy_metals.py`
(`test_mn_cd_sentinel_zero`) y en `test_pb_log_transform` que verifica
que la transformación log1p produce 0.0 limpio para comunas sin Pb
declarado.

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
- **Sin año 2023–2024:** los datos de 2023 y 2024 existen en RETC pero no
  están agregados aún; pueden extenderse con `--end-year 2024` una vez
  verificada la calidad de declaración post-2022.
- **Sin componente temporal intra-anual:** el RETC no entrega resolución
  mensual/semanal, solo anual. Para variabilidad estacional habría que
  complementar con datos de suelo o deposición atmosférica.

## Reproducibilidad

- **Caché:** archivos anuales en `cache/retc_efp_YYYY.{csv,xlsx}` (~500 MB
  total para 2015–2022). Si están presentes, el script corre offline
  sin necesidad de red.
- **Tiempo de cómputo:** ~2 min desde caché en MacBook Pro M2; ~5 min si
  hay que re-descargar.
- **Idempotencia:** re-ejecutar `python scripts/run_heavy_metals.py` con
  la caché completa produce un CSV **byte-idéntico** al de la corrida
  anterior (verificado con md5: `613b4b…d3bc`). La metadata solo cambia
  el campo `created_utc`.
- **Test de regresión:** `tests/test_heavy_metals.py` (13 tests) cubre
  schema, 52 comunas, sentinel Mn/Cd, transformación log, outliers
  (Tiltil), y propagación al master. La suite completa corre en <5 s.
- **Re-build completo (test opcional):** con la variable de entorno
  `RUN_HEAVY_METALS_BUILD_TEST=1` se activa un test de round-trip
  adicional que re-construye la capa desde caché (~3 min, no
  habilitado por defecto por costo).

## Referencias

- Livingston G. et al. *Dementia prevention, intervention, and care: 2024
  report of the Lancet standing Commission.* Lancet, 2024.
- Lanphear B.P. et al. *Low-level lead exposure and mortality in US adults.*
  Lancet Public Health, 2018.
- MMA Chile. *Informe Consolidado de Emisiones y Transferencias de
  Contaminantes del RETC 2014–2023.* Santiago, 2024.
