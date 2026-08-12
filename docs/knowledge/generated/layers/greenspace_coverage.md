<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "greenspace_coverage"
category: "master_required"
required: true
generated: true
---

# Areas verdes - cobertura satelital

Identificador canónico: `greenspace_coverage`.

## Fuentes y navegación

- Metodología: [greenspace_coverage_methodology.md](../../../greenspace_coverage_methodology.md)
- Configuración: [layers.yaml](../../../../config/layers.yaml)
- Implementación: [greenspace_satellite.py](../../../../src/exposome/greenspace_satellite.py)
- Revisión: [greenspace_coverage.md](../../../review_prompts/greenspace_coverage.md)
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
exposome run --study santiago_communes --layers greenspace_coverage --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/greenspace_coverage/santiago_greenspace_coverage.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/greenspace_coverage/santiago_greenspace_coverage.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/greenspace_coverage/santiago_greenspace_coverage_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/greenspace_coverage/greenspace_coverage_santiago_2panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: CSV GeoJSON metadata figura y tests verificados; EVI saneado (evi_max<=0.999 tras mascara); metodologia documentada; integracion al master correcta; rebuild master propagó EVI saneado.
