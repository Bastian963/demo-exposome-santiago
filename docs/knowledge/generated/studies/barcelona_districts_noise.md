<!-- GENERATED FILE: do not edit manually -->
---
type: exposome-study
study_id: "barcelona_districts_noise"
location: "es/barcelona"
hidden: false
generated: true
---

# Estudio: barcelona_districts_noise

- Configuración: [barcelona_districts_noise.yaml](../../../../config/studies/barcelona_districts_noise.yaml)
- Ubicación: `es/barcelona`
- Modalidad: `aggregate`
- Período: `2022-01-01` a `2022-12-31`
- Unidad espacial: `distrito`
- Unidades esperadas: `10`

## Capas

- `noise_spain` (sin ficha en el inventario de Santiago)

## Comandos

```bash
exposome run --study barcelona_districts_noise --dry-run
exposome run --study barcelona_districts_noise --resume
exposome publish --study barcelona_districts_noise
exposome verify --study barcelona_districts_noise
```

> Los asistentes no ejecutan recolecciones reales contra proveedores externos.
