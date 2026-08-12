# Evaluación de estadísticas criminales argentinas para AMBA

## Decisión de uso

La fuente prioritaria es **SAT Propiedad** de la Dirección Nacional de
Estadística Criminal (DNEC). Produce el exposoma contextual
`community_safety`: hechos registrados de delitos contra la propiedad por
100.000 habitantes, para las 15 comunas de CABA y 40 partidos bonaerenses del
estudio `buenos_aires_amba`. La segunda capa, `community_violence`, queda
implementada y validada con datos sintéticos, pero no se publica hasta disponer
del SNIC departamental anual oficial.

No se interpreta como incidencia real, victimización individual ni resultado
clínico. Las diferencias pueden reflejar propensión a denunciar, cobertura
institucional, reglas de registro y cambios temporales de clasificación.

## Cobertura y unidad de análisis

- SAT Propiedad es una tabla agregada por departamento/partido/comuna, mes,
  año y categoría de delito. Se suman los campos `cantidad_hechos`; nunca se
  cuentan filas como si fueran eventos.
- La salida conserva tasas anuales de 2017 a 2024 y una tasa del período
  calculada con hechos acumulados y personas-año acumuladas.
- Los denominadores son las estimaciones oficiales de INDEC por comuna o
  partido: la serie 2010-2025 para 2017-2021 y la serie revisada con base en
  Censo 2022 para 2022-2024.
- En los datos ya ingresados, AMBA contiene 2.070.820 de 2.315.185 hechos
  elegibles (89,45 %). El resto corresponde a partidos bonaerenses fuera del
  estudio; no se pierde silenciosamente y queda documentado por año.
- `Departamento sin determinar` queda fuera de la capa y no se imputa a una
  unidad territorial.

## Campos publicados

- `crime_property_rate_100k`: indicador principal del período 2017-2024.
- `crime_robbery_rate_100k`, `crime_theft_rate_100k` y
  `crime_vehicle_rate_100k`: desagregaciones registradas.
- `crime_public_space_pct` y `crime_firearm_pct`: caracterización del hecho
  registrado, no prevalencia poblacional.
- Cada una de las seis familias anteriores conserva columnas anuales
  `<indicador>_<año>` para el selector temporal.

Los insumos individuales de SAT no se publican ni se incorporan a esta capa.
Suicidios y muertes viales se producen como resultados ecológicos separados;
no forman parte de este indicador ni del EBI. La web recibe únicamente tasas
agregadas con ventanas móviles de tres años; las celdas con 1–4 eventos se
suprimen y nunca viajan identificadores ni recuentos. Las asociaciones con el
exposoma permanecen cerradas mientras falten covariables censales y
estandarización por edad y sexo.

## Fuentes pendientes o no integradas

| Fuente | Decisión | Motivo |
|---|---|---|
| SNIC país/provincias | Benchmark | Su granularidad no llega a las 55 unidades AMBA. |
| SNIC departamentos anual | Pipeline listo, fuente pendiente | Alimenta `community_violence`; no se sustituye con provincia o país. |
| SAT Homicidios Dolosos | No usado en la capa actual | El SNIC departamental agregado evita publicar microdatos y aporta categorías comparables. |
| SAT Suicidios | Resultado ecológico | Agregado por víctima única, fuera del master/EBI y publicado solo como tasa sanitizada. |
| SAT Muertes Viales | Resultado ecológico | Filtra víctimas únicas, fuera del master/EBI y publicado solo como tasa sanitizada. |
| PUFEAF | Exploratorio | Evaluar cobertura territorial y definiciones antes de cualquier capa. |
| ENV 2017 | Requiere microdatos | La descarga actual contiene cuestionario y documentación, no la base analítica. |

## Reproducibilidad y privacidad

Los originales, hashes, extracciones Markdown y nombres canónicos se registran
en `docs/sources/ar/security_dnec/`. Los diagnósticos de conservación de
totales y de registros no mapeados viajan con el artefacto
`community_safety/diagnostics/`. No se publicarán direcciones, coordenadas ni
identificadores de hechos; cualquier futuro comparador de eventos raros deberá
suprimir recuentos entre 1 y 4.
