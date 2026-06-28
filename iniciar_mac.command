#!/bin/bash
# =============================================================================
# Tablero de Oleaje — lanzador automático para macOS
# =============================================================================
# Uso: doble clic en este archivo desde Finder (o en Terminal: ./iniciar_mac.command)
#
# El script:
#   1. Se coloca en la carpeta del proyecto (aunque Finder lo abra desde otro sitio).
#   2. Crea un entorno virtual Python (.venv) si aún no existe.
#   3. Activa ese entorno.
#   4. Instala/actualiza dependencias desde requirements.txt (salida mínima).
#   5. Arranca la aplicación principal (app_web.py --gui).
#
# Requisito: Python 3.11 o superior instalado (python.org o Homebrew).
# =============================================================================

set -euo pipefail

# --- 1. Ir siempre a la carpeta donde está este script ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$SCRIPT_DIR"

# --- 2. Localizar Python 3 ---
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo ""
  echo "ERROR: No se encontró Python 3."
  echo "Instala Python 3.11+ desde https://www.python.org/downloads/macos/"
  echo "o con Homebrew: brew install python@3.12"
  echo ""
  read -r -p "Presiona Enter para cerrar..." _
  exit 1
fi

# Comprobar versión mínima (3.11)
PY_MAJOR=$("$PY" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PY" -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
  echo ""
  echo "ERROR: Se requiere Python 3.11 o superior (detectado: $("$PY" --version))."
  echo ""
  read -r -p "Presiona Enter para cerrar..." _
  exit 1
fi

# --- 3. Crear entorno virtual si no existe ---
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creando entorno virtual en .venv ..."
  if ! "$PY" -m venv "$VENV_DIR"; then
    echo ""
    echo "ERROR: No se pudo crear el entorno virtual."
    read -r -p "Presiona Enter para cerrar..." _
    exit 1
  fi
fi

# --- 4. Activar el entorno virtual ---
# shellcheck disable=SC1091
if ! source "$VENV_DIR/bin/activate"; then
  echo ""
  echo "ERROR: No se pudo activar el entorno virtual."
  read -r -p "Presiona Enter para cerrar..." _
  exit 1
fi

# --- 5. Instalar dependencias de forma silenciosa (solo errores visibles) ---
echo "Verificando dependencias (puede tardar la primera vez)..."
python -m pip install --upgrade pip -q
if ! python -m pip install -r requirements.txt -q; then
  echo ""
  echo "ERROR al instalar dependencias."
  echo "Revisa GUIAS DE USO/GUIA DE USO MAC.txt"
  echo "o ejecuta manualmente: pip install -r requirements.txt"
  echo ""
  read -r -p "Presiona Enter para cerrar..." _
  exit 1
fi

# --- 6. Ejecutar la aplicación ---
echo "Iniciando Tablero de Oleaje..."
python app_web.py --gui
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
  echo ""
  echo "La aplicación terminó con error (código $EXIT_CODE)."
  echo "Revisa salidas/app_web.log dentro de la carpeta del proyecto."
  echo ""
  read -r -p "Presiona Enter para cerrar..." _
fi
exit "$EXIT_CODE"
