# Datos y artefactos

El repositorio versiona sólo insumos espaciales de referencia pequeños,
configuración, documentación, manifests compactos y evidencia de validación.
Las descargas de proveedores, resultados procesados y paquetes web son
artefactos reproducibles y no se almacenan como payloads grandes en Git.

## Jerarquía canónica

```text
data/
├── reference/<iso2>/<city>/<study>/       # contrato espacial pequeño
├── raw/<provider>/<dataset>/<version>/    # snapshots originales inmutables
├── interim/<iso2>/<city>/<study>/         # transformaciones reproducibles
├── processed/<iso2>/<city>/<study>/       # bundles, master y release
└── validation/                            # evidencia compacta
```

Un bundle se consume por `manifest.json`; una entrega integrada, por
`release_manifest.json`. Ambos declaran assets y SHA-256. Nunca se selecciona
«el primer CSV» de una carpeta.

`cache/<iso2>/<city>/<study>/<layer>/` está fuera de `data/` porque contiene
checkpoints y aceleración evictable. Un caché no es raw, bundle ni release.

## Propiedad y versionado

| Clase | Git | Almacén de artefactos |
|---|---|---|
| Referencias pequeñas revisadas | Sí | Opcional |
| Manifests y documentación compacta | Sí | Sí, junto al payload |
| Payloads raw | No | Sí |
| Interim y processed grandes | No | Sí cuando sean necesarios o aceptados |
| Caché | No | Sólo recuperación explícita |
| Credenciales y entornos | Nunca | Nunca |

Una referencia generada en un nodo puede ocultarse temporalmente con
`.git/info/exclude`, pero conserva estado de staging hasta que sea revisada e
integrada centralmente.

## Copias nuevas y nodos externos

Una copia nueva materializa artefactos desde el backend elegido o recalcula el
Study. Antes de publicar o analizar, verifica la release:

```bash
exposome verify --study santiago_communes
```

Los nodos externos no sincronizan su árbol en vivo. Entregan un handoff
inmutable que preserva raw, referencias, bundles y procedencia; la arquitectura
está en
[`docs/architecture/distributed-collection-nodes.md`](../docs/architecture/distributed-collection-nodes.md).

La elección de backend —disco, red, S3, DVC u otro— permanece fuera del
contrato. Debe materializar exactamente los paths canónicos y respetar los
manifests antes de ejecutar el mismo verificador.
