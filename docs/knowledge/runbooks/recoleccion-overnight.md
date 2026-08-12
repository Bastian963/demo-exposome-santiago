# Recolección overnight

Los asistentes no ejecutan recolecciones reales contra GEE, Open-Meteo,
OSM/Overpass o Esri. Preparan el comando exacto para que una persona lo ejecute.

Antes de entregar un comando confirma que el script tenga:

1. barra de progreso sobre la unidad principal;
2. checkpoint incremental después de cada año, comuna, etiqueta o tile;
3. reanudación que omita unidades ya cacheadas.

Ejecuta siempre desde la raíz y con `.venv`. Documenta el archivo de salida, el
cache esperado y el comando de reanudación.

## Orquestador multiciudad

`scripts/run_multicity_overnight.py` compone el pipeline canónico; no contiene
otro camino científico. El batch declarativo
`config/operations/multicity_14.yaml` relaciona cada estudio agregado con su
acompañante nativo y exige las 14 capas portables comunes. Cada capa y cada
producto temporal es una tarea separada, de modo que el presupuesto nocturno se
detiene únicamente entre checkpoints durables.

Los estudios actuales son Lima, Bogotá, Valle de Aburrá, Medellín, CDMX, São
Paulo y Buenos Aires AMBA. El orden por defecto sigue la prioridad de la cohorte
y nunca paraleliza proveedores. `--city` acepta el id corto o el Study agregado.

Primero inspecciona el plan; esto no escribe ni contacta proveedores:

```bash
.venv/bin/python scripts/run_multicity_overnight.py \
  --city lima \
  --dry-run
```

Después deja una ciudad durante una noche. En macOS, `caffeinate` evita que el
equipo se suspenda; el runner se detiene entre tareas al alcanzar diez horas:

```bash
caffeinate -dimsu .venv/bin/python scripts/run_multicity_overnight.py \
  --city lima \
  --max-hours 10
```

Ejecuta exactamente el mismo comando la noche siguiente. `--resume` valida los
bundles existentes y cada recolector omite sus años, regiones, tags o celdas ya
cacheados. No es necesario editar una lista de pendientes.

Para procesar la cola completa durante varias noches:

```bash
caffeinate -dimsu .venv/bin/python scripts/run_multicity_overnight.py \
  --max-hours 10
```

Una corrida completa atraviesa estas fases:

1. preflight offline de estudios agregado y nativo;
2. 14 capas agregadas, una tarea por capa;
3. 14 capas nativas, una tarea por capa, y release nativa;
4. productos anuales, una tarea por ciudad y capa temporal;
5. COGs verificables y grilla Dynamic World real;
6. gate de serie temporal completa, perfiles, release final y verificación;
7. publicación de prueba bajo `cache/`, auditoría espacial estricta y gate de
   cobertura `production`;
8. publicación canónica atómica y repetición de ambos gates sobre la app.

Se puede repetir `--phase` para recuperar una parte concreta:

```bash
# Solo productos anuales que aún falten
.venv/bin/python scripts/run_multicity_overnight.py \
  --city lima --phase temporal --max-hours 10

# Solo posproceso, publicación y gates; no vuelve a recolectar las 14 capas
.venv/bin/python scripts/run_multicity_overnight.py \
  --city lima \
  --phase resolution --phase publish --phase validate \
  --max-hours 10
```

`--max-hours 0` desactiva el límite, pero no se recomienda para todo el batch:
una sola ciudad puede requerir unas 13 horas cuando faltan 63 productos
capa-año. El límite se evalúa entre tareas; nunca mata una descarga a mitad de
su checkpoint.

## Estado y recuperación

Cada invocación crea un directorio local ignorado por Git:

```text
cache/multicity_runs/<YYYYMMDD_HHMMSS>/
├── summary.json
├── summary.md
├── incident_candidates.md
└── tasks/*.log
```

El estado se reescribe atómicamente después de cada tarea. `failed` conserva el
log y permite continuar con tareas independientes; `blocked` evita publicar una
ciudad con un prerrequisito fallido; `deferred` indica que terminó el presupuesto
horario y no es un error. Un lock en `cache/.multicity_overnight.lock` impide dos
corridas simultáneas que competirían por GEE/Overpass.

La app canónica no se reemplaza directamente: primero se construye el mismo
bundle bajo `cache/multicity_publish_gate/<ciudad>/`. Solo si ese bundle pasa la
auditoría estricta, la cobertura `production` y el panel de información se
publica en `webapp/public/data`. Una serie temporal incompleta también bloquea
esta promoción.

Tras un fallo, revisa `summary.md` e `incident_candidates.md` y vuelve a ejecutar
el mismo comando. El cache científico no se borra y `--force` no forma parte de
este flujo. Sigue [Incidentes multiciudad](incidentes-multiciudad.md) para
convertir el fallo en una lección estable.

## Qué significa «14 en resolución»

El número 14 mide capas portables completas, no promete catorce rásters finos.
El soporte publicable depende del método: un COG nativo, una grilla analítica
real o un resumen administrativo pueden ser la representación honesta. La
ciudad solo se gradúa cuando `spatial-audit --strict` y
`resolution-coverage --tier production` aceptan lo que su manifest declara;
no se infiere detalle desde el catálogo global ni desde el nombre de la capa.
