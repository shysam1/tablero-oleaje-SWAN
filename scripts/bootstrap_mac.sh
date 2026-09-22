#!/bin/bash
# Se carga desde launch_mac.sh; valida el entorno sin descargar en cada apertura.
if [ -n "${TABLERO_APP_ROOT:-}" ]; then
  APP_ROOT="$TABLERO_APP_ROOT"
else
  _BS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  APP_ROOT="$(cd "$_BS_DIR/.." && pwd)"
fi
APP_SUPPORT="$HOME/Library/Application Support/Tablero de Oleaje"
mkdir -p "$APP_SUPPORT" || return 1
LOG_FILE="$APP_SUPPORT/install.log"
BOOTSTRAP_OK=""
_log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"; }
if [ -w "$APP_ROOT" ] && [[ "$APP_ROOT" != *.app/Contents/Resources ]]; then
  VENV_DIR="$APP_ROOT/.venv"
else
  VENV_DIR="$APP_SUPPORT/.venv"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
ESTADO="$APP_ROOT/scripts/estado_entorno.py"
REQUISITOS="$APP_ROOT/requirements.txt"
MARCADOR="$VENV_DIR/.tablero-listo.json"
if [ -x "$VENV_PYTHON" ] && "$VENV_PYTHON" "$ESTADO" comprobar "$REQUISITOS" "$MARCADOR"; then
  BOOTSTRAP_OK="1"
  export APP_ROOT VENV_PYTHON BOOTSTRAP_OK LOG_FILE APP_SUPPORT
  return 0
fi
_log "Preparando el entorno de Tablero de Oleaje..."
VALIDAR_PYTHON="import sys,struct; sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)"
if [ ! -x "$VENV_PYTHON" ]; then
  PY=""
  # Finder no hereda el PATH del shell; se incluyen python.org y Homebrew.
  for candidato in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python; do
    if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c "$VALIDAR_PYTHON" >/dev/null 2>&1; then
      PY="$candidato"
      break
    fi
  done
  if [ -z "$PY" ]; then
    _log "Instala Python 3.11 o superior de 64 bits desde python.org."
    osascript -e 'display dialog "Tablero de Oleaje necesita Python 3.11 o superior de 64 bits. Instalalo desde python.org y vuelve a abrir la aplicacion." buttons {"OK"} default button 1 with icon caution' >/dev/null 2>&1 || true
    return 1
  fi
  if ! "$PY" -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1; then
    _log "ERROR: no se pudo crear el entorno virtual."
    return 1
  fi
fi
if ! "$VENV_PYTHON" -c "$VALIDAR_PYTHON" >> "$LOG_FILE" 2>&1; then
  _log "ERROR: entorno incompatible. Renombra $VENV_DIR y vuelve a abrir."
  return 1
fi
_log "Instalando/verificando requirements.txt. La primera vez requiere internet."
if ! "$VENV_PYTHON" -m pip install --disable-pip-version-check -r "$REQUISITOS" >> "$LOG_FILE" 2>&1; then
  _log "ERROR: fallo pip; el proximo inicio reintentara la instalacion."
  return 1
fi
if ! "$VENV_PYTHON" "$ESTADO" registrar "$REQUISITOS" "$MARCADOR" >> "$LOG_FILE" 2>&1; then
  _log "ERROR: no se pudieron cargar las dependencias. Consulta install.log."
  return 1
fi
BOOTSTRAP_OK="1"
_log "Entorno listo."
export APP_ROOT VENV_PYTHON BOOTSTRAP_OK LOG_FILE APP_SUPPORT
