<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "precipitation"
category: "master_required"
required: true
generated: true
---

# Precipitacion CHIRPS

Identificador canónico: `precipitation`.

## Fuentes y navegación

- Metodología: [precipitation_methodology.md](../../../precipitation_methodology.md)
- Configuración: [precipitation.yaml](../../../../config/layers/precipitation.yaml)
- Implementación: [precipitation.py](../../../../src/exposome/precipitation.py)
- Revisión: [precipitation.md](../../../review_prompts/precipitation.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [bogota_localidades](../studies/bogota_localidades.md)
- [bogota_native](../studies/bogota_native.md)
- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [buenos_aires_amba_native](../studies/buenos_aires_amba_native.md)
- [buenos_aires_comunas](../studies/buenos_aires_comunas.md)
- [buenos_aires_zipcodes](../studies/buenos_aires_zipcodes.md)
- [caba_native](../studies/caba_native.md)
- [cdmx_alcaldias](../studies/cdmx_alcaldias.md)
- [cdmx_native](../studies/cdmx_native.md)
- [lima_distritos](../studies/lima_distritos.md)
- [lima_native](../studies/lima_native.md)
- [medellin_comunas](../studies/medellin_comunas.md)
- [medellin_native](../studies/medellin_native.md)
- [san_juan_departamentos](../studies/san_juan_departamentos.md)
- [santiago_communes](../studies/santiago_communes.md)
- [santiago_native](../studies/santiago_native.md)
- [sao_paulo_distritos](../studies/sao_paulo_distritos.md)
- [sao_paulo_native](../studies/sao_paulo_native.md)
- [valle_aburra_municipios](../studies/valle_aburra_municipios.md)
- [valle_aburra_native](../studies/valle_aburra_native.md)

## Ejecución

```bash
exposome run --study santiago_communes --layers precipitation --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/precipitation/santiago_communes_precipitation_chirps_2015_2024.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/precipitation/santiago_communes_precipitation_chirps_2015_2024.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/precipitation/santiago_precipitation_chirps_2015_2024.json`
- Figura: `data/processed/cl/santiago/santiago_communes/precipitation/precipitation_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; CHIRPS daily reproducible cache-first; metadata enriquecida con columns_description y limitations; metodologia documentada con brain health; figura 4-panel dedicada; tests en verde; integracion master correcta.
