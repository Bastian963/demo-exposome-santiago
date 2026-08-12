<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "sao_paulo_distritos"
location: "br/sao_paulo"
hidden: false
generated: true
---

# Estudio: sao_paulo_distritos

- Configuración: [sao_paulo_distritos.yaml](../../../../config/studies/sao_paulo_distritos.yaml)
- Ubicación: `br/sao_paulo`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `distrito`
- Unidades esperadas: `96`

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
exposome run --study sao_paulo_distritos --dry-run
exposome run --study sao_paulo_distritos --resume
exposome publish --study sao_paulo_distritos
exposome verify --study sao_paulo_distritos
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
