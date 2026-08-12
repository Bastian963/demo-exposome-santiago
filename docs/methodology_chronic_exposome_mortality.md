# Exposición crónica del exposoma y mortalidad por causa en la Región Metropolitana (52 comunas)

Análisis de factibilidad, no confirmatorio. Estudio ecológico de área pequeña — genera hipótesis, no establece causalidad individual.

## Pregunta y motivación

¿La exposición crónica (acumulada, no del día de la muerte) a factores del exposoma se correlaciona con mortalidad por causa a nivel comunal, controlando por confusores obvios? Diseño explícitamente orientado a la exposición de **años previos** a la muerte, no a exposición contemporánea del día del deceso.

## Datos

- **Desenlace:** DEIS, defunciones RM 2018–2022 con fecha, comuna y causa (CIE-10) completas al 100%. 52 comunas = Región Metropolitana completa (confirmado: total `all_cause` = 234.923, idéntico al conteo crudo de toda la RM en el período).
- **Causas analizadas (primarias):** `all_cause` (234.923 muertes), `cardiovascular` — I20-I25 isquémico + I50 insuficiencia cardíaca (19.925), `respiratory` — J12-J18 neumonía + J20-J22 agudo bajo + J40-J47 EPOC/crónico, excluyendo J30-J39 vía alta (15.316).
- **Causas exploratorias (latencia larga, ver limitaciones):** demencia, alzheimer, cerebrovascular (I60-I69), parkinsonismo.
- **Exposición primaria:** PM2.5 (ACAG/van Donkelaar, satelital, ~1km, GEE), ventana **histórica antecedente 2000–2017** — precede por completo la ventana de mortalidad 2018–2022.
- **Exposición de sensibilidad:** PM2.5 contemporáneo 2015–2022 (se solapa con la mortalidad; conservado solo como comparación).
- **Covariables:** `nse_index` (nivel socioeconómico), `demo_pct_pop_65_plus`.

## Método

1. **Estandarización indirecta por edad** (0-14, 15-64, 65+): tasas de referencia calculadas a nivel de toda la región, aplicadas a la estructura etaria de cada comuna → `expected`. `SMR = observed/expected`.
2. **Diagnóstico de colinealidad PRIMERO** (antes de cualquier regresión): matriz de correlación + VIF entre las 10 exposiciones del exposoma y NSE.
3. **Regresión GLM Poisson y binomial-negativa (NB)**, single-pollutant, `observed ~ PM2.5 + nse_index + demo_pct_pop_65_plus`, `offset = log(expected)`. Razón de tasas (RR) reportada por incremento de 5 µg/m³ de PM2.5.
4. **Endurecimiento espacial:** Moran's I sobre los residuos NB (contigüidad queen, 52 comunas) para decidir si un término espacial (BYM) es necesario.
5. **Control negativo:** mortalidad por lesiones/envenenamientos (CIE-10 S00-T98 — DEIS no usa V01-Y89 en `DIAG1`; confirmado empíricamente, 0 registros), sin vínculo biológico plausible con PM2.5 crónico.

## Resultados

### Colinealidad (`data/processed/analysis/exposure_collinearity_vif.csv`)

NO2, caminabilidad y tránsito forman un cluster casi colineal (VIF 17.9 / 16.1 / 12.4 — forma urbana + tráfico local). **PM2.5 es comparativamente independiente** (VIF 3.19, similar a NSE 3.18) → justifica usarlo como exposición principal en modelos single-pollutant; un modelo NO2 mutuamente ajustado por caminabilidad/tránsito no sería identificable a n=52.

### Precedencia temporal

PM2.5 histórico (2000-2017) y contemporáneo (2015-2022) correlacionan **r=0.995** entre comunas — el patrón espacial de contaminación en Santiago es muy persistente en el tiempo. Se logró precedencia temporal genuina (ventanas no solapadas), pero **no aporta identificación adicional** más allá de la exposición contemporánea, porque ambas miden esencialmente el mismo gradiente espacial fijo. Limitación documentada, no oculta.

### Modelo primario (NB, `data/processed/analysis/santiago_mortality_smr_regression.csv`)

Sobredispersión severa confirmada en todas las causas (dispersión Poisson 6.7–46 sobre grados de libertad) → **Poisson ingenuo es inválido aquí**; NB es el modelo correcto. Los IC de Poisson son artificialmente estrechos y varias "significancias" de Poisson no sobreviven bajo NB.

| Causa | RR por 5µg/m³ PM2.5 (hist.) | IC 95% | p (NB) |
|---|---|---|---|
| **Cardiovascular** | **1.11** | 1.02–1.22 | **0.022** |
| All-cause | 1.09 | 1.02–1.16 | 0.008 |
| Respiratorio | 1.06 | 0.94–1.19 | 0.36 (no robusto) |
| Demencia (exploratorio) | 0.90 | 0.76–1.06 | 0.19 (dirección inversa, no plausible) |
| Alzheimer, cerebrovascular, parkinsonismo (exploratorio) | ~1.0 | cruzan 1 | todos ns |

### Autocorrelación espacial residual (`residual_morans_i.csv`)

Ninguna causa primaria muestra autocorrelación espacial significativa en los residuos NB (all_cause p=0.47, cardiovascular p=0.45, respiratorio p=0.13). El modelo no-espacial ajustado por NSE ya absorbe razonablemente el patrón; no se ejecutó un BYM completo (PyMC/R-INLA) dado que el diagnóstico no lo motiva — **decisión de alcance explícita**, no omisión.

### Control negativo (`negative_control_external_causes.csv`)

Lesiones/envenenamientos (sin vínculo plausible con PM2.5): RR=1.06 [0.95–1.19], p=0.31 — **no significativo**. PM2.5 no predice espuriamente una causa sin relación biológica esperada, lo que respalda que la asociación cardiovascular no es un artefacto genérico de confusión de área (p.ej., PM2.5 actuando solo como proxy de "comuna pobre" que eleva todas las causas de muerte por igual).

## Profundización (Fase A): subcausas, barrido multi-exposición y estructura de colinealidad

Salidas: `data/processed/analysis/santiago_exposure_sweep_smr.csv` (barrido); las subcausas se propagan por `santiago_mortality_smr_by_cause.csv`.

### Subcausas respiratorias

Partición disjunta del agregado respiratorio (mortalidad 2018–2022): neumonía J12–J18 = 8.343, agudo bajo J20–J22 = 214, EPOC/crónico J40–J47 = 6.759 (suma = 15.316, cuadra). Ninguna subcausa sobrevive la corrección por multiplicidad en mortalidad — partir el conteo compra especificidad (EPOC es el brazo más plausible para PM2.5 crónico) pero pierde potencia. El déficit de potencia es exactamente lo que motiva las hospitalizaciones (Fase B).

### Barrido multi-exposición single-pollutant + FDR

Se corrió cada eje del exposoma (13 exposiciones, z-estandarizadas, RR por +1 SD) single-pollutant, ajustado por NSE y edad, NB con `offset=log(esperadas)`, por outcome primario, con corrección Benjamini-Hochberg sobre la familia primaria.

**Hallazgo central — cluster colineal, no separabilidad.** El resultado dominante NO es un contaminante ganador, sino la confirmación de que las exposiciones trazan **un mismo gradiente ambiental–socioeconómico**. Exhibit A es `all_cause`: NO2, área verde, tránsito y caminabilidad **cruzan FDR juntas** (q≈0.03) en la dirección esperada — cuatro "ganadores" que son **una sola señal** de forma urbana + contaminación + NSE. A n=52 bajo esa colinealidad (VIF NO2/caminabilidad/tránsito 12–18), ningún eje es identificable por separado; es la misma estructura que hacía que el script roto arrojara el mismo rho para 14 ejes.

**Cardiovascular dentro del cluster.** Tanto PM2.5 (correlación parcial con SMR | NSE,edad = +0.37) como `heat_exposure_index` (parcial +0.42) rastrean el gradiente cardiovascular; están correlacionados entre sí r≈0.45 (moderado) y **no son separables**. Un modelo NB de dos exposiciones lo *demuestra* (en vez de solo afirmarlo): con PM2.5 y calor juntos, el coeficiente de PM2.5 se atenúa de RR/SD 1.056 (p=0.015) a 1.026 (p=0.28) y el de calor de 1.066 a 1.056 — la señal compartida se reparte de forma inestable entre ambos. **Advertencia explícita:** `heat_exposure_index` es un índice compuesto (promedio de z-scores de métricas de calor, no °C), y a n=52 con r≈0.45 el orden entre PM2.5 y calor **no es estimable de forma confiable**. Esto es evidencia de **no-atribución** a un factor específico, **no** de que el calor sea el mecanismo. No se debe leer como "el calor gana".

**Guardrail (imprescindible).** El estimador puntual de PM2.5 **no cambió** (RR/SD 1.054 → RR 1.11 por 5µg/m³, idéntico al reporte previo). Lo único que cambió es que, bajo un test de multiplicidad más duro, la *significancia específica de PM2.5* se **ablanda** a q≈0.10 porque la magnitud es compartida con co-exposiciones colineales. Es una afirmación sobre **identificabilidad en este diseño ecológico de n=52**, no sobre si PM2.5 causa enfermedad cardiovascular. La evidencia de cohorte individual (Krewski et al. 2009; Seis Ciudades) que este mismo plan invoca **no puede ser refutada** por 52 unidades ecológicas: "ablandado", no "fallido"; PM2.5 no queda exonerado.

**Composición de la familia FDR (declarada).** Familia = 6 outcomes primarios × 13 exposiciones = 78 tests. Infla el tamaño de familia de dos formas conocidas: `pm25_hist` y `pm25_recent` son la misma variable dos veces (r=0.995), y el agregado `respiratory` convive con sus tres subcausas (anidamiento). El resultado cualitativo (PM2.5 cardiovascular q≈0.10, cluster colineal en all_cause) se sostiene también dentro de una familia solo-cardiovascular; se declara la composición en vez de re-optimizarla.

## Hospitalizaciones (Fase B): pipeline listo, datos pendientes

**Código completo y probado de punta a punta**, esperando solo la adquisición de datos:
- `src/exposome/neuro_hospitalizations.py`: `OUTCOME_PREFIXES` extendido con cardiovascular (I20–I25, I50) y respiratorio + subcausas (espejo de mortalidad); loader multi-año (glob/lista, concatena por año); metadata de cobertura (`coverage_window`, `coverage_gap` con pasos de remediación, `use_cases`).
- `scripts/analysis/build_hosp_smr_by_cause.py`: estandarización indirecta de egresos → observadas/esperadas, mismo esquema que mortalidad; el barrido corre sobre él con `--smr-csv`.

**Pre-check ICD (B0), condición previa a confiar en conteos.** El campo `DIAG1` de egresos **sí puebla** códigos I y J (RM 2006): cardiovascular 12.010, respiratorio 33.407 en **un solo año**. (Contrasta con defunciones, donde `DIAG1` usa S00–T98 para lesiones — verificado por separado.)

**Argumento de potencia.** Ese único año de hospitalizaciones (33.407 respiratorios) supera **al doble** los 15.316 respiratorios de mortalidad en 5 años. Las hospitalizaciones son la vía para dar potencia a la pregunta de subcausas respiratorias que la mortalidad deja inconclusa.

**Bloqueo honesto.** Solo existe egresos **2006** en disco; DEIS responde 403 a descarga automática, así que 2018–2022 debe bajarse manualmente (ver `coverage_gap.remediation_steps` en la metadata y el comentario en `config/cities/santiago.yaml`). El run 2006 ejecutado es un **smoke test del pipeline, NO un hallazgo** — año único sin ventana de exposición antecedente pareada; sus filas "q<0.05" no se reportan como resultado. Lo que sí queda demostrado: el pipeline corre completo y los códigos ICD pueblan.

## Veredicto (go/no-go)

**Cardiovascular: existe un gradiente ambiental de área, real pero NO atribuible a un factor específico.** Hay una señal cardiovascular robusta a nivel comunal, y **no es un mero proxy de pobreza** (NSE se relaciona débil/negativamente con el SMR cardiovascular; el control negativo de lesiones pasa; sin autocorrelación espacial residual). Pero PM2.5, calor y otros ejes ambientales co-varían (cluster colineal, r≈0.45 entre PM2.5 y calor) y **no se separan a n=52**: la significancia específica de PM2.5 se ablanda bajo FDR (q≈0.10) aunque su tamaño de efecto es idéntico al previo (RR≈1.11/5µg) y consistente con la cohorte. **Go** para "existe un gradiente cardiovascular ambiental que merece dato individual/temporal más largo"; **no-go** para "PM2.5 es el culpable identificado" — el diseño ecológico no lo puede afirmar.

**All-cause: señal modesta pero consistente**, en la dirección esperada y de magnitud menor (arrastrada en parte por el componente cardiovascular). Es el exhibit más claro del cluster colineal (varios ejes cruzan FDR juntos).

**Respiratorio: inconcluso en mortalidad, requiere hospitalizaciones.** No sobrevive el ajuste por sobredispersión (p=0.36 bajo NB vs. p=0.02 bajo Poisson ingenuo — falso positivo textbook por sobredispersión no modelada), y las subcausas (neumonía/EPOC) no alcanzan potencia con conteos de mortalidad. El pipeline de hospitalizaciones (Fase B) está listo para resolverlo apenas se adquieran los egresos 2018–2022.

**Neuro (demencia, alzheimer, cerebrovascular, parkinsonismo): no hay señal defendible.** Las correlaciones transversales previas (p.ej. demencia↔ruido, demencia↔PM2.5) no sobreviven al diseño de estandarización + NB + control de confusión, y la dirección del efecto PM2.5→demencia se invierte de forma biológicamente implausible. Consistente con la limitación anticipada: la latencia de la demencia (10-30 años) excede la ventana de datos de exposición disponible (2000-2022 como máximo), por lo que la ventana etiológicamente relevante (exposición de los años 80-90) simplemente no está medida. **No se recomienda construir ninguna capa o vista de app sobre el brazo neuro con los datos actuales.**

## Limitaciones (declaradas, no implícitas)

- **Diseño ecológico de área pequeña**: falacia ecológica, mala clasificación de exposición (asignación por comuna, no por dirección individual), confusión residual no medida (tabaquismo, acceso a salud, ocupación) — genera hipótesis, no prueba causalidad individual.
- **N=52** limita potencia, especialmente para causas exploratorias con menos eventos.
- **PM2.5 histórico y contemporáneo casi colineales** (r=0.995): la precedencia temporal lograda es conceptualmente correcta pero no añade poder identificador extra frente a confusión espacial fija.
- **Multiplicidad**: la Fase A aplicó FDR (Benjamini-Hochberg) al barrido multi-exposición (familia = 6 outcomes primarios × 13 exposiciones). Con corrección, la significancia específica de PM2.5 cardiovascular se ablanda a q≈0.10; el hallazgo defendible es el gradiente cardiovascular de área, no la atribución a un contaminante puntual. Familia con dobles conteos declarados (PM2.5 hist/recent r=0.995; respiratorio agregado + subcausas anidadas).
- **No separabilidad a n=52**: con exposiciones colineales (VIF NO2/caminabilidad/tránsito 12–18; PM2.5–calor r≈0.45), ningún modelo separa efectos mutuamente ajustados por contaminante; es una restricción de identificación del diseño, reportada como veredicto válido, no como fracaso.
- **Hospitalizaciones aún no adquiridas**: la Fase B está codificada y probada (smoke test 2006) pero la ventana válida 2018–2022 depende de descarga manual desde DEIS.

## Corrección de un bug preexistente (hallazgo colateral)

Durante la revisión de correlaciones ya disponibles en el repo se detectó que `scripts/compare_exposome_vs_neuro.py` (el otro comparador exposoma↔neuro, descriptivo, distinto del pipeline riguroso usado arriba) tenía un bug: para cualquier eje del exposoma salvo el propio EBI, la variable `x` caía silenciosamente al valor de `ebi_score` (rama `else` de un `if/elif/else` cuya condición `elif axis_col in ebi.columns` nunca se cumplía, porque `environmental_burden_index.csv` solo guarda versiones percentiladas `pct_*`, no las columnas crudas `pm25_mean`, `no2_surface_ug_m3`, etc.). Esto producía el mismo `rho` para los 14 ejes en cada outcome — confirmado empíricamente antes de la corrección (`rho=0.389` idéntico para PM2.5/NO2/ALAN/ruido/calor/verde/caminabilidad frente a `all_cause`).

**Corregido** (`scripts/compare_exposome_vs_neuro.py`): ahora fusiona la tabla maestra cruda (`santiago_exposome_master.csv`) para obtener cada columna de eje real, y lanza un error explícito si un eje configurado no se encuentra (en vez de recaer silenciosamente en EBI). Re-ejecutado: `data/processed/exposome_vs_neuro.csv` ahora tiene 14 valores de `rho` distintos por cada combinación outcome×tipo, como corresponde. Los 9 tests de `tests/test_compare_exposome_vs_neuro.py` pasan. Este script sigue siendo **descriptivo** (Spearman simple, sin control de confusores ni FDR) — se mantiene como exploración complementaria, no reemplaza el modelo NB/SMR de este documento.

## Reproducibilidad

```
.conda/envs/exposome/bin/python scripts/run_neuro_mortality.py                               # desenlaces + SMR base (10 outcomes, incl. subcausas resp.)
.conda/envs/exposome/bin/python scripts/analysis/diag_exposure_collinearity.py               # Paso 1
.conda/envs/exposome/bin/python scripts/analysis/fetch_pm25_historical.py                    # Paso 2 (requiere GEE)
.conda/envs/exposome/bin/python scripts/analysis/build_smr_by_cause.py                       # Paso 3
.conda/envs/exposome/bin/python scripts/analysis/ecological_smr_regression.py                # Paso 4 (PM2.5 por 5µg/m³)
.conda/envs/exposome/bin/python scripts/analysis/exposure_sweep_smr_regression.py            # Fase A2/A3 (barrido multi-exposición + FDR)
.conda/envs/exposome/bin/python scripts/analysis/robustness_spatial_and_negative_controls.py # Paso 5-6
.conda/envs/exposome/bin/python scripts/compare_exposome_vs_neuro.py                          # comparador descriptivo (bug corregido)

# Fase B (hospitalizaciones) — requiere egresos DEIS; con solo 2006 es smoke test:
.conda/envs/exposome/bin/python scripts/run_neuro_hospitalizations.py                         # egresos → morbilidad por causa (15 outcomes)
.conda/envs/exposome/bin/python scripts/analysis/build_hosp_smr_by_cause.py                   # SMR indirecto de egresos
.conda/envs/exposome/bin/python scripts/analysis/exposure_sweep_smr_regression.py \
    --smr-csv data/processed/analysis/santiago_hosp_smr_by_cause.csv \
    --out-csv data/processed/analysis/santiago_hosp_exposure_sweep_smr_2006_smoketest.csv     # barrido sobre hospitalizaciones
```

Para la Fase B válida (2018–2022): bajar `EGRE_DATOS_ABIERTOS_20{18..22}.csv` de https://deis.minsal.cl/#datosabiertos a `data/raw/deis/egresos/`, ajustar `neuro_hospitalizations.years` y `source.path`/`paths` en `config/cities/santiago.yaml`, y re-correr los tres comandos de arriba.

Salidas en `data/processed/analysis/`. No se generó ninguna capa ni vista de app en este análisis — está explícitamente fuera de alcance hasta una decisión posterior informada por este veredicto.
