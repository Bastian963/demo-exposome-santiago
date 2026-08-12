# ADR 0011: el estudio native compañero se exige en config, no en el tier

- Estado: aceptado
- Fecha: 2026-08-11
- Alcance: todo estudio agregado visible en el selector de ciudades
- Enmienda: [ADR 0004](0004-published-spatial-support-contract.md)

## Contexto

[ADR 0004](0004-published-spatial-support-contract.md) fijó el contrato de
soporte espacial publicado: el visor toma unidad, soporte y activo de detalle
desde `spatial_indicators` del manifest, y una unidad administrativa sólo es
máscara (`boundary_role: mask_only`) cuando existe un activo nativo detrás. La
regla está además escrita en `docs/resolution_manifest.md` y en `CLAUDE.md`.

**Y aun así se incumplió tres veces.** El 2026-08-11, revisando España en
GEMMA, `pais_vasco_provincias` pintaba 3 provincias planas. Medido sobre el
bundle publicado:

```
spatial_completion: status=partial, publication_tier=preview
  required_indicators 14   complete 1   missing 13
```

Sus 47 indicadores resolvían a `boundary_role: analysis_unit` — la provincia
*definía* el valor pintado en vez de recortarlo. El estudio tenía sus 14 capas
materializadas y sus 83 series anuales validadas; no faltaba dato.

La cadena causal es enteramente de configuración:

1. `config/studies/pais_vasco_provincias.yaml` no declaraba bloque `detail:`.
2. No existía `config/studies/pais_vasco_native.yaml`.
3. Sin productos nativos, `exposome detail` (`cli.py:101`) —post-proceso local
   que nunca contacta un proveedor— no tenía qué convertir.
4. Sin `detail/*.tif`, `spatial_coverage` marca cada indicador ráster `missing`.

`spatial_plan.py:113` ya emitía el prerrequisito en prosa («declare
detail.native_study with a validated dissolved AOI»), pero sólo cuando alguien
le pedía un plan de recuperación. Nada en la ruta de publicación lo consultaba.

### El defecto de fondo: el tier se satisface publicando menos

`spatial_coverage.py:93`:

```python
base_required = bool(target.get("required_for_production")) and available
```

Un indicador **sólo se exige si su capa está publicada**. De ahí que
`cataluna_comarques` figurara en el catálogo como `production / complete /
required_indicators: 0`: se había publicado con `noise_spain` sola, así que no
había ningún indicador ráster que exigir. Tenía exactamente el mismo defecto que
País Vasco, mejor disimulado.

Dicho de otro modo: **un estudio mejora su `publication_tier` publicando menos
capas.** El tier no mide cobertura espacial; mide cobertura espacial *de lo que
se decidió publicar*. Esa es la razón de que la regla estuviera escrita en tres
sitios y aun así nadie la viera incumplirse.

## Decisión

**El compañero native se exige en tiempo de configuración, con un test, y no se
toca la fórmula de `publication_tier`.**

`tests/test_native_detail_contract.py` recorre los estudios agregados con
`hidden: false` y exige tres cosas:

1. cada uno declara `detail.native_study`;
2. el estudio apuntado existe y es `mode: native`;
3. todo estudio native tiene su AOI legible en disco.

La única exención son los pilotos de una sola capa vectorial
(`barcelona_districts_noise`, `barcelones_noise_pilot`), cuyo detalle es MVT
`vector_contours` y no ráster nativo. La lista de exentos vive en el test, es
corta y cada entrada lleva su motivo: es el único modo de optar por salirse.

`publication_tier` **no cambia**. Queda registrado aquí que `production` con
`required_indicators: 0` no es prueba de cobertura, y que cualquier auditoría
que lo use como tal está leyendo mal.

## Alternativas consideradas

- **Cambiar la fórmula del tier para exigir contra las capas *configuradas* y no
  las publicadas.** Es el arreglo de fondo y sigue siendo lo correcto a medio
  plazo. Descartado ahora porque re-clasificaría cada ciudad ya publicada en una
  sola corrida, la víspera de una entrega; el riesgo de re-tiering masivo supera
  al del defecto, que ya está acotado por el test. Deuda consciente.
- **Una guarda en runtime que levante excepción en `publish`.** Descartado: llega
  tarde. El coste del fallo no es publicar mal, es *descubrir* en la última etapa
  que falta una corrida native de horas. En País Vasco eso se supo el día antes
  de la entrega; un test de config lo habría dicho semanas antes.
- **Derivar el estudio native automáticamente cuando falte.** Descartado: el AOI
  necesita validación humana contra la superficie oficial (el de País Vasco da
  7.225,2 km² contra 7.234 oficiales, y conserva a propósito el enclave de
  Treviño y dos islas). Generar uno en silencio es justo el tipo de detalle
  fabricado que ADR 0004 prohíbe.
- **Sólo documentarlo mejor.** Descartado por evidencia directa: ya estaba
  documentado en tres sitios cuando falló tres veces.

## Consecuencias

- Los tres estudios que incumplían quedaron declarados el 2026-08-11:
  `pais_vasco_provincias` → `pais_vasco_native`, `cataluna_comarques` →
  `cataluna_native`, y `san_juan_departamentos` → `san_juan_native`. Este último
  **lo encontró el test**, no la revisión visual: no estaba en el plan y todavía
  no se había corrido, así que su native se recolectará en la misma pasada que el
  resto en vez de como emergencia.
- Abrir una ciudad nueva cuesta un paso más —el AOI y el YAML native— y ese paso
  ahora está en el checklist de `docs/multicity_status.md` con sus cinco
  subpasos verificables, no como la línea vaga «conservar productos finos».
- `scripts/migrations/build_native_aoi.py` hace el AOI reproducible por
  disolución de las unidades ya validadas del agregado. Los de `santiago_native`
  y `cdmx_native` se hicieron a mano y no se re-generan: cambiarlos movería el
  fingerprint de ciudades publicadas sin ganar nada.
- El tier sigue siendo engañoso en el caso `required_indicators: 0`. Mientras no
  se cambie la fórmula, la lectura correcta de cobertura es
  `missing_indicators`, no `publication_tier`.
