#!/usr/bin/env bash
# Overnight batch: full portable layer set for Valle de Aburra + Medellin.
# Each `exposome run` call is its own checkpointed pipeline (tqdm progress,
# skip-if-cached per layer); --resume lets a second run pick up cleanly if
# this gets interrupted partway through. Two independent studies, same
# relationship as buenos_aires_amba (metro) + buenos_aires_comunas (city) --
# run sequentially here, not derived from one another.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

mkdir -p logs
stamp="$(date +%Y%m%d_%H%M)"

echo "=== INICIO: $(date) ==="

echo "--- valle_aburra_municipios (14 layers, agregado por municipio) ---"
exposome run --study valle_aburra_municipios --resume 2>&1 | tee "logs/valle_aburra_municipios_${stamp}.log"

echo "--- medellin_comunas (14 layers, agregado por comuna/corregimiento) ---"
exposome run --study medellin_comunas --resume 2>&1 | tee "logs/medellin_comunas_${stamp}.log"

echo "=== FIN: $(date) ==="
echo "Revisa logs/ para el detalle de cada estudio."
