<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "wildfire"
category: "master_required"
required: true
generated: true
---

# Incendios forestales

Identificador canónico: `wildfire`.

## Fuentes y navegación

- Metodología: [wildfire_methodology.md](../../../wildfire_methodology.md)
- Configuración: [wildfire.yaml](../../../../config/layers/wildfire.yaml)
- Implementación: [wildfire.py](../../../../src/exposome/wildfire.py)
- Revisión: [wildfire.md](../../../review_prompts/wildfire.md)
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
exposome run --study santiago_communes --layers wildfire --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/wildfire/wildfire_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; MODIS MCD64A1 + FIRMS reproducibles cache-first; metodología documentada con limitaciones y brain health; figura 4-panel; tests en verde; integración master correcta.
