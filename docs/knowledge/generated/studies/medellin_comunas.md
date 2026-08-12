<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "medellin_comunas"
location: "co/medellin"
hidden: false
generated: true
---

# Estudio: medellin_comunas

- Configuración: [medellin_comunas.yaml](../../../../config/studies/medellin_comunas.yaml)
- Ubicación: `co/medellin`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `comuna_corregimiento`
- Unidades esperadas: `21`

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
exposome run --study medellin_comunas --dry-run
exposome run --study medellin_comunas --resume
exposome publish --study medellin_comunas
exposome verify --study medellin_comunas
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
