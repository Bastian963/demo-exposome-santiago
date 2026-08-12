<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "san_juan_departamentos"
location: "ar/san_juan"
hidden: false
generated: true
---

# Estudio: san_juan_departamentos

- Configuración: [san_juan_departamentos.yaml](../../../../config/studies/san_juan_departamentos.yaml)
- Ubicación: `ar/san_juan`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `departamento`
- Unidades esperadas: `19`

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
exposome run --study san_juan_departamentos --dry-run
exposome run --study san_juan_departamentos --resume
exposome publish --study san_juan_departamentos
exposome verify --study san_juan_departamentos
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
