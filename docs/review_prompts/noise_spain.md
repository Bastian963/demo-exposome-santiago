# Revision de capa: noise_spain

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Ruido MER/SICA España` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `python scripts/build_noise_vector_tiles.py --study barcelona_districts_noise --resume`
- CSV: `data/processed/es/barcelona/barcelona_districts_noise/noise_spain/barcelona_districts_noise_noise_spain_mer_2022.csv`
- GeoJSON: `data/processed/es/barcelona/barcelona_districts_noise/noise_spain/barcelona_districts_noise_noise_spain_mer_2022.geojson`
- Metadata: `data/processed/es/barcelona/barcelona_districts_noise/noise_spain/barcelona_districts_noise_noise_spain_mer_2022_metadata.json`
- Metodologia: `docs/noise_spain_methodology.md`
- Figura/mapa: `data/processed/es/barcelona/barcelona_districts_noise/detail/noise_lden.vector_contours.json`

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
layer_id: noise_spain
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
