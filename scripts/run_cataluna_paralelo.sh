#!/usr/bin/env bash
# Adelanta capas de Cataluña en paralelo al batch grande (run_spain_night.sh),
# que ahora mismo está en las capas OSM de País Vasco.
#
#   ./scripts/run_cataluna_paralelo.sh gee    # 8 capas GEE, ~2 h
#   ./scripts/run_cataluna_paralelo.sh osm    # food_environment + healthcare
#
# Por qué se puede paralelizar, y hasta dónde:
#
#   gee -> Google Earth Engine y Overpass son proveedores distintos y no
#   comparten cuota. Cero contención con lo que corre en País Vasco. Es la
#   paralelización gratis.
#
#   osm -> comprobado 2026-08-10 contra https://overpass-api.de/api/status:
#   "Rate limit: 2, 2 slots available now". El batch grande usa un slot, así
#   que este proceso usa el segundo y no se pasa del límite por IP. NO lanzar
#   un tercer flujo OSM. Estas dos capas usan POINT_TAG_MAX_TILE_SPAN_DEG=1.0,
#   o sea 43 tiles por capa en vez de los 1.786 de greenspace_access, así que
#   son las baratas y las que conviene adelantar.
#
# greenspace_access de Cataluña NO se puede partir: corre como un bloque por
# estudio. Sus 1.786 tiles son el 69% del tiempo total y necesitan otra
# solución (extracto local de Geofabrik), no más concurrencia.
#
# Ambos escriben en directorios de salida y caché propios por capa, y usan
# --no-build-master, así que no chocan con el batch grande. Cuando éste llegue
# a Cataluña, --resume saltea lo que estos dejaron hecho.
#
# OJO: esto consume batería. Sin cargador enchufado, lanzar procesos en
# paralelo acelera la muerte por hibernación (ver 2026-08-06, 15:27).
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
source .venv/bin/activate

GEE_LAYERS="air_quality_satellite,alan,greenspace_coverage,greenspace_multisource,precipitation,climate_heat,wind,wildfire"
OSM_LAYERS="food_environment,healthcare"

case "${1:-}" in
    gee) layers="$GEE_LAYERS"; tag="gee" ;;
    osm) layers="$OSM_LAYERS"; tag="osm" ;;
    *) echo "uso: $0 [gee|osm]" >&2; exit 2 ;;
esac

if ! pmset -g batt 2>/dev/null | grep -q "AC Power"; then
    echo "*** AVISO: estás en batería. Esto la consume más rápido y la corrida" >&2
    echo "*** puede morir por hibernación sin dejar error en el log." >&2
fi

stamp="$(date +%Y%m%d_%H%M)"
mkdir -p logs
log="logs/cataluna_${tag}_${stamp}.log"

echo "=== cataluna_comarques [${tag}] INICIO: $(date) ==="
echo "capas: ${layers}"

if exposome run --study cataluna_comarques --layers "$layers" --resume \
    --no-build-master 2>&1 | tee "$log"; then
    rc=0
else
    rc=$?
fi

echo "=== cataluna_comarques [${tag}] FIN: $(date) (codigo ${rc}) ==="
n=$(find data/processed/es/cataluna/cataluna_comarques -maxdepth 2 -name manifest.json 2>/dev/null | wc -l | tr -d ' ')
echo "Cataluña ahora: ${n}/14 capas con manifest.json"
exit "$rc"
