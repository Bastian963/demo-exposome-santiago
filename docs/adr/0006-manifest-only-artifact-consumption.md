# ADR 0006: Consumo de artefactos exclusivamente por manifests

## Decisión

El pipeline canónico consume únicamente Layer Artifact bundles y Study releases
v2 verificadas. La existencia de un CSV, un directorio o un nombre histórico no
demuestra completitud ni provenance.

Un Layer manifest v2 declara identidad de Study/Layer/modo, fingerprint de
ejecución, contrato espacial, assets con roles explícitos, tamaño y SHA-256, y
referencias checksumadas a snapshots raw cuando existan. Una Study release v2
declara el conjunto exacto de Layers habilitadas y todos los assets de master y
publicación que pueden salir del repositorio procesado.

Los manifests v1 sólo pueden entrar mediante un migrador explícito y local. El
migrador exige una release v1 verificable, fingerprint de settings vigente,
identidad, cobertura y columnas válidas; si falta evidencia solicita rebuild.
`run`, `resume`, master y publish nunca adoptan archivos legacy automáticamente.

## Consecuencias

- Resume deja de saltar una Layer por encontrar un CSV suelto.
- Master y publicación no buscan el primer archivo que coincida con un patrón.
- Un run parcial puede actualizar bundles, pero no reemplaza master ni release.
- Santiago conserva un adapter de migración hasta completar ADR-0003, no
  fallbacks distribuidos dentro del camino canónico.
- Los directorios no declarados por la release no se publican ni se consideran
  protegidos por ella.
