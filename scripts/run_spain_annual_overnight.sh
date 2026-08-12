#!/usr/bin/env bash
# Overnight batch: annual (temporal) exposome series for the two Spanish
# studies -- the `temporal` phase, which run_cataluna_overnight.sh does NOT do.
#
# The layers phase writes one cross-sectional row per unit (pm25_acag_2015_2022
# is a single 2015-2022 mean, not eight yearly values). This script produces
# data/processed/es/<city>/<study>/temporal_exposomes/<layer>/<year>/annual.csv,
# the same artifact Bogota, Lima, CDMX and Santiago already have and the one
# the GEMMA time slider reads. Bogota's reference shape is 9 layers x ~10 years
# = 83 files; expect a similar count here, minus whatever a study does not
# enable. OSM snapshots and the static Meta canopy produce no series by design.
#
# Requires the layers phase to be complete for each study: the temporal specs
# are discovered from layers that actually ran. Use --wait to launch this
# before run_cataluna_overnight.sh has finished; it will block until that batch
# exits and only then start.
#
# Same two departures from the CDMX/Medellin pattern as run_cataluna_overnight.sh:
# Pais Vasco first (3 provinces, fast validation of the whole path), and a
# failing study does not abort the other.
#
# Do NOT run this from an agent session: it contacts GEE and Open-Meteo and
# takes hours. A human launches it.
#
#   ./scripts/run_spain_annual_overnight.sh --status   # offline, what is missing
#   caffeinate -i ./scripts/run_spain_annual_overnight.sh --wait
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

RUNNER="scripts/run_missing_annual_exposomes.py"
STUDIES=(pais_vasco_provincias cataluna_comarques)

# --only permite adelantar la fase anual de UN estudio mientras el otro sigue
# en sus capas OSM. Las series anuales salen de GEE y no dependen de las capas
# OSM (comprobado 2026-08-10: pais_vasco_provincias declara 83 targets, todos
# de las 9 capas GEE, que ya estaban completas mientras greenspace_access
# seguia corriendo). Sin esto habria que esperar dias de Overpass para empezar
# 15 h de trabajo que no dependen de Overpass en absoluto.
mode="run"
usage() {
    echo "uso: $0 [--status|--wait] [--only <study_id>]" >&2
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        --status) mode="status"; shift ;;
        --wait)   mode="wait";   shift ;;
        --only)
            [ -n "${2:-}" ] || usage
            case " ${STUDIES[*]} " in
                *" $2 "*) STUDIES=("$2") ;;
                *) echo "study_id desconocido: $2 (validos: ${STUDIES[*]})" >&2; exit 2 ;;
            esac
            shift 2
            ;;
        *) usage ;;
    esac
done

if [ "$mode" = "status" ]; then
    for study in "${STUDIES[@]}"; do
        echo "=== $study ==="
        PYTHONPYCACHEPREFIX=/tmp .venv/bin/python "$RUNNER" --study "$study" --status
    done
    exit 0
fi

if [ "$mode" = "wait" ]; then
    if pgrep -f run_cataluna_overnight.sh >/dev/null 2>&1; then
        echo "Esperando a que termine run_cataluna_overnight.sh (fase layers)..."
        while pgrep -f run_cataluna_overnight.sh >/dev/null 2>&1; do
            sleep 60
        done
        echo "Fase layers terminada a las $(date '+%H:%M:%S'). Arrancando fase anual."
    fi
fi

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"
failed=()

echo "=== INICIO fase anual: $(date) ==="

for study in "${STUDIES[@]}"; do
    echo "--- ${study} (series anuales por exposoma) ---"
    if PYTHONPYCACHEPREFIX=/tmp .venv/bin/python "$RUNNER" \
        --study "$study" --resume 2>&1 | tee "logs/${study}_annual_${stamp}.log"; then
        echo "    ${study}: OK"
    else
        echo "    ${study}: FALLO (ver logs/${study}_annual_${stamp}.log)" >&2
        failed+=("$study")
    fi
done

echo "=== FIN fase anual: $(date) ==="

if [ ${#failed[@]} -gt 0 ]; then
    echo "Estudios con fallos: ${failed[*]}" >&2
    echo "Reanudable: volver a lanzar salta las cosechas ya materializadas." >&2
    exit 1
fi

echo "Series anuales completas. Conteo final:"
for study in "${STUDIES[@]}"; do
    case "$study" in
        pais_vasco_provincias) loc="es/pais_vasco" ;;
        cataluna_comarques)    loc="es/cataluna" ;;
    esac
    n=$(find "data/processed/$loc/$study/temporal_exposomes" -name annual.csv 2>/dev/null | wc -l | tr -d ' ')
    echo "  $study: $n archivos annual.csv"
done
