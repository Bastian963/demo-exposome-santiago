# Integrar entregas del nodo WSL en GEMMA

Este runbook convierte resultados producidos en el computador compartido de
Joaquín (`brainlat-wsl-amd-iii`) en datos publicables por GEMMA sin convertir
ese computador en servidor de producción. Aplica primero a Santa Marta,
Cartagena y Pasto, pero el procedimiento es deliberadamente reutilizable.

La autoridad del contrato está en la
[arquitectura de nodos distribuidos](../../architecture/distributed-collection-nodes.md)
y en [ADR 0013](../../adr/0013-distributed-collection-node-handoff.md). Este
documento define el orden operativo.

## Resultado esperado

```text
nodo WSL de Joaquín
  -> handoff inmutable por ciudad
    -> transporte reanudable
      -> staging central fuera de data/
        -> verificación y aceptación
          -> promoción a data/
            -> release y detalle espacial
              -> preview de GEMMA
                -> publicación de producción
```

El nodo WSL recolecta y conserva checkpoints. El workspace central decide qué
se acepta y publica. GEMMA nunca lee directamente desde WSL, una carpeta
compartida, Dropbox en sincronización activa ni un handoff sin verificar.

## Unidad de entrega

La unidad normal es **una ciudad completa**, siempre con sus dos Studies:

| Ciudad | Study agregado | Study nativo |
|---|---|---|
| Santa Marta | `santa_marta_urban` | `santa_marta_native` |
| Cartagena | `cartagena_urban` | `cartagena_native` |
| Pasto | `pasto_urban` | `pasto_native` |

Entregar por ciudad reduce el tiempo hasta el primer resultado visible y hace
que un incidente de una ciudad no bloquee las otras. El orden recomendado es:

1. Santa Marta como piloto de extremo a extremo.
2. Cartagena después de validar el procedimiento con el piloto.
3. Pasto reutilizando exactamente los mismos gates.

Una entrega puede ser `partial`, pero no puede presentarse como lista para
GEMMA. Las capas válidas de una entrega parcial sí pueden aceptarse y
deduplicarse para no repetir descargas.

## Qué sale del nodo

Cada handoff incluye sólo artefactos durables relacionados con la ciudad:

- `data/raw/`: snapshots de proveedor con `source_manifest.json`;
- `data/reference/`: referencia DANE revisable de los Studies;
- `data/processed/`: bundles con `manifest.json` y releases disponibles;
- `operations/`: `summary.json`, `summary.md` e incidentes de las corridas;
- `handoff_manifest.json`: inventario, commit productor, tamaños y SHA-256.

Nunca incluye `.git`, `.venv`, `cache/`, `~/.netrc`, credenciales de Earth
Engine, URLs OAuth, tokens ni archivos de configuración personales. Si otro
nodo necesita continuar una tarea interrumpida, el caché viaja en un paquete de
recuperación distinto; no se mezcla con evidencia científica.

## Gate 1: congelar en el nodo

Una persona realiza este gate cuando la corrida ya devolvió el prompt:

1. Confirmar que no haya un recolector Python activo y que el lock
   `cache/.multicity_overnight.lock` no esté retenido.
2. Registrar `node_id`, commit, rama, proyecto GEE, Studies solicitados y último
   directorio de `cache/multicity_runs/`.
3. Inventariar capas completas, fallidas y pendientes desde sus manifests y
   resúmenes; nunca inferir éxito porque existe una carpeta.
4. Construir el handoff en una ruta nueva con un `run_id` UTC. No modificarlo
   después de calcular hashes.
5. Marcar `status: partial` si falta cualquier capa solicitada o release.
6. Conservar la copia original del nodo hasta recibir aceptación y confirmación
   de un respaldo central.

No se congela mientras `tmux` siga ejecutando una tarea. Estar desacoplado de
`tmux` no significa que la tarea terminó.

## Gate 2: transporte eficiente

El contrato no depende del medio, pero el orden de preferencia es:

1. almacenamiento de objetos o servidor SSH con transferencia reanudable y
   verificación de checksum;
2. SSD externo para una entrega presencial;
3. archivo congelado en un área de transferencia de nube, fuera del checkout y
   sin sincronizar el árbol vivo del repositorio.

Git y Git LFS no son el transporte de payloads. Tampoco se copia el VHD completo
de WSL para una entrega normal.

Para minimizar tiempo y espacio:

- transferir por ciudad, no esperar las tres para iniciar integración;
- deduplicar por SHA-256 al recibir, nunca sólo por nombre;
- reanudar archivos incompletos en vez de reiniciar toda la transferencia;
- no recomprimir GeoTIFF, PBF u otros formatos ya comprimidos sólo para reducir
  bytes; un contenedor puede servir para atomicidad, no como prueba de integridad;
- transferir de nuevo únicamente assets ausentes o cuyo hash esperado cambió.

Un archivo recibido parcialmente permanece en staging y nunca adopta su nombre
canónico hasta que tamaño y SHA-256 coincidan.

## Gate 3: recepción central

La recepción ocurre fuera de `data/`, por ejemplo bajo una raíz administrada de
staging. El importador debe operar en este orden:

1. Validar el esquema y la identidad de `handoff_manifest.json`.
2. Rechazar paths absolutos, `..`, enlaces y cualquier asset no inventariado.
3. Verificar tamaño y SHA-256 de todos los archivos antes de abrirlos.
4. Confirmar que el commit productor existe y que sus Study configs son
   compatibles con el workspace de integración.
5. Validar `source_manifest.json`, `manifest.json` y
   `release_manifest.json` con los loaders canónicos.
6. Comparar cada destino: mismo path y mismo hash se deduplica; mismo path y
   hash distinto bloquea la entrega completa.
7. Generar un informe de aceptación con assets aceptados, deduplicados,
   rechazados y pendientes.
8. Promover atómicamente sólo los assets aceptados a la jerarquía canónica de
   `data/`.

No se corrigen archivos dentro del handoff. Una corrección produce un handoff
nuevo para mantener trazabilidad.

## Gate 4: construir una candidata para GEMMA

Después de promover una ciudad, el workspace central realiza procesamiento
local y publicación de preview. El orden conceptual es:

1. sellar o verificar el Study nativo;
2. materializar la release agregada desde bundles aceptados;
3. generar el detalle web desde productos nativos ya aceptados;
4. comprobar completitud temporal y perfiles;
5. volver a materializar la release final;
6. ejecutar `exposome verify`;
7. publicar primero en una raíz de preview fuera de `webapp/public/data`;
8. ejecutar auditoría espacial estricta y cobertura de producción;
9. revisar GEMMA en navegador;
10. publicar al destino canónico y regenerar el catálogo.

Los comandos canónicos de bajo nivel son `exposome materialize`, `detail`,
`verify`, `publish`, `spatial-audit` y `resolution-coverage`. El orquestador
multiciudad ya compone esos gates; no se deben omitir manualmente para acelerar
una publicación.

## Gate 5: aceptación visual y científica

Una ciudad sólo entra en producción cuando se cumplen todos estos puntos:

- la release y todos sus assets verifican por checksum;
- no quedan capas obligatorias ausentes ni valores requeridos faltantes;
- cada indicador publica el soporte espacial que realmente posee;
- el detalle nativo tiene procedencia y resolución canónica verificadas;
- las series temporales requeridas están completas y usan un dominio de color
  consistente;
- FUENTE, ESPECIFICACIONES, METODOLOGÍA, CITACIÓN y DESCARGAR están completos;
- mapa, tooltip, leyenda, selector temporal y descarga se revisaron en navegador;
- la comparación entre agregado y nativo no revela desplazamientos, geometrías
  equivocadas ni reutilización de datos de otra ciudad;
- el catálogo identifica país, ciudad, Study, versión y tier correctos.

Una preview puede mostrar brechas explícitas. Producción no puede ocultarlas
mediante fallbacks silenciosos.

## Paridad de exposomas y resolución nativa

Santa Marta, Cartagena y Pasto deben cumplir el mismo contrato que las demás
ciudades. Paridad significa mismos IDs de capa, unidades, metodología,
procedencia, validaciones y comportamiento de GEMMA. No significa forzar todos
los datos a una cuadrícula común ni prometer detalle donde la fuente no lo
permite.

Cada pareja de Studies separa dos productos:

- el Study nativo conserva el soporte máximo permitido por el proveedor dentro
  del AOI;
- el Study agregado resume por la unidad DANE y sólo enlaza detalle cuando el
  producto nativo ha sido verificado.

La matriz mínima que debe auditarse por ciudad es:

| Exposoma | Soporte de fuente o análisis esperado | Regla para GEMMA |
|---|---|---|
| PM2.5 | ACAG 0,01°, aproximadamente 1.113 m | COG canónico sólo con resolución y procedencia verificadas |
| NO₂ | grilla analítica de 1.113 m; observación TROPOMI de aproximadamente 3,5 × 5,5–7 km | informar ambas escalas; nunca llamar 1.113 m a la huella física |
| ALAN | VIIRS DNB 463,83 m | COG canónico, sin remuestreo que aparente más detalle |
| Verde Landsat | 30 m | producto nativo a 30 m y resumen administrativo |
| Verde multifuente | Dynamic World 10 m y canopy 1 m; análisis de canopy a 30 m | declarar cada componente; detalle GeoJSON sólo con grilla métrica alineada al AOI |
| Precipitación | CHIRPS, aproximadamente 5.566 m | detalle sólo si el raster canónico y las cosechas requeridas verifican |
| Calor | ERA5-Land, aproximadamente 11.132 m | conservar warning cuando sea más grueso que la unidad |
| Viento | ERA5-Land, aproximadamente 11.132 m | COG de velocidad/bandas verificadas, sin falsa mejora por sobremuestreo |
| Incendios | MODIS 500 m y FIRMS 1 km | componentes separados; no fusionarlos en una resolución inventada |
| OSM | geometrías vectoriales | sin resolución raster ficticia; publicación administrativa salvo producto específico verificable |
| Infraestructura social y salud | OSM vectorial con grilla analítica de 1 km para accesibilidad | distinguir fuente vectorial, soporte analítico y geometría renderizada |

El `manifest.json.spatial_indicators` publicado es la autoridad. Para cada
indicador debe distinguir `downloaded`, `observation`, `analysis` y `rendered`.
El detalle se anuncia sólo cuando descriptor y sidecar prueban
`canonical_resolution_verified: true`, la misma
`source_native_resolution_m` y `source_support_preserved: true`. Si falta una
prueba, GEMMA muestra el agregado administrativo y registra la brecha; no usa
un raster histórico, no copia datos de Santiago y no elimina un
`resolution_warning` mediante sobremuestreo.

Antes de producción, la tabla de aceptación por ciudad debe listar las 14 capas
portables y, para cada una, bundle agregado, producto nativo, resolución o tipo
vectorial, período, hash, estado de detalle y motivo de cualquier ausencia. Una
capa pendiente permanece explícitamente pendiente; nunca se sustituye por la de
otra ciudad.

## Estado actual y automatización pendiente

El nodo, el layout canónico, los bundles, los verificadores y los gates de
publicación ya existen. La exportación e importación completa del handoff siguen
siendo una interfaz planificada; hasta implementarlas, cualquier primera
entrega manual requiere revisión humana archivo por archivo y no autoriza
publicación directa.

Las herramientas futuras deben exponer dos operaciones separadas:

- `export handoff`: inventario, denylist de secretos, dry-run, congelado y
  hashes; nunca mueve ni borra el origen;
- `import handoff`: staging, verificación, informe de colisiones y promoción
  atómica; nunca sobrescribe.

Pruebas mínimas: manipulación de hash, path traversal, symlinks, manifiestos
duplicados, handoff parcial, deduplicación por hash, colisión por contenido y
reanudación de una transferencia interrumpida.

## Cierre de cada ciudad

Después de publicar y respaldar:

1. registrar el `handoff_id` aceptado y la release publicada;
2. guardar el informe de aceptación junto al handoff central;
3. confirmar que hay al menos una copia central adicional;
4. comunicar al operador qué puede limpiar;
5. conservar en el nodo sólo lo necesario para reanudar pendientes o preparar
   el siguiente handoff.

La limpieza nunca se presume por haber copiado archivos: requiere confirmación
explícita de aceptación y respaldo.
