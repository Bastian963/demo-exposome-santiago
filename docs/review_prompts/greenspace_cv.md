# Revision de capa: greenspace_cv

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Validacion CV de vegetacion` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers greenspace_cv --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/greenspace_cv/santiago_greenspace_cv_commune.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/greenspace_cv/missing.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/greenspace_cv/greenspace_cv_metadata.json`
- Metodologia: `docs/greenspace_cv_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/greenspace_cv/greenspace_cv_santiago.png`

## Checklist
- Confirmar que el CSV existe, tiene 52 unidades y `spatial_id` sin duplicados ni faltantes.
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- No es una capa del master; revisar su rol como validacion/comparador y sus cruces con el master.
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: greenspace_cv
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
