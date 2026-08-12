<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "pobreza_sae"
category: "master_optional"
required: false
generated: true
---

# Pobreza comunal SAE

Identificador canónico: `pobreza_sae`.

## Fuentes y navegación

- Metodología: [pobreza_sae_methodology.md](../../../pobreza_sae_methodology.md)
- Configuración: [pobreza_sae.yaml](../../../../config/layers/pobreza_sae.yaml)
- Implementación: [pobreza_sae.py](../../../../src/exposome/pobreza_sae.py)
- Revisión: [pobreza_sae.md](../../../review_prompts/pobreza_sae.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers pobreza_sae --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/pobreza_sae/santiago_pobreza_sae.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/pobreza_sae/santiago_pobreza_sae.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/pobreza_sae/santiago_pobreza_sae_metadata.json`
- Figura: `no declarado`

## Estado

- Automático: `ready_for_review`
- Revisión: `not_started`
- Integrado en master: `true`
- Check final: `false`
- Bloqueadores: —
- Próxima acción: Abrir sesion de revision con el prompt de la capa.
