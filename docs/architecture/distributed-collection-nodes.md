# Nodos distribuidos de recolección y handoff de artefactos

Esta guía aplica [ADR 0013](../adr/0013-distributed-collection-node-handoff.md).
Define cómo un computador auxiliar puede descargar exposomas sin convertirse
en un segundo repositorio científico ni sincronizar estados parciales.

## Roles y autoridad

| Rol | Responsabilidad | No debe hacer |
|---|---|---|
| Nodo de recolección | Ejecutar, reanudar, checkpointar y preparar entregas | Publicar directamente o asumir autoridad central |
| Almacén de artefactos | Custodiar payloads aceptados e inmutables | Inferir identidad por nombres de archivo |
| Workspace de integración | Verificar, promover, materializar y publicar | Consumir carpetas sin manifests |
| Git | Versionar código, configuración, docs y referencias pequeñas revisadas | Transportar raw, cachés o credenciales |

La autoridad de un artefacto sigue esta secuencia:

```text
recolectando en nodo
  -> congelado en handoff
    -> copiado a staging central
      -> hashes y manifests verificados
        -> aceptado y promovido
```

Hasta el último paso, la copia del nodo es staging y debe conservarse.

## Identidad del primer nodo

| Campo | Valor |
|---|---|
| `node_id` | `brainlat-wsl-amd-iii` |
| Plataforma | Ubuntu 24.04 sobre WSL 2, distribución `BrainLat` |
| Almacenamiento físico | `D:\bastian\WSL\BrainLat` |
| Workspace Linux | `/home/bayala/projects/Brainlat-runner` |
| Rama operativa | `runner/multicity-2026-08-12` |
| Estudios asignados | Santa Marta, Cartagena y Pasto; agregado y nativo |
| Credenciales | Aprovisionamiento humano local; nunca forman parte del handoff |

La tabla registra capacidad e identidad, no estado vivo. El progreso real queda
en los resúmenes de cada corrida bajo `cache/multicity_runs/`.

## Clasificación de datos

| Path | Propiedad | Handoff normal | Retención en nodo |
|---|---|---|---|
| `data/reference/` | Contrato espacial pequeño | Sí; luego revisión y versionado central | Hasta aceptación |
| `data/raw/` | Snapshot original inmutable | Sí, con `source_manifest.json` | Hasta aceptación y respaldo |
| `data/interim/` | Transformación reproducible | Sólo si un bundle la declara necesaria | Hasta verificar productos |
| `data/processed/` | Bundles, master y release | Sí, con manifests y SHA-256 | Hasta aceptación y respaldo |
| `cache/` | Checkpoint evictable | No; sólo recuperación explícita | Mientras pueda reanudarse |
| Resúmenes de corrida | Evidencia operativa | Sí, como `operations/` | Según política del nodo |
| `.venv`, `.git`, tokens, `.netrc` | Entorno o secreto | Nunca | Local únicamente |

Ocultar una referencia local mediante `.git/info/exclude` sólo mantiene limpio
el checkout operativo. No la vuelve descartable: sigue siendo staging y debe
entrar al handoff antes de limpiar o retirar el nodo.

## Estructura del handoff

```text
handoff/<node_id>/<run_id>/
├── handoff_manifest.json
├── data/
│   ├── raw/...
│   ├── reference/...
│   └── processed/...
└── operations/
    ├── summary.json
    ├── summary.md
    └── incident_candidates.md
```

`run_id` debe ser estable y único, recomendado en UTC como
`YYYYMMDDTHHMMSSZ-<git_short_sha>`. Todos los paths del manifiesto son relativos
a la raíz del handoff.

### Contrato mínimo de `handoff_manifest.json`

| Campo | Regla |
|---|---|
| `schema_version` | Entero; comienza en `1` |
| `handoff_id` | Igual a `<node_id>/<run_id>` |
| `node_id`, `created_at` | Identidad del productor y timestamp UTC |
| `repository.commit`, `repository.branch` | Código exacto usado para producir |
| `status` | `complete` o `partial` |
| `studies` | IDs de Study y capas solicitadas/completas/fallidas/pendientes |
| `artifacts` | `path`, `role`, `size_bytes`, `sha256` y manifest propietario |
| `exclusions` | Cachés o productos omitidos, con razón |

El manifiesto no contiene contraseñas, URLs OAuth, tokens ni variables de
entorno. Cada asset debe estar cubierto exactamente una vez y su path no puede
escapar de la raíz del paquete.

## Procedimiento de aceptación

1. Confirmar que no haya procesos escribiendo en el workspace del nodo.
2. Inventariar estudios, manifests y pendientes; marcar el handoff `partial` si
   falta cualquier capa declarada.
3. Copiar únicamente los paths admitidos a una raíz de staging inmutable.
4. Verificar tamaño y SHA-256 de cada asset antes de interpretar su contenido.
5. Validar source manifests, bundles y releases con sus loaders canónicos.
6. Resolver colisiones: mismo path + mismo hash se deduplica; mismo path + hash
   distinto detiene toda promoción.
7. Promover atómicamente a las rutas canónicas de `data/`.
8. Ejecutar `exposome verify --study <id>` para cada release completa. Para una
   entrega parcial, materializar centralmente sólo cuando estén todos los
   bundles requeridos.
9. Registrar aceptación y respaldo; recién entonces autorizar limpieza local.

No se publican bundles web directamente desde el handoff. La publicación parte
de una Study release aceptada y verificada en el workspace de integración.

El procedimiento concreto para promover una ciudad hasta una candidata de
GEMMA está en el
[runbook de integración WSL → GEMMA](../knowledge/runbooks/integrar-nodo-wsl-en-gemma.md).

## Estrategia de incorporación a GEMMA

La unidad de promoción es una ciudad con su Study agregado y su compañero
nativo. Santa Marta funciona como piloto; Cartagena y Pasto se incorporan sólo
después de validar el mismo circuito de aceptación. Esto permite mostrar valor
temprano sin declarar completa toda la cohorte colombiana.

La frontera de producción permanece en el workspace central:

```text
nodo: recolectar + checkpoint + handoff
central: aceptar + promover + materializar + preview + auditar + publicar
GEMMA: consumir sólo bundles publicados y catalogados
```

Los payloads compartidos entre ciudades se pueden deduplicar por SHA-256 en el
almacén central, pero cada handoff debe declarar la dependencia exacta. La
deduplicación física nunca elimina procedencia lógica.

La promoción también exige paridad científica con las ciudades existentes. El
Study nativo conserva el máximo soporte real de cada proveedor y el agregado
publica detalle sólo si el contrato espacial v3 lo verifica. No se igualan
resoluciones mediante sobremuestreo, no se asignan metros ficticios a OSM y no
se reutilizan datos de otra ciudad para completar una capa ausente. La matriz y
los gates concretos están en el runbook WSL → GEMMA.

## Fallos y recuperación

- Una interrupción durante el empaquetado invalida ese handoff; se crea otro
  `run_id` en vez de completar silenciosamente el anterior.
- Un artefacto válido dentro de una corrida parcial puede aceptarse sin marcar
  completo el Study.
- Si otro nodo debe continuar la recolección, el caché viaja en un paquete de
  recuperación separado, identificado por fingerprints; nunca se mezcla con el
  handoff científico.
- Si el backend central no está disponible, el nodo conserva raw, referencias,
  processed y checkpoints. No se usa GitHub como respaldo improvisado.

## Interfaz implementada

`exposome handoff-export` exige releases verificadas y congela la clausura de
assets durables con SHA-256. `exposome handoff-import` valida rutas, symlinks,
hashes y fingerprints de configuración antes de staging; `--promote` nunca
sobrescribe una colisión. Los resúmenes operativos se conservan como evidencia
en staging, no como parte del árbol central de productos.
