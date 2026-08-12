# Bibliografía: Clima y Envejecimiento Cerebral

Colección de papers organizados para RAG con NotebookLM MCP.

## Estructura

Cada paper es un archivo markdown con frontmatter YAML.

## Papers incluidos

| # | Paper | Año | Diseño | Relevancia |
|---|---|---|---|---|
| 01 | Gao et al. — Hot nights and dementia mortality | 2024 | Case-crossover | Justifica `tropical_nights` como métrica principal |
| 02 | Liu et al. — Heat waves and dementia mortality | 2024 | DLNM case-crossover | Justifica `heat_wave_days` y `cold_spell_days` |
| 03 | Hou & Xu — Temperature and cognition | 2023 | Longitudinal | Justifica temperatura crónica continua, no solo extremos |
| 04 | Wei et al. — Seasonal temperature and dementia | 2019 | Cox + MODIS LST | Justifica variabilidad térmica + anomalías estacionales |
| 05 | Yan et al. — Heat + ozone and BBB disruption | 2023 | Rat experimental | Mecanismo neuroinflamación/BBB, justifica interacción aire-clima |

## Cómo usar con NotebookLM

1. Agregar esta carpeta como fuente en NotebookLM
2. Preguntar: "¿Cuáles son las métricas térmicas más predictivas de demencia?"
3. Preguntar: "¿Qué mecanismos biológicos conectan calor y envejecimiento cerebral?"
4. Preguntar: "¿Cómo debería diseñar mi exposoma climático para Santiago?"

## Papers pendientes por agregar

- Li et al. 2026 — Temperature variability and cognition (CHARLS, China)
- Sisodiya et al. 2024 — Climate change and disorders of the nervous system (Lancet Neurology review)
- Assari & Zare 2025 — Extreme heat and cognitive ability in US children (ABCD)
- Lo et al. 2021 — Temperature and mild cognitive impairment (Taiwan)
- Vered et al. 2020 — Diurnal temperature range and stroke (Israel)

## Notas metodológicas

- Los percentiles locales (P90, P95) son el estándar para definir olas de calor
- Las noches tropicales (Tmin > 20°C) son tan importantes como los días calurosos
- La variabilidad térmica tiene evidencia mixta — incluir como exploratorio
- El frío también importa (cold spells) — no descartar invierno
- La co-exposición ozono-calor es biológicamente plausible
