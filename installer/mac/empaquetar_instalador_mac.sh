#!/bin/bash
# =============================================================================
# Tablero de Oleaje - genera el instalador .dmg (macOS)
# =============================================================================
# EJECUTAR SOLO EN MAC. Arma "Tablero de Oleaje.app" copiando el codigo en
# Contents/Resources, y crea dist/"Tablero de Oleaje 1.0.dmg".
#
#   chmod +x installer/mac/empaquetar_instalador_mac.sh
#   ./installer/mac/empaquetar_instalador_mac.sh
#
# No firma ni notariza (Opcion A). El usuario abrira con clic derecho -> Abrir.
# =============================================================================

set -euo pipefail

VERSION="1.0.0"
VOLNAME="Tablero de Oleaje 1.0"
APPNAME="Tablero de Oleaje.app"

# --- Rutas ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"          # installer/mac
PROYECTO="$(cd "$SCRIPT_DIR/../.." && pwd)"                              # raiz del repo
PLANTILLA="$SCRIPT_DIR/$APPNAME"                                         # bundle plantilla
DIST="$PROYECTO/dist"
STAGING="$DIST/staging_mac"
APP_OUT="$STAGING/$APPNAME"
RES="$APP_OUT/Contents/Resources"
DMG_OUT="$DIST/$VOLNAME.dmg"

echo "Tablero de Oleaje - empaquetado macOS"
echo "====================================="
echo "Proyecto: $PROYECTO"
echo "Salida:   $DMG_OUT"
echo ""

# --- Limpiar staging ---
rm -rf "$STAGING"
mkdir -p "$RES"
[ -f "$DMG_OUT" ] && rm -f "$DMG_OUT"

# --- Copiar la plantilla del bundle (Info.plist, MacOS/launcher) ---
cp -R "$PLANTILLA/Contents/Info.plist" "$APP_OUT/Contents/Info.plist"
mkdir -p "$APP_OUT/Contents/MacOS"
cp "$PLANTILLA/Contents/MacOS/launcher" "$APP_OUT/Contents/MacOS/launcher"
chmod +x "$APP_OUT/Contents/MacOS/launcher"

# --- Icono (si existe) ---
if [ -f "$PROYECTO/assets/tablero.icns" ]; then
  cp "$PROYECTO/assets/tablero.icns" "$RES/tablero.icns"
else
  echo "AVISO: no existe assets/tablero.icns; el bundle usara el icono por defecto."
fi

# --- Carpetas de codigo a incluir en Resources ---
CARPETAS=( "ui" "assets" "scripts" "GUIAS DE USO" )
for c in "${CARPETAS[@]}"; do
  if [ -d "$PROYECTO/$c" ]; then
    echo "  + carpeta $c"
    rsync -a --exclude "__pycache__" --exclude ".pytest_cache" "$PROYECTO/$c/" "$RES/$c/"
  fi
done

# --- Archivos sueltos a incluir en Resources ---
ARCHIVOS=(
  "requirements.txt"
  "app_web.py" "api_web.py" "motor_web.py" "sistema.py" "config.py"
  "rutas.py" "seguridad.py" "tablero_oleaje.py" "tablero_swan.py"
  "video_swan.py" "previews.py" "productos.py" "productos_swan.py"
  "productos_particion.py" "particion_espectral.py" "validacion.py"
  "io_oleaje.py" "io_era5.py" "io_swan.py" "io_swan_nonst.py"
  "io_batimetria.py" "geo_malla.py" "borde_oleaje.py" "swan_builder.py"
  "swan_runner.py" "prioridad.py" "app_tablero.py" "asistente.py"
  "estilo.py" "gui_swan.py" "pasos_analizar.py" "pasos_modelar.py" "pasos_ver.py"
)
for f in "${ARCHIVOS[@]}"; do
  if [ -f "$PROYECTO/$f" ]; then
    cp "$PROYECTO/$f" "$RES/$f"
  else
    echo "AVISO: no se encontro '$f'; se omite."
  fi
done

# --- Permisos de ejecucion en los scripts ---
chmod +x "$RES/scripts/launch_mac.sh" 2>/dev/null || true
chmod +x "$RES/scripts/bootstrap_mac.sh" 2>/dev/null || true

# --- Documentacion suelta dentro del .dmg ---
if [ -f "$PROYECTO/GUIAS DE USO/GUIA INSTALACION MAC.txt" ]; then
  cp "$PROYECTO/GUIAS DE USO/GUIA INSTALACION MAC.txt" "$STAGING/GUIA INSTALACION MAC.txt"
fi
cat > "$STAGING/LEEME - Python obligatorio.txt" <<'EOF'
TABLERO DE OLEAJE - ANTES DE ABRIR

1. Necesitas Python 3.11 o superior instalado (python.org o Homebrew).
2. Arrastra "Tablero de Oleaje.app" a la carpeta Aplicaciones.
3. La PRIMERA vez: clic derecho sobre la app -> Abrir -> Abrir
   (es necesario porque la app no esta firmada).
4. El primer arranque descarga librerias: necesita internet y puede tardar.

Mas detalles en "GUIA INSTALACION MAC.txt".
EOF

# --- Enlace a /Applications para arrastrar ---
ln -s /Applications "$STAGING/Applications" 2>/dev/null || true

# --- Crear el .dmg ---
echo ""
echo "Creando imagen .dmg ..."
hdiutil create -volname "$VOLNAME" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  "$DMG_OUT"

echo ""
echo "Listo:"
echo "  $DMG_OUT"
echo ""
echo "Recuerda: para el icono, crea assets/tablero.icns antes de empaquetar."
