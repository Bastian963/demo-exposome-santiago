# ADR 0007: el soporte espacial anual es atómico

- Estado: aceptado
- Fecha: 2026-07-21
- Alcance: publicación y renderizado de series temporales en todos los estudios

## Contexto

Una tabla anual puede cambiar correctamente mientras el mapa conserva el COG
promedio o vuelve a polígonos administrativos. Esa mezcla hace que el selector
parezca una serie espacial aunque cambie de soporte al elegir un año. Los
límites administrativos delimitan y permiten consultas, pero no reemplazan los
píxeles de un método raster.

## Decisión

Cuando `temporal_indicators.<id>.spatial_target.required_for_production` es
`true`, la serie es atómica: todos los años declarados en `expected_years`
deben publicar un `detail` específico de esa cosecha y del tipo declarado.

- `native_raster`: COG con grilla fuente canónica, hash, sidecar, soporte
  preservado y `temporal_support.year` idéntico al año seleccionado.
- `analysis_grid`: GeoJSON real, alineado a la grilla métrica del AOI, con hash,
  sidecar y soporte temporal idéntico.
- Distintos años deben tener contenido fuente distinto.
- Toda la serie comparte un dominio cromático.
- El COG base o promedio nunca se hereda en un año particular.
- Si falta un año, la publicación de producción falla y la app oculta el
  selector completo. Un estado obsoleto queda marcado como no disponible,
  nunca como mapa comunal silencioso.

Los métodos cuyo soporte original es administrativo, una encuesta, un snapshot
OSM o un compuesto sin una escala única conservan
`required_for_production: false`. Para ellos la geometría administrativa sigue
siendo el producto honesto y no se fabrica detalle raster.

## Consecuencias

La recolección anual produce conjuntamente tabla y detalle espacial, mantiene
checkpoints por año y cambia su namespace cuando cambia colección, banda,
período o configuración científica. `spatial-audit --strict` y
`resolution-coverage --tier production` verifican también la completitud
temporal. Incorporar una ciudad nueva no requiere reglas de frontend: sus
obligaciones nacen de los `config/layers/*.yaml` resueltos para ese estudio.
