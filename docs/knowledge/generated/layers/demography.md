<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "demography"
category: "master_required"
required: true
generated: true
---

# Demografia

Identificador canónico: `demography`.

## Fuentes y navegación

- Metodología: [demography_methodology.md](../../../demography_methodology.md)
- Configuración: [demography.yaml](../../../../config/layers/demography.yaml)
- Implementación: [demography.py](../../../../src/exposome/demography.py)
- Revisión: [demography.md](../../../review_prompts/demography.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers demography --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/demography/santiago_demography.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/demography/santiago_demography.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/demography/santiago_demography_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/demography/demography_santiago_2panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: CSV GeoJSON metadata master tests verificados; mantener capa en master y dejar validacion externa oficial como mejora futura.
