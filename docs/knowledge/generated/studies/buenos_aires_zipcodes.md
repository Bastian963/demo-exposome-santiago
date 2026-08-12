<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "buenos_aires_zipcodes"
location: "ar/buenos_aires"
hidden: false
generated: true
---

# Estudio: buenos_aires_zipcodes

- Configuración: [buenos_aires_zipcodes.yaml](../../../../config/studies/buenos_aires_zipcodes.yaml)
- Ubicación: `ar/buenos_aires`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `postal_code`
- Unidades esperadas: `no declarado`

## Capas

- [air_quality_pm25](../layers/air_quality_pm25.md) (configurado como `pm25`)
- [alan](../layers/alan.md)
- [greenspace_coverage](../layers/greenspace_coverage.md)
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
exposome run --study buenos_aires_zipcodes --dry-run
exposome run --study buenos_aires_zipcodes --resume
exposome publish --study buenos_aires_zipcodes
exposome verify --study buenos_aires_zipcodes
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
