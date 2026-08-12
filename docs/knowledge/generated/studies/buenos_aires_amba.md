<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "buenos_aires_amba"
location: "ar/buenos_aires_amba"
hidden: false
generated: true
---

# Estudio: buenos_aires_amba

- Configuración: [buenos_aires_amba.yaml](../../../../config/studies/buenos_aires_amba.yaml)
- Ubicación: `ar/buenos_aires_amba`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `admin_unit`
- Unidades esperadas: `55`

## Capas

- `community_safety` (sin ficha en el inventario de Santiago)
- `community_violence` (sin ficha en el inventario de Santiago)
- `suicide_mortality` (sin ficha en el inventario de Santiago)
- `road_traffic_mortality` (sin ficha en el inventario de Santiago)
- [air_quality_pm25](../layers/air_quality_pm25.md) (configurado como `pm25`)
- [alan](../layers/alan.md)
- [greenspace_coverage](../layers/greenspace_coverage.md)
- [greenspace_multisource](../layers/greenspace_multisource.md)
- [precipitation](../layers/precipitation.md)
- [precipitation_spi](../layers/precipitation_spi.md)
- [climate_heat](../layers/climate_heat.md)
- [climate_openmeteo](../layers/climate_openmeteo.md)
- [air_quality_satellite](../layers/air_quality_satellite.md)
- [air_quality](../layers/air_quality.md)
- [wind](../layers/wind.md)
- [wildfire](../layers/wildfire.md)
- [greenspace_access](../layers/greenspace_access.md)
- [walkability](../layers/walkability.md)
- [social_infrastructure](../layers/social_infrastructure.md)
- [food_environment](../layers/food_environment.md)
- [healthcare](../layers/healthcare.md)

## Comandos

```bash
exposome run --study buenos_aires_amba --dry-run
exposome run --study buenos_aires_amba --resume
exposome publish --study buenos_aires_amba
exposome verify --study buenos_aires_amba
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
