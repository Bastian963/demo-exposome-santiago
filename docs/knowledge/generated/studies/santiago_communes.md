<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "santiago_communes"
location: "cl/santiago"
hidden: false
generated: true
---

# Estudio: santiago_communes

- Configuración: [santiago_communes.yaml](../../../../config/studies/santiago_communes.yaml)
- Ubicación: `cl/santiago`
- Modalidad: `aggregate`
- Período: `2015-01-01` a `2024-12-31`
- Unidad espacial: `commune`
- Unidades esperadas: `52`

## Capas

- [socioeconomic](../layers/socioeconomic.md)
- [air_quality](../layers/air_quality.md)
- [air_quality_pm25](../layers/air_quality_pm25.md) (configurado como `pm25`)
- [heavy_metals](../layers/heavy_metals.md)
- [air_quality_satellite](../layers/air_quality_satellite.md)
- [alan](../layers/alan.md)
- [sleep_context](../layers/sleep_context.md)
- [greenspace_coverage](../layers/greenspace_coverage.md)
- [greenspace_multisource](../layers/greenspace_multisource.md)
- [precipitation](../layers/precipitation.md)
- [precipitation_spi](../layers/precipitation_spi.md)
- [climate_heat](../layers/climate_heat.md)
- [climate_openmeteo](../layers/climate_openmeteo.md)
- [wind](../layers/wind.md)
- [wildfire](../layers/wildfire.md)
- [noise](../layers/noise.md)
- [greenspace_access](../layers/greenspace_access.md)
- [walkability](../layers/walkability.md)
- [public_transport](../layers/public_transport.md)
- [social_infrastructure](../layers/social_infrastructure.md)
- [food_environment](../layers/food_environment.md)
- [healthcare](../layers/healthcare.md)
- [demography](../layers/demography.md)
- [food_insecurity](../layers/food_insecurity.md)
- [pobreza_sae](../layers/pobreza_sae.md)
- [greenspace_cv](../layers/greenspace_cv.md)
- [neuro_mortality](../layers/neuro_mortality.md)
- [neuro_hospitalizations](../layers/neuro_hospitalizations.md)

## Comandos

```bash
exposome run --study santiago_communes --dry-run
exposome run --study santiago_communes --resume
exposome publish --study santiago_communes
exposome verify --study santiago_communes
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
