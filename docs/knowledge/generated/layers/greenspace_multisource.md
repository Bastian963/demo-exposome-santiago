<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "greenspace_multisource"
category: "master_required"
required: true
generated: true
---

# Areas verdes - integración multifuente

Identificador canónico: `greenspace_multisource`.

## Fuentes y navegación

- Metodología: [greenspace_multisource_methodology.md](../../../greenspace_multisource_methodology.md)
- Configuración: [layers.yaml](../../../../config/layers.yaml)
- Implementación: [greenspace_multisource.py](../../../../src/exposome/greenspace_multisource.py)
- Revisión: [greenspace_multisource.md](../../../review_prompts/greenspace_multisource.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [bogota_localidades](../studies/bogota_localidades.md)
- [bogota_native](../studies/bogota_native.md)
- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [buenos_aires_amba_native](../studies/buenos_aires_amba_native.md)
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
exposome run --study santiago_communes --layers greenspace_multisource --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/greenspace_multisource/santiago_communes_greenspace_multisource.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/greenspace_multisource/santiago_communes_greenspace_multisource.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/greenspace_multisource/santiago_communes_greenspace_multisource_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/greenspace_multisource/figures/greenspace_multisource_santiago_communes_2panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `not_started`
- Integrado en master: `true`
- Check final: `false`
- Bloqueadores: —
- Próxima acción: Abrir sesion de revision con el prompt de la capa.
