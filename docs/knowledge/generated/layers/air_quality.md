<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "air_quality"
category: "master_required"
required: true
generated: true
---

# Calidad del aire legacy

Identificador canónico: `air_quality`.

## Fuentes y navegación

- Metodología: [air_quality_legacy_methodology.md](../../../air_quality_legacy_methodology.md)
- Configuración: [air_quality.yaml](../../../../config/layers/air_quality.yaml)
- Implementación: [air_quality.py](../../../../src/exposome/air_quality.py)
- Revisión: [air_quality.md](../../../review_prompts/air_quality.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers air_quality --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_before_after_satellite.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa legacy CAMS verificada como comparador historico; usa solo no2_mean n_grid y no2_who_ratio en el master; no requiere rebuild y el PM2.5 canonico permanece en air_quality_pm25.
