# Revision de capa: neuro_hospitalizations

Usa el entorno `exposome` y ejecuta todo desde la raiz del repo.

## Objetivo
Revisar si `Comparador egresos neuropsiquiatricos` esta lista para marcarse como `checked` en `docs/exposome_status.csv`.

## Archivos principales
- Script: `exposome run --study santiago_communes --layers neuro_hospitalizations --resume`
- CSV: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_communes_neuro_hospitalizations_2011_2020.csv`
- GeoJSON: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_communes_neuro_hospitalizations_2011_2020.geojson`
- Metadata: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/santiago_neuro_hospitalizations_2011_2020_qc.json`
- Metodologia: `docs/neuro_outcomes_methodology.md`
- Figura/mapa: `data/processed/cl/santiago/santiago_communes/neuro_hospitalizations/neuro_outcomes_santiago_4panel.png`

## Checklist
- Confirmar que el CSV existe, contiene comunas validas y permite multiples filas por comuna cuando hay varios outcomes.
- Confirmar que las columnas requeridas para la capa estan presentes.
- Revisar que el script sea reproducible desde la raiz del repo y que sus inputs externos esten documentados.
- Revisar metadata, metodologia, supuestos, limitaciones y unidades de los indicadores.
- No es una capa del master; revisar su rol como validacion/comparador y sus cruces con el master.
- Revisar si existe una figura/mapa suficiente para inspeccion visual; si no existe, proponer la accion minima.

## Respuesta esperada
Devuelve un veredicto breve con este formato:

```text
layer_id: neuro_hospitalizations
review_status: checked|partial|blocked
review_tool: codex|claude|opencode
blockers:
next_action:
final_check: true|false
notes:
```
