#!/usr/bin/env bash
# Sequential resume of the 6 studies left incomplete by the 2026-07-17
# Overpass outage: four `exposome run --resume` batches (valle_aburra,
# medellin, cdmx, lima+bogota launched separately) ran in parallel and all
# stalled at once because they saturated overpass-api.de's per-IP connection
# limit together. This script runs the same studies one at a time -- a
# single consumer of Overpass -- so a mirror outage in one study's OSM layer
# doesn't cascade into every study's retries colliding again.
#
# Each `exposome run --study X --resume` is independently checkpointed
# (tqdm progress, skip-if-cached per layer, per-region/tag OSM caches under
# cache/); interrupting this script and re-running it later picks up exactly
# where each study left off. A study that still fails does not stop the
# rest -- this script keeps going and prints a pass/fail summary at the end.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"

STUDIES=(
  valle_aburra_municipios   # wind, wildfire, 5 OSM layers, master
  medellin_comunas          # 14 layers from scratch (never started)
  lima_distritos            # greenspace_access (18/50 regions cached) + 4 OSM layers + master
  bogota_localidades        # greenspace_access (8/20 regions cached) + 4 OSM layers + master
  cdmx_native               # food_environment + healthcare
  sao_paulo_distritos       # 14 portable layers; 96 districts, intentionally last
)

echo "=== INICIO: $(date) ==="

FAILED=()
for study in "${STUDIES[@]}"; do
  echo "--- ${study} ---"
  log="logs/${study}_resume_${stamp}.log"
  if exposome run --study "${study}" --resume 2>&1 | tee "${log}"; then
    echo "${study}: OK"
  else
    echo "${study}: FAILED (see ${log})"
    FAILED+=("${study}")
  fi
done

echo "=== FIN: $(date) ==="
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "Estudios con fallos: ${FAILED[*]}"
  echo "Revisa logs/ para el detalle; --resume solo reintenta lo que falta."
  exit 1
fi
echo "Los 6 estudios terminaron sin capas fallidas."
