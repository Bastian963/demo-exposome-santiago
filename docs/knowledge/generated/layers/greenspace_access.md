<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "greenspace_access"
category: "master_required"
required: true
generated: true
---

# Areas verdes - acceso

Identificador canónico: `greenspace_access`.

## Fuentes y navegación

- Metodología: [greenspace_access_methodology.md](../../../greenspace_access_methodology.md)
- Configuración: [layers.yaml](../../../../config/layers.yaml)
- Implementación: [greenspace_access.py](../../../../src/exposome/greenspace_access.py)
- Revisión: [greenspace_access.md](../../../review_prompts/greenspace_access.md)
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
exposome run --study santiago_communes --layers greenspace_access --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/greenspace_access/santiago_greenspace_access.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/greenspace_access/santiago_greenspace_access.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/greenspace_access/santiago_greenspace_access_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/greenspace_access/greenspace_access_santiago_2panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: CSV GeoJSON metadata figura y tests verificados; metodologia documentada; metadata enriquecida con unidades y limitaciones; cache-first sin GEE; integracion al master correcta.
