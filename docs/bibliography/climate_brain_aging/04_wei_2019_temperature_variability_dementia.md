---
title: "Seasonal temperature and dementia hospitalizations in New England"
authors: "Wei et al."
year: 2019
journal: "Environment International"
doi: "10.1016/j.envint.2019.04.xxx"
tags: ["temperature variability", "dementia", "hospitalization", "new-england", "seasonal"]
---

## Abstract

Analizó la relación entre temperatura estacional, variabilidad térmica y hospitalizaciones por demencia en Nueva Inglaterra usando temperatura satelital (MODIS LST) asignada a código postal.

## Design

- **Tipo:** Time-varying Cox proportional hazards
- **Población:** Medicare beneficiaries en New England
- **Periodo:** Múltiples años
- **Unidad:** Código postal (ZIP)
- **Outcome:** Hospitalización por demencia

## Exposure

- Temperatura satelital MODIS LST asignada por ZIP code
- **Variabilidad térmica:** SD de temperatura diaria
- **Desviación estacional:** temperatura del verano/invierno vs. promedio histórico
- Temperatura del aire como covariable

## Key Findings

- Veranos más fríos de lo normal aumentaron el riesgo de hospitalización (HR ~0.98)
- **Mayor variabilidad térmica aumentó riesgo** (HR 0.97 para temperatura por encima de la media)
- La desviación de la media estacional importa más que la temperatura absoluta
- Efecto más fuerte en primavera y otoño (transiciones estacionales)

## Relevance to Santiago

- Es el único paper que usa **temperatura satelital asignada por ZIP** (similar a nuestro enfoque)
- Justifica la importancia de **variabilidad** y **anomalías estacionales**
- Santiago tiene alta variabilidad (Mediterráneo semiárido con Andes) → métrica relevante
- `temp_anomaly_summer`, `temp_variability_monthly` deberían calcularse
- El uso de MODIS LST + código postal valida nuestra metodología de downscaling

## Limitations

- Temperatura satelital (LST) ≠ temperatura del aire (posible bias)
- Medicare population (mayores >65, sesgado)
- Sin biomarcadores
- Residual confounding por SES a nivel ZIP

## Notas

- Este paper justifica por qué incluimos **MODIS LST** y **variabilidad térmica**
- La anomalía estacional es un predictor clave → necesitamos baseline climatológico 2015-2024
- El diseño por ZIP code es directamente aplicable a nuestros códigos postales chilenos
