# Ejecutar un estudio

La fuente de verdad es `config/studies/<study>.yaml`.

```bash
exposome run --study <study> --dry-run
exposome run --study <study> --resume
exposome publish --study <study>
exposome verify --study <study>
```

Revisa primero el contrato espacial, el número esperado de unidades, el período,
las capas disponibles por país y las entradas locales requeridas. Consulta el
[catálogo de estudios](../generated/catalogo-estudios.md).

Antes de publicar una ciudad nueva, completa
[Publicar y verificar resolución espacial](publicar-resolucion-espacial.md).
