---
title: "Ambient temperatures and reduced cognitive function in older adults in China"
authors: "Hou & Xu"
year: 2023
journal: "Scientific Reports"
doi: "10.1038/s41598-023-xxx"
tags: ["temperature", "cognition", "mmse", "elderly", "longitudinal", "china"]
---

## Abstract

Evaluó la asociación entre temperatura ambiental y función cognitiva en adultos mayores chinos usando datos del CLHLS (Chinese Longitudinal Healthy Longevity Survey). La temperatura alta mostró una asociación más fuerte con declive cognitivo que la temperatura baja.

## Design

- **Tipo:** Longitudinal (repeated measures)
- **Población:** CLHLS, adultos mayores chinos
- **Outcome:** MMSE (Mini-Mental State Examination)
- **Exposure:** Temperatura mensual promedio

## Exposure

- Temperatura mensual promedio (Tmean)
- Temperatura máxima mensual (Tmax)
- Temperatura mínima mensual (Tmin)
- Variables asignadas por ciudad (ecológico)

## Key Findings

- **Por cada 1°C de aumento en temperatura máxima mensual, MMSE disminuyó -0.48 puntos**
- El efecto del frío fue menor (-0.14 puntos por 1°C de descenso)
- Asociación lineal (no solo extremos): temperaturas más altas = peor cognición
- Efecto más fuerte en verano

## Relevance to Santiago

- Justifica modelar **temperatura como variable continua**, no solo extremos
- `tmax_mean_summer` y `tmean_annual` son predictores relevantes
- El MMSE es outcome común en cohortes chilenas → comparable
- Si tenemos neuropsicología, podríamos replicar este análisis
- Importancia del calor crónico (verano entero), no solo olas de calor

## Limitations

- Asignación ecológica por ciudad (no individual)
- MMSE tiene efecto techo/suelo
- No controla por uso de AC (raro en China en ese periodo)
- Residual confounding por SES y salud general

## Notas

- Este paper es clave porque muestra que **no solo los extremos importan**
- La exposición crónica a temperaturas altas está asociada con declive cognitivo
- Para nuestro pipeline: calcular medias estacionales y anuales, no solo conteos de días extremos
