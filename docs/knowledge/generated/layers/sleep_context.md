<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "sleep_context"
category: "master_optional"
required: false
generated: true
---

# Contexto sueno-circadiano

Identificador canónico: `sleep_context`.

## Fuentes y navegación

- Metodología: [sleep_context_methodology.md](../../../sleep_context_methodology.md)
- Configuración: [sleep_context.yaml](../../../../config/layers/sleep_context.yaml)
- Implementación: [sleep_context.py](../../../../src/exposome/sleep_context.py)
- Revisión: [sleep_context.md](../../../review_prompts/sleep_context.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers sleep_context --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/sleep_context/santiago_communes_sleep_context.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/sleep_context/santiago_communes_sleep_context.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/sleep_context/santiago_sleep_context_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/sleep_context/sleep_context_santiago.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Ninguna accion adicional; capa cerrada (14 tests OK; 70/30 weighting verificada; contraste urbano/rural documentado; fig regenerada con edgecolor=white)
