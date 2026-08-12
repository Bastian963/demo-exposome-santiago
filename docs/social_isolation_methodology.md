# Aislamiento social — factor no incluido (razón documentada)

## Factor y relevancia

El **aislamiento social** está listado como uno de los 14 factores modificables
de riesgo de demencia por la Lancet Commission 2024 (Livingston et al., *Lancet*
2024). La evidencia incluye:

- Riesgo relativo: 1.60 (IC 95%: 1.28–2.00) para demencia en personas
  socialmente aisladas vs. conectadas (Holt-Lunstad et al., *PLOS Medicine* 2015).
- Mecanismo propuesto: falta de estimulación cognitiva y reducción de reserva
  cerebral; inflamación crónica por estrés social sostenido.
- Indicadores epidemiológicos estándar: % hogares unipersonales (`pct_hogares_unipersonales`)
  y % adultos ≥65 viviendo solos (`pct_65plus_solos`) por zona geográfica.

## Por qué no está en el exposome

### Fuente intentada: Censo 2017 manzana (INE)

El repositorio ya descarga y procesa `Censo2017_Manzanas.csv` (RAR del INE)
para la capa demográfica (`src/exposome/demography.py`). Las columnas disponibles
a nivel de manzana son:

```
REGION, COMUNA, PERSONAS, HOMBRES, MUJERES,
EDAD_0A5, EDAD_6A14, EDAD_15A64, EDAD_65YMAS,
CANT_HOG,  ← total de hogares (sin desglose por tamaño)
VIV_PART, VIV_COL, TOTAL_VIV, P01_*, P03A/B/C_*, P05_*
```

El campo `CANT_HOG` es el **total** de hogares en la manzana; no hay columna
`HOG_1PER` (hogares de 1 persona). El desglose por número de integrantes del
hogar **no está en el microdato manzana** — está en el cuestionario de hogar
del Censo 2017 (microdato individual, no publicado en el RAR utilizado).

### Alternativa evaluada: composite de variables existentes

Una variable compuesta `z(pct_pop_65_plus) + z(-hacinamiento_phh)` combina
dos variables ya presentes en el master y añade una etiqueta pero **no añade
información nueva** al espacio de predictores. Sería colineal con sus propios
insumos en modelos de regresión. Se descartó por este motivo.

### Alternativa evaluada: SINIM

El SINIM (Sistema Nacional de Información Municipal) cuenta con variables de
"Centros del adulto mayor" (variable 719) y "Pensiones Básicas Solidarias de
Vejez" (variable 3899), pero ninguna mide directamente aislamiento social o
composición de hogares. Se descartaron como proxy insuficiente.

## Qué se necesitaría para incluirlo

### Opción 1 — CASEN 2022 microdata (fuente correcta)

El Ministerio de Desarrollo Social publica el microdato de la CASEN 2022
como archivo `.dta` (Stata). Desde éste se puede calcular:

```python
# Pseudocódigo
df = pd.read_stata("casen_2022.dta")
unipersonales = df.groupby(["cut_comuna", "id_hogar"])["numper"].first().reset_index()
unipersonales["es_1per"] = unipersonales["numper"] == 1
pct_unipersonales = unipersonales.groupby("cut_comuna")["es_1per"].mean()

df_65plus = df[(df["edad"] >= 65)]
solo_65 = df_65plus.groupby(["cut_comuna", "id_hogar"])["numper"].first().reset_index()
solo_65["vive_solo"] = solo_65["numper"] == 1
pct_65plus_solos = solo_65.groupby("cut_comuna")["vive_solo"].mean()
```

**Limitación para comunas pequeñas del RM:** Tiltil, Alhué, María Pinto,
San Pedro y Curacaví tienen muestras CASEN muy pequeñas (< 200 hogares).
Los estimativos para estas comunas tendrían coeficientes de variación > 20%
y no serían estadísticamente confiables sin factores de expansión comunal.

### Opción 2 — Censo 2017 cuestionario de hogar (INE microdato completo)

INE publicó el microdato completo del Censo 2017 incluyendo variables de
tipo de hogar (`p07` = número de personas en el hogar). Este archivo es
considerablemente más grande (> 5 GB) y requeriría procesamiento adicional,
pero permitiría estimados censales (no muestrales) para todas las 52 comunas.

## Estado actual

El exposome RM cubre **8 de los 14 factores modificables** de demencia
(Lancet Commission 2024) con proxies espaciales abiertos a nivel comunal.
El aislamiento social queda como brecha documentada. Los 6 factores restantes
(hipertensión, obesidad, tabaquismo, alcohol, pérdida auditiva, traumatismo
craneal) tampoco tienen fuentes abiertas a nivel comunal en Chile.

## Referencias

- Livingston G. et al. *Dementia prevention, intervention, and care: 2024
  report of the Lancet standing Commission.* Lancet, 2024.
- Holt-Lunstad J. et al. *Social relationships and mortality risk: a
  meta-analytic review.* PLoS Medicine, 2010.
- INE Chile. *Microdato Censo 2017 — Manzanas.* Disponible en
  redatam-ine.ine.cl.
- MDS Chile. *Encuesta CASEN 2022.* observatorio.ministeriodesarrollosocial.gob.cl.
