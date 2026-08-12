# Gates para retirar la arquitectura legacy

La migración no elimina scripts ni formatos históricos por calendario. Cada
paso se hace sólo tras aprobar los siguientes gates comprobables.

| Gate | Evidencia requerida | Comando / dueño |
|---|---|---|
| Configuración | La capa tiene defaults en `config/layers/<id>.yaml`; país, ubicación y estudio no dependen de `config/cities/santiago.yaml`. | `exposome run --study <id> --dry-run` |
| Ejecución | El catálogo tiene un runner registrado y el CLI no invoca un wrapper legacy para esa capa. | test de `exposome.runners` + dry-run |
| Contrato espacial | El estudio usa `data/reference/<country>/<city>/<study>/` con IDs estables y conteo validado. | `python scripts/audit_exposome_status.py --study <id>` |
| Artefactos | Cada salida tiene `manifest.json`; el master tiene `release_manifest.json` y checksums válidos. | `exposome verify --study <id>` |
| Paridad | Para Santiago, columnas requeridas y 52 CUT son equivalentes al baseline histórico. | `python scripts/migrations/verify_santiago_portable_parity.py` |
| Publicación | El webapp se construye desde el release con manifiesto completo, sin fallback plano. | `exposome publish --study <id>` |
| Calidad | Unit tests no requieren `data/processed`, `figures` ni descargas locales; pruebas de artefactos son explícitas. | `python -m unittest discover -s tests`; aceptación: `EXPOSOME_RUN_ARTIFACT_TESTS=1 …` |

## Orden de retiro

1. Migrar una capa y añadir sus pruebas de runner/manifiesto.
2. Ejecutar paridad y publicar una release verificada.
3. Cambiar la documentación de la capa al path canónico.
4. Marcar su wrapper `scripts/run_<layer>.py` como adaptador deprecado; eliminarlo
   sólo si no tiene consumidores.
5. Eliminar `config/cities/santiago.yaml` únicamente cuando el último llamador
   directo haya sido migrado y los tests lo demuestren.

Los archivos bajo `data/processed/` y `figures/` no vuelven a versionarse para
cumplir un gate: se recrean o se materializan como una release verificable.
