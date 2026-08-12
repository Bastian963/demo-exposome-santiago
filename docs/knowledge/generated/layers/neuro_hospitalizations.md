<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "neuro_hospitalizations"
category: "comparator"
required: false
generated: true
---

# Comparador egresos neuropsiquiatricos

Identificador canónico: `neuro_hospitalizations`.

## Fuentes y navegación

- Metodología: [neuro_outcomes_methodology.md](../../../neuro_outcomes_methodology.md)
- Configuración: [neuro_hospitalizations.yaml](../../../../config/layers/neuro_hospitalizations.yaml)
- Implementación: [neuro_hospitalizations.py](../../../../src/exposome/neuro_hospitalizations.py)
- Revisión: [neuro_hospitalizations.md](../../../review_prompts/neuro_hospitalizations.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers neuro_hospitalizations --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_communes_neuro_hospitalizations_2011_2020.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_communes_neuro_hospitalizations_2011_2020.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_neuro_hospitalizations_2011_2020_qc.json`
- Figura: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/neuro_outcomes_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `not_applicable`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Serie DEIS 2011-2020 completa: 832 filas agregadas, 52 comunas y 16 desenlaces; el cubo confirmatorio contiene 8.320 celdas comuna-año-desenlace con observed/expected y población INE. annual-v2.0 cerró 768/768 screening, 10/10 elastic-net y 142/142 BYM2; v1 queda legacy/not_accepted. La evidencia es ecológica y no causal.
