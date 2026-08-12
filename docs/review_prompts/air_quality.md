# Revision de capa: air_quality

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Calidad del aire legacy` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers air_quality --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_exposome_rm_santiago_metadata.json`
- Metodologia: `docs/air_quality_legacy_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/air_quality/air_quality_before_after_satellite.png`

## Checklist
- Confirmar que el CSV legacy existe, tiene 52 comunas, conserva PM2.5 solo como comparador y que `name` no tiene duplicados ni faltantes.
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- Confirmar que el master contiene `n_grid` y `no2_who_ratio`, nunca PM2.5 CAMS.
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: air_quality
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
