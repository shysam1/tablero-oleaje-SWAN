#!/bin/bash
# =============================================================================
# Tablero de Oleaje - lanzador diario (macOS)
# =============================================================================
# Lo invoca el bundle .app (Contents/MacOS/launcher) y tambien el alias
# iniciar_mac.command del .zip. Prepara el entorno (primera vez) y arranca
# la aplicacion.
# =============================================================================

# --- Localizar este script y el bootstrap ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Cargar la logica de preparacion (define APP_ROOT, VENV_PYTHON, BOOTSTRAP_OK)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/bootstrap_mac.sh"

if [ -z "${BOOTSTRAP_OK:-}" ] || [ -z "${VENV_PYTHON:-}" ] || [ ! -x "${VENV_PYTHON}" ]; then
  echo ""
  echo "ERROR: no se pudo preparar el entorno de Tablero de Oleaje."
  echo "Revisa el registro: ${LOG_FILE:-$HOME/Library/Application Support/Tablero de Oleaje/install.log}"
  echo "y la guia: GUIAS DE USO/GUIA INSTALACION MAC.txt"
  osascript -e 'display dialog "No se pudo preparar Tablero de Oleaje.\n\nRevisa install.log en:\n~/Library/Application Support/Tablero de Oleaje/" buttons {"OK"} default button 1 with icon stop' >/dev/null 2>&1 || true
  exit 1
fi

# --- Ejecutar la aplicacion desde la raiz del codigo ---
cd "$APP_ROOT"
echo "Iniciando Tablero de Oleaje..."
"$VENV_PYTHON" app_web.py --gui
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  echo ""
  echo "La aplicacion termino con error (codigo $EXIT_CODE)."
  echo "Revisa salidas/app_web.log y el install.log en Application Support."
fi
exit "$EXIT_CODE"
