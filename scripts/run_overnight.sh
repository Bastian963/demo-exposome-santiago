#!/usr/bin/env bash
# Overnight script to complete missing exposome layers and rebuild the master table.
# Safe for interrupted sessions: ERA5-Land caches each year separately.

set -euo pipefail

REPO="/Users/bastianayalainostroza/Dropbox/Brainlat"
cd "$REPO"
ENV="$REPO/.conda/envs/exposome"

echo "=== INICIO: $(date) ==="

# FASE 1: Capas GEE que faltan
# Nota: Open-Meteo 2015-2024 no se reintenta aqui porque sigue bloqueado por rate limit 429.

echo "--- ERA5-Land 2015-2024 ---"
for year in 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
    echo "  Fetching $year..."
    mamba run -p "$ENV" python scripts/run_climate_fetch.py --years "$year"
done

echo "--- Greenspace coverage ---"
mamba run -p "$ENV" python scripts/run_greenspace_coverage.py

echo "--- Precipitation CHIRPS 2015-2024 ---"
mamba run -p "$ENV" python scripts/run_precipitation.py

# FASE 2: Metricas climaticas anuales desde ERA5-Land completo
echo "--- Climate metrics 2015-2024 ---"
mamba run -p "$ENV" python scripts/run_climate_metrics.py \
    --daily-csv data/processed/santiago_climate_era5land_daily_2015_2024.csv

# FASE 3: Integracion final
echo "--- Rebuild master exposome ---"
mamba run -p "$ENV" python scripts/build_master_exposome.py

echo "--- Sleep context update ---"
mamba run -p "$ENV" python scripts/run_sleep_context.py

echo "=== FIN: $(date) ==="
echo "Verifica los outputs en data/processed/"
