# Arquitectura canónica del pipeline v2

La ejecución científica tiene cinco seams explícitos y verificables:

```text
StudyContext resuelto
  -> DAG de Layers
    -> LayerRunner(LayerExecutionContext)
      -> LayerBuildResult
        -> Artifact bundle v2
          -> master + Study release v2
            -> publicación web
```

## Caché y fuentes

- `data/raw/<provider>/<dataset>/<version>/` guarda snapshots originales,
  inmutables y checksumados por `source_manifest.json`.
- `cache/<country>/<location>/<study>/<layer>/` guarda únicamente respuestas,
  checkpoints y aceleración descartable.
- Una entrada reutilizable está identificada por producto, colección, bandas,
  reducer, escala/CRS, máscaras, período, parámetros del algoritmo y fingerprint
  espacial. El archivo por sí solo nunca es un cache hit.
- Los sidecars se publican después del payload; un proceso interrumpido no puede
  convertir una generación incompleta en válida.

Migración RETC, primero en dry-run:

```bash
.venv/bin/python scripts/migrations/migrate_retc_raw.py
.venv/bin/python scripts/migrations/migrate_retc_raw.py --write
```

El builder canónico de metales pesados exige ese snapshot. Sólo
`scripts/run_heavy_metals.py` conserva temporalmente un fallback explícito y
deprecado para originales ya presentes en `cache/`; no descarga nuevos
originales al caché.

## Ejecución y dependencias

`StudyContext` compone settings, unidades espaciales, CRS métrico e inputs una
sola vez. El adapter de funciones legacy inyecta esa configuración resuelta, de
modo que las Layers no vuelven a leer y transformar YAML durante el mismo run.

`build_execution_graph()` ordena dependencias por niveles. Una dependencia no
solicitada sólo puede entrar si ya existe un Artifact bundle verificado. Las
Layers que requieren el master se ejecutan después de una barrera explícita.
Un run parcial puede actualizar bundles, pero no reemplaza master ni release.

## Manifests como única autoridad

- Layer manifest: schema v2, roles explícitos, identidad de ejecución, soporte
  espacial, SHA-256/tamaño y referencias a raw source manifests.
- Study release: schema v2, conjunto **exacto** de Layers habilitadas, assets de
  master y assets de publicación preexistentes.
- Resume valida identidad y checksum. Master no acepta directorios. Publish no
  busca nombres históricos ni la raíz plana de Santiago.

Migración local de una release v1 verificable:

```bash
.venv/bin/python scripts/migrations/upgrade_artifact_manifests_v2.py \
  --study santiago_communes
.venv/bin/python scripts/migrations/upgrade_artifact_manifests_v2.py \
  --study santiago_communes --write
```

El migrador no llama proveedores, conserva backups `*.v1.json` y restaura la
versión anterior si la verificación v2 falla.

Cuando una recuperación parcial ya sustituyó algunas capas por manifests v2,
usa el migrador explícito con `--allow-stale-settings` sólo tras re-ejecutar las
capas afectadas, y cierra con `exposome materialize --study <id>`. Ese paso local
regenera el master y la release: un `run --layers ...` nunca debe reemplazarlos.

## Retiro de scripts

Los `scripts/run_*.py` siguen presentes como adapters de compatibilidad. Su
estado y gates viven en `config/runner_parity.yaml`. No se retira un script
hasta aprobar paridad científica, metadata, identidad de resume, ejecución
multi-Study y prueba contractual offline.

```bash
.venv/bin/python scripts/audit_runner_parity.py
```

Actualmente los 32 runners están registrados, los 32 scripts permanecen en
estado `adapter` y ninguno está marcado prematuramente como retirado.

## Verificación offline

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest \
  tests.test_cache tests.test_execution tests.test_artifact_contract \
  tests.test_manifest_migration tests.test_raw_sources tests.test_runner_parity
```

Las decisiones de fondo están registradas en
`docs/adr/0005-cache-identity-and-lifecycle.md` y
`docs/adr/0006-manifest-only-artifact-consumption.md`.
