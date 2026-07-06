# AGENTS.md

Antes de tocar código, lee `HANDOFF.md` (bitácora compartida, fuente de verdad) y
`CLAUDE.md`. Lo de abajo es solo para agentes en la nube (Cursor Cloud).

## Cursor Cloud specific instructions

Herramienta de análisis de oleaje y SWAN (Python + xarray). La **única interfaz**
es la app de escritorio `app_web.py` (pywebview, HTML/CSS/JS en `ui/`); el motor sin
GUI vive en `motor_web.py` / `api_web.py`, y los pipelines en `io_*.py`,
`productos*.py`, `tablero*.py`, `video_swan.py`. El código tkinter (`app_tablero.py`,
`asistente.py`, `pasos_*.py`, `gui_swan.py`) está obsoleto y solo se conserva para tests.

### Entorno

- Las dependencias se instalan en un venv en `.venv/` (lo crea el script de arranque).
  Actívalo con `source .venv/bin/activate`.
- El venv se crea con `--system-site-packages` **a propósito**: pywebview necesita el
  backend GTK/WebKit2 del sistema (`python3-gi`, `gir1.2-webkit2-4.1`), que no es un
  paquete pip y solo es visible desde el venv si éste hereda los site-packages del sistema.
- No hay linter configurado; la red de seguridad es pytest. Para un chequeo de sintaxis
  rápido: `python -m compileall *.py`.

### Correr la app (GUI)

- Hay un display headless en `:1`. Lanza la GUI con `DISPLAY=:1 python app_web.py`
  (NO uses la flag `--gui`: redirige stdout/stderr a `salidas/app_web.log` y solo sirve
  para ocultar la consola en Windows; en la nube dificulta depurar).
- El flujo "Analizar oleaje en un punto" carga un `.mat/.csv/.nc` y genera el tablero PNG;
  las salidas van a `salidas/<fuente>/`. La descarga ERA5 requiere credenciales CDS
  (`~/.cdsapirc` o la barra lateral → Credenciales ERA5), por defecto no configuradas.

### Tests — caveats importantes (no obvios)

Comando recomendado:

```
pytest test_regresion.py test_nesting.py test_motor_web.py test_asistente.py -q \
  --basetemp="$HOME/pytest-tmp" \
  --deselect test_regresion.py::test_descargar_serie_paralelo_max_dos \
  --deselect test_regresion.py::test_descargar_serie_largo_concatena_tramos
```

- **`--basetemp` bajo `$HOME` es obligatorio.** `seguridad.confina_usuario` solo permite
  rutas bajo el home del usuario o `salidas/`. El `tmp_path` por defecto de pytest cae en
  `/tmp` (fuera del home), y unas ~4 pruebas que validan rutas de archivo fallan en falso.
- **Dos tests de descarga ERA5 en paralelo provocan segfault en esta VM**
  (`test_descargar_serie_paralelo_max_dos`, `test_descargar_serie_largo_concatena_tramos`):
  escriben NetCDF concurrentemente desde un `ThreadPoolExecutor`, y el wheel pip de
  `netCDF4` trae un HDF5 **no thread-safe**, así que la librería C revienta el proceso
  entero. Es una limitación del entorno, no un bug del código (pasan en los builds
  Windows/macOS de los mantenedores). Deselecciónalos.
- **8 tests se saltan** salvo que exportes `TABLERO_DATOS_SWAN` / `TABLERO_DATOS_OLEAJE`
  apuntando a datasets SWAN/oleaje reales (no incluidos en el repo).

Con esos ajustes la suite queda en verde (≈137 passed, 8 skipped, 2 deselected).

### Tests con datos reales (equipo local)

En la máquina del usuario se pueden exportar variables de entorno para correr los
8 tests que usan datasets reales (por defecto skipped):

```
set TABLERO_DATOS_SWAN=C:\Users\123ja\OneDrive\Escritorio\Proyectos\Python\SWAN_Coronel
set TABLERO_DATOS_OLEAJE=<ruta al .mat de Talcahuano>
pytest test_regresion.py test_asistente.py test_nesting.py test_motor_web.py -q
```
