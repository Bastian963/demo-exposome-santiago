<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "valle_aburra_municipios"
location: "co/valle_aburra"
hidden: false
generated: true
---

# Estudio: valle_aburra_municipios

- Configuración: [valle_aburra_municipios.yaml](../../../../config/studies/valle_aburra_municipios.yaml)
- Ubicación: `co/valle_aburra`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `municipio`
- Unidades esperadas: `10`

## Capas

- [air_quality_pm25](../layers/air_quality_pm25.md) (configurado como `pm25`)
- [air_quality_satellite](../layers/air_quality_satellite.md)
- [alan](../layers/alan.md)
- [greenspace_coverage](../layers/greenspace_coverage.md)
- [greenspace_multisource](../layers/greenspace_multisource.md)
- [precipitation](../layers/precipitation.md)
- [climate_heat](../layers/climate_heat.md)
- [wind](../layers/wind.md)
- [wildfire](../layers/wildfire.md)
- [greenspace_access](../layers/greenspace_access.md)
- [walkability](../layers/walkability.md)
- [social_infrastructure](../layers/social_infrastructure.md)
- [food_environment](../layers/food_environment.md)
- [healthcare](../layers/healthcare.md)

## Comandos

```bash
exposome run --study valle_aburra_municipios --dry-run
exposome run --study valle_aburra_municipios --resume
exposome publish --study valle_aburra_municipios
exposome verify --study valle_aburra_municipios
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
