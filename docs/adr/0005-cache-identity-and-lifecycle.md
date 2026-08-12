# ADR 0005: Identidad y ciclo de vida del caché

## Decisión

Un caché reutilizable se identifica por la operación científica que materializa,
no sólo por ciudad o año. Su identidad incluye proveedor/producto, colección,
bandas, escala y proyección, reducer, máscaras y factores, período exacto,
parámetros algorítmicos relevantes y fingerprint del soporte espacial.

Cada entrada vive bajo el caché canónico del Study y publica un sidecar con la
identidad completa, SHA-256, tamaño, columnas, filas, estado y unidades de
trabajo completadas. Los datos y el sidecar se escriben atómicamente; un
`.partial` sólo se reanuda dentro de la misma identidad. `--force` permite
recalcular, pero no omite la validación de identidad.

Los cachés planos sin provenance suficiente no se adoptan automáticamente. Se
mantienen sin borrar durante la migración y un cache miss materializa el nuevo
namespace. Los originales de proveedor pertenecen a `data/raw/`, no al caché.

## Consecuencias

- Cambiar colección, banda, escala, período, geometría o algoritmo produce un
  cache miss verificable.
- Cambiar settings ajenos a la operación no invalida trabajo costoso.
- La existencia aislada de un archivo deja de demostrar que el caché es válido.
- La poda futura puede proteger locks y parciales y explicar qué identidad
  elimina, sin confundir checkpoints con fuentes durables.
