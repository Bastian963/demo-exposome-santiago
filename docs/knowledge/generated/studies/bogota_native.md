<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "bogota_native"
location: "co/bogota"
hidden: true
generated: true
---

# Estudio: bogota_native

- Configuración: [bogota_native.yaml](../../../../config/studies/bogota_native.yaml)
- Ubicación: `co/bogota`
- Modalidad: `native`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `no declarada`
- Unidades esperadas: `no declarado`

## Capas

- [air_quality_pm25](../layers/air_quality_pm25.md)
- [alan](../layers/alan.md)
- [greenspace_coverage](../layers/greenspace_coverage.md)
- [greenspace_multisource](../layers/greenspace_multisource.md)
- [precipitation](../layers/precipitation.md)
- [climate_heat](../layers/climate_heat.md)
- [wind](../layers/wind.md)
- [wildfire](../layers/wildfire.md)
- [air_quality_satellite](../layers/air_quality_satellite.md)
- [greenspace_access](../layers/greenspace_access.md)
- [walkability](../layers/walkability.md)
- [social_infrastructure](../layers/social_infrastructure.md)
- [food_environment](../layers/food_environment.md)
- [healthcare](../layers/healthcare.md)

## Comandos

```bash
exposome run --study bogota_native --dry-run
exposome run --study bogota_native --resume
exposome publish --study bogota_native
exposome verify --study bogota_native
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
