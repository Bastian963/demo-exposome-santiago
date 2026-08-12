# Revision de capa: healthcare

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Acceso a salud` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers healthcare --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/healthcare/santiago_healthcare_access.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/healthcare/santiago_healthcare_access.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/healthcare/santiago_healthcare_access_metadata.json`
- Metodologia: `docs/healthcare_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/healthcare/healthcare_access_santiago.png`

## Checklist
- Confirmar que el CSV existe, tiene 52 unidades y `spatial_id` sin duplicados ni faltantes.
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- Debe verificarse integración en `master.csv` y en el `release_manifest.json` del estudio.
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: healthcare
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
