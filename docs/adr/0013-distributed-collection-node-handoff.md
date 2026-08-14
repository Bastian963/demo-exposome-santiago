# ADR 0013: los nodos de recolección entregan artefactos verificables, no carpetas sincronizadas

- Estado: aceptado
- Fecha: 2026-08-12
- Alcance: nodos externos que recolectan o procesan datos de exposoma
- Complementa: [ADR 0002](0002-artifact-ownership.md),
  [ADR 0005](0005-cache-identity-and-lifecycle.md) y
  [ADR 0006](0006-manifest-only-artifact-consumption.md)

## Contexto

Las descargas GEE, Open-Meteo y OSM pueden ocupar horas o días. Ejecutarlas sólo
en el computador principal desperdicia capacidad disponible y acopla la
recolección a una única máquina. El primer nodo externo es una distribución WSL
2 dedicada en un computador Windows compartido, usada para Santa Marta,
Cartagena y Pasto.

Copiar posteriormente el árbol completo del nodo no es un contrato de
integración. Mezclaría credenciales, entorno, cachés incompletos y resultados
válidos sin poder distinguirlos. Tampoco basta con copiar `data/processed/`: una
release debe conservar la procedencia de sus fuentes y las referencias
espaciales que fijan su identidad.

## Decisión

### 1. Separar tres responsabilidades

- El **nodo de recolección** ejecuta tareas reanudables y conserva staging local.
- El **almacenamiento central de artefactos** custodia payloads grandes una vez
  aceptados. El backend puede ser disco, red, S3, DVC u otro.
- **Git** conserva código, configuración, documentación, manifiestos compactos y
  referencias espaciales pequeñas ya revisadas. No transporta payloads grandes.

Un nodo no se convierte en fuente de verdad por haber terminado una descarga.
La autoridad cambia al almacenamiento central sólo después de verificar y
aceptar una entrega.

### 2. Integrar mediante un handoff inmutable

Cada entrega se congela bajo `handoff/<node_id>/<run_id>/` y contiene un
`handoff_manifest.json`. El manifiesto registra nodo, fecha, commit, estudios,
capas, estado completo o parcial, rutas relativas, roles, tamaños y SHA-256.
También enlaza los `source_manifest.json`, `manifest.json` y
`release_manifest.json` presentes.

El paquete puede incluir `data/raw/`, `data/reference/`, `data/processed/` y un
resumen operativo. Excluye `.git`, `.venv`, credenciales y caché ordinaria.

### 3. Tratar cada clase de datos según su ciclo de vida

- `data/reference/` es staging hasta revisión. Las referencias pequeñas
  aceptadas se versionan centralmente.
- `data/raw/` es durable, inmutable y viaja con un source manifest verificable.
- `data/processed/` viaja sólo como bundles o releases manifestados.
- `cache/` es evictable y no es evidencia científica. Sólo puede transportarse
  como paquete de recuperación explícito para continuar una corrida.
- Los resúmenes operativos explican fallos y pendientes, pero no sustituyen un
  manifest de fuente, bundle o release.

### 4. Verificar antes de promover

La recepción ocurre en staging. Una ruta ya existente con el mismo hash se
deduplica; con hash diferente se rechaza y exige nueva versión o investigación.
Nunca se sobrescribe silenciosamente. Después de promover los paths canónicos,
`exposome verify` valida la release. Si la entrega es parcial, se pueden aceptar
sus fuentes y bundles válidos, pero no declararla release completa.

No se sincroniza un árbol mientras haya un recolector escribiendo. El nodo
retiene su copia hasta que la aceptación y al menos un respaldo central estén
confirmados.

## Alternativas consideradas

- **Sincronizar el repositorio en vivo:** rechazada; expone estados parciales y
  mezcla caché con artefactos durables.
- **Copiar sólo productos procesados:** rechazada; pierde raw, referencia y
  procedencia necesarias para auditar o reproducir.
- **Subir todo a Git/Git LFS:** rechazada; Git no es el backend de artefactos y
  no resuelve staging, aceptación ni credenciales.
- **Repetir centralmente cada descarga:** válida como recuperación extrema, pero
  desperdicia el trabajo del nodo y no es el flujo normal.

## Consecuencias

- El transporte queda desacoplado del contrato científico.
- Una entrega parcial conserva progreso válido sin aparentar completitud.
- `exposome handoff-export` e `exposome handoff-import` implementan este
  contrato: el export congela sólo releases verificadas y el import valida en
  staging, compara hashes/configuración y exige `--promote` explícito.
- El nodo WSL actual se documenta en el
  [runbook operativo](../knowledge/runbooks/nodo-wsl-descargas.md).

## Capas y estudios afectados

Todas las capas y estudios ejecutados fuera del workspace central, comenzando
por `santa_marta_urban`, `santa_marta_native`, `cartagena_urban`,
`cartagena_native`, `pasto_urban` y `pasto_native`.
