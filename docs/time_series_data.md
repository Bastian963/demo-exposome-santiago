# Series temporales en la webapp

La webapp soporta tres contratos, en este orden:

1. `manifest.temporal_indicators`: contrato moderno por estudio, con años,
   archivo tabular, columna, checksum y procedencia.
2. `has_annual`: compatibilidad con GeoJSON anuales antiguos, como PM2.5 de
   Santiago.
3. `year_columns`: cosechas que ya viajan como columnas del master.

Los archivos del contrato moderno se cargan sólo al elegir un año y se unen a
la geometría del master mediante `spatial_id`. El selector no se muestra si el
bundle activo no publicó años válidos. Los perfiles usan exactamente las mismas
tablas para construir `profile.timeseries`.

## Detalle espacial anual

Una tabla anual y su detalle espacial son activos distintos. El mapa sólo
activa un COG o una grilla analítica desde
`temporal_indicators.<id>.years.<año>.detail` cuando:

- `temporal_support.kind` es `year` y su año coincide con la cosecha activa;
- el descriptor y el sidecar prueban grilla fuente canónica, soporte conservado
  y hash del contenido;
- los hashes de los distintos años no se repiten;
- todos los años usan el mismo `temporal_indicators.<id>.color_domain`.

Para un `spatial_target.required_for_production: true`, la serie es atómica. Si
falta el detalle de un solo `expected_year`, la publicación de producción falla
y la app oculta el selector completo. Nunca superpone el COG crónico/promedio ni
convierte silenciosamente esa cosecha en un mapa administrativo. Las series de
origen administrativo o compuesto pueden declarar el detalle como no exigible.
El COG agregado del período sólo corresponde a la vista base/promedio y debe
declarar `temporal_support.kind: period`.

PM2.5 ACAG publica los valores anuales tabulares y, tras la recolección nativa,
un raster 0,01° específico por año. La publicación calcula una escala cromática
robusta común sobre todos esos rasters para que la animación sea comparable.
La misma regla cubre NO₂, ALAN, calor ERA5-Land, lluvia CHIRPS, viento ERA5-Land
y la grilla anual de verde Dynamic World.

## Contrato visual del selector

Tooltip, indicador de píxel, leyenda y preview del monitor deben mostrar el
mismo valor formateado y la misma unidad. El tooltip siempre incluye el nombre
de la unidad bajo el cursor y el soporte activo. La barra de color conserva un
ancho de 320 px; los nombres largos se envuelven sin estirarla.

No se crean series históricas para snapshots OSM ni para el dosel Meta
estático. Los índices compuestos de calor y lluvia permanecen como resúmenes del
período; sus subindicadores medidos sí pueden ser anuales.

El flujo operativo y los comandos multi-ciudad están documentados en
[`multicity_annual_exposomes.md`](multicity_annual_exposomes.md).
