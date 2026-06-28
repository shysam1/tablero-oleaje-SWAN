# Instalador Pro macOS — Plan de implementación

> **Estado:** planificado, pendiente de implementación (versión **1.0**).
> **Orden:** implementar **después** del instalador Windows (`docs/plans/2026-06-28-instalador-windows.md`).
> **Para el agente:** leer este documento + `HANDOFF.md` antes de tocar código.
> El usuario generará y probará el `.dmg` en su Mac.

**Goal:** Que una persona sin conocimientos técnicos instale Tablero de Oleaje arrastrando la app a Aplicaciones, sin Terminal ni `chmod +x`, y abra la app con doble clic.

**Base existente:** `iniciar_mac.command`, `empaquetar_entrega.ps1`, `GUIAS DE USO/GUIA DE USO MAC.txt`.

---

## Decisiones cerradas

| Tema | Decisión |
|------|----------|
| Plataforma | Después de Windows |
| Python | Lo instala el usuario **antes**; nota visible en el `.dmg` |
| Internet | Obligatorio la primera vez (`.venv` + `pip install`) |
| Destino | `/Applications/Tablero de Oleaje.app` (arrastrar desde `.dmg`) |
| SWAN / ffmpeg | Fuera del `.dmg`; solo en guía |
| Distribución | GitHub Releases + envío directo |
| Versión inicial | **1.0.0** |
| Firma / notarización | **Opción A — sin firmar** (sin cuenta Apple de pago) |
| Arquitectura | **Universal** (Intel + Apple Silicon) |
| Pruebas | Las hace el usuario en Mac real |

---

## Arquitectura

```
Tablero de Oleaje 1.0.dmg
    → Fondo visual: arrastrar app → Aplicaciones
    → Incluye GUIA INSTALACION MAC.txt + nota Python obligatorio

Tablero de Oleaje.app  (bundle)
    Contents/MacOS/launcher     → ejecutable que llama launch_mac.sh
    Contents/Resources/         → código Python + ui/ + requirements.txt
    Contents/Info.plist         → versión 1.0, CFBundleIdentifier, icono

Primer arranque (bootstrap_mac.sh)
    → Verifica python3 >= 3.11
    → Si falta: osascript diálogo + URL python.org, exit 1
    → Crea .venv en ~/Library/Application Support/Tablero de Oleaje/.venv
       (o dentro de Resources — ver nota abajo)
    → pip install -r requirements.txt
    → python app_web.py --gui

Arranques siguientes
    → Solo activa .venv y abre la app
```

### Nota: ubicación de `.venv`

En Mac, escribir dentro de `Tablero de Oleaje.app` en `/Applications` puede fallar por permisos. **Recomendación:**

- Código de la app: dentro del `.app` (solo lectura tras copiar).
- `.venv` y `salidas/`: en `~/Library/Application Support/Tablero de Oleaje/`.

Documentar en `bootstrap_mac.sh` y en la guía.

**Ventaja Mac vs Windows:** WebKit viene con macOS; no hace falta instalar WebView2.

---

## Gatekeeper (sin firma — Opción A)

Sin Apple Developer ID, al abrir la primera vez macOS puede mostrar:

> "Tablero de Oleaje" no se puede abrir porque proviene de un desarrollador no identificado.

**Instrucción en la guía (obligatoria):**

1. Clic derecho (o Control + clic) en la app → **Abrir**.
2. Confirmar **Abrir** en el diálogo.
3. Solo hace falta la primera vez.

No intentar notarizar sin certificado de pago.

---

## Estructura de archivos a crear/modificar

| Archivo | Acción | Rol |
|---------|--------|-----|
| `scripts/bootstrap_mac.sh` | Crear | Verificar Python, crear `.venv`, pip install, log |
| `scripts/launch_mac.sh` | Crear | Arranque diario |
| `iniciar_mac.command` | Modificar | Delegar en launch (compatibilidad zip manual) |
| `installer/mac/Tablero de Oleaje.app/` | Crear | Bundle de la aplicación |
| `installer/mac/Contents/Info.plist` | Crear | Metadatos, versión 1.0 |
| `installer/mac/Contents/MacOS/launcher` | Crear | Shell script ejecutable |
| `assets/tablero.icns` | Crear | Icono Mac (convertir desde PNG/ICO existente) |
| `installer/mac/empaquetar_instalador_mac.sh` | Crear | Arma `.app` + genera `.dmg` |
| `GUIAS DE USO/GUIA INSTALACION MAC.txt` | Crear | Guía 1 página |
| `HANDOFF.md` | Actualizar | Tras implementar |

---

## Fase M1 — Refactor de lanzadores

### `scripts/bootstrap_mac.sh`

1. Resolver rutas: `APP_SUPPORT="$HOME/Library/Application Support/Tablero de Oleaje"`.
2. Buscar `python3` o `python`; exigir `>= 3.11`.
3. Si falta Python:
   ```bash
   osascript -e 'display dialog "Instala Python 3.11+ desde python.org" buttons {"OK"} default button 1'
   open "https://www.python.org/downloads/macos/"
   exit 1
   ```
4. Crear `$APP_SUPPORT/.venv` si no existe: `python3 -m venv "$APP_SUPPORT/.venv"`.
5. `pip install --upgrade pip -q` y `pip install -r requirements.txt`.
6. Log: `$APP_SUPPORT/install.log`.
7. Exportar variables para el lanzador: `VENV_PYTHON`, `APP_ROOT`.

### `scripts/launch_mac.sh`

1. Source o llamar `bootstrap_mac.sh`.
2. `cd` al directorio de recursos de la app.
3. `"$VENV_PYTHON" app_web.py --gui`.
4. Si error: mencionar `install.log` y `salidas/app_web.log`.

### `iniciar_mac.command`

Mantener como alias que llama a `scripts/launch_mac.sh` (modo zip manual / desarrollo).

---

## Fase M2 — Bundle `.app`

### Estructura

```
Tablero de Oleaje.app/
  Contents/
    Info.plist
    MacOS/
      launcher          # chmod +x, shebang #!/bin/bash
    Resources/
      app_web.py
      api_web.py
      ... (misma lista que empaquetar_entrega.ps1)
      ui/
      assets/
      requirements.txt
      scripts/
        bootstrap_mac.sh
        launch_mac.sh
    Resources/tablero.icns
```

### `Contents/MacOS/launcher`

```bash
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
export TABLERO_APP_ROOT="$DIR"
exec "$DIR/scripts/launch_mac.sh"
```

### `Info.plist` — campos mínimos

- `CFBundleName`: Tablero de Oleaje
- `CFBundleIdentifier`: `com.tablerooleaje.app` (ajustar si hay dominio)
- `CFBundleVersion` / `CFBundleShortVersionString`: `1.0.0`
- `CFBundleExecutable`: `launcher`
- `CFBundleIconFile`: `tablero.icns`
- `LSMinimumSystemVersion`: `11.0` (macOS Big Sur+, coherente con Python 3.11)

---

## Fase M3 — Generar `.dmg`

### `installer/mac/empaquetar_instalador_mac.sh`

Ejecutar **solo en Mac**:

1. Copiar/staging del `.app` con todos los Resources.
2. `chmod +x` en `Contents/MacOS/launcher` y scripts.
3. Crear imagen de fondo opcional (`installer/mac/dmg-background.png`).
4. Usar `create-dmg` (brew) o `hdiutil` nativo:

```bash
hdiutil create -volname "Tablero de Oleaje 1.0" \
  -srcfolder "dist/staging" \
  -ov -format UDZO \
  "dist/Tablero de Oleaje 1.0.dmg"
```

5. Incluir en el `.dmg` (junto a la `.app`):
   - `GUIA INSTALACION MAC.txt`
   - `LEEME - Python obligatorio.txt` (nota corta)

Salida: `dist/Tablero de Oleaje 1.0.dmg`

---

## Fase M4 — Guía de instalación

Crear `GUIAS DE USO/GUIA INSTALACION MAC.txt`:

1. Requisitos: macOS 11+, Python 3.11+ (python.org o Homebrew), internet 1ª vez, ~500 MB.
2. Pasos: instalar Python → abrir `.dmg` → arrastrar a Aplicaciones → **clic derecho → Abrir** (Gatekeeper).
3. Primera apertura: puede tardar varios minutos (descarga librerías).
4. SWAN / ffmpeg: opcionales (referencia a guía de uso Mac).
5. Apple Silicon vs Intel: pip instala wheels correctos; si falla `netCDF4`, ver sección problemas de la guía Mac existente.
6. Dónde quedan datos: `~/Library/Application Support/Tablero de Oleaje/` y `salidas/`.

Actualizar `LEEME PRIMERO.txt` para mencionar el `.dmg` como opción preferida en Mac.

---

## Fase M5 — Distribución

GitHub Release `v1.0.0`:

- `Tablero_Oleaje_Setup_1.0.0.exe` (Windows)
- `Tablero de Oleaje 1.0.dmg` (macOS)
- Zip clásico opcional como respaldo

---

## Fase M6 — Checklist QA (usuario, Mac real)

- [ ] Mac **sin** Python → diálogo claro, no crashea.
- [ ] Python 3.11+ instalado → app abre tras bootstrap.
- [ ] Apple Silicon (M1/M2/M3) → deps instalan y app abre.
- [ ] Intel (si disponible) → idem.
- [ ] Primer arranque con internet → `.venv` en Application Support, app abre.
- [ ] Segundo arranque sin internet → abre sin reinstalar.
- [ ] Gatekeeper: flujo clic derecho → Abrir documentado y probado.
- [ ] App en `/Applications` → permisos de escritura solo en Application Support.
- [ ] Desinstalar: arrastrar `.app` a Papelera; opcional limpiar `~/Library/Application Support/Tablero de Oleaje/`.

---

## Limitaciones del Cloud Agent

El agente en VM Linux **puede escribir** scripts, `Info.plist`, plantilla `.app` y guías, pero **no puede** generar `.dmg`, `.icns` ni probar Gatekeeper. Build y QA en Mac del usuario.

### Crear `tablero.icns` (en Mac del usuario)

```bash
# Desde un PNG 1024x1024
mkdir tablero.iconset
sips -z 512 512 icon.png --out tablero.iconset/icon_512x512@2x.png
# ... tamaños estándar ...
iconutil -c icns tablero.iconset -o assets/tablero.icns
```

O usar herramienta online / `png2icns`.

---

## Relación con instalador Windows

Misma filosofía:

| Componente | Windows | macOS |
|------------|---------|-------|
| Bootstrap | `bootstrap_windows.ps1` | `bootstrap_mac.sh` |
| Lanzador | `launch_windows.bat` | `launch_mac.sh` + `.app` |
| Empaquetado | Inno Setup `.exe` | `.dmg` + `.app` |
| Python | Usuario lo instala | Usuario lo instala |
| `.venv` | Junto al proyecto en Program Files | Application Support (writable) |
| Firma | Sin firma (SmartScreen posible) | Sin firma (Gatekeeper + clic derecho Abrir) |

Implementar primero Windows Fases 1–2; replicar patrón bootstrap/launch en Mac Fase M1 antes del bundle.
