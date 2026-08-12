#!/usr/bin/env bash
# Finish only the layers still missing after run_resume_missing.sh.
#
# By default this waits for the Santiago temporal download before touching GEE
# or Overpass. Set WAIT_FOR_SANTIAGO=0 to process only the other cities in
# parallel. Every command uses the existing layer/year/region/tag checkpoints.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: falta .venv. Ejecuta primero: uv sync --all-extras"
  exit 2
fi
source .venv/bin/activate

mkdir -p logs cache
STAMP="$(date +%Y%m%d_%H%M)"
LOCK_DIR="cache/.run_finish_pending.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID=""
  if [ -r "$LOCK_DIR/pid" ]; then
    read -r LOCK_PID < "$LOCK_DIR/pid" || true
  fi
  if [[ "$LOCK_PID" =~ ^[0-9]+$ ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "ERROR: ya existe $LOCK_DIR y su proceso sigue activo (PID $LOCK_PID)."
    exit 2
  fi

  echo "Aviso: recuperando bloqueo obsoleto de una ejecución anterior."
  rm -f "$LOCK_DIR/pid"
  if ! rmdir "$LOCK_DIR" 2>/dev/null || ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "ERROR: no fue posible recuperar $LOCK_DIR de forma segura." >&2
    exit 2
  fi
fi
echo "$$" > "$LOCK_DIR/pid"
WAIT_SLEEP_PID=""
cleanup_lock() {
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
handle_signal() {
  local exit_code="$1"
  if [ -n "${WAIT_SLEEP_PID:-}" ]; then
    kill -TERM "$WAIT_SLEEP_PID" 2>/dev/null || true
  fi
  exit "$exit_code"
}
trap cleanup_lock EXIT
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

echo "=== INICIO: $(date) ==="
echo "Repositorio: $REPO"

# Avoid competing with the independent 103-task Santiago temporal run unless
# the caller explicitly opts into parallel execution.
WAIT_FOR_SANTIAGO="${WAIT_FOR_SANTIAGO:-1}"
case "$WAIT_FOR_SANTIAGO" in
  0)
    echo "[$(date)] Modo paralelo: no se esperará a Santiago; iniciando las demás ciudades."
    ;;
  1)
    while pgrep -f "[r]un_santiago_missing_annual_exposomes.py" >/dev/null 2>&1; do
      echo "[$(date)] Santiago temporal sigue activo; esperando 5 minutos..."
      sleep 300 &
      WAIT_SLEEP_PID=$!
      wait "$WAIT_SLEEP_PID" || true
      WAIT_SLEEP_PID=""
    done
    echo "[$(date)] No hay descarga temporal de Santiago activa; iniciando pendientes."
    ;;
  *)
    echo "ERROR: WAIT_FOR_SANTIAGO debe ser 0 o 1 (valor: $WAIT_FOR_SANTIAGO)." >&2
    exit 2
    ;;
esac

run_logged() {
  local label="$1"
  shift
  local log="logs/${label}_${STAMP}.log"

  echo "--- ${label} ---"
  if "$@" 2>&1 | tee "$log"; then
    echo "${label}: OK"
    return 0
  fi
  echo "${label}: FAILED (ver ${log})"
  return 1
}

run_pass() {
  local pass="$1"
  local pass_failed=0

  echo "=== PASADA ${pass}: $(date) ==="

  # Invalid all-NaN caches from the old ERA5 parser are quarantined
  # automatically and fetched again. Valid caches are loaded immediately.
  run_logged "p${pass}_medellin_era5land_2024" \
    python scripts/run_climate_fetch.py \
      --city medellin_comunas \
      --years 2024 \
      --cache-dir cache/co/medellin/medellin_comunas/climate_heat \
    || pass_failed=1

  run_logged "p${pass}_sao_paulo_era5land_2024" \
    python scripts/run_climate_fetch.py \
      --city sao_paulo_distritos \
      --years 2024 \
      --cache-dir cache/br/sao_paulo/sao_paulo_distritos/climate_heat \
    || pass_failed=1

  # Only the absent layers are selected. Existing manifests and all granular
  # caches remain untouched; a successful study call also builds its master.
  run_logged "p${pass}_medellin_pendientes" \
    exposome run --study medellin_comunas \
      --layers climate_heat,wind,wildfire,greenspace_access,healthcare \
      --resume \
    || pass_failed=1

  sleep 180
  run_logged "p${pass}_lima_pendientes" \
    exposome run --study lima_distritos \
      --layers greenspace_access \
      --resume \
    || pass_failed=1

  sleep 180
  run_logged "p${pass}_bogota_pendientes" \
    exposome run --study bogota_localidades \
      --layers greenspace_access,healthcare \
      --resume \
    || pass_failed=1

  sleep 180
  run_logged "p${pass}_cdmx_pendientes" \
    exposome run --study cdmx_native \
      --layers food_environment \
      --resume \
    || pass_failed=1

  sleep 180
  run_logged "p${pass}_sao_paulo_pendientes" \
    exposome run --study sao_paulo_distritos \
      --layers climate_heat,greenspace_access,healthcare \
      --resume \
    || pass_failed=1

  return "$pass_failed"
}

SUCCESS=0
if run_pass 1; then
  SUCCESS=1
else
  echo "[$(date)] Quedaron fallos transitorios; esperando 15 minutos antes de una segunda pasada."
  echo "Las capas completadas se saltaran gracias a --resume."
  sleep 900
  if run_pass 2; then
    SUCCESS=1
  fi
fi

echo "=== FIN: $(date) ==="
if [ "$SUCCESS" -eq 1 ]; then
  echo "Todos los estudios pendientes terminaron y sus masters pudieron construirse."
  exit 0
fi

echo "Persisten uno o mas fallos despues de dos pasadas. Revisa logs/p2_*_${STAMP}.log."
echo "Los checkpoints y resultados validos quedaron conservados."
exit 1
