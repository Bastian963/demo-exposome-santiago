<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "climate_heat"
category: "master_required"
required: true
generated: true
---

# Clima y calor urbano

Identificador canónico: `climate_heat`.

## Fuentes y navegación

- Metodología: [climate_heat_methodology.md](../../../climate_heat_methodology.md)
- Configuración: [climate_heat.yaml](../../../../config/layers/climate_heat.yaml)
- Revisión: [climate_heat.md](../../../review_prompts/climate_heat.md)
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
exposome run --study santiago_communes --layers climate_heat --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/climate_heat/climate_heat_exposome_rm_santiago.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/climate_heat/climate_heat_exposome_rm_santiago.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/climate_heat/santiago_communes_climate_heat_era5land_2024_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/climate_heat/climate_heat_santiago_pub.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: ERA5-Land es la fuente canónica cache-first; métricas por píxel nativo y agregación posterior ponderada por área sin fallback administrativo; Open-Meteo queda como comparador legacy separado; metodología y master integration documentados.
