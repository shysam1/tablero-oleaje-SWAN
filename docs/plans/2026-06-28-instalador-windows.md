# Instalador Pro Windows — Plan de implementación

> **Estado:** planificado, pendiente de implementación (versión **1.0**).
> **Para el agente:** leer este documento + `HANDOFF.md` antes de tocar código.
> El usuario compilará y probará el `.exe` en su PC Windows (Inno Setup).

**Goal:** Que una persona sin conocimientos técnicos instale Tablero de Oleaje con un asistente gráfico (`.exe`), sin instalar Python manualmente durante el setup del instalador (Python debe estar **ya instalado** en el sistema), y abra la app desde el escritorio o el menú Inicio.

**Base existente:** `iniciar_windows.bat`, `empaquetar_entrega.ps1`, `GUIAS DE USO/GUIA DE USO WINDOWS.txt`.

---

## Decisiones cerradas

| Tema | Decisión |
|------|----------|
| Plataforma | Windows primero (Mac después) |
| Python | Lo instala el usuario **antes** del instalador; el `.exe` muestra nota visible |
| Internet | Obligatorio la primera vez (creación de `.venv` + `pip install`) |
| Destino | `C:\Program Files\Tablero de Oleaje` (pide administrador) |
| SWAN / ffmpeg | Fuera del instalador; solo en guía |
| Distribución | GitHub Releases + envío directo |
| Versión inicial | **1.0.0** |
| Pruebas | Las hace el usuario en máquina Windows real |

---

## Arquitectura

```
Setup_TableroOleaje_1.0.0.exe  (Inno Setup)
    → Verifica Python 3.11+ en PATH
    → Si falta: aviso + enlace python.org, aborta limpio
    → Copia archivos a C:\Program Files\Tablero de Oleaje
    → Crea acceso directo escritorio + menú Inicio → launch_windows.bat
    → Registra desinstalador en "Agregar o quitar programas"

Primer arranque (launch_windows.bat → bootstrap_windows.ps1)
    → Crea .venv + pip install -r requirements.txt (requiere internet)
    → Ventana/mensaje "Preparando, solo la primera vez…"
    → python app_web.py --gui

Arranques siguientes
    → Solo activa .venv y abre la app (rápido, sin internet)
```

**No incluir en el instalador:** `.venv` pregenerado, `pytest`, tests, datos de prueba, Python embebido.

**No usar:** PyInstaller / ejecutable monolítico (numpy/xarray/netCDF4/pywebview son frágiles así).

---

## Estructura de archivos a crear/modificar

| Archivo | Acción | Rol |
|---------|--------|-----|
| `scripts/bootstrap_windows.ps1` | Crear | Lógica única: verificar Python 3.11+, crear `.venv`, `pip install`, log |
| `scripts/launch_windows.bat` | Crear | Arranque diario; llama bootstrap si falta entorno |
| `scripts/check_prereqs.ps1` | Crear (opcional) | Python, WebView2, espacio disco, internet |
| `iniciar_windows.bat` | Modificar | Delegar en bootstrap + launch (compatibilidad zip manual) |
| `installer/windows/TableroOleaje.iss` | Crear | Script Inno Setup |
| `empaquetar_instalador.bat` | Crear | Invoca compilador Inno Setup → `dist/Tablero_Oleaje_Setup_1.0.0.exe` |
| `GUIAS DE USO/GUIA INSTALACION WINDOWS.txt` | Crear | Guía 1 página (Python, WebView2, SWAN/ffmpeg opcionales) |
| `empaquetar_entrega.ps1` | Revisar | Reutilizar lista de archivos a copiar |
| `HANDOFF.md` | Actualizar | Tras implementar |

---

## Fase 1 — Refactor de lanzadores

### `scripts/bootstrap_windows.ps1`

Responsabilidades:

1. `cd` a la raíz del proyecto (resolver ruta desde `$PSScriptRoot/..`).
2. Buscar Python: `py -3`, luego `python`. Exigir `>= 3.11`.
3. Si no hay Python: `MessageBox` o `Write-Host` + URL `https://www.python.org/downloads/` + `exit 1`.
4. Si no existe `.venv\Scripts\python.exe`: `python -m venv .venv`.
5. `pip install --upgrade pip -q` y `pip install -r requirements.txt`.
6. Escribir log en `salidas/install.log` (crear carpeta si falta).
7. En error de pip: mensaje claro + referencia a `GUIAS DE USO/GUIA INSTALACION WINDOWS.txt`.

### `scripts/launch_windows.bat`

1. `cd /d "%~dp0\.."` (raíz del proyecto).
2. Si no existe `.venv\Scripts\python.exe`, llamar `powershell -File scripts\bootstrap_windows.ps1`.
3. Activar `.venv` y ejecutar `python app_web.py --gui`.
4. Si error: mencionar `salidas\app_web.log` y `salidas\install.log`.

### `iniciar_windows.bat`

Mantener como alias de compatibilidad que llama a `scripts\launch_windows.bat`.

---

## Fase 2 — Instalador Inno Setup

### Requisito en máquina de build

Instalar [Inno Setup 6](https://jrsoftware.org/isinfo.php) en Windows del desarrollador.

### `installer/windows/TableroOleaje.iss` — puntos clave

```iss
#define MyAppName "Tablero de Oleaje"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "..." 
#define MyAppExeName "launch_windows.bat"
DefaultDirName={autopf}\Tablero de Oleaje
PrivilegesRequired=admin
```

Pantallas y lógica:

1. **Página de información / prerequisitos** (antes de instalar):
   - Texto fijo: *"Esta aplicación requiere Python 3.11 o superior instalado y agregado al PATH. Descárgalo de https://www.python.org/downloads/ antes de continuar."*
   - *"La primera vez que abra la aplicación necesitará conexión a internet para descargar librerías."*

2. **Función Pascal `InitializeSetup`**: ejecutar `py -3 -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)"` o equivalente. Si falla, `MsgBox` y `Result := False`.

3. **`[Files]`**: copiar todos los archivos del proyecto (misma lista que `empaquetar_entrega.ps1`). **No** copiar: `.venv`, `dist`, `salidas`, `__pycache__`, `.git`, tests (`test_*.py`), `docs/`, `.cursor/`.

4. **`[Icons]`**:
   - Escritorio: `{app}\scripts\launch_windows.bat`
   - Menú Inicio: idem

5. **`[UninstallDelete]`**: no borrar `salidas` ni archivos de usuario fuera de `{app}`.

6. **`[Run]`** (opcional): ofrecer "Abrir Tablero de Oleaje" al finalizar.

### `empaquetar_instalador.bat`

```bat
@echo off
rem Requiere Inno Setup 6 en PATH o ruta estándar
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "%~dp0installer\windows\TableroOleaje.iss"
```

Salida: `dist\Tablero_Oleaje_Setup_1.0.0.exe`

---

## Fase 3 — Guía de instalación

Crear `GUIAS DE USO/GUIA INSTALACION WINDOWS.txt` con:

1. Requisitos: Windows 10/11 64-bit, Python 3.11+, WebView2, ~500 MB, internet 1ª vez.
2. Paso a paso: instalar Python (marcar "Add to PATH") → ejecutar Setup → abrir acceso directo.
3. SWAN y ffmpeg: opcionales, enlace a sección de la guía de uso existente.
4. Problemas frecuentes: Python no en PATH, WebView2, firewall, primer arranque lento.
5. Desinstalar: Panel de control → no pierde `salidas` si estaban en otra ruta (documentar dónde guarda la app).

Actualizar `LEEME PRIMERO.txt` para mencionar el instalador `.exe` como opción preferida.

---

## Fase 4 — Distribución

1. `empaquetar_instalador.bat` → genera `.exe` en `dist/`.
2. Mantener `empaquetar_entrega.bat` → zip clásico como respaldo.
3. GitHub Release `v1.0.0`:
   - `Tablero_Oleaje_Setup_1.0.0.exe`
   - `Tablero_Oleaje_entrega_YYYY-MM-DD.zip` (opcional)

---

## Fase 5 — Checklist QA (usuario, máquina Windows)

- [ ] Windows 10/11 **sin** Python → instalador muestra aviso y no instala (o aborta en setup).
- [ ] Python 3.11+ en PATH → instalador completa, acceso directo creado.
- [ ] Primer arranque con internet → crea `.venv`, instala deps, abre app.
- [ ] Segundo arranque sin internet → abre app sin reinstalar deps.
- [ ] Sin WebView2 → mensaje útil (app o guía).
- [ ] Desinstalar → archivos de `{app}` eliminados; `salidas` del usuario intactas si están fuera.
- [ ] SmartScreen / antivirus: documentar si aparece advertencia (sin firma de código).

---

## Limitaciones del Cloud Agent

El agente en VM Linux **puede escribir** todos los scripts (`.iss`, `.ps1`, `.bat`, guías) pero **no puede compilar ni probar** el `.exe`. Compilación y QA en PC Windows del usuario.

---

## Relación con environment del Cloud Agent

El script de environment de Cursor (`venv` + `pip install -r requirements.txt` + `pytest`) es el mismo patrón que `bootstrap_windows.ps1`, excepto:

- **Sí** en bootstrap: `requirements.txt`
- **No** en instalador usuario: `pytest`, `TABLERO_DATOS_*`, `--system-site-packages`
