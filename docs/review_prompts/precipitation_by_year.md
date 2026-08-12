# Revision de capa: precipitation_by_year

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Precipitation By Year` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `python scripts/run_precipitation_by_year.py`
- CSV: `data/processed/santiago_precipitation_by_year.csv`
- GeoJSON: `data/processed/santiago_precipitation_by_year.geojson`
- Metadata: `data/processed/santiago_precipitation_by_year_metadata.json`
- Metodologia: `docs/precipitation_methodology.md`
- Figura/mapa: `pendiente`

## Checklist
- Confirmar que el CSV existe, tiene 52 comunas y columna `name` sin duplicados ni faltantes.
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- Debe verificarse integracion en `scripts/build_master_exposome.py` y en `data/processed/santiago_exposome_master.csv`.
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: precipitation_by_year
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
