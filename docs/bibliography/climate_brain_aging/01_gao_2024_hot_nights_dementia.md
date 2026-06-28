---
title: "Heat exposure and dementia-related mortality in China"
authors: "Gao et al."
year: 2024
journal: "JAMA Network Open"
doi: "10.1001/jamanetworkopen.2024.xxxx"
tags: ["heat", "nighttime", "dementia", "mortality", "case-crossover", "china"]
---

## Abstract

Evaluó la asociación entre exposición al calor y mortalidad relacionada con demencia en China continental usando un diseño case-crossover. Se analizaron 132,573 muertes por demencia. El calor nocturno mostró una carga de riesgo comparable o mayor que el calor diurno. Las noches extremadamente cálidas persistieron en su efecto por ~6 días.

## Design

- **Tipo:** Case-crossover estratificado por tiempo
- **Población:** 132,573 muertes por demencia en China (nacional)
- **Periodo:** Varias temporadas de calor
- **Unidad de análisis:** Individual (registros de mortalidad)

## Exposure

- **Métricas:**
  - Hot Day Excess (HDE): Tmax > P97.5 local
  - Hot Night Excess (HNE): Tmin > P97.5 local
  - Definiciones basadas en percentiles locales para adaptación poblacional
- **Ventana:** Día de muerte + 6 días previos (lag distribuido)
- **Fuente:** Datos meteorológicos estacionales

## Key Findings

- OR 1.38 para HNE extremo (noches extremadamente calurosas)
- OR 1.46 para HDE extremo (días extremadamente calurosos)
- **El calor nocturno tuvo una carga comparable o mayor que el diurno**
- Efectos más fuertes en mujeres, >75 años, menor educación
- Persistencia del efecto: 6 días para noches, 10 días para días

## Relevance to Santiago

- Santiago tiene alta amplitud diurna y UHI nocturno pronunciado → las noches tropicales son relevantes
- La población chilena envejece rápidamente → cohortes geriátricas vulnerables
- No hay estudios similares en Latinoamérica → oportunidad de llenar vacío
- Deberíamos calcular `tropical_nights` y `hot_night_excess` como métricas principales

## Limitations

- Diseño ecológico en la exposición (temperatura asignada por estación más cercana, no individual)
- Solo mortalidad, no biomarcadores ni neuroimagen
- China ≠ Chile (diferencias en adaptación, AC, vivienda)
- No controla por contaminación del aire (sinergia ozono-calor)

## Notas

- Este paper justifica por qué **Tmin importa tanto como Tmax** para demencia
- Sugiere que las métricas de exposoma deben incluir noches, no solo días calurosos
