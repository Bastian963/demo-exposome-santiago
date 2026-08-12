#!/usr/bin/env bash
# Overnight batch: full portable layer set for CDMX (aggregate + native).
# Each `exposome run` call is its own checkpointed pipeline (tqdm progress,
# skip-if-cached per layer); --resume lets a second run pick up cleanly if
# this gets interrupted partway through.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"

echo "=== INICIO: $(date) ==="

echo "--- cdmx_alcaldias (14 layers, agregado por alcaldia) ---"
exposome run --study cdmx_alcaldias --resume 2>&1 | tee "logs/cdmx_alcaldias_${stamp}.log"

echo "--- cdmx_native (13 layers, GeoTIFF/nativo a resolucion de pixel) ---"
exposome run --study cdmx_native --resume 2>&1 | tee "logs/cdmx_native_${stamp}.log"

echo "=== FIN: $(date) ==="
echo "Revisa logs/ para el detalle de cada estudio."
