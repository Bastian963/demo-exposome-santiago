<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "walkability"
category: "master_optional"
required: false
generated: true
---

# Caminabilidad

Identificador canónico: `walkability`.

## Fuentes y navegación

- Metodología: [walkability_methodology.md](../../../walkability_methodology.md)
- Configuración: [walkability.yaml](../../../../config/layers/walkability.yaml)
- Implementación: [walkability.py](../../../../src/exposome/walkability.py)
- Revisión: [walkability.md](../../../review_prompts/walkability.md)
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
exposome run --study santiago_communes --layers walkability --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/walkability/santiago_walkability.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/walkability/santiago_walkability.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/walkability/santiago_walkability_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/walkability/walkability_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; metricas de red OSM (osmnx network_type=all) en EPSG:32719; top 5 La Granja/Ñuñoa/Providencia/San Joaquín/San Ramón (grids densos del inner ring); bottom 5 rurales (San José de Maipo/San Pedro/Alhué/Tiltil/Curacaví); walk_index 0-100 percentil-rescaled; figura 4-panel con edgecolor white; 21 tests offline pasan; integracion al master verificada.
