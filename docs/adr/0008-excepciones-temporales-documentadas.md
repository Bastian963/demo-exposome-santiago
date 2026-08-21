# ADR 0008: excepciones temporales documentadas para huecos permanentes de fuente

- Estado: aceptado
- Fecha: 2026-07-27
- Alcance: publicación de series anuales espaciales en todos los estudios

## Contexto

[ADR 0007](0007-annual-spatial-support-is-atomic.md) exige que, cuando
`temporal_indicators.<id>.spatial_target.required_for_production` es `true`,
todos los años de `expected_years` publiquen `detail`; si falta uno, «la
publicación **de producción** falla y la app oculta el selector completo»
(ADR 0007, punto 5). Ese diseño asume que un año faltante es temporal:
provisión pendiente, corrida no completada, error a reintentar.

`bogota_localidades`/`greenspace_multisource` expuso un caso distinto. Dynamic
World (composite Oct–Mar) devuelve cero píxeles válidos para la localidad Los
Mártires en 2019, de forma determinista — confirmado dos veces contra los
zonal stats cacheados. Las otras 19 localidades y los otros 8 años (2016–2018,
2020–2024) están completos
(`docs/greenspace_multisource_methodology.md#limitations`). Reintentar no
cambia el resultado: no es un estado transitorio, es un hueco de fuente
permanente para una celda espacio-temporal específica.

Sin un mecanismo para esto, `exposome publish` aborta indefinidamente dentro
de `_write_temporal_assets()` (`src/exposome/publishing.py`), y no hay forma
de publicar el resto del estudio — 13 de 14 capas completas y correctas — sin
alguna de estas dos malas opciones: (a) editar a mano el `raise` para saltear
el chequeo (deja de proteger contra huecos reales en otros estudios), o (b)
inventar un valor para 2019 (viola el principio de ADR 0007 de nunca fabricar
detalle).

## Decisión

Un estudio puede declarar `temporal_exceptions` en su
`config/studies/<id>.yaml`:

```yaml
temporal_exceptions:
  - layer_id: greenspace_multisource
    indicator: green
    years: [2019]
    reason: >-
      Motivo verificable, no "no disponible" sin más.
    doc: docs/greenspace_multisource_methodology.md#limitations
```

- `layer_id` debe estar entre las capas habilitadas del estudio; si no, la
  excepción es letra muerta y `studies.py` falla al parsear.
- `reason` y `doc` son obligatorios y no vacíos: una excepción sin motivo
  verificable no es una excepción, es un agujero en el contrato.
- La excepción actúa a nivel de **capa** (`spec.layer_id`), no de indicador
  individual — coincide con la granularidad con la que
  `_write_temporal_assets()` y `discover_temporal_specs()` ya evalúan
  `missing_years`. Si una capa futura con múltiples indicadores requeridos
  necesita exceptuar sólo uno, el chequeo deberá bajar a nivel de indicador
  antes de declarar esa excepción.

Publicación y auditoría honran la excepción **sin tocar `expected_years`**:

1. `_write_temporal_assets()` resta los años exceptuados de esa capa antes de
   decidir si aborta. Un año faltante **no declarado** sigue abortando la
   publicación exactamente como antes — el forzante de ADR 0007 no se debilitó
   para el resto del sistema, sólo para la celda específica documentada.
2. El manifest publicado agrega, junto a `expected_years` (que sigue listando
   los N años completos, sin recortar), dos campos nuevos:
   `excepted_years: ["2019"]` y `exceptions: [{year, reason, doc}]`.
3. `spatial_audit._audit_temporal_details()` con `--strict` resta
   `excepted_years` de `expected_years` antes de calcular `missing_years` y
   `missing_detail`, y agrega dos validaciones propias: todo año exceptuado
   debe estar dentro de `expected_years` (una excepción no puede *agregar* un
   año fuera de la serie declarada), y debe tener su `reason` correspondiente
   en `exceptions`.
4. `spatial_coverage.py` (`resolution-coverage`) **no cambia**. Sigue
   evaluando `expected_years` completo sin descontar la excepción, así que el
   indicador exceptuado sigue reportándose `missing` y el estudio permanece en
   `publication_tier: preview`, nunca vuelve a `production` en silencio.
5. `run_missing_annual_exposomes.py` conserva la fila pendiente en su
   inventario, pero excluye el `(layer_id, year)` documentado de la cola de
   reintentos y de `--require-complete`. Así un supervisor multiciudad puede
   publicar el resto del estudio sin volver a llamar al proveedor para un hueco
   ya confirmado; su salida informa por separado los objetivos exceptuados y
   los objetivos requeridos completos.
6. `run_multicity_overnight.py` detecta la excepción declarada y ejecuta
   `resolution-coverage --tier preview` para su bundle de staging y el bundle
   publicado. No reemplaza el gate temporal: los años faltantes que no estén
   declarados siguen bloqueando la publicación antes de llegar a esa auditoría.
   Sin excepciones documentadas, el supervisor conserva `--tier production`.

En el navegador, `temporalSeriesSpatiallyComplete()`
(`webapp/src/data-repository.js`) ya evalúa si `years` cubre todo
`expected_years` — sin cambios de código ahí. Como la excepción nunca toca
`expected_years`, la serie sigue viéndose incompleta: el selector temporal de
ese indicador se oculta (`studyAnnualYears()` devuelve `[]`, `choropleth.js`
cae a `{ column: expo.column, yearLabel: null }` en vez de un año puntual),
pero el indicador en sí sigue visible con su soporte espacial habitual — si
publica grilla fina (`subcomuna/*.geojson`) o COG, esa capa se sigue
renderizando; el bloqueo temporal no la colapsa a un choropleth
administrativo, sólo retira el eje de años. Verificado en vivo para
`bogota_localidades`/`green`: la grilla fina de 1.861 celdas
(`subcomuna/green.geojson`) se renderiza con el rótulo de período «Dynamic
World · meses peak Oct–Mar 2024» y sin selector de años. No hay fallback
comunal silencioso: la ausencia se declara, no se disimula.

## Alternativas consideradas

- **Editar el `raise` para ignorar cualquier hueco:** descartado — reabriría
  la puerta que ADR 0007 cerró; un hueco real de recolección en otro estudio
  pasaría desapercibido.
- **Interpolar o rellenar el valor faltante:** descartado — fabricar un dato
  donde Dynamic World no observó nada viola directamente el principio de
  «nunca se fabrica detalle» de ADR 0004/0007.
- **Recortar `expected_years` para que el año faltante deje de exigirse:**
  descartado — borraría la evidencia de que 2019 existe en el período del
  estudio y le mentiría al selector, que volvería a mostrar una serie
  «completa» de 8 años sin explicar el hueco.
- **Un flag de CLI (`--allow-incomplete-temporal`) en vez de config
  declarada:** descartado como mecanismo principal — no deja rastro en el
  manifest, hay que recordarlo en cada republicación, y podría aplicarse por
  error a un estudio donde el hueco sí es un bug real. Una excepción en el
  YAML del estudio es durable, auto-documentada y no se filtra entre
  estudios.

## Consecuencias

- Un estudio con un hueco de fuente permanente y documentado puede publicarse
  en `preview` con 13/14 (o N-1/N) indicadores completos, en vez de bloquearse
  indefinidamente.
- La consecuencia de tier es explícita y deliberada: `resolution-coverage`
  sigue exigiendo la serie completa para `production`. Ninguna excepción sube
  de tier por sí sola; el supervisor verifica explícitamente `preview` para
  permitir publicar el resto del estudio declarado.
- Toda excepción queda grabada en `config/studies/<id>.yaml` (fuente de
  verdad versionada) y viaja al `manifest.json` publicado — auditable sin
  releer el código de la capa.
- Declarar una excepción sin un motivo verificable y sin apuntar a
  documentación de metodología no es válido: `studies.py`,
  `spatial_audit.py` y las pruebas asociadas lo rechazan.
- Ver [`bogota_localidades.yaml`](../../config/studies/bogota_localidades.yaml)
  para el primer uso real de este mecanismo, y
  [`publicar-resolucion-espacial.md`](../knowledge/runbooks/publicar-resolucion-espacial.md)
  para el procedimiento operativo.
