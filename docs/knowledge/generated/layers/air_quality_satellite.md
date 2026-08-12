<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "air_quality_satellite"
category: "master_required"
required: true
generated: true
---

# Calidad del aire satelital

Identificador canónico: `air_quality_satellite`.

## Fuentes y navegación

- Metodología: [plan_a_plus_methodology.md](../../../plan_a_plus_methodology.md)
- Configuración: [air_quality_satellite.yaml](../../../../config/layers/air_quality_satellite.yaml)
- Implementación: [air_quality.py](../../../../src/exposome/air_quality.py)
- Revisión: [air_quality_satellite.md](../../../review_prompts/air_quality_satellite.md)
- Dashboard: [estado de exposomas](../../../exposome_status.md)

## Estudios

- [bogota_localidades](../studies/bogota_localidades.md)
- [bogota_native](../studies/bogota_native.md)
- [buenos_aires_amba](../studies/buenos_aires_amba.md)
- [buenos_aires_amba_native](../studies/buenos_aires_amba_native.md)
- [buenos_aires_comunas](../studies/buenos_aires_comunas.md)
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
exposome run --study santiago_communes --layers air_quality_satellite --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/air_quality_satellite/santiago_air_quality_satellite_2024.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/air_quality_satellite/santiago_air_quality_satellite_2024.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/air_quality_satellite/santiago_communes_air_quality_satellite_2024_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/air_quality_satellite/air_quality_satellite_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: v1.1 audit: o3_surface_ug_m3 (15718-21785 ug/m3) y o3_who_ratio (261-363) removidos del CSV/master porque S5P O3 es columna total con ~90% estratosferico; formula column*M/BLH sobre-estimaba surface 5-10x; o3_mean se mantiene para ranking relativo; o3_peak_season removido de who_guidelines; nuevo test de regresion test_o3_surface_columns_dropped lock-in que esas cols no reaparezcan; master -2 cols (264 -> 262 transitorio, recompuesto con wind a 274 total); doc section 7.1 + 7.5 documentan el cambio.
