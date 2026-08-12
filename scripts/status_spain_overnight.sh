#!/usr/bin/env bash
# Read-only progress snapshot for the Spanish overnight batch
# (scripts/run_cataluna_overnight.sh). Contacts nothing: it only looks at
# running processes and at which layers have already written a manifest.json,
# which is the only honest completion signal -- a tqdm bar at 0% tells you
# nothing about whether the layer produced output.
#
#   ./scripts/status_spain_overnight.sh          # one snapshot
#   ./scripts/status_spain_overnight.sh --watch  # refresh every 30 s
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PORTABLE=(
    air_quality_pm25 air_quality_satellite alan greenspace_coverage
    greenspace_multisource precipitation climate_heat wind wildfire
    greenspace_access walkability social_infrastructure food_environment
    healthcare
)

# study_id:<iso2>/<city>
STUDIES=(
    pais_vasco_provincias:es/pais_vasco
    cataluna_comarques:es/cataluna
)

snapshot() {
    printf '\n=== %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')"

    # La corrida del 2026-08-06 murio a las 15:27 sin error ni traceback: el
    # portatil se quedo sin bateria y entro en 'Low Power Sleep' con 1% de
    # carga. caffeinate -i evita el sleep por inactividad pero NO la
    # hibernacion por bateria agotada, asi que el estado de energia es parte
    # del diagnostico, no un adorno.
    local batt
    batt="$(pmset -g batt 2>/dev/null)"
    if printf '%s' "$batt" | grep -q "AC Power"; then
        echo "energia: ENCHUFADO"
    else
        printf 'energia: *** EN BATERIA *** %s\n' \
            "$(printf '%s' "$batt" | sed -n '2s/.*\t\(.*\)present.*/\1/p')"
        echo "         enchufalo o la corrida muere sin dejar rastro en el log"
    fi

    # Puede haber varios `exposome run` a la vez: el batch grande mas los
    # procesos de adelanto (run_cataluna_paralelo.sh). Se listan todos -- 0% de
    # CPU significa esperando red (GEE/Overpass), no colgado.
    local pids pid study layers cpu
    pids="$(pgrep -f 'exposome run --study' 2>/dev/null)"
    if [ -z "$pids" ]; then
        echo "procesos: NINGUNO corriendo"
    else
        for pid in $pids; do
            study="$(ps -o command= -p "$pid" 2>/dev/null | sed -n 's/.*--study \([a-z_]*\).*/\1/p')"
            cpu="$(ps -o %cpu= -p "$pid" 2>/dev/null | tr -d ' ')"
            layers="$(ps -o command= -p "$pid" 2>/dev/null | sed -n 's/.*--layers \([a-z_,]*\).*/\1/p')"
            if [ -n "$layers" ]; then
                layers="$(printf '%s' "$layers" | tr ',' ' ' | wc -w | tr -d ' ') capas"
            else
                layers="estudio completo"
            fi
            printf 'proceso: %-24s %-18s cpu %s%%\n' "${study:-?}" "$layers" "${cpu:-?}"
        done
    fi
    if pgrep -f run_spain_night.sh >/dev/null 2>&1; then
        echo "         (batch principal vivo)"
    else
        echo "         *** batch principal NO corriendo ***"
    fi

    local entry study loc dir done_n missing layer
    for entry in "${STUDIES[@]}"; do
        study="${entry%%:*}"
        loc="${entry##*:}"
        dir="data/processed/$loc/$study"
        done_n=0
        missing=""
        for layer in "${PORTABLE[@]}"; do
            if [ -f "$dir/$layer/manifest.json" ]; then
                done_n=$((done_n + 1))
            else
                missing="$missing $layer"
            fi
        done
        printf '%-24s %2d/%d capas' "$study" "$done_n" "${#PORTABLE[@]}"
        [ -n "$missing" ] && printf '\n    faltan:%s' "$missing"
        printf '\n'
    done

    # --- fase anual (temporal_exposomes) ---
    # Sólo aparece una vez que run_spain_annual_overnight.sh arrancó. La
    # referencia son Lima y CDMX: 9 capas x ~10 años = 83 annual.csv (Bogotá
    # tiene 82, le falta greenspace_multisource/2019 -- hueco conocido y
    # aceptado, no un fallo). Las 5 capas OSM no generan serie por diseño, así
    # que 14/14 en la fase de capas nunca da 14 acá.
    if pgrep -f run_spain_annual_overnight.sh >/dev/null 2>&1; then
        if pgrep -f run_missing_annual_exposomes.py >/dev/null 2>&1; then
            echo ""
            echo "fase anual: CORRIENDO"
        else
            echo ""
            echo "fase anual: EN ESPERA (arranca cuando termine la fase de capas)"
        fi
    fi

    local total_annual=0
    for entry in "${STUDIES[@]}"; do
        study="${entry%%:*}"
        loc="${entry##*:}"
        dir="data/processed/$loc/$study/temporal_exposomes"
        [ -d "$dir" ] || continue
        local n_files
        n_files="$(find "$dir" -name annual.csv 2>/dev/null | wc -l | tr -d ' ')"
        total_annual=$((total_annual + n_files))
        printf '%-24s %3d annual.csv (ref. Lima/CDMX: 83)\n' "$study" "$n_files"
        local ldir layer years
        for ldir in "$dir"/*/; do
            [ -d "$ldir" ] || continue
            layer="$(basename "$ldir")"
            years="$(ls -1 "$ldir" 2>/dev/null | sort | tr '\n' ' ')"
            printf '    %-24s %s\n' "$layer" "$years"
        done
    done
    [ "$total_annual" -gt 0 ] && printf 'total annual.csv: %d\n' "$total_annual"

    local newest
    newest="$(ls -t logs/pais_vasco_provincias_*.log logs/cataluna_comarques_*.log logs/*_annual_*.log 2>/dev/null | head -1)"
    if [ -n "$newest" ]; then
        printf '\nultima linea de %s:\n  ' "$newest"
        tr '\r' '\n' < "$newest" | grep -v '^[[:space:]]*$' | tail -1
    fi
}

if [ "${1:-}" = "--watch" ]; then
    while true; do
        snapshot
        sleep 30
    done
else
    snapshot
fi
