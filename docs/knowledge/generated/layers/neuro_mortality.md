<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "neuro_mortality"
category: "comparator"
required: false
generated: true
---

# Comparador mortalidad neurologica

Identificador canónico: `neuro_mortality`.

## Fuentes y navegación

- Metodología: [neuro_outcomes_methodology.md](../../../neuro_outcomes_methodology.md)
- Configuración: [neuro_mortality.yaml](../../../../config/layers/neuro_mortality.yaml)
- Implementación: [neuro_mortality.py](../../../../src/exposome/neuro_mortality.py)
- Revisión: [neuro_mortality.md](../../../review_prompts/neuro_mortality.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers neuro_mortality --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/neuro_mortality/santiago_neuro_mortality_2018_2022.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/neuro_mortality/santiago_neuro_mortality_2018_2022.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/neuro_mortality/santiago_neuro_mortality_2018_2022_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/neuro_mortality/neuro_outcomes_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `not_applicable`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Comparador auditado: 260 filas (52 comunas x 5 outcomes, 2018-2022) desde DEIS defunciones 1990-2023; alineado con ventana PM2.5 cronica 2015-2022; metadata documenta ventana y mismatch temporal con hospitalizations; figura 4-panel comparativa (mortalidad + hospitalizacion) con edgecolor white; 12 tests pasan; validacion para joint exposure-outcome analysis.
