<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "socioeconomic"
category: "master_required"
required: true
generated: true
---

# Nivel socioeconomico

Identificador canónico: `socioeconomic`.

## Fuentes y navegación

- Metodología: [socioeconomic_methodology.md](../../../socioeconomic_methodology.md)
- Configuración: [socioeconomic.yaml](../../../../config/layers/socioeconomic.yaml)
- Implementación: [socioeconomic.py](../../../../src/exposome/socioeconomic.py)
- Revisión: [socioeconomic.md](../../../review_prompts/socioeconomic.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers socioeconomic --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/socioeconomic/socioeconomic_exposome_rm_santiago.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/socioeconomic/socioeconomic_exposome_rm_santiago.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/socioeconomic/socioeconomic_exposome_rm_santiago_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/socioeconomic/socioeconomic_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; columnas nucleo completas; metadata consistente; reproduccion confirmada usando cache local; integracion correcta al master. Validacion externa oficial queda como mejora futura no bloqueante.
