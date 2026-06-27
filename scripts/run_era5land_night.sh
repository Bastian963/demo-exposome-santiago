#!/usr/bin/env bash
# Run ERA5-Land extraction year-by-year overnight.
# Safe for sessions that get killed: each year is cached separately.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_PATH="$REPO_ROOT/.conda/envs/exposome"

echo "=== ERA5-Land nightly fetch: 2015-2024 ==="
echo "Started: $(date)"

for year in 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
    echo ""
    echo "--- Fetching $year ---"
    mamba run -p "$ENV_PATH" python scripts/run_climate_fetch.py --years "$year"
    echo "Completed $year at $(date)"
done

echo ""
echo "=== All years fetched ==="
echo "Combined file should be at: data/processed/santiago_climate_era5land_daily_2015_2024.csv"
echo "Finished: $(date)"

# Optional: run metrics once the full series is available
# echo ""
# echo "=== Running annual metrics ==="
# mamba run -p "$ENV_PATH" python scripts/run_climate_metrics.py \
#     --daily-csv data/processed/santiago_climate_era5land_daily_2015_2024.csv
