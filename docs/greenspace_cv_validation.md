# Validacion formal de metodos verdes OSM + CV

## Proposito

Este flujo no reemplaza `greenspace_cv`. Lo complementa con una validacion
cuantitativa para decidir si una metrica verde enriquecida puede aprobarse como
capa cientifica final.

Se comparan cuatro mascaras sobre las mismas escenas etiquetadas manualmente:

- `osm`: inventario formal desde OpenStreetMap
- `cv_strict`: ExG + Otsu actual
- `cv_refined`: ExG estricto + paso RGB relajado
- `hybrid`: `OSM ∪ CV refinado`

La validacion busca responder dos preguntas distintas:

1. Cuanto verde visible detecta el CV puro.
2. Si el inventario hibrido mejora la representacion cientifica del verde urbano
   respecto de OSM solo.

## Workflow

### 1. Preparar paquete de etiquetado

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/prepare_greenspace_validation.py
```

Esto escribe:

- `data/validation/greenspace_cv/greenspace_cv_sites.csv`
- `data/validation/greenspace_cv/greenspace_cv_second_pass_sites.csv`
- `data/validation/greenspace_cv/greenspace_cv_annotation_batches.csv`
- `data/validation/greenspace_cv/images/*.png`
- `data/validation/greenspace_cv/labels/*.json`
- `data/validation/greenspace_cv/labels_second_pass/`
- `data/validation/greenspace_cv/greenspace_cv_annotation_contact_sheet.pdf`
- `data/validation/greenspace_cv/README.md`

El protocolo de etiquetado recomendado esta en:

- `docs/greenspace_cv_annotation_protocol.md`
- `docs/greenspace_cv_approval_checklist.md`

Para retomar el trabajo sin reconstruir contexto, usar primero:

- `data/validation/greenspace_cv/README.md`

La seleccion usa tres escenas por comuna desde las muestras existentes:

- mayor `osm_green_pct`
- mayor `cv_outside_osm_pct`
- menor `osm_green_pct + cv_green_pct`

Ademas agrega los sitios curados del showcase.
Estos sitios `showcase` sirven para auditoria visual y ejemplos curados, pero no
cuentan para la compuerta formal de cobertura de `52` comunas oficiales.

El archivo `greenspace_cv_second_pass_sites.csv` define una submuestra reproducible
de 20 escenas para doble etiquetado humano.

El archivo `greenspace_cv_annotation_batches.csv` organiza el trabajo en lotes
reproducibles, y `greenspace_cv_annotation_contact_sheet.pdf` entrega una vista
rapida de las escenas para repartir anotacion y control visual.

### 2. Etiquetar manualmente

Las etiquetas usan un subconjunto compatible con LabelMe JSON. Cada poligono
debe tener `label = "vegetation"`. No se usan categorias adicionales en esta
primera version.

### 3. Correr validacion

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/run_greenspace_validation.py
```

Outputs:

- `data/processed/santiago_greenspace_cv_validation_metrics.csv`
- `data/processed/santiago_greenspace_cv_validation_summary.csv`
- `data/processed/santiago_greenspace_cv_validation_summary_by_commune.csv`
- `data/processed/santiago_greenspace_cv_validation_comparison_summary.csv`
- `data/processed/santiago_greenspace_cv_validation_method_ranking.csv`
- `data/processed/santiago_greenspace_cv_validation_audit.md`
- `data/processed/santiago_greenspace_cv_validation_annotator_agreement.csv` (si hay segunda pasada)
- `data/processed/santiago_greenspace_cv_validation_decision.json`
- `data/processed/santiago_greenspace_cv_validation_decision.md`
- `data/processed/santiago_greenspace_cv_validation_metadata.json`
- `figures/greenspace_cv_validation_summary.png`
- `figures/greenspace_cv_validation_examples/*.png`

## Metricas

Por sitio y metodo se calculan:

- `precision`
- `recall`
- `f1`
- `iou`
- `green_pct_pred`
- `green_pct_truth`
- `mae_pct`
- `false_positive_pct`
- `false_negative_pct`

Ademas se resume por `metodo x comuna` para detectar si el hibrido solo mejora
en unos pocos barrios o si la mejora es consistente en la ciudad.

La tabla `comparison_summary` resume deltas directamente relevantes para la
decision cientifica: ganancia de recall del CV refinado y mejora o deterioro
del hibrido frente a OSM por estrato.

La tabla `method_ranking` resume, por estrato, que metodo gana en `IoU`, `F1`
y `MAE`, para que la aprobacion final no dependa solo de una lectura manual de
varias tablas separadas.

El archivo `validation_audit.md` consolida decision, progreso, criterios,
comparacion por estrato y ranking de metodos en un solo reporte legible.

## Criterio de interpretacion

- `cv_refined` debe mejorar recall frente a `cv_strict` sin derrumbar precision.
- `hybrid` debe reducir el error absoluto de cobertura verde frente a `osm` en
  sitios donde OSM submapea.
- Si `hybrid` solo funciona como narrativa visual pero no mejora error de forma
  consistente, no debe entrar al master.
- La mediana de `iou` entre primera y segunda etiqueta humana debe quedar alta
  antes de usar estas etiquetas como referencia para decidir aprobacion.
- La cobertura comunal formal se calcula solo sobre escenas `sample`; los casos
  `showcase` no pueden inflar artificialmente el cumplimiento de `52` comunas.

## Decision automatica

El runner escribe una decision reproducible con cuatro estados:

- `pending_no_labels`: no hay escenas etiquetadas.
- `pending_more_labels`: hay resultados parciales, pero aun no cumplen cobertura
  o acuerdo minimo entre anotadores.
- `approved_as_hybrid_layer`: el hibrido pasa los criterios definidos.
- `approved_as_validation_only` o `not_approved`: el CV sirve como validacion del
  sesgo OSM, pero no como capa final aprobada.

## Seguimiento de avance

Para ver cuanto del paquete ya fue etiquetado:

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/check_greenspace_validation_progress.py
```

Este comando resume avance primario y de segunda pasada, incluyendo desglose
por estrato y por lote. Lee directamente los JSON de etiquetas actuales, por lo
que no requiere rerun de validacion para reflejar progreso de anotacion.

Para exportar la cola exacta de pendientes y el siguiente batch recomendado:

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/export_greenspace_annotation_queue.py
```

Esto escribe:

- `data/validation/greenspace_cv/greenspace_cv_annotation_queue.csv`
- `data/validation/greenspace_cv/greenspace_cv_annotation_queue_summary.json`

Para exportar un paquete compacto del siguiente lote pendiente, o de un lote
especifico:

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/export_greenspace_annotation_batch.py
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/export_greenspace_annotation_batch.py --batch-id batch_02
```

Esto escribe, por ejemplo para `batch_01`:

- `data/validation/greenspace_cv/batches/batch_01/batch_01_annotation_manifest.csv`
- `data/validation/greenspace_cv/batches/batch_01/README.md`

## Limitaciones

- Las etiquetas manuales siguen siendo una verdad de referencia operativa, no
  verdad terreno botanica.
- Esri World Imagery puede mezclar fechas y condiciones de iluminacion.
- El CV refinado sigue siendo RGB puro; no distingue especie, salud vegetal ni
  temporalidad.
- `hybrid` es un inventario enriquecido, no una medicion puramente observacional
  de vegetacion.
