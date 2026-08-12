<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "food_insecurity"
category: "master_optional"
required: false
generated: true
---

# Food Insecurity

Identificador canónico: `food_insecurity`.

## Fuentes y navegación

- Metodología: [food_insecurity_methodology.md](../../../food_insecurity_methodology.md)
- Configuración: [food_insecurity.yaml](../../../../config/layers/food_insecurity.yaml)
- Implementación: [food_insecurity.py](../../../../src/exposome/food_insecurity.py)
- Revisión: [food_insecurity.md](../../../review_prompts/food_insecurity.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers food_insecurity --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/food_insecurity/santiago_food_insecurity.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/food_insecurity/santiago_food_insecurity.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/food_insecurity/santiago_food_insecurity_metadata.json`
- Figura: `no declarado`

## Estado

- Automático: `ready_for_review`
- Revisión: `not_started`
- Integrado en master: `true`
- Check final: `false`
- Bloqueadores: —
- Próxima acción: Abrir sesion de revision con el prompt de la capa.
