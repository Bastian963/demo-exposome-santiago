# Nodo WSL para descargar exposomas

Este runbook prepara un computador Windows compartido como nodo de recolección
de BrainLat. El código, el entorno Python, los checkpoints y los resultados
viven dentro de una distribución WSL 2 dedicada. No se reutilizan Anaconda,
Python ni Docker de Windows.

Este nodo es staging operativo, no una fuente de verdad paralela. La propiedad,
entrega y aceptación futura de sus datos se rige por la
[arquitectura de nodos distribuidos](../../architecture/distributed-collection-nodes.md)
y [ADR 0013](../../adr/0013-distributed-collection-node-handoff.md).

## Identidad del nodo

| Campo | Valor |
|---|---|
| ID lógico | `brainlat-wsl-amd-iii` |
| Host observado | `AMD-III` |
| Distribución | WSL 2 `BrainLat`, Ubuntu 24.04 |
| Rama | `runner/multicity-2026-08-12` |
| Estudios | Santa Marta, Cartagena y Pasto; agregado y nativo |

El estado vivo no se escribe en esta tabla. Se consulta en `tmux`, los outputs y
los resúmenes de corrida.

## Disposición esperada

La distribución se registra como `BrainLat` y su disco virtual reside en
`D:\bastian\WSL\BrainLat`. Dentro de Ubuntu se trabaja únicamente desde:

```text
/home/bayala/projects/Brainlat-runner/
├── .venv/
├── cache/
├── config/
├── data/
│   ├── raw/
│   ├── reference/
│   └── processed/
├── scripts/
├── src/
└── tests/
```

No ejecutes el pipeline desde `/mnt/c` ni `/mnt/d`: el cruce entre NTFS y WSL
penaliza Git, Python y las escrituras incrementales. Aunque las rutas Linux se
vean bajo `/home/bayala`, su almacenamiento físico sigue dentro del VHD de
`D:\bastian\WSL\BrainLat`.

## Instalación inicial

En Ubuntu 24.04:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git curl ca-certificates build-essential pkg-config unzip tmux
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone --branch runner/multicity-2026-08-12 --single-branch https://github.com/Bastian963/demo-exposome-santiago.git Brainlat-runner
cd Brainlat-runner
uv sync --all-extras
```

`pyproject.toml` y `uv.lock` son la única autoridad del entorno. No uses Conda,
no ejecutes `pip install` y no sincronices `.venv` mientras haya una recolección
Python activa.

Verifica la instalación sin contactar proveedores:

```bash
.venv/bin/python --version
.venv/bin/exposome --help
PYTHONPYCACHEPREFIX=/tmp .venv/bin/python -m unittest tests.test_multicity_overnight tests.test_settings tests.test_studies
.venv/bin/python scripts/run_multicity_overnight.py --city lima --dry-run
```

## Referencias urbanas de Colombia

Santa Marta, Cartagena y Pasto usan la cabecera municipal oficial del Marco
Geoestadístico Nacional 2024 del DANE. No se usa el municipio rural completo y
no se inventan barrios. Una persona ejecuta una vez el constructor reanudable:

```bash
cd "$HOME/projects/Brainlat-runner"
.venv/bin/python scripts/migrations/build_colombia_urban_references.py
```

El comando muestra una barra de progreso de tres ciudades. Después de cada una
guarda un snapshot inmutable y manifestado bajo `data/raw/dane/`, y genera el
GeoJSON normalizado bajo `data/reference/co/`. Si se interrumpe, ejecuta el
mismo comando: verificará y omitirá las ciudades ya guardadas.

Mientras se revisan, esas referencias son staging local y se pueden ocultar del
estado Git sin borrarlas. Deben incluirse en el handoff y, una vez aceptadas,
versionarse centralmente como referencias espaciales pequeñas:

```bash
printf '%s\n' '/data/reference/co/santa_marta/santa_marta_urban/' '/data/reference/co/cartagena/cartagena_urban/' '/data/reference/co/pasto/pasto_urban/' >> .git/info/exclude
```

## Credenciales humanas

Google Earth Engine separa la identidad autenticada del proyecto que consume la
cuota. El nodo compartido usa su proyecto dedicado `brainlat`, seleccionado por
una variable local que no se versiona. Los demás nodos conservan
`exposome-api` como valor predeterminado:

```bash
export EXPOSOME_GEE_PROJECT=brainlat
.venv/bin/earthengine authenticate --auth_mode=notebook
.venv/bin/python -c "import ee,os; ee.Initialize(project=os.environ['EXPOSOME_GEE_PROJECT']); print('GEE OK')"
```

Para que las nuevas sesiones de Bash y `tmux` hereden la selección, guarda una
sola línea `export EXPOSOME_GEE_PROJECT=brainlat` en `~/.bashrc`. La variable
contiene únicamente el ID público del proyecto; el token OAuth permanece en
`~/.config/earthengine/credentials`, fuera del repositorio y del handoff.

ECOSTRESS no usa GEE. Requiere una cuenta NASA Earthdata y autenticación
interactiva humana:

```bash
.venv/bin/python -c "import earthaccess; earthaccess.login(strategy='interactive', persist=True)"
```

Esto guarda las credenciales en `~/.netrc`, fuera del repositorio. Nunca copies
ese archivo al proyecto, GitHub, logs o mensajes. El resto de las capas puede
usar GEE, Open-Meteo, OSM/Overpass o fuentes locales según su configuración.

## Preflight de las tres ciudades

Ejecuta siempre desde la raíz del repositorio. Antes de una noche de trabajo,
comprueba espacio, estado Git y el plan offline:

```bash
cd "$HOME/projects/Brainlat-runner"
df -h /
git status --short
.venv/bin/python scripts/run_multicity_overnight.py --city santa_marta --city cartagena --city pasto --dry-run
```

El dry-run no descarga ni escribe productos. Cuando el plan sea correcto, abre
una sesión persistente:

```bash
tmux new -s brainlat
cd "$HOME/projects/Brainlat-runner"
.venv/bin/python scripts/run_multicity_overnight.py --city santa_marta --city cartagena --city pasto --max-hours 10
```

Desacopla `tmux` con `Ctrl-b` y luego `d`. Para volver:

```bash
tmux attach -t brainlat
```

El computador debe permanecer conectado a corriente y Windows no debe entrar
en suspensión. Como es un equipo compartido, cualquier cambio global de energía
se coordina antes con su propietario.

### Convención de comandos para este nodo

Entrega al operador un solo comando por mensaje, en una única línea física, sin
continuaciones `\`. Así se evita que copiar y pegar introduzca un Enter en medio
de una URL, ruta o argumento.

Si GEE aún no está disponible, las cuatro capas OSM independientes se pueden
dejar secuencialmente en un `tmux` dedicado. Este comando cubre los seis Studies
y continúa con el siguiente aunque una invocación falle; `--resume` reutiliza
los checkpoints:

```bash
for s in {santa_marta,cartagena,pasto}_{urban,native}; do .venv/bin/exposome run --study "$s" --layers greenspace_access,walkability,food_environment,healthcare --resume --no-build-master; done
```

## Reanudación y orden de archivos

Después de una interrupción o al día siguiente, ejecuta exactamente el mismo
comando. Los recolectores omiten unidades ya cacheadas; no borres `cache/` ni
uses `--force` para simular una reanudación.

Cada invocación escribe su control bajo:

```text
cache/multicity_runs/<YYYYMMDD_HHMMSS>/
├── summary.json
├── summary.md
├── incident_candidates.md
└── tasks/*.log
```

Los payloads originales durables quedan en `data/raw/`, los checkpoints en
`cache/` y los productos normalizados en `data/processed/`. Revisa tamaños sin
mover archivos:

```bash
du -sh cache data/raw data/processed 2>/dev/null
```

No borres raw, referencias ni processed después de terminar. Permanecen en el
nodo hasta que un handoff sea verificado, aceptado y respaldado centralmente.
`cache/` tampoco se limpia mientras pueda ser necesario reanudar.

## Integración futura

No copies el repositorio completo ni sincronices mientras Python esté
escribiendo. La entrega futura se congelará bajo
`handoff/brainlat-wsl-amd-iii/<run_id>/` e incluirá:

- snapshots raw con `source_manifest.json`;
- referencias DANE de los seis Studies;
- bundles y releases procesadas con manifests;
- resúmenes e incidentes de las corridas.

Quedan fuera `.git`, `.venv`, `.netrc`, tokens y el caché ordinario. El workspace
central verificará tamaños y SHA-256 en staging antes de promover paths. Un path
existente con hash distinto bloqueará la importación; nunca se sobrescribirá.

## Actualización del runner

No edites código en el nodo de descarga. No ejecutes `git pull` ni `uv sync`
mientras exista una recolección activa. Cuando no haya procesos Python y se
publique una revisión:

```bash
cd "$HOME/projects/Brainlat-runner"
git status --short
git pull --ff-only origin runner/multicity-2026-08-12
uv sync --all-extras
```

`git status --short` debe estar vacío antes del pull. Los datos, checkpoints y
logs están ignorados por Git y permanecen en el nodo.

## Detención segura

`Ctrl-C` solicita detener la tarea activa; sus checkpoints anteriores se
conservan. Espera a recuperar el prompt antes de apagar WSL. Desde PowerShell:

```powershell
wsl --terminate BrainLat
```

No uses `wsl --unregister BrainLat`: ese comando elimina la distribución y todo
su VHD, incluidos datos y resultados.
