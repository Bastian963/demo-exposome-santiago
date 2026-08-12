<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "noise"
category: "master_optional"
required: false
generated: true
---

# Ruido urbano

Identificador canónico: `noise`.

## Fuentes y navegación

- Metodología: [noise_methodology.md](../../../noise_methodology.md)
- Configuración: [noise.yaml](../../../../config/layers/noise.yaml)
- Implementación: [noise.py](../../../../src/exposome/noise.py)
- Revisión: [noise.md](../../../review_prompts/noise.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers noise --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/noise/santiago_noise_mma_2023.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/noise/santiago_noise_mma_2023.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/noise/santiago_noise_mma_2023_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/noise/noise_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; 35 dentro del perimetro GSU con exposicion modelada (MMA 2024 Minuta Mapa de Ruido 2023); 17 rurales con noise_in_gsu_map=0 documentado como gap de cobertura no como exposicion cero; metricas Lden/Ln coherentes con umbrales END; figura 4-panel con edgecolor white; 18 tests offline pasan; integracion al master verificada.
