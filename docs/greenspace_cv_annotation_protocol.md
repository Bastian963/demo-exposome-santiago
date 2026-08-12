# Protocolo de Anotacion Manual: Greenspace CV

## Objetivo

Generar una verdad de referencia operativa, consistente entre anotadores, para
comparar cuatro metodos:

- `osm`
- `cv_strict`
- `cv_refined`
- `hybrid`

La unidad de validacion es la escena PNG exportada en
`data/validation/greenspace_cv/images/`.

## Regla central

Anotar solo poligonos `vegetation`.

Se incluye:

- copa de arbol visible desde arriba
- arbustos
- cesped natural
- jardines privados visibles
- bandejones o medianas plantadas
- laderas y cerros con cobertura vegetal visible

Se excluye:

- sombra
- agua
- tierra desnuda
- superficies grises o techos con tinte verde
- pasto sintetico visible como superficie artificial
- cultivos o superficies periurbanas ambiguas cuando no son claramente verde urbano

## Casos ambiguos

Cuando haya duda, usar estas reglas:

1. Si parece vegetacion pero la textura es claramente artificial, excluir.
2. Si la copa esta parcialmente en sombra, incluir solo la parte visible como vegetacion.
3. Si hay jardineras muy pequenas, incluirlas solo si forman una superficie continua visible.
4. Si la escena mezcla parque urbano con borde agricola, priorizar anotar solo la vegetacion urbana evidente y dejar una nota en el JSON si la herramienta lo permite.

## Consistencia entre anotadores

- Dibujar pocos poligonos grandes cuando la masa vegetal es continua.
- Evitar fragmentar una misma copa en muchos poligonos pequenos.
- No usar categorias distintas de `vegetation`.
- No rellenar huecos internos pequenos causados por sombras puntuales.

## Casos de control recomendados

Revisar al inicio algunos ejemplos tipicos antes de anotar en lote:

- `Plaza de Armas`: estructura fina y arbolado duro.
- `Plaza Nunoa`: calles arboladas y verde residencial.
- `Parque O'Higgins`: parque grande bien mapeado.
- `Cerro San Cristobal`: vegetacion extensa y heterogenea.

## Flujo de trabajo

1. Abrir las escenas PNG y sus plantillas JSON en LabelMe.
2. Completar la primera pasada en `data/validation/greenspace_cv/labels/`.
3. Completar la segunda pasada independiente solo para la submuestra en
   `data/validation/greenspace_cv/labels_second_pass/`.
4. Correr:

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/run_greenspace_validation.py --no-include-examples
```

5. Revisar progreso con:

```bash
PYTHONPYCACHEPREFIX=/tmp ./.conda/envs/exposome/bin/python scripts/check_greenspace_validation_progress.py
```

## Criterio minimo antes de decidir aprobacion

- cobertura primaria en al menos `150` escenas
- cobertura de `52` comunas
- segunda pasada completa en la submuestra definida
- acuerdo humano mediano `IoU >= 0.75`

Si estas condiciones no se cumplen, la decision debe seguir siendo
`pending_more_labels` aunque los resultados preliminares del hibrido se vean buenos.
