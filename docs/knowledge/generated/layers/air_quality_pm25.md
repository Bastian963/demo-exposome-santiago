<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "air_quality_pm25"
category: "master_required"
required: true
generated: true
---

# PM2.5 cronico

Identificador canónico: `air_quality_pm25`.

## Fuentes y navegación

- Metodología: [pm25_methodology.md](../../../pm25_methodology.md)
- Configuración: [pm25.yaml](../../../../config/layers/pm25.yaml)
- Implementación: [pm25.py](../../../../src/exposome/pm25.py)
- Revisión: [air_quality_pm25.md](../../../review_prompts/air_quality_pm25.md)
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
exposome run --study santiago_communes --layers air_quality_pm25 --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/air_quality_pm25/santiago_communes_pm25_acag_2015_2022.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/air_quality_pm25/santiago_communes_pm25_acag_2015_2022.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/air_quality_pm25/santiago_pm25_acag_2015_2022_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/air_quality_pm25/pm25_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Revision completa; mantener capa en master. Recomendada validacion SINCA futura y fijar banda ACAG en config.
