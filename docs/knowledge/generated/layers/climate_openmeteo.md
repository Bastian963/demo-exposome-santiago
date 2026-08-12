<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "climate_openmeteo"
category: "master_required"
required: true
generated: true
---

# Metricas climaticas anuales

Identificador canónico: `climate_openmeteo`.

## Fuentes y navegación

- Metodología: [climate_openmeteo_methodology.md](../../../climate_openmeteo_methodology.md)
- Configuración: [climate_openmeteo.yaml](../../../../config/layers/climate_openmeteo.yaml)
- Implementación: [climate_metrics.py](../../../../src/exposome/climate_metrics.py)
- Revisión: [climate_openmeteo.md](../../../review_prompts/climate_openmeteo.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers climate_openmeteo --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/climate_metrics_santiago.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa cerrada con 2024-only scope; archivo amplio 2015-2024 disponible pero no usado para mantener consistencia con climate_heat
