#!/bin/bash
# =============================================================================
# Tablero de Oleaje - lanzador (macOS)
# =============================================================================
# Compatibilidad: este archivo se mantiene para la entrega en .zip (doble clic
# desde Finder). Toda la logica vive ahora en scripts/launch_mac.sh (+ bootstrap),
# que es lo que usa tambien el bundle .app. Aqui solo delegamos.
#
# Requisito: Python 3.11 o superior (python.org o Homebrew).
# Primera vez en Terminal:  chmod +x iniciar_mac.command
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

LAUNCH="$SCRIPT_DIR/scripts/launch_mac.sh"
if [ ! -f "$LAUNCH" ]; then
  echo ""
  echo "ERROR: no se encontro scripts/launch_mac.sh"
  echo "La carpeta del proyecto parece incompleta."
  read -r -p "Presiona Enter para cerrar..." _
  exit 1
fi

bash "$LAUNCH"
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
  read -r -p "Presiona Enter para cerrar..." _
fi
exit "$EXIT_CODE"
