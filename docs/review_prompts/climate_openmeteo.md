# Revision de capa: climate_openmeteo

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Metricas climaticas anuales` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers climate_openmeteo --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/santiago_climate_metrics_annual_metadata.json`
- Metodologia: `docs/climate_openmeteo_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/climate_openmeteo/climate_metrics_santiago.png`

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
layer_id: climate_openmeteo
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
