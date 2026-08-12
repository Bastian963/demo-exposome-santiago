#!/usr/bin/env bash
# Toda la noche española en un solo proceso: fase de capas y despues fase
# anual, para los dos estudios. Reemplaza el encadenado por --wait de dos
# procesos independientes -- si el watcher moria, la fase anual no corria y
# nadie se enteraba hasta la mañana.
#
#   1. run_cataluna_overnight.sh    -> 14 capas x 2 estudios
#   2. run_spain_annual_overnight.sh -> series anuales x 2 estudios
#
# Todo es reanudable: relanzar salta lo que ya tenga manifest.json y las
# cosechas anuales ya materializadas. Matar y relanzar no pierde trabajo.
#
# La fase anual corre aunque la de capas haya fallado en algun estudio: el
# runner descubre las series desde las capas que efectivamente corrieron, asi
# que produce lo que se pueda y el resto queda para la proxima pasada.
#
# No ejecutar desde una sesion de agente: contacta GEE, Open-Meteo y Overpass.
#
#   nohup caffeinate -i ./scripts/run_spain_night.sh >> logs/noche.out 2>&1 &
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

echo "############################################################"
echo "### NOCHE ESPAÑOLA -- INICIO: $(date)"
echo "############################################################"

layers_rc=0
annual_rc=0

echo ""
echo "### FASE 1/2: capas ###"
./scripts/run_cataluna_overnight.sh || layers_rc=$?

echo ""
echo "### FASE 2/2: series anuales ###"
if [ "$layers_rc" -ne 0 ]; then
    echo "(la fase de capas termino con codigo ${layers_rc}; se sigue igual"
    echo " con lo que haya quedado materializado)"
fi
./scripts/run_spain_annual_overnight.sh || annual_rc=$?

echo ""
echo "############################################################"
echo "### NOCHE ESPAÑOLA -- FIN: $(date)"
echo "###   fase capas:  codigo ${layers_rc}"
echo "###   fase anual:  codigo ${annual_rc}"
echo "############################################################"

if [ "$layers_rc" -ne 0 ] || [ "$annual_rc" -ne 0 ]; then
    echo "Hubo fallos. Relanzar este mismo script retoma donde quedo." >&2
    exit 1
fi
