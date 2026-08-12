<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "wind"
category: "master_optional"
required: false
generated: true
---

# Wind

Identificador canónico: `wind`.

## Fuentes y navegación

- Metodología: [wind_methodology.md](../../../wind_methodology.md)
- Configuración: [wind.yaml](../../../../config/layers/wind.yaml)
- Implementación: [wind.py](../../../../src/exposome/wind.py)
- Revisión: [wind.md](../../../review_prompts/wind.md)
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
exposome run --study santiago_communes --layers wind --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/wind/santiago_communes_wind.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/wind/santiago_communes_wind.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/wind/santiago_wind_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/wind/wind_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: v1.1 upgrade: 12 nuevas columnas estacionales (winter/summer speed, p99, calm, u, v, dir) generadas via GEE cache-first; winter calma >> annual calma (mayoria de comunas 60%+, lock-in por test_winter_calm_ge_annual_calm); 26 tests OK (4 nuevos: seasonal_columns_present, seasonal_speed_sane_range, seasonal_dir_in_range, winter_calm_ge_annual_calm); figura 4-panel wind_santiago_seasonal.png; master 264 -> 276 cols; 17/52 comunas comparten pixel ERA5 (documentado); doc con seccion Seasonal analysis (winter vs summer).
