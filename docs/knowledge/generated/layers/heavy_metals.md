<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "heavy_metals"
category: "master_optional"
required: false
generated: true
---

# Metales pesados industriales

Identificador canónico: `heavy_metals`.

## Fuentes y navegación

- Metodología: [heavy_metals_methodology.md](../../../heavy_metals_methodology.md)
- Configuración: [heavy_metals.yaml](../../../../config/layers/heavy_metals.yaml)
- Implementación: [heavy_metals.py](../../../../src/exposome/heavy_metals.py)
- Revisión: [heavy_metals.md](../../../review_prompts/heavy_metals.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers heavy_metals --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/heavy_metals/santiago_heavy_metals_retc_2015_2022.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/heavy_metals/santiago_heavy_metals_retc_2015_2022.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/heavy_metals/santiago_heavy_metals_retc_2015_2022_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/heavy_metals/heavy_metals_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Ninguna accion adicional; capa cerrada (RETC 2015-2022; 13 tests OK; sentinel Mn/Cd documentado y testeado; fig regenerada con edgecolor=white)
