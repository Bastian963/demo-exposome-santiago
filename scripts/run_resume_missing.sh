#!/usr/bin/env bash
# Complete only the work still missing after the 2026-07-17/18 batch.
#
# The two ERA5-Land prefetches create the cache required by climate_heat.
# Study runs are sequential to avoid saturating Overpass; --resume reuses all
# layer, year, region, tag and commune checkpoints already on disk.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"
FAILED=()

run_logged() {
  local label="$1"
  shift
  local log="logs/${label}_${stamp}.log"

  echo "--- ${label} ---"
  if "$@" 2>&1 | tee "$log"; then
    echo "${label}: OK"
  else
    echo "${label}: FAILED (see ${log})"
    FAILED+=("${label}")
  fi
}

echo "=== INICIO: $(date) ==="

# climate_heat uses ERA5-Land and needs this study-scoped 2024 cache first.
run_logged \
  medellin_comunas_era5land_2024 \
  python scripts/run_climate_fetch.py \
    --city medellin_comunas \
    --years 2024 \
    --cache-dir cache/co/medellin/medellin_comunas/climate_heat

run_logged \
  sao_paulo_distritos_era5land_2024 \
  python scripts/run_climate_fetch.py \
    --city sao_paulo_distritos \
    --years 2024 \
    --cache-dir cache/br/sao_paulo/sao_paulo_distritos/climate_heat

# Valle de Aburrá is already complete, so it is intentionally omitted.
STUDIES=(
  medellin_comunas
  lima_distritos
  bogota_localidades
  cdmx_native
  sao_paulo_distritos
)

for study in "${STUDIES[@]}"; do
  run_logged "${study}_resume" exposome run --study "$study" --resume
done

echo "=== FIN: $(date) ==="
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "Tareas con fallos: ${FAILED[*]}"
  echo "Los checkpoints válidos se conservaron; vuelve a ejecutar este mismo script."
  exit 1
fi

echo "Todos los estudios pendientes terminaron correctamente."
