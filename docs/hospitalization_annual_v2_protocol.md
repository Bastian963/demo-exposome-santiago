# Protocolo v2: exposoma anual y hospitalizaciones en Santiago

## Propósito y alcance

Este análisis ecológico longitudinal contrasta hospitalizaciones DEIS agregadas
por comuna y año con exposiciones ambientales anuales materializadas por el
pipeline canónico. Es un producto analítico **offline**: no modifica el master,
la publicación espacial ni la aplicación web. Tampoco reemplaza la inferencia
BYM2 transversal v1; sus resultados viven en un directorio v2 independiente.

La unidad es comuna-año. Los datos individuales de egresos nunca se exportan ni
se leen en esta etapa. Los conteos observados y esperados ya estandarizados se
usan con `log(expected)` como offset.

## Ventanas y temporalidad

- Análisis primario: desenlaces 2015–2019, antes de COVID-19.
- Sensibilidad COVID: 2015–2020, informada por separado.
- Asociación contemporánea: exposición y desenlace del mismo año.
- Rezago 1: exposición del año anterior y desenlace del año corriente.
- NO2 sólo tiene solapamiento DEIS 2019–2020. Se reporta como análisis limitado;
  no se promueve a evidencia primaria ni se fuerza un rezago no identificable.
- El compuesto ambiental usa como período de referencia común 2016–2019 porque
  Dynamic World comienza en 2016.

## Desenlaces

Los cinco desenlaces primarios son cardiovascular, respiratorio, EPOC/asma,
cerebrovascular y salud mental. Diez desenlaces adicionales son exploratorios.
Lesiones y envenenamientos constituyen el control negativo preespecificado.

## Exposiciones y compuesto

Cada cosecha anual debe provenir de un `manifest.json` del contrato temporal
soportado (schemas 1 o 2) cuyo SHA-256, estudio, capa, año, número de filas y
tabla anual sean coherentes. Schema 1 se admite para tablas administrativas sin
detalle; schema 2 es obligatorio cuando se declara detalle espacial anual. No se
admite reutilizar un promedio estático como año. Los componentes primarios del
compuesto son PM2.5, ALAN, calor, verde, sequía pluviométrica, viento, incendios
y metales pesados. NO2 se analiza por separado debido a cobertura temporal.

Los componentes se winsorizan en los percentiles 1 y 99 del período común y se
estandarizan usando una única media/desviación pre-COVID. El signo se orienta a
mayor carga: verde y viento se invierten. La carga ambiental es la media de los
ocho z-scores orientados, sólo cuando están todos disponibles. Un análisis de
Horn/PCA y una mezcla elastic-net agrupada por comuna evalúan la dependencia de
la ponderación uniforme.

## Nivel socioeconómico

La privación primaria es el negativo del z-score de `nse_index_pca`; el índice
original es sensibilidad. Al ser prácticamente estática, no se interpreta como
efecto longitudinal dentro de comuna. Los efectos fijos comunales absorben su
efecto principal; se estima:

1. el cambio anual de exposición dentro de comuna;
2. su interacción con privación estática;
3. diferencias entre comunas en modelos Mundlak/BYM2 sin efecto fijo comunal;
4. resultados estratificados por quintil como descripción de heterogeneidad.

El indicador descriptivo de doble carga es
`0.5 × percentil(carga ambiental) + 0.5 × percentil(privación)`. No se presenta
como coeficiente causal.

## Estrategia estadística

La fase de screening incluye Spearman residualizado por comuna/año con bootstrap
por comuna, PPML con offset y efectos fijos comuna/año, errores agrupados por
comuna, descomposición within/between, Moran de residuos y sensibilidad dejando
una comuna fuera. La multiplicidad se controla con Benjamini–Hochberg dentro de
familias preespecificadas de desenlace, temporalidad y tipo de análisis.

La fase confirmatoria usa binomial negativa BYM2 espacio-temporal con efecto de
año, exposición within, media between, privación y la interacción
within×privación. Se ejecutan cuatro cadenas, diagnóstico estricto, un reintento
preespecificado si falla convergencia, PSIS-LOO y refits exactos para Pareto-k
alto cuando se solicita. Se guardan trazas NetCDF de forma atómica y reanudable.

## Interpretación y límites

Los resultados son asociaciones ecológicas, no efectos individuales ni
causales. Se reportan como `supported`, `suggestive`, `unstable`, `null` o
`not_estimable`; no se seleccionan sólo por p < 0.05. Se exige coherencia de
dirección, estabilidad a comunas influyentes, control negativo, convergencia y
diagnóstico predictivo. La autocorrelación espacial, error de medición, cambios
de residencia, movilidad y confusión temporal residual permanecen como límites.

## Reproducibilidad

La configuración canónica es
`config/analyses/hospitalization_annual_v2.yaml`. La preparación registra hashes
de configuración, protocolo, desenlaces, master, geometría y cada tabla/manifiesto
anual. Cambiar cualquiera invalida el estado previo. Las fases son reanudables y
no contactan GEE, Open-Meteo, OSM ni otro proveedor.

Desde la raíz del repositorio:

```bash
# Rápido: valida hashes y prepara panel, privación, doble carga y Horn/PCA.
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase prepare

# Inspección sin ejecutar modelos.
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase screen --dry-run
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase joint --dry-run
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase bayesian --dry-run

# Largos, locales y reanudables; correr con caffeinate si corresponde.
caffeinate -i .venv/bin/python scripts/run_hospitalization_annual_v2.py --phase screen --resume
caffeinate -i .venv/bin/python scripts/run_hospitalization_annual_v2.py --phase joint --resume

# PyMC/ArviZ son extras declarados, no instalaciones ad-hoc.
uv sync --extra dev --extra spatial
caffeinate -i .venv/bin/python scripts/run_hospitalization_annual_v2.py --phase bayesian --resume

# Sólo se completa cuando las 768 pruebas, 10 mezclas y 142 modelos están presentes.
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase finalize
.venv/bin/python scripts/run_hospitalization_annual_v2.py --phase status
```

Los filtros repetibles `--outcome`, `--exposure`, `--timing` y `--window`
permiten dividir una ejecución entre noches. Los checkpoints parciales conservan
el fingerprint científico; no se pueden mezclar resultados de configuraciones
distintas. `exact_reloo` vive en la configuración y no es un interruptor de
línea de comandos para impedir que dos corridas con el mismo fingerprint usen
criterios predictivos diferentes.
