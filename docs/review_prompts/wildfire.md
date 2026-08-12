# Revision de capa: wildfire

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Incendios forestales` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers wildfire --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/wildfire/santiago_wildfire_2015_2024_metadata.json`
- Metodologia: `docs/wildfire_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/wildfire/wildfire_santiago_4panel.png`

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
layer_id: wildfire
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
