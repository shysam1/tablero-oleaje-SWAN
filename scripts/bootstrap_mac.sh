#!/bin/bash
# =============================================================================
# Tablero de Oleaje - bootstrap (macOS)
# =============================================================================
# Logica unica de preparacion del entorno en Mac. La usan tanto el bundle
# .app (instalado en /Applications, solo lectura) como el lanzador clasico
# del .zip / desarrollo.
#
# Disenado para SOURCEARSE desde launch_mac.sh:
#     source "scripts/bootstrap_mac.sh"
# Al terminar deja definidas las variables:
#     APP_ROOT      -> raiz con el codigo (app_web.py, requirements.txt, ui/)
#     VENV_PYTHON   -> ruta al python del entorno virtual
#     BOOTSTRAP_OK  -> "1" si el entorno quedo listo, vacio si fallo
#
# Si .venv puede vivir junto al codigo (carpeta escribible, modo .zip/dev) se
# crea ahi. Si el codigo es de solo lectura (.app en /Applications) el entorno
# y los logs van a:
#     ~/Library/Application Support/Tablero de Oleaje/
# =============================================================================

# --- Resolver raiz del codigo ---
if [ -n "${TABLERO_APP_ROOT:-}" ]; then
  APP_ROOT="$TABLERO_APP_ROOT"
else
  _BS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  APP_ROOT="$(cd "$_BS_DIR/.." && pwd)"
fi

APP_SUPPORT="$HOME/Library/Application Support/Tablero de Oleaje"
mkdir -p "$APP_SUPPORT"
LOG_FILE="$APP_SUPPORT/install.log"

BOOTSTRAP_OK=""

_log() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] $1"
  echo "[$ts] $1" >> "$LOG_FILE"
}

_dialogo_python() {
  # Aviso grafico (si hay sesion) + abrir python.org
  osascript -e 'display dialog "Tablero de Oleaje necesita Python 3.11 o superior.\n\nInstalalo desde python.org y vuelve a abrir la aplicacion." buttons {"OK"} default button 1 with icon caution' >/dev/null 2>&1 || true
  open "https://www.python.org/downloads/macos/" >/dev/null 2>&1 || true
}

_log "===== Preparando entorno de Tablero de Oleaje (macOS) ====="
_log "Codigo en: $APP_ROOT"

# --- Localizar Python 3.11+ ---
PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
fi

if [ -z "$PY" ]; then
  _log "No se encontro Python 3."
  _dialogo_python
else
  PY_MAJOR="$("$PY" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)"
  PY_MINOR="$("$PY" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)"
  _log "Python detectado: $("$PY" --version 2>&1)"
  if [ -z "$PY_MAJOR" ] || [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    _log "Version insuficiente; se requiere Python 3.11 o superior."
    _dialogo_python
    PY=""
  fi
fi

if [ -n "$PY" ]; then
  # --- Decidir ubicacion del entorno virtual ---
  if [ -w "$APP_ROOT" ]; then
    VENV_DIR="$APP_ROOT/.venv"
  else
    VENV_DIR="$APP_SUPPORT/.venv"
    _log "Codigo de solo lectura; el entorno ira en Application Support."
  fi
  VENV_PYTHON="$VENV_DIR/bin/python"

  # --- Crear entorno si falta ---
  if [ ! -x "$VENV_PYTHON" ]; then
    _log "Creando entorno virtual en: $VENV_DIR"
    if ! "$PY" -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1; then
      _log "ERROR: no se pudo crear el entorno virtual."
      VENV_PYTHON=""
    fi
  else
    _log "Entorno virtual ya existe."
  fi

  # --- Instalar dependencias ---
  if [ -n "$VENV_PYTHON" ] && [ -x "$VENV_PYTHON" ]; then
    _log "Actualizando pip..."
    "$VENV_PYTHON" -m pip install --upgrade pip -q >> "$LOG_FILE" 2>&1 || true
    _log "Instalando dependencias (requirements.txt). Puede tardar la primera vez..."
    if "$VENV_PYTHON" -m pip install -r "$APP_ROOT/requirements.txt" >> "$LOG_FILE" 2>&1; then
      _log "Entorno listo."
      BOOTSTRAP_OK="1"
    else
      _log "ERROR: fallo la instalacion de dependencias."
      _log "Consulta 'GUIAS DE USO/GUIA INSTALACION MAC.txt' (seccion Problemas)."
    fi
  fi
fi

export APP_ROOT VENV_PYTHON BOOTSTRAP_OK LOG_FILE APP_SUPPORT
