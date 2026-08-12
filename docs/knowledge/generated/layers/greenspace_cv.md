<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "greenspace_cv"
category: "validation"
required: false
generated: true
---

# Validacion CV de vegetacion

Identificador canónico: `greenspace_cv`.

## Fuentes y navegación

- Metodología: [greenspace_cv_methodology.md](../../../greenspace_cv_methodology.md)
- Configuración: [layers.yaml](../../../../config/layers.yaml)
- Implementación: [greenspace_cv.py](../../../../src/exposome/greenspace_cv.py)
- Revisión: [greenspace_cv.md](../../../review_prompts/greenspace_cv.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers greenspace_cv --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/greenspace_cv/santiago_greenspace_cv_commune.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/greenspace_cv/missing.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/greenspace_cv/greenspace_cv_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/greenspace_cv/greenspace_cv_santiago.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `not_applicable`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Validacion CV confirma sub-mapeo OSM (~93% verde CV fuera de OSM); n=5 muestras por comuna con std real (0.33-28.1%); metodologia documentada; tests ExG/Otsu en verde.
