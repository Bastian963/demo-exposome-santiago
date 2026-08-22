# Cola LatAm de cohorte: operación semanal

Este documento es el registro operativo para extender GEMMA con las ciudades
priorizadas por la residencia agregada de la cohorte 2026-07. No contiene
registros individuales: los conteos proceden del notebook
`notebooks/cohort/participant_location_rankings.ipynb` y de
`docs/multicity_status.md`.

El criterio acordado es **n >= 25 participantes**. Una ciudad no se considera
completa por haber descargado capas: debe pasar sus manifest, soporte espacial,
verificación y publicación atómica en GEMMA.

## Fuente de verdad y regla de entrada

El checkout de **Joaco (`Brainlat-runner`)** es la fuente de verdad inicial para
Cartagena, Pasto y Santa Marta. Antes de añadir una de esas ciudades a la cola
versionada se deben recuperar en Git, desde ese equipo, sus configuraciones,
polígonos de referencia, README de procedencia/licencia, bundles y manifests.
No se copian caches como fuente científica.

Una ciudad entra a `config/operations/cohort_latam_ready.yaml` solo si cumple:

1. estudio agregado y companion native versionados, misma ubicación y
   `detail.native_study` declarado;
2. polígonos oficiales con fuente y licencia reproducibles;
3. `exposome run --study <study> --dry-run` limpio para ambos estudios;
4. las 14 capas portables habilitadas o una excepción explícita y documentada.

La cola ejecutable actual solo contiene San Juan y São Paulo porque son los
únicos pares que este checkout puede validar por sí mismo. Es intencional:
evita que el computador de Joaco consuma una semana intentando una ciudad cuya
referencia todavía no se ha versionado.

## Bitácora de Joaco — 2026-08-19

La siguiente evidencia es operativa y agregada; no incluye payloads de
proveedores ni datos de participantes.

| Ciudad/estudio | Resultado observado | Checkpoint y siguiente acción |
|---|---|---|
| Cartagena agregado | Las nueve capas no-OSM se reanudan como `skipped`; `healthcare` agotó dos intentos en cada mirror Overpass. | Los bundles válidos se conservan y el master/release no se reemplazó. Reintentar solo `healthcare` con `--resume` desde la cola OSM. |
| Pasto agregado/native | Las nueve capas no-OSM se reanudan como `skipped`; las advertencias de resolución no son errores. | Quedan únicamente las capas OSM por comprobar/reanudar. |
| Cartagena native | Las nueve capas no-OSM se reanudan como `skipped`. | Quedan únicamente las capas OSM por comprobar/reanudar. |
| Santa Marta agregado/native | Bundles existentes, series anuales 83/83, detalle native de 11 indicadores y perfiles generados. | Publicación canónica terminada; no se vuelve a encolar. |

### Publicación confirmada: Santa Marta

La secuencia que pasó en Joaco fue: `materialize` → `verify` (89 assets) →
estado anual 83/83 → `detail --resume` (11 COGs) → perfiles → `materialize`
→ `verify` (90 assets) → publicación de staging → `spatial-audit --strict`
(47 indicadores, 0 issues) → `resolution-coverage --tier production` →
publicación canónica → repetición de ambos gates. Los dos checks de cobertura
devolvieron exit code 0. Esto prueba el contrato de detalle native verificable;
no afirma falsamente que todos los indicadores sean rásteres nativos.

### Incidente OSM: Cartagena healthcare

Dos reanudaciones separadas agotaron el mismo patrón: `overpass-api.de` lanzó
`ConnectionError`, `overpass.openstreetmap.fr` lanzó
`ResponseStatusCodeError` y `overpass.osm.ch` agotó el plazo por intento. Cada
mirror recibió dos intentos con su espera interna. La capa terminó con
`ConnectionError: Failed to download OSM tag 'amenity'`; no se invalidó ningún
cache ni se reemplazó el release. Es una caída transitoria del proveedor, no
un fallo de geometría, estudio o contrato espacial.

## Prioridades y estado al 2026-08-19

| Prioridad | Ciudad | País | n | Estado para GEMMA | Acción antes de ejecutar/publicar |
|---:|---|---|---:|---|---|
| 1 | San Juan (provincia) | AR | 195 | recolección activa en equipo local | Terminar allí; no duplicar en Joaco. Transferir release validado. |
| 2 | São Paulo | BR | 143 | datos agregados existentes, no publicada | Verificar/reanudar el par agregado/native y correr gates de publicación. |
| 3 | Santa Marta | CO | 74 | publicada y validada en Joaco; pendiente de recuperar en este checkout | Incorporar configuraciones, referencias y release por Git; no repetir la colección. |
| 4 | Belo Horizonte | BR | 52 | preparación RMBH oficial en curso | Congelar las fuentes IBGE, construir los 34 municipios RMBH (sin Colar), pasar preflight agregado/native y luego encolar. |
| 5 | Cartagena | CO | 31 | agregado en Joaco; `healthcare` estaba en reanudación | Terminar `healthcare`, recuperar configuración y validar ambos estudios. |
| 6 | Arequipa | PE | 31 | sin estudio versionado | Preparar límites oficiales, configuración, companion native y preflight. |
| 7 | Pasto | CO | 30 | preflight remoto exitoso; capas no iniciadas | Recuperar configuración de Joaco y verificarla en Git antes de encolarla. |
| 8 | Barranquilla | CO | 29 | sin estudio versionado | Preparar límites oficiales, configuración, companion native y preflight. |
| 9 | Cali | CO | 25 | sin estudio versionado | Preparar límites oficiales, configuración, companion native y preflight. |

Ciudades ya visibles en GEMMA no vuelven a la cola por defecto. Solo se
reabren si falta un gate de publicación o si cambió la proveniencia de una capa.

### Onboarding: Belo Horizonte — RMBH oficial

La ciudad #10 por cohorte se procesa como **Região Metropolitana de Belo
Horizonte (RMBH)** y no como el municipio central: son exactamente 34
municipios oficiales; el **Colar Metropolitano** es una categoría legal
separada y queda fuera. El migrador
`scripts/migrations/build_belo_horizonte_rmbh_reference.py` exige dos fuentes
IBGE congeladas: la membresía oficial de Recortes Metropolitanos y la Malha
Municipal Digital de Minas Gerais que aporta las geometrías. No descarga nada;
rechaza otra cantidad de unidades, códigos sin geometría, duplicados y
geometrías no poligonales.

Después de la migración, el estudio visible es `belo_horizonte_rmbh` y su
companion oculto es `belo_horizonte_native`. Ambos usan el mismo snapshot
Geofabrik `sudeste/260819`: salud, alimentación, infraestructura social,
acceso verde **y caminabilidad** leen el PBF local. Por lo tanto, ninguna de
esas capas debe volver a Overpass. Belo Horizonte sólo entra en la cola semanal
después de que ambos `exposome run --dry-run` pasen en el equipo que tiene
tanto el PBF como las referencias IBGE.

## Ejecución humana en Joaco

La recolección real la ejecuta una persona. El supervisor es secuencial, usa
los checkpoints de la app y no usa `--force`. Cada slice dura como máximo diez
horas; al completarlo, la siguiente ciudad pendiente toma el turno. Tres ciclos
con fallo dejan la ciudad como `needs_review` y el resto de la cola continúa.

Primero, sin red ni escrituras, valida la configuración:

```bash
cd ~/projects/Brainlat-runner
.venv/bin/python scripts/run_cohort_latam_week.py --dry-run
```

Mientras San Juan siga en el otro equipo, en Joaco se puede seleccionar solo
São Paulo con una ventana de una semana:

```bash
mkdir -p logs
nohup .venv/bin/python scripts/run_cohort_latam_week.py \
  --city sao_paulo \
  --duration-hours 168 \
  --slice-hours 10 \
  > logs/cohort_latam_week.log 2>&1 &
```

Tras integrar las ciudades de Joaco en
`config/operations/cohort_latam_ready.yaml`, ejecutar el mismo comando sin
`--city` procesa la cola completa. El estado durable, solo local, queda en
`cache/cohort_latam_week/cohort_latam_ready.json`; cada slice enlaza además a
su `cache/multicity_runs/<timestamp>/summary.md` y logs por tarea.

Para reiniciar una cola después de cambiar deliberadamente la configuración,
primero revisar las ciudades `completed` y luego usar `--reset-state`. No se
borra el cache científico.

### Recuperación automática y espaciada de OSM

`scripts/run_osm_recovery_week.py` es el supervisor específico para una caída
de Overpass: corre únicamente `greenspace_access`, `walkability`,
`social_infrastructure`, `food_environment` y `healthcare`, primero agregado y
luego native, una tarea por vez. Usa `--resume`, escribe estado y logs bajo
`cache/osm_recovery_week/`, espera seis horas entre pasadas y tras tres fallos
deja la ciudad en `needs_review` para no martillar los mirrors.

Cuando todas las capas OSM de una ciudad pasan, el supervisor llama al runner
canónico para completar temporal, detalle, staging, auditorías y publicación.
No se debe iniciar mientras haya una ejecución manual del mismo estudio.

En Joaco, después de recuperar este script y sus configuraciones por Git:

```bash
.venv/bin/python scripts/run_osm_recovery_week.py --dry-run
```

La corrida humana de una semana se deja en segundo plano con:

```bash
mkdir -p logs
nohup .venv/bin/python scripts/run_osm_recovery_week.py \
  --duration-hours 168 \
  > logs/osm_recovery_week.log 2>&1 &
```

### Fallback local para Colombia cuando Overpass agota sus mirrors

Si `healthcare` o cualquier capa por tags agota los mirrors `.de`, `.fr` y
`.ch` en ciclos espaciados, no se paralelizan las consultas ni se borran los
checkpoints. Se usa un snapshot manual de Geofabrik, que conserva la misma
fuente OSM en un archivo local y evita Overpass.

En Joaco el archivo se guarda fuera de Dropbox, con la fecha del snapshot:

```bash
cd ~/projects/Brainlat-runner
mkdir -p data/raw/geofabrik/colombia/260819
curl -fL -C - -o data/raw/geofabrik/colombia/260819/colombia.osm.pbf \
  https://download.geofabrik.de/south-america/colombia-260819.osm.pbf
sha256sum data/raw/geofabrik/colombia/260819/colombia.osm.pbf
```

El archivo correcto es únicamente `colombia-260819.osm.pbf`; nunca una variante
`free.shp.zip` o `free.gpkg.zip`. Antes de apuntar estudios a él, correr el
migrador de ingesta para crear `source_manifest.json`, revisar el hash y
versionar el manifiesto/configuración. Este fallback sirve para salud,
alimentación, infraestructura social, acceso verde y caminabilidad. En
`walkability`, el extracto se traduce localmente a un grafo vial; no se consulta
Overpass por comuna.

### Snapshots OSM locales para la campaña LATAM

La campaña de cohorte usa snapshots Geofabrik fechados de **2026-08** para las
cuatro capas por tags (`greenspace_access`, `food_environment`, `healthcare` y
`social_infrastructure`) y para la red vial de `walkability` en ciudades nuevas
o reintentos. No se recalculan publicaciones anteriores solo para cambiar este
backend.

El inventario, URLs fechadas y cobertura por ciudades están en
[`config/operations/geofabrik_latam_cohort.yaml`](../config/operations/geofabrik_latam_cohort.yaml).
Incluye Colombia, Perú, Chile, México, Argentina y Brasil Sudeste; este último
cubre São Paulo y Belo Horizonte sin descargar el PBF nacional completo.

En Joaco, antes de bajar cualquier archivo, revisar qué falta y mostrar los
comandos manuales que reanudan una transferencia interrumpida:

```bash
cd ~/projects/Brainlat-runner
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python \
  scripts/check_geofabrik_latam_cohort.py --commands
```

El operador ejecuta solo los bloques de regiones `missing` o `unfrozen`, uno a
la vez. Después de cada ingesta, versiona únicamente
`data/raw/geofabrik/<region>/260819/source_manifest.json`; el PBF queda fuera
de Git. El check completo —sin red— es:

```bash
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python \
  scripts/check_geofabrik_latam_cohort.py --require-payload --verify-hash
```

No se crean scripts de descarga ni tareas periódicas de actualización. Cambiar
de snapshot es un cambio científico de entrada: se añade una nueva versión,
se valida y se declara explícitamente en los estudios afectados.

### Checklist PBF antes de una ciudad nueva o una recuperación

Este checklist evita repetir la secuencia de errores observada en Cartagena,
Pasto y São Paulo. Se aplica por ciudad, agregado y native, antes de dejar una
semana de ejecución autónoma:

1. Ejecutar `check_geofabrik_latam_cohort.py --require-payload --verify-hash`.
   Un PBF descargado sin `source_manifest.json` no se considera fuente lista.
2. Declarar el mismo `osm_extract` fechado en los cinco bloques: acceso verde,
   caminabilidad, infraestructura social, alimentación y salud, tanto para el
   estudio agregado como native. La ruta de verde es
   `greenspace.access.osm_extract`; las otras cuatro usan su bloque de capa.
3. Correr `exposome run --study <study> --layers walkability --dry-run` para
   ambos modos. La configuración resuelta debe mencionar el extracto esperado.
4. Ejecutar primero caminabilidad agregada y revisar el log: exige
   `highway lines: N features` con `N > 0` y unidades `ok`; una salida de todas
   las unidades `sparse/empty` no es un resultado válido aunque diga
   `executed`.
5. Sólo entonces ejecutar las otras cuatro capas nativas y el supervisor de la
   semana. Nunca iniciar dos procesos sobre el mismo estudio a la vez.

**Excepción de escala provincial:** si el estudio agregado cubre una provincia
completa pero el companion native sólo contiene raster, los cinco overrides se
declaran en el agregado. No se fabrican overrides native para layers que ese
native no tiene. En reducciones GEE zonales largas, el runner debe guardar una
unidad por vez; un timeout no autoriza a borrar resultados ya checkpointed.

El agotamiento consecutivo de los mirrors Overpass (`.de`, `.fr`, `.ch`) es un
incidente de proveedor, no una razón para aumentar reintentos o paralelizar.
Si la ciudad ya tiene un PBF congelado, el log de estas cinco capas debe decir
`reading ... from <region>.osm.pbf`; las líneas `attempt ... via
https://overpass...` indican que falta el override o que se está ejecutando un
proceso iniciado antes de actualizar el código.

Después de corregir código/configuración, no se reinicia la semana de inmediato:
se recuperan primero las capas fallidas una por una, se revisan sus artefactos,
y recién entonces se ejecuta el supervisor con `--reset-state`. Ese flag sólo
reinicia el estado operacional bajo `cache/`; no borra checkpoints ni PBFs.

## Gates de publicación

Por cada ciudad: capas agregadas -> native -> series anuales -> detalle
verificable -> perfiles -> release -> staging -> auditoría espacial estricta
-> cobertura `production` -> publicación canónica -> auditoría final.

Los resultados publicados deben pasar `exposome verify`,
`exposome spatial-audit --strict` y `exposome resolution-coverage --tier
production`. Si falta un polígono reproducible, una serie temporal requerida o
la cobertura de producción, la ciudad queda `blocked`/`partial` y GEMMA no se
modifica.

Después de cada ciudad, actualizar `docs/multicity_status.md`; tras cambios
estructurales, refrescar OpenWiki manualmente según `AGENTS.md`.
