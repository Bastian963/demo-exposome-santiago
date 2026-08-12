---
title: "Extreme temperature events and dementia mortality in Chinese adults"
authors: "Liu et al."
year: 2024
journal: "International Journal of Epidemiology"
doi: "10.1093/ije/dyae001"
tags: ["heat waves", "cold spells", "dementia", "mortality", "attributable fraction", "china"]
---

## Abstract

Estimó la fracción atribuible de muertes por demencia a eventos de temperatura extrema (olas de calor y olas de frío) en China. El 6.14% de las muertes por demencia fueron atribuibles a temperaturas extremas.

## Design

- **Tipo:** Case-crossover con Distributed Lag Non-Linear Model (DLNM)
- **Población:** Base poblacional nacional china
- **Periodo:** Múltiples años
- **Unidad:** Muertes individuales

## Exposure

- **Ola de calor:** Tmean > P90 durante ≥2 días consecutivos
- **Ola de frío:** Tmean < P10 durante ≥2 días consecutivos
- Definiciones de percentil local
- Análisis separado por intensidad (P90, P92.5, P95, P97.5)

## Key Findings

- **6.14% de muertes por demencia atribuibles** a eventos extremos de temperatura
- Olas de calor: fracción atribuible creciente con intensidad
- Olas de frío: también contribuyen significativamente
- Efectos más pronunciados en adultos mayores y mujeres
- La combinación de calor + frío en el mismo año aumenta el riesgo

## Relevance to Santiago

- Santiago tiene **ambos extremos**:
  - Veranos secos y calurosos con olas de calor
  - Inviernos fríos con heladas nocturnas
- Las olas de frío son subestudiadas en exposoma cerebral → métrica valiosa
- Justifica incluir `cold_spell_days` además de `heat_wave_days`
- El cálculo de percentiles locales es metodológicamente correcto para Santiago

## Limitations

- No biomarcadores (solo mortalidad)
- Asignación por estación meteorológica más cercana
- Sin datos de uso de calefacción/aire acondicionado
- Adaptación local no medida directamente

## Notas

- Este paper establece el estándar de cómo definir **olas de calor y frío** con percentiles locales + duración consecutiva
- Nuestro pipeline debería calcular:
  - `heat_wave_days` (Tmax > P90, ≥2 días)
  - `cold_spell_days` (Tmin < P10, ≥2 días)
  - Fracción atribuible podría estimarse si tenemos cohorte longitudinal
