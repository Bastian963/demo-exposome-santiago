#!/usr/bin/env bash
# Overnight batch: full portable layer set (14) for the two Spanish studies.
# Each `exposome run` call is its own checkpointed pipeline (tqdm progress,
# skip-if-cached per layer); --resume lets a second run pick up cleanly if
# this gets interrupted partway through.
#
# Two deliberate departures from run_cdmx_overnight.sh / run_medellin_overnight.sh:
#
#   1. Pais Vasco runs FIRST. It is 3 GISCO provinces against Catalunya's 43
#      ICGC comarques, so it finishes quickly and exercises the whole Spanish
#      path -- config, boundaries, ES country_args, OSM region_query tiling --
#      before committing hours to the long one.
#
#   2. A failing study does not abort the other. Those scripts use a bare
#      `set -e` with `tee`, which would kill the batch outright. These two
#      studies are independent (no shared inputs, no derived layers between
#      them), so an Overpass outage in one must not cost the other. Each run's
#      status is captured, the batch continues, and the script exits non-zero
#      at the end if anything failed.
#
# Do NOT run this from an agent session: it contacts GEE, Open-Meteo and
# OSM/Overpass and takes hours. A human launches it, ideally under caffeinate.
#
#   caffeinate -i ./scripts/run_cataluna_overnight.sh
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"
failed=()

run_study() {
    local study="$1"
    local label="$2"
    echo "--- ${study} (${label}) ---"
    if exposome run --study "$study" --resume 2>&1 | tee "logs/${study}_${stamp}.log"; then
        echo "    ${study}: OK"
    else
        echo "    ${study}: FALLO (ver logs/${study}_${stamp}.log)" >&2
        failed+=("$study")
    fi
}

echo "=== INICIO: $(date) ==="

run_study pais_vasco_provincias "14 layers, agregado por provincia (3 unidades)"
run_study cataluna_comarques "14 layers, agregado por comarca (43 unidades)"

echo "=== FIN: $(date) ==="

if [ ${#failed[@]} -gt 0 ]; then
    echo "Estudios con fallos: ${failed[*]}" >&2
    echo "Reanudables: volver a lanzar este script salta lo que ya tenga manifest.json." >&2
    exit 1
fi

echo "Ambos estudios completos. Siguiente paso:"
echo "  exposome verify --study pais_vasco_provincias"
echo "  exposome verify --study cataluna_comarques"
