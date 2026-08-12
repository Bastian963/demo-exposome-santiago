<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "public_transport"
category: "master_optional"
required: false
generated: true
---

# Transporte publico

Identificador canónico: `public_transport`.

## Fuentes y navegación

- Metodología: [public_transport_methodology.md](../../../public_transport_methodology.md)
- Configuración: [public_transport.yaml](../../../../config/layers/public_transport.yaml)
- Implementación: [public_transport.py](../../../../src/exposome/public_transport.py)
- Revisión: [public_transport.md](../../../review_prompts/public_transport.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers public_transport --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/public_transport/santiago_public_transport.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/public_transport/santiago_public_transport.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/public_transport/santiago_public_transport_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/public_transport/public_transport_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; 11815 paraderos RED unicos + 137 estaciones Metro S.A. deduplicadas (25m snap); 27 comunas con Metro (L1-L6); top 5 Santiago/Lo Prado/Providencia/Ñuñoa/San Miguel (corredor L1); bottom 5 rurales sin Metro (San José de Maipo/Lo Barnechea/Alhué/Curacaví/Colina); transit_index 0-100 con Metro doblando puntaje; sentinel 50000m para comunas sin Metro documentado; figura 4-panel con edgecolor white; 24 tests offline pasan; integracion al master verificada.
