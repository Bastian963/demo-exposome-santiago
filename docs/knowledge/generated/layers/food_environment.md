<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-layer
layer_id: "food_environment"
category: "master_optional"
required: false
generated: true
---

# Entorno alimentario

Identificador canónico: `food_environment`.

## Fuentes y navegación

- Metodología: [food_environment_methodology.md](../../../food_environment_methodology.md)
- Configuración: [food_environment.yaml](../../../../config/layers/food_environment.yaml)
- Implementación: [food_environment.py](../../../../src/exposome/food_environment.py)
- Revisión: [food_environment.md](../../../review_prompts/food_environment.md)
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
exposome run --study santiago_communes --layers food_environment --resume
```

## Artefactos esperados

- CSV: `data/processed/cl/santiago/santiago_communes/food_environment/santiago_food_environment.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/food_environment/santiago_food_environment.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/food_environment/santiago_food_environment_metadata.json`
- Figura: `data/processed/cl/santiago/santiago_communes/food_environment/food_environment_santiago_4panel.png`

## Estado

- Automático: `ready_for_review`
- Revisión: `checked`
- Integrado en master: `true`
- Check final: `true`
- Bloqueadores: —
- Próxima acción: Capa auditada: 52 comunas; metricas OSM con gap estructural documentado (solo 596 supermercados capturados; 0 en greengrocer/marketplace/fast_food/convenience por cobertura OSM Chile insuficiente, no por bug en modulo); food_mrfei degenerado (100 en 51/52 comunas); food_swamp_ratio = 0 en todas; food_index se reduce a composite de healthy_density + distancia al supermercado (Spearman r = -0.85 con mean_dist_supermarket_m); doc de metodologia con bloque Critical coverage gap; metadata con coverage_gap explicito y 4 remediation_steps (~6-8h); plot 4-panel con edgecolor white; 25 tests pasan (incluyendo asserts que lock-in el gap para detectar regresiones silenciosas si OSM Chile mejora la cobertura); integracion al master verificada (13 columnas).
