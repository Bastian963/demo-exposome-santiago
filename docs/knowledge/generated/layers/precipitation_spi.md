<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "precipitation_spi"
category: "master_required"
required: true
generated: true
---

# Sequias SPI

Identificador canónico: `precipitation_spi`.

## Fuentes y navegación

- Metodología: [precipitation_methodology.md](../../../precipitation_methodology.md)
- Configuración: [precipitation_spi.yaml](../../../../config/layers/precipitation_spi.yaml)
- Implementación: [precipitation_spi.py](../../../../src/exposome/precipitation_spi.py)
- Revisión: [precipitation_spi.md](../../../review_prompts/precipitation_spi.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [santiago_communes](../studies/santiago_communes.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers precipitation_spi --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/precipitation_spi/santiago_precipitation_spi.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/precipitation_spi/santiago_precipitation_spi.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/precipitation_spi/santiago_precipitation_spi_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/precipitation_spi/precipitation_spi_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa cerrada (SPI-3/6/12 sobre CHIRPS 2015-2024; 13 tests OK; byte-identical cache-first)
