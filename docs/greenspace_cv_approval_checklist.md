# Checklist de Aprobacion: Greenspace CV / Hybrid

> **Reencuadre (capa multi-fuente adoptada, un solo anotador).** La capa verde de
> producción es ahora `greenspace_multisource` (Dynamic World 10 m + Meta canopy
> 1 m), fuentes peer-reviewed que ya superan a productos 10-30 m en ciudades. No
> depende de promover el detector CV artesanal. Con **un solo anotador**, el gate
> formal de acuerdo inter-anotador (mediana `IoU >= 0.75` en 20 escenas de doble
> pasada) **no es alcanzable y deja de ser bloqueante**. En su lugar, el
> `scripts/greenspace_multisource_sanity_check.py` corre un *sanity-check de
> confirmación con un anotador* sobre ~36 escenas estratificadas (incluyendo el
> borde periurbano norte, donde Dynamic World falla): cuantifica el sub-conteo de
> OSM con IC bootstrap y compara el MAE de OSM vs DW vs canopy contra las
> etiquetas. Las secciones de gating duro abajo aplican solo si se retoma la ruta
> de validacion formal del CV Esri (Framing A) con dos anotadores.

Usar esta lista junto al reporte:

- `data/processed/santiago_greenspace_cv_validation_audit.md`
- `data/processed/santiago_greenspace_multisource_sanity.json` (confirmacion 1 anotador)

## Gating duro

- [ ] Hay al menos `150` escenas etiquetadas manualmente.
- [ ] Las `52` comunas oficiales estan cubiertas en escenas `sample`.
- [ ] La submuestra de segunda pasada esta completa.
- [ ] La mediana de `IoU` entre anotadores es `>= 0.75`.

Si cualquiera de estos puntos falla, la capa no se aprueba todavia.

## Desempeno del CV refinado

- [ ] `cv_refined` mejora recall frente a `cv_strict` en magnitud material.
- [ ] Esa mejora no destruye precision.
- [ ] La mejora no aparece solo en uno o dos estratos.

## Desempeno del hibrido

- [ ] `hybrid` reduce el error absoluto frente a `osm` en escenas `cv_outside_high`.
- [ ] `hybrid` no rompe de forma relevante los estratos `osm_green_high`.
- [ ] `hybrid` no introduce un aumento inaceptable de falsos positivos.
- [ ] `hybrid` mantiene mejora o neutralidad en varias comunas, no solo en casos showcase.

## Criterio cientifico

- [ ] La recomendacion automatica es coherente con las tablas y no contradice la inspeccion manual.
- [ ] La interpretacion epidemiologica de la variable esta escrita con claridad.
- [ ] Las limitaciones quedan explicitadas: OSM submapea, RGB puro falla en ciertos parques, posibles falsos positivos y falsos negativos.

## Decision final

Marcar una opcion:

- [ ] `approved_as_hybrid_layer`
- [ ] `approved_as_validation_only`
- [ ] `not_approved`

Notas de la decision:

- Si el hibrido gana solo como narrativa visual, no entra al master.
- Si el hibrido mejora de forma estable y defendible, puede usarse como metrica final dentro del alcance validado.
- Los sitios `showcase` sirven como auditoria visual y control cualitativo, no como cobertura formal de comunas.
