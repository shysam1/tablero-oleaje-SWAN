# Handoff — Herramienta "Tablero Oleaje" (contexto para nueva conversación)

> **Bitácora compartida entre agentes.** Esta app se desarrolla con dos asistentes
> en paralelo (Cursor y Claude Code). Para que se entiendan, **todo cambio se
> registra abajo con su PORQUÉ**, lo más reciente primero. Antes de tocar código,
> lee esta sección; después de cambiar algo, añade una entrada.
>
> **Regla de proyecto:** actualizar HANDOFF es **obligatorio** al cerrar tareas con
> cambios relevantes; leer HANDOFF al empezar. No dar por terminado el trabajo sin
> cumplirlo. Implementado en:
> - Cursor: `.cursor/rules/handoff-bitacora.mdc`
> - Claude Code: `CLAUDE.md`

## Registro de cambios (más reciente primero)

### 2026-06-28 · Entorno de desarrollo para Cursor Cloud (Cursor)
*Qué/por qué:* preparación del entorno en la VM de la nube: venv en `.venv/` con
`--system-site-packages` (pywebview usa el backend GTK/WebKit2 del sistema), instalación
de `requirements.txt` + `pytest`, y verificación end-to-end (suite en verde y app web
corriendo en el display `:1`, flujo «Analizar» → tablero PNG).
*Archivos:* `AGENTS.md` (nuevo, sección «Cursor Cloud specific instructions»),
`.gitignore` (ignora `.venv/`), `HANDOFF.md`.
*Notas:* correr pytest con `--basetemp="$HOME/pytest-tmp"` (si no, fallan en falso los
tests de rutas por `seguridad.confina_usuario`). Dos tests de descarga ERA5 paralela
(`test_descargar_serie_paralelo_max_dos`, `test_descargar_serie_largo_concatena_tramos`)
hacen segfault en Linux por el HDF5 no thread-safe del wheel pip de netCDF4 (deseleccionarlos);
no es bug del código. Detalle completo en `AGENTS.md`.

### 2026-06-27 · Repo público: sin rutas personales (Cursor)
*Qué/por qué:* Eliminadas rutas personales del código y docs; tests de
regresión usan variables de entorno `TABLERO_DATOS_SWAN` / `TABLERO_DATOS_OLEAJE`;
bloques `__main__` piden la entrada por CLI. Repo en GitHub hecho público.
*Archivos:* `test_regresion.py`, `Tablero Oleaje.vbs`, `tablero_oleaje.py`,
`io_oleaje.py`, `tablero_swan.py`, `io_swan.py`, `io_swan_nonst.py`, `video_swan.py`,
`productos_swan.py`, `HANDOFF.md`, `docs/plans/2026-06-27-nesting-swan.md`
*Notas:* Sin `TABLERO_DATOS_*` los tests con datos reales se saltan; en local exportar
esas vars apuntando a tus carpetas de prueba.

### 2026-06-27 · Revisión final pre-entrega (Cursor)
*Qué/por qué:* auditoría completa Windows + macOS antes de envío: suite de tests
(147 passed), imports/smoke, zip de entrega regenerado, guías alineadas con
carpeta `GUIAS DE USO/`, lanzador Mac con manejo de errores (pip/app + log),
`pytest` fuera de `requirements.txt` (solo desarrollo).
*Archivos:* `iniciar_mac.command`, `GUIAS DE USO/*.txt`, `requirements.txt`,
`dist/Tablero_Oleaje_entrega_2026-06-27.zip`, `HANDOFF.md`.
*Notas:* tests dev: `pip install pytest` + `pytest test_regresion.py test_asistente.py test_motor_web.py test_nesting.py -q`.

### 2026-06-27 · Empaquetado para entrega (Cursor)
*Qué/por qué:* script `empaquetar_entrega.bat` / `.ps1` genera zip limpio en `dist/`
(sin .venv, salidas, tests, docs dev, config local) + `LEEME PRIMERO.txt` para el
receptor. Guías en `GUIAS DE USO/`.
*Archivos:* `empaquetar_entrega.bat`, `empaquetar_entrega.ps1`, `LEEME PRIMERO.txt`,
`.gitignore`, `README.md`, `iniciar_windows.bat`, `requirements.txt`, `HANDOFF.md`.

### 2026-06-27 · Guía y lanzador Windows (Cursor)
*Qué/por qué:* paridad con Mac: `iniciar_windows.bat` (venv + pip + app),
`GUIA DE USO WINDOWS.txt` para usuario final; `.lnk` apunta al .bat (sin ruta
hardcodeada de Python del desarrollador).
*Archivos:* `iniciar_windows.bat`, `GUIA DE USO WINDOWS.txt`, `crear_acceso_directo.ps1`,
`README.md`, `requirements.txt`, `HANDOFF.md`.

### 2026-06-27 · Guía Mac en texto plano (Cursor)
*Qué/por qué:* renombrar documentación Mac a `GUIA DE USO MAC.txt` (texto plano,
orientada al usuario final, sin markdown).
*Archivos:* `GUIA DE USO MAC.txt` (nuevo), eliminado `README_MAC.md`, `README.md`,
`requirements.txt`, `HANDOFF.md`.

### 2026-06-27 · Entrega macOS: compatibilidad y lanzador (Cursor)
*Qué/por qué:* preparar entrega al cliente Mac (Intel + Apple Silicon): rutas
multiplataforma, apertura de archivos sin `os.startfile`, backend pywebview Cocoa,
`requirements.txt` completo, `iniciar_mac.command` y `GUIA DE USO MAC.txt`.
*Archivos:* `sistema.py` (nuevo), `app_web.py`, `api_web.py`, `motor_web.py`,
`pasos_analizar.py`, `pasos_modelar.py`, `pasos_ver.py`, `gui_swan.py`,
`app_tablero.py`, `rutas.py`, `requirements.txt`, `iniciar_mac.command` (nuevo),
`GUIA DE USO MAC.txt` (nuevo), `HANDOFF.md`.
*Notas:* entrada principal `app_web.py --gui`; en Mac ejecutar `chmod +x iniciar_mac.command`
la primera vez; SWAN/ffmpeg siguen siendo opcionales del sistema.

### 2026-06-27 · Inicio: tarjeta «Procesar SWAN» (Cursor)
*Qué/por qué:* el panel para correr un caso SWAN existente solo estaba en Modo avanzado;
ahora hay una 4.ª tarjeta en la página principal que abre la misma vista (carpeta → correr).
*Archivos:* `ui/js/views.js`, `ui/js/core.js`, `ui/styles.css`, `HANDOFF.md`.

### 2026-06-27 · Validación .bot vs malla en paso Batimetría (Cursor)
*Qué/por qué:* al elegir un `.bot` propio, la app valida de inmediato el conteo de nodos
`(myc+1)×(mxc+1)`, muestra el número esperado, bloquea «Siguiente» si no cuadra, y corrige
el preview (antes usaba `mxc×myc`). Al recalcular malla se invalida la batimetría previa.
*Archivos:* `io_batimetria.py`, `previews.py`, `motor_web.py`, `api_web.py`,
`ui/js/wizard-modelar.js`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* endpoint `validar_bot_malla`; +3 tests regresión.

### 2026-06-27 · Borde SWAN: derivación automática desde ERA5 (Cursor)
*Qué/por qué:* en Modelar, el paso Borde rellena Hs/Tp/Dir solo si hay ERA5 en caché
(centro de la malla + rango de prefs); botón descarga+deriva si falta; archivo manual opcional.
*Archivos:* `motor_web.py`, `api_web.py`, `ui/js/wizard-modelar.js`, `ui/js/core.js`, `HANDOFF.md`.

### 2026-06-27 · UI solo web: tkinter obsoleto (Cursor)
*Qué/por qué:* el usuario usa exclusivamente la interfaz web; tkinter queda retirada
del flujo de uso. `app_tablero.py` redirige a `app_web.py --gui` si alguien lo ejecuta.
*Archivos:* `app_tablero.py`, `README.md`, `CLAUDE.md`, `HANDOFF.md`.
*Notas:* no borrar `pasos_*` / `gui_swan` aún (tests); no añadir features en tkinter.

### 2026-06-27 · Implementación informe QA (P0–P2) (Cursor)
*Qué/por qué:* correcciones del informe QA: seguridad CDS, bordes NaN/Gumbel, caché ERA5,
nido/batimetría, confinamiento API, límites de malla, productos SWAN y robustez general.
*Cambios principales:*
- **`seguridad.py`:** `validar_url_cds`, `es_finito_positivo/en_rango`; fix `sanitizar_nombre_fuente`.
- **`io_era5.py`:** caché 4 decimales, normalización longitud, `validar_coord_era5`.
- **`borde_oleaje.py` / `swan_builder.py` / `pasos_modelar.py`:** rechazo no finitos; Gumbel validado.
- **`motor_web.py` / `pasos_modelar.py`:** `.bot` únicos (`bati_grande.bot` / `bati_nido.bot`); path resuelto tablero.
- **`api_web.py`:** `ruta_existe` confinado, lock SWAN, errores sanitizados.
- **`geo_malla.py`:** tope celdas/nodos; **`productos_swan.py`**, **`video_swan.py`**, **`swan_runner.py`**, etc.
*Archivos:* `seguridad.py`, `io_era5.py`, `borde_oleaje.py`, `swan_builder.py`, `motor_web.py`,
`pasos_modelar.py`, `api_web.py`, `geo_malla.py`, `productos_swan.py`, `video_swan.py`,
`swan_runner.py`, `validacion.py`, `io_oleaje.py`, `io_swan_nonst.py`, `config.py`, `app_web.py`,
`test_regresion.py`, `test_asistente.py`, `HANDOFF.md`.
*Notas:* +9 tests regresión, +2 asistente; correr suite completa tras pull.

### 2026-06-27 · Wizard Modelar: batimetría clara, plantillas, nido, checklist (Cursor)
*Qué/por qué:* el paso batimetría era opaco («descargar» vs generar .bot desde ETOPO).
Reorden pasos: malla → nido → batimetría → borde → correr. UI con plantillas (Coronel,
Reñaca, Golfo), carpeta del caso en malla, tabs grande/nido, resumen semáforo post-.bot,
raster .nc local, diagrama de borde, preview anidamiento, checklist pre-SWAN, logs .prt.
*Archivos:* `motor_web.py`, `api_web.py`, `previews.py`, `ui/js/wizard-modelar.js`,
`ui/js/core.js`, `ui/styles.css`, `test_regresion.py`, `HANDOFF.md`.

### 2026-06-27 · Mejoras UX/UI masivas (web): previews, ERA5 espectro, caché, SWAN web (Cursor)
*Qué/por qué:* implementación del paquete de mejoras acordado (excepto modo oscuro,
animaciones entre pasos e export informe): espectro ERA5 + partición en UI, vista previa
in-app, mapas malla/batimetría, Procesar SWAN en web (sin tk), gestión caché ERA5,
inicio enriquecido, semáforo revisión, comparación vs referencia, footnotes en tablero PNG,
persistencia prefs/sesión, atajos teclado, Acerca de, `requirements.txt`, tests motor web,
`ui/` modularizado en `js/`.
*Archivos:* `previews.py`, `motor_web.py`, `api_web.py`, `tablero_oleaje.py`,
`ui/index.html`, `ui/styles.css`, `ui/js/*.js`, `ui/app.js`, `requirements.txt`,
`test_regresion.py`, `test_motor_web.py`, `README.md`, `HANDOFF.md`.
*Notas:* multipanel video ya existía (`video_swan.multipanel=True`); la UI lo menciona.
Legacy `gui_swan` sigue en repo pero ya no se invoca desde avanzado.

### 2026-06-27 · Ver corrida SWAN: UTM auto desde carpeta (Cursor)
*Qué/por qué:* en «Ver corrida», UTM X/Y ya no son siempre los defaults de Coronel;
se infieren al cargar la carpeta (tablero_swan.json → CGRID UTM → default).
*Cambios:*
- **`io_swan.py`:** `guardar_meta_caso`, `inferir_utm_desde_carpeta`, `tablero_swan.json`.
- **`motor_web.py` / `pasos_modelar.py`:** guardan meta al escribir el caso.
- **`info_carpeta_swan`:** devuelve utm_x, utm_y, origen, mensaje.
- **`ui/app.js` / `pasos_ver.py`:** rellenan campos y muestran de dónde salió el offset.
*Archivos:* `io_swan.py`, `motor_web.py`, `pasos_modelar.py`, `pasos_ver.py`,
`ui/app.js`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* casos viejos CGRID (0,0) siguen con default Coronel (editable); +3 tests.

### 2026-06-27 · Tablero: paneles multi-anuales exigen span ≥ 730 d (Cursor)
*Qué/por qué:* con ~1 año ERA5 (jul-2024→jul-2025) aparecían régimen extremo, Gumbel
y climatología con 2 máximos anuales parciales (feo e inestable). Ahora se exige
span ≥ 730 d **y** ≥ 2 años calendario (`datos_suficientes_multi_anual`); mismo
criterio en `borde_oleaje` modo retorno.
*Archivos:* `productos.py`, `borde_oleaje.py`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* +2 tests (caso ERA5 1 año / 2 años completos); regenerar tablero tras el cambio.

### 2026-06-27 · ERA5 origen: sin botón credenciales inline (Cursor)
*Qué/por qué:* el paso «Descargar de ERA5» ya no muestra botón «Credenciales CDS…»;
si faltan credenciales, la barra de estado muestra «Error: Faltan credenciales ERA5».
La configuración sigue en la barra lateral → Credenciales ERA5.
*Archivos:* `ui/app.js`, `api_web.py`, `HANDOFF.md`.

### 2026-06-27 · UI: pantalla Credenciales ERA5 (Copernicus CDS) (Cursor)
*Qué/por qué:* cada usuario debe configurar su propia cuenta CDS sin editar
archivos a mano ni reutilizar la API key de otra persona.
*Cambios:*
- **`io_era5.py`:** `estado_credenciales_cds`, `guardar_credenciales_cds`,
  `probar_credenciales_cds` (GET /v2/tasks); clave enmascarada en la UI.
- **`api_web.py`:** endpoints `estado_cds_credenciales`, `guardar_cds_credenciales`,
  `probar_cds_credenciales`, `abrir_url_externa`; bloqueo de descarga ERA5 sin credenciales.
- **`ui/`:** nav «Credenciales ERA5», formulario guardar/probar; aviso en paso ERA5 del asistente.
*Archivos:* `io_era5.py`, `api_web.py`, `ui/index.html`, `ui/app.js`, `ui/styles.css`,
`test_regresion.py`, `README.md`, `HANDOFF.md`.
*Notas:* +4 tests credenciales CDS; el archivo sigue siendo `~/.cdsapirc` (compatible con cdsapi).

### 2026-06-27 · Fix timeout UI en descarga ERA5 larga (Cursor)
*Qué/por qué:* `waitTask("era5")` cortaba a los 10 min aunque la descarga siguiera;
rangos anuales necesitan mucho más. Timeout deslizante (30–60 min sin actividad),
renovación en cada línea de log, latido cada 5 min mientras el CDS responde.
*Archivos:* `ui/app.js`, `io_era5.py`, `HANDOFF.md`.

### 2026-06-27 · ERA5: descarga paralela de tramos (2 a la vez) (Cursor)
*Qué/por qué:* rangos largos eran lentos porque los tramos se pedían en serie;
ahora hasta 2 peticiones CDS simultáneas (cliente cdsapi por hilo, logs con lock).
*Archivos:* `io_era5.py`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* test `test_descargar_serie_paralelo_max_dos` verifica el tope; si el CDS
empieza a devolver errores de cola, bajar a 1 worker.

### 2026-06-27 · ERA5: descarga larga en tramos mensuales + concat (Cursor)
*Qué/por qué:* peticiones >~31 días al CDS devolvían 403 *cost limits exceeded*;
ahora rangos largos se parten en tramos (fin de mes), se cachean en `chunks/` y
se concatenan en un único `era5_serie.nc`.
*Archivos:* `io_era5.py`, `test_regresion.py`, `HANDOFF.md`.

### 2026-06-27 · Caché ERA5 por rango de fechas (Cursor)
*Qué/por qué:* al descargar otro periodo en la misma lat/lon, se reutilizaba
`salidas/ERA5_{lat}_{lon}_serie/era5_serie.nc` y el tablero mostraba siempre el
primer rango.
*Arreglo:* `_nombre_fuente` y `ruta_cache_serie` incluyen inicio/fin; tablero PNG
junto a la carpeta ERA5; UI invalida descarga si cambian fechas/coords.
*Archivos:* `io_era5.py`, `motor_web.py`, `pasos_analizar.py`, `app_tablero.py`,
`tablero_oleaje.py`, `ui/app.js`, `test_regresion.py`, `HANDOFF.md`.

### 2026-06-27 · Fix ERA5: poll_eventos roto en UI web (Cursor)
*Qué/por qué:* la descarga ERA5 (y cualquier tarea en hilo) parecía colgarse
indefinidamente: `ui/app.js` llamaba `callPy("poll_eventos")` pero la función
correcta es `py()`, así que la cola de eventos nunca se drenaba y `waitTask`
no recibía `task_done`.
*Arreglo:* `py("poll_eventos")` cada 150 ms; mensajes de progreso ERA5 vía
`log_fn` en `io_era5`/`motor_web`/`api_web`; `_retrieve_atomico` ya no borra
el `.part` tras una descarga exitosa.
*Archivos:* `ui/app.js`, `api_web.py`, `motor_web.py`, `io_era5.py`, `HANDOFF.md`.

### 2026-06-27 · Fixes QA: rutas confinadas, fugas, borde None, cancel SWAN (Cursor)
*Qué/por qué:* implementación completa del informe QA: confinamiento de rutas vía API
web, zip-slip robusto, validación ERA5/borde, cierre de datasets y cancelación SWAN
desde la UI web.
*Cambios principales:*
- **`seguridad.py`:** `confina_usuario()` (home + `salidas/`).
- **`motor_web.py` / `api_web.py`:** todas las rutas de lectura/escritura validadas;
  `cancelar_swan()` + botón en UI; `abrir_en_explorador` confinado.
- **`io_era5.py`:** `validar_rango_fechas()`; zip-slip con `is_relative_to`.
- **`swan_builder.py`:** `validar_caso` ante `per`/`dir` None; nido sin división por cero.
- **Fugas:** `ds.close()` en `pasos_modelar`, `gui_swan`, `app_tablero`, `pasos_analizar`;
  rasters en `io_batimetria` con context manager.
- **`validacion.py`:** chequeo temporal sin coord `time`; **`io_oleaje.py`:** CSV sin columnas;
  **`config.py`:** aviso si falla escritura; **`ui/app.js`:** null en borde + cancel SWAN.
*Archivos:* `seguridad.py`, `motor_web.py`, `api_web.py`, `io_era5.py`, `swan_builder.py`,
`pasos_modelar.py`, `gui_swan.py`, `app_tablero.py`, `pasos_analizar.py`, `io_batimetria.py`,
`validacion.py`, `io_oleaje.py`, `config.py`, `ui/app.js`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* 92 tests regresión+nesting en verde (+5 tests: confina_usuario, fechas, borde None,
zip-slip, validación sin time).

### 2026-06-27 · Endurecimiento QA: seguridad, validación y robustez (Cursor)
*Qué/por qué:* implementación del informe QA completo: saneamiento de rutas/nombres,
validación más estricta, corrección ERA5 `mwd`→`Dir` (procedencia náutica), UI web más
segura en hilos y datos degenerados.
*Cambios principales:*
- **`seguridad.py` (nuevo):** whitelist de nombres SWAN (sin espacios), segmentos de
  ruta, confinamiento, zip-slip en referencias READINP.
- **`io_era5.py`:** conversión `mwd`+180°; zip-slip al extraer CDS; exige swh/pp1d/mwd.
- **`validacion.py`:** NaN cuenta como fallo en Hs/Tp/Dir/peralte.
- **`swan_runner.py` / `gui_swan.py`:** rechazo de nombres con espacios; `matar_proceso_arbol`
  (taskkill /T); `proteger_swan` acotado al PID lanzador.
- **`swan_builder.py` / `motor_web.py` / `pasos_modelar.py`:** escritura sanitizada;
  validación SWAN sin copiar `.bot`; copia solo al escribir/correr; NONSTAT exige tiempos.
- **`api_web.py` / `ui/app.js`:** cola de eventos + `poll_eventos`; errores sin traceback
  completo; JSON guards; `waitTask` con timeout; validación borde/ERA5/rutas en web.
- **`productos.py` / `borde_oleaje.py` / `tablero_oleaje.py`:** guardas ante series vacías
  o degeneradas; `ds.close()` en finally.
- **`config.py`:** lock en escritura; **`geo_malla.py`:** zona UTM acotada 1–60.
*Archivos:* `seguridad.py`, `rutas.py`, `io_era5.py`, `validacion.py`, `swan_*`, `motor_web.py`,
`api_web.py`, `ui/app.js`, `productos*.py`, `borde_oleaje.py`, `tablero_oleaje.py`,
`io_batimetria.py`, `io_swan*.py`, `prioridad.py`, `config.py`, `geo_malla.py`,
`particion_espectral.py`, `gui_swan.py`, `pasos_modelar.py`, `app_tablero.py`,
`test_regresion.py`, `HANDOFF.md`.
*Notas:* 87 tests regresión+nesting en verde; +4 tests nuevos (ERA5 Dir, seguridad, NaN).
`test_asistente` puede fallar si Tcl/Tk no está disponible en el entorno de CI.

### 2026-06-27 · Tablero adaptativo para series cortas (ERA5 ~1 mes) (Cursor)
*Qué/por qué:* al descargar ERA5 de un mes, el tablero mostraba paneles pensados para
series multi-anuales (serie con 2 puntos mensuales, climatología con meses vacíos,
máximo anual trivial). Ahora el registro adaptativo de `productos.py` ajusta qué se dibuja
según la duración de los datos.
*Cambios:*
- **Serie temporal:** si el span es &lt; 365 días → Hs en resolución nativa (cada paso ERA5);
  si no → media mensual como antes.
- **Climatología mensual** y **régimen extremo (máx. anual):** solo si hay ≥ 2 años (mismo
  criterio que Gumbel); en series cortas se omiten con motivo en el informe de capacidades.
- **Curva de excedencia:** anotaciones P50, P90 y P99 sobre la curva.
*Archivos:* `productos.py`, `test_regresion.py`, `HANDOFF.md`.
*Notas:* 99 tests en verde. Regenerar tablero tras descargar ERA5 para ver el nuevo layout.

### 2026-06-27 · Fix UI web: «Siguiente» quedaba muerto tras cada tarea + regla de commit (Claude Code)
*Qué/por qué:* tras descargar ERA5 (o cualquier tarea en hilo) la UI web **no dejaba
avanzar** con «Siguiente». En `ui/app.js`, `setBusy(on)` deshabilitaba todos los botones
`.btn.primary` al iniciar la tarea (`if (on) b.disabled = true`) pero **nunca los
re-habilitaba** al terminar (no había rama para `on === false`). Como «Siguiente →» es
`btn primary`, quedaba `disabled` y el clic no hacía nada. Afectaba a todos los botones
primarios después de cualquier tarea (descarga, batimetría, tablero…).
*Arreglo:* `setBusy` ahora hace `b.disabled = on` (deshabilita al ocupar, re-habilita al
terminar).
*Regla de proyecto:* a pedido del usuario, `CLAUDE.md` deja de prohibir commitear: ahora se
**commitea** el trabajo relevante al terminar (mensaje en español + entrada de HANDOFF en el
mismo commit), en la rama actual; sin push ni `--force` salvo que el usuario lo pida.
*Archivos:* `ui/app.js`, `CLAUDE.md`, `HANDOFF.md`.
*Notas:* fix de JS no cubierto por pytest (la suite no ejerce la UI web). El usuario verifica
en la app: descargar ERA5 → «Siguiente» avanza a Revisión.

### 2026-06-27 · ERA5 serie con el CDS nuevo: ZIP multi-stream + valid_time + cache limpia (Claude Code)
*Qué/por qué:* el camino «Analizar → Descargar de ERA5 por coordenada» fallaba. La causa
estaba **oculta** porque el wizard mostraba «NoneType: None» (se corrigió antes en
`asistente.py`: `traceback.format_exc()` se evaluaba en el lambda diferido a `after`, fuera
del `except`). Ya visible, aparecieron dos problemas reales encadenados:
1. **Licencias del dataset no aceptadas** (403 del CDS) — acción del usuario, ya resuelta
   (aceptar en `cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels`).
2. **Formato del CDS nuevo:** la serie llega como **ZIP con un `.nc` por *stream*** (olas y
   atmósfera, **grillas lat/lon distintas**) y coordenada **`valid_time`**, no `time`.
   `xr.open_dataset` reventaba al parsear y al validar la cache; y como el pipeline re-lee
   `era5_serie.nc` con `io_oleaje.cargar` (tkinter `pasos_analizar` y web `motor_web`), el
   zip crudo tampoco se podía abrir ahí.
*Arreglo (`io_era5.py`):*
- `_abrir_descarga_cds()` abre indistintamente un `.nc` plano o un `.zip` multi-stream.
- `_parsear_serie_nc()` selecciona el punto en **cada** stream (grillas distintas), los une
  y renombra `valid_time`→`time`.
- `descargar_serie()` ahora **cachea la serie YA PARSEADA** (Hs/Tp/Dir/time en un punto) en
  `era5_serie.nc`, de modo que `io_oleaje.cargar` la abre como un `.nc` normal **sin acoplar
  io_oleaje a ERA5**. Reaprovecha un zip crudo ya cacheado (auto-sana, sin re-pedir al CDS).
- `_cache_utilizable()` y `_parsear_espectro_nc()` también manejan el zip.
*Archivos:* `io_era5.py`; `test_regresion.py` (2 tests: zip multi-stream → Hs/Tp/Dir/time;
descargar_serie deja cache `.nc` limpia legible por `io_oleaje.cargar`).
*Notas:* 95 en verde (regresión+nesting+asistente). Verificado **end-to-end sobre la cache
real** del usuario (zip → `.nc` limpio, sin red). El espectro 2D quedó robusto al zip, pero
su selección de punto/estructura no se validó con datos reales (no se usa ahora).

### 2026-06-27 · Lanzador definitivo: `.lnk` en carpeta + `--gui` sin consola (Cursor)
*Qué/por qué:* el usuario abría la app desde un acceso directo que **no funcionaba** o
abría la **UI tk antigua** (`pythonw.exe app_tablero.py`). Tras varios intentos, la
combinación que **funciona en su PC** (Python 3.13, pywebview/WebView2) quedó así.
*Estado final verificado por el usuario.*
*Lanzador principal:*
- **`Tablero de Oleaje.lnk`** en la **raíz del repo** (no en el Escritorio).
- Apunta a `python.exe` + `app_web.py --gui` (ruta fija Python313 si hace falta).
- Regenerar con `crear_acceso_directo.ps1` o `Crear Tablero.bat` (regenera y abre).
*Flag `--gui` en `app_web.py`:*
- Redirige stdout/stderr a `os.devnull`.
- Oculta la consola al inicio (`ShowWindow`) y ~1,5 s después la **cierra** con
  `FreeConsole()` en un hilo daemon (después de `create_window`, antes/durante
  `webview.start`). **No** llamar `FreeConsole()` antes de que pywebview arranque:
  la app sale con código 1.
*Trampas en el PC del usuario (no reintentar sin leer esto):*
| Intento | Resultado |
|---------|-----------|
| `py -3w` | Falla: *No suitable Python runtime* (launcher solo registra `python.exe`). |
| `pythonw.exe app_web.py` | Sale al instante con código 1; pywebview no arranca. |
| `.vbs` con `WindowStyle=0` (sin consola desde el spawn) | No abre la app (mismo efecto). |
| `python.exe app_web.py` | ✅ Funciona. |
| `python.exe app_web.py --gui` | ✅ Funciona sin ventana negra persistente. |
*Archivos:* `app_web.py`, `crear_acceso_directo.ps1`, `Crear Tablero.bat`.
`Tablero Oleaje.vbs` queda como respaldo legacy; **no** es el lanzador principal.
*Nota:* el `.lnk` viejo del Escritorio se elimina al correr `crear_acceso_directo.ps1`.

### 2026-06-27 · Acceso directo en carpeta del proyecto (UI web) — iteración intermedia (Cursor)
*Qué/por qué:* reemplazar `.lnk` interno que apuntaba a `app_tablero.py` (UI tk).
*Notas:* ver entrada anterior para el estado final (`--gui`, sin `.vbs` como principal).

### 2026-06-27 · Fix acceso directo: python.exe oculto, no pythonw (Cursor)
*Qué/por qué:* el acceso directo seguía sin abrir aunque `python app_web.py` funcionara.
`pythonw.exe` lanza `app_web.py` pero **sale al instante con código 1** (pywebview/WebView2
no arranca bien sin consola en este PC). `python.exe` sí mantiene la ventana abierta.
*Arreglo:* `Tablero Oleaje.vbs` usa `python.exe` con `WindowStyle=0` (consola oculta) en
lugar de `pythonw`.
*Archivo:* `Tablero Oleaje.vbs`.

### 2026-06-27 · Fix acceso directo: lanzador .vbs — py -3w (Cursor)
*Qué/por qué:* primer intento: `py -3w` fallaba silenciosamente (*No suitable Python runtime*).
*Arreglo:* se pasó a `pythonw.exe` (insuficiente; ver entrada anterior).

### 2026-06-27 · CLAUDE.md — misma regla HANDOFF para Claude Code (Cursor)
*Qué/por qué:* paridad con la regla Cursor; Claude Code debe leer/escribir HANDOFF sin
que el usuario lo recuerde.
*Archivo:* `CLAUDE.md` en la raíz del repo (punteros rápidos + formato de entrada).

### 2026-06-27 · Regla Cursor: HANDOFF obligatorio (Cursor)
*Qué/por qué:* el HANDOFF solo se actualizaba cuando el usuario lo pedía; hacía falta
forzarlo como regla del repo para Cursor y Claude Code.
*Archivo:* `.cursor/rules/handoff-bitacora.mdc` (`alwaysApply: true`) — leer HANDOFF al
inicio; escribir entrada + secciones desactualizadas al terminar cambios relevantes.

### 2026-06-27 · UI web pywebview (estilo Mac) + acceso directo (Cursor)
*Qué/por qué:* la GUI tkinter (`app_tablero.py` + `estilo.py`) se acercaba poco al
mockup `preview_mac.html` (sombras, bordes redondeados, controles planos). Se migró la
**interfaz principal** a **pywebview** (WebView2/Edge Chromium en Windows): HTML/CSS/JS
real, mismo look que el preview, sin reescribir el motor.
*Archivos nuevos:*
- `app_web.py` — punto de entrada (ventana pywebview, fallback si no hay Edge).
- `ui/index.html`, `ui/styles.css`, `ui/app.js` — SPA (inicio, 3 wizards, avanzado).
- `motor_web.py` — lógica GUI **sin tkinter** (revision_datos, mallas, ERA5, SWAN, etc.).
- `api_web.py` — puente JS↔Python (`js_api`), diálogos de archivo/carpeta, tareas en hilo
  con eventos `log`/`progress`/`task_done` hacia la UI.
- `Tablero Oleaje.vbs` — respaldo legacy (no lanzador principal).
- `crear_acceso_directo.ps1` — crea `Tablero de Oleaje.lnk` **en la carpeta del proyecto**.
*Lanzadores:* doble clic en `Tablero de Oleaje.lnk` (`python.exe app_web.py --gui`) o
`Crear Tablero.bat`. Ver entrada «Lanzador definitivo» en registro de cambios.
*Dependencia:* `pip install pywebview`.
*Qué NO se tocó:* pipelines (`tablero_oleaje`, `swan_runner`, `pasos_*.py` lógica de
negocio). `app_tablero.py` + `asistente.py` + `estilo.py` **siguen** como respaldo tkinter.
*Modo avanzado web:* botón «Procesar SWAN…» abre `gui_swan.VentanaSwan` en hilo tk
(`api_web.abrir_procesar_swan_legacy`) — única ventana tk que queda en el flujo web.
*Detalle UI:* barra superior sin semáforos decorativos (solo título «Tablero de Oleaje»).
`preview_mac.html` queda como mockup de referencia, no se usa en runtime.

### 2026-06-27 · Guard pythonw + nota de flake tkinter (Cursor)
*Qué/por qué:* la app se lanza con **pythonw.exe** (`.lnk`/`.bat`), donde
`sys.stdout`/`sys.stderr` son **None**. Cualquier `print()` del pipeline (avisos de dedup
de `io_swan`, reporte de validación, capacidades de `productos`, etc.) reventaría con
`AttributeError: 'NoneType' has no attribute 'write'`. Algunos flujos capturan stdout con
`redirect_stdout`, pero otros (camino "Ver" del asistente, que llama `cargar_corrida`) no.
*Arreglo:* `app_tablero._asegurar_salida_estandar()` reemplaza stdout/stderr por un
`_SumideroNulo` **sólo si son None**; se llama en `AppTablero.__init__` y en el `__main__`.
Con consola o bajo pytest no toca nada. *Test:* `test_asegurar_salida_estandar_repara_stdout_none`.

> ⚠️ **Flake de entorno (no es un bug del código):** al correr la suite completa, los tests
> que crean `tk.Tk()` en `test_asistente.py` fallan **de forma intermitente** con
> `TclError: Can't find a usable tk.tcl … couldn't read file "…/tk8.6/<X>.tcl"` (cambia el
> archivo: `tk.tcl`, `winTheme.tcl`, `cursors.tcl`, `msgs/es.msg`). Es tkinter que no puede
> **leer sus propios archivos Tcl** del install de Python (probable OneDrive on-demand / AV
> bloqueando lecturas, agravado al crear muchos `Tk()` y por Claude Code corriendo en
> paralelo). **Re-correr lo pone en verde** (verificado: 2 fallos → 0 al repetir, sin tocar
> código). `test_regresion.py`+`test_nesting.py` (77) son estables. Si se quiere robustez:
> excluir on-demand la carpeta `Python313\tcl` de OneDrive/AV, o serializar las pruebas GUI.

### 2026-06-27 · ALTA #8 — carreras GUI/hilos (winfo_exists + cancelar al cerrar) (Cursor)
*Qué/por qué + arreglo:*
- **`gui_swan.VentanaSwan`**: ninguno de los callbacks que el hilo de SWAN marshalaba a
  la GUI (`_log`, `_set_progreso`, `_terminar`, `_error`, `_cancelado_fin`, `_bati_worker`)
  comprobaba `winfo_exists()`, y **cerrar la ventana mientras corría SWAN dejaba un
  `swan.exe` huérfano** (no había handler de cierre). *Arreglo:* helper `_marshal()` que
  agenda con `after` envuelto en `try/except TclError` y sólo ejecuta si `_vivo()`;
  `protocol("WM_DELETE_WINDOW", _al_cerrar)` que setea la cancelación y `terminate()` del
  proceso antes de destruir. Todos los callbacks pasan ahora por `_marshal`.
- **`app_tablero.VistaAvanzado`**: las tres callbacks ya chequeaban `winfo_exists()`, pero
  el `self.after(...)` de `_descargar_era5`/`_procesar` podía lanzar `TclError` si la app
  se cerraba a mitad, y `ruta_datos.set` iba sin guard. *Arreglo:* mismo helper `_marshal()`
  para todo el marshaling de los hilos.
*Tests:* `test_ventana_swan_cierre_cancela_proceso` (cerrar mata el proceso y marca
cancelación) y `test_ventana_swan_marshal_no_revienta_tras_cerrar` (marshal tras destroy
no lanza ni ejecuta). 92 en verde.

### 2026-06-27 · ALTA #7 — Gumbel sin protección con series cortas (Cursor)
*Qué:* `productos._calc_retorno` ajustaba Gumbel sobre `groupby("time.year").max()` sin
mirar cuántos años había, y `evaluar()` lo calcula de forma **anticipada** para todo
producto disponible. Con <2 años el ajuste es degenerado (`scale→0`): scipy soltaba
"overflow/invalid value" y la fit reventaba/daba NaN. *Por qué importa:* además de la
curva sin sentido, hacía que `evaluar()` lanzara excepción → y esa excepción es justo la
que dejaba en **rojo** el test de Claude Code `test_paso_revision_avanza_con_datos_buenos`
(serie de prueba de 1 año). `borde_oleaje` ya estaba protegido (`n<2 → ValueError`); esto
faltaba en `productos`.
*Arreglo:* `_calc_retorno` lanza `ValueError` claro si hay <2 años; el registro de
productos admite un predicado opcional `aplicable(ds)` y el de Gumbel usa
`_n_anios(ds) >= 2`; `evaluar()` marca el producto **no disponible** con el motivo
"≥ 2 años de datos…" (sin calcular nada). Patrón "registro adaptativo" intacto y compatible
con `tablero_oleaje`.
*Efecto colateral bueno:* la suite completa (incluyendo `test_asistente.py`) vuelve a
**90 en verde**; el rojo de ALTA #1 (Claude Code) era consecuencia de este bug, no de su
implementación, así que se resolvió **sin tocar sus archivos**.
*Tests:* 3 nuevos en `test_regresion.py` (no disponible con serie corta, `_calc_retorno`
lanza con 1 año, disponible con 4 años).

### 2026-06-27 · ALTA #6 — cache ERA5 sin validar + HTTP de batimetría sin chequeo (Cursor)
*Qué/por qué + arreglo:*
- **`io_era5` (cache)**: `descargar_serie`/`descargar_espectro` confiaban en cualquier
  `.nc` existente (`if not destino.exists()`). Una descarga interrumpida deja un `.nc` de
  0 bytes o truncado → al parsearlo, error críptico (o datos a medias). *Arreglo:*
  `_cache_utilizable()` (existe + no vacío + se abre) decide si re-descargar, y
  `_retrieve_atomico()` baja a un `.part` y renombra al final, así nunca queda una cache
  a medio escribir.
- **`io_batimetria.descargar_raster` (HTTP)**: `urlretrieve` sólo falla con status de
  error, pero ERDDAP suele responder **200 con un cuerpo de error** (texto/HTML); eso se
  guardaba como si fuera NetCDF y xarray reventaba. *Arreglo:* `urlopen` con chequeo de
  status, content-type y **bytes mágicos** (`CDF`/`\x89HDF`); si no es NetCDF, `RuntimeError`
  con el detalle del servidor y la sugerencia de usar un `.bot` local. `HTTPError` ahora
  incluye código + cuerpo.
*Tests:* `test_descargar_serie_redescarga_cache_corrupta` (cache de 0 bytes → re-descarga)
y `test_descargar_raster_rechaza_respuesta_no_netcdf` (200 con HTML → RuntimeError). 71 verde.

### 2026-06-27 · ALTA #5 — I/O frágil (.mat, CGRID, SPEC2D) (Cursor)
*Qué/por qué + arreglo:*
- **`io_oleaje._leer_mat`**: hacía `loadmat(ruta)[variable]` → `KeyError` críptico si el
  .mat no traía `DataTarea`, y armaba el DataFrame aunque el nº de columnas no calzara.
  Ahora valida la presencia de la variable (mensaje que **lista las disponibles**) y que
  la matriz sea 2D con el nº de columnas esperado.
- **`_leer_cgrid` (io_swan e io_swan_nonst)**: `dx = xlenc/mxc` reventaba con
  `ZeroDivisionError` si `mxc=0`, y `partes[6/7]` con `IndexError` si el CGRID venía
  truncado. Ahora exige ≥8 tokens y `mxc/myc ≥ 1`, con errores claros.
- **SPEC2D truncado (`leer_espectro_swan` e `leer_espectro_temporal`)**: leer la matriz
  más allá del fin de archivo daba `IndexError`/arreglo ragged. Ahora se valida que haya
  frecuencias/direcciones declaradas y que las filas existan y tengan el ancho correcto,
  lanzando `ValueError` "truncado" entendible. El temporal devuelve `None` si falta el
  encabezado AFREQ/CDIR (no es SPEC2D válido).
*Tests:* 6 nuevos en `test_regresion.py` (.mat sin var / columnas, CGRID mxc=0 en ambos
módulos, CGRID truncado, SPEC2D estacionario y temporal truncados). 69 en verde.

### 2026-06-27 · ALTA #3 y #4 — falso éxito de SWAN por `norm_end` global (Cursor)
*Qué:* `swan_runner.correr_caso` decidía el éxito con `(carpeta/"norm_end").exists()`,
pero `norm_end` es un **único archivo por carpeta** (SWAN no lo nombra por caso). Si el
dominio grande lo dejaba y luego el nido fallaba sin reescribirlo, el nido **heredaba el
éxito** del grande. Además el `.erf` (terminación con errores) sólo se usaba para el log,
no para el veredicto. *Por qué:* un par anidado con el nido roto reportaba OK y el
asistente dejaba avanzar a graficar resultados inválidos.
*Arreglo (ALTA #3, `swan_runner.py`):* antes de cada caso se borran el `norm_end` global
y el `<caso>.erf` viejo; el veredicto pasa a ser `ok = norm_end.exists() and not <caso>.erf`,
así refleja SÓLO ese caso. `correr_swan` ya hacía `ok_global &= correr_caso(...)`, que
ahora es correcto.
*Arreglo (ALTA #4, `pasos_modelar.PasoCorrer`):* se separa "aún no corre" de "corrió y
falló" con un flag `corrido`; el log dice "terminó normalmente" vs "terminó CON ERRORES
(.prt/.erf)" y `validar()` bloquea con un mensaje claro cuando `ok` es False (antes decía
"SWAN terminó con avisos" y el mensaje de validación implicaba que no había corrido).
*Tests:* `test_correr_swan_no_hereda_exito_si_falla_el_nido` (SWAN simulado: grande deja
norm_end, nido deja .erf y stale norm_end → `ok_global=False`), `test_correr_swan_ok_si_
todos_los_casos_terminan` y `test_paso_correr_distingue_no_corrido_fallo_y_ok`. 63 en verde.

### 2026-06-27 · ALTA #2 — `validacion._chequeo_tiempo` con series cortas (Cursor)
*Qué:* `_chequeo_tiempo` calculaba `pd.Series(dif).mode()[0]` sobre los intervalos
entre timestamps; con una serie de 0 o 1 paso, `dif` queda vacío y `mode()` también,
así que `[0]` lanzaba `IndexError` y tumbaba toda la validación. *Por qué:* el chequeo
debe degradar con gracia, no reventar, cuando no hay intervalos que comparar.
*Arreglo:* guard `if len(t) < 2:` que devuelve `(0, "serie de N paso(s): sin intervalos
que evaluar")` antes de tocar `mode()`. El camino normal (≥2 pasos) no cambió.
*Tests:* 3 nuevos en `test_regresion.py` (1 paso, serie vacía, y caso normal con hueco
+ duplicado que sigue contando 2). `test_regresion.py`+`test_nesting.py` en verde (60).

> ⚠️ **Coordinación:** ALTA #1 (`PasoRevision`) lo implementó **Claude Code** en paralelo
> (cambios sin commitear en `pasos_analizar.py` y `test_asistente.py`). Cursor NO lo tocó.
> Su test `test_paso_revision_avanza_con_datos_buenos` estuvo **rojo** un rato, pero el
> rojo era consecuencia de ALTA #7 (Gumbel reventaba en `evaluar` con la serie de 1 año
> del test), no de la implementación de Claude Code. Al corregir ALTA #7 quedó en verde.

### 2026-06-27 · Revisión QA — corrección de los 4 bugs CRÍTICOS (Cursor)
Tras una auditoría QA de todos los `.py`, se corrigieron los 4 fallos que podían
tumbar la app o eran riesgo de seguridad. **Los 72 tests pasan** tras los cambios.
Nota de entorno: en este equipo el shell debe correr **sin sandbox** (la política
`workspace_readwrite` de Windows no está soportada), o `pytest` falla por entorno,
no por código.

1. **Inyección de comandos en `swan_runner.py`** — *por qué:* el nombre del caso
   (stem del `.swn`, influido por el usuario) se interpolaba en `subprocess` con
   `shell=True` (`f'swanrun "{caso}"'`), permitiendo ejecutar comandos arbitrarios.
   *Arreglo:* lista blanca `_NOMBRE_CASO_OK` + `_validar_nombre_caso()`, y
   `shell=False` resolviendo `swanrun` con `shutil.which` y pasando el caso como
   argumento aparte (con `cmd /c` solo si es `.bat/.cmd`).
2. **`ZeroDivisionError` con 0 productos en `tablero_oleaje.py` / `tablero_swan.py`**
   — *por qué:* si el dataset no tenía variables ploteables, `cols = 0` reventaba al
   armar la figura. *Arreglo:* si `disponibles` está vacío, se lanza `ValueError`
   con mensaje claro (oleaje además cierra el `ds`) antes de construir la figura.
3. **`video_swan.animar_multipanel` sin campo `Dir`** — *por qué:* `actualizar()`
   llamaba `qv_g.set_UVC(...)` aunque `_dibujar_mapa` devuelve `qv_g=None` cuando no
   hay dirección (o es todo NaN). *Arreglo:* guarda `if qv_g is not None:` antes de
   tocar la flecha y `large["Dir"]`. (`animar_campo` ya estaba protegido.)
4. **Duplicados SWAN silenciosos en `io_swan.py` / `io_swan_nonst.py`** — *por qué:*
   varias salidas para la misma variable+malla se resolvían con un dict donde
   "ganaba el último" sin avisar (riesgo de usar un resultado viejo). *Arreglo:*
   helper `_asignar_campos()` que detecta la colisión, **avisa** y conserva el
   archivo **más reciente** (`mtime`).

**Pendiente: bugs de ALTA prioridad (siguiente tanda):**
1. `pasos_analizar.PasoRevision` deja avanzar con datos rotos — **EN CURSO (Claude Code)**.
2. ✅ `validacion._chequeo_tiempo` con serie de 1 timestamp — **HECHO (Cursor, ver arriba)**.
3. ✅ `swan_runner`: `norm_end` global por carpeta → falso éxito — **HECHO (Cursor, ver arriba)**.
4. ✅ `pasos_modelar.PasoCorrer` trataba SWAN con errores como OK — **HECHO (Cursor, ver arriba)**.
5. ✅ I/O frágil (`.mat` sin variable, CGRID `mxc=0`, SPEC2D truncado) — **HECHO (Cursor)**.
6. ✅ ERA5 cacheada sin validar + HTTP sin chequeo de status — **HECHO (Cursor)**.
7. ✅ Gumbel sin protección con series cortas (`productos`; `borde_oleaje` ya estaba) — **HECHO (Cursor)**.
8. ✅ Carreras GUI/hilos (winfo_exists + cancelar al cerrar) — **HECHO (Cursor)**.

**Regla de trabajo:** correr `python -m pytest test_regresion.py test_asistente.py
test_nesting.py -q` tras cada cambio (sin sandbox en este equipo) y mantener la
coherencia entre módulos.

## Qué es
Herramienta personal reutilizable de análisis de oleaje, construida iterativamente
para aprender `xarray` dirigiendo a la IA. Raíz del repositorio: carpeta del clone
local de `tablero-oleaje` (código separado de carpetas de tareas académicas).

Patrón común de todo el código: **registro adaptativo** — cada producto declara
`requiere=[...]`; el pipeline genera solo lo que los datos permiten y reporta lo que falta.

## Estado: TODO funcionando y verificado

### A) Tablero de curvas (serie temporal en un punto)
- `io_oleaje.py`: `.mat/.csv/.nc` → Dataset xarray (coord `time` real) → NetCDF.
- `validacion.py`: chequeos físicos (rangos Hs/Tp/Dir, peralte aguas profundas, continuidad temporal).
- `productos.py`: 10 productos (resumen, serie mensual, climatología mensual, excedencia,
  régimen extremo máx anual, **períodos de retorno Gumbel→Hs diseño 50/100 a**, Rayleigh,
  Hs–Tp, rosa, JONSWAP) + placeholder "espectro medido S(f)".
- `tablero_oleaje.py`: orquestador → tablero PNG.
- Datos de prueba: `Proyectos\Python\Tarea 3 Costas\Datos_Nodo10_37S_75W_Talcahuano.mat`
  (36 años, 3-horario; Hs/Tp/Dir).

### B) Tablero de mapas SWAN (campos 2D estacionarios, p. ej. TR100)
- `io_swan.py`: **genérico** (autodetecta dominios/campos de cualquier corrida, no
  sólo Coronel). Clasifica los `.swn` por su CGRID (padre = origen 0,0; anidados por
  `xpc,ypc`); la variable de cada salida `.txt` se lee del comando `BLOCK` del `.swn`
  (cantidad SWAN HS/TPS/DIR/SETUP → `_QUANT_VAR`), con fallback al nombre; se asigna
  al dominio por tamaño de campo. Offset UTM del large = parámetro `utm_large`
  (default Coronel `620494/5876451`); el del nido se deriva. Convención MATLAB:
  reshape+flipud, rellenos `−9/−999 → NaN`. Probado: TR100/TR10/reinante reproducen
  Hs de borde, y una corrida con archivos renombrados + cantidades `HSIGN/RTP`.
- `productos_swan.py`: mapas Hs (large/n1) con dirección y batimetría, set-up, espectro
  direccional polar.
- `tablero_swan.py`: orquestador (layout `constrained`).
- Datos: `Proyectos\Python\SWAN_Coronel\extremo_Tr100` (también `extremo_Tr10`, `reinante`,
  misma estructura). Verificado: `Hs.max=8.17 m` = condición de borde TR100 (NW, Hs 8.16,
  Tp 13 s, Dp 315°).

### C) Videos SWAN no estacionarios (evento que evoluciona en el tiempo)
- `io_swan_nonst.py`: **genérico** (autodetecta dominios y campos de cualquier
  carpeta NonSt, no sólo Coronel). Clasifica los `.swn` por su CGRID (padre =
  origen local 0,0; anidados por su `xpc,ypc`) y reparte los `.mat`/`.bot` al
  dominio **por tamaño de campo**. Apila las 168 matrices timestamped
  (`<Pref>_YYYYMMDD_HHMMSS`) en `DataArray (time,y,x)` con coord `time` real.
  Misma orientación (`flipud`) y rellenos que MATLAB/io_swan (reusa
  `EXCEPCION`/`ATRIBUTOS`). El offset UTM del large es parámetro `utm_large`
  (default Coronel `620494/5876451`); el del nido se deriva. `es_corrida_nonst()`
  detecta el modo. Verificado: peak en paso 118 (= `frames_clave_3d.m`), Hs large
  máx 6.997 m, isla Santa María en su sitio.
- `video_swan.py`: `FuncAnimation` con escala de color **global fija** + timestamp.
  `animar_multipanel` (producto principal): mapa Hs Golfo + dirección, mapa Hs
  nido (escala propia), serie temporal con cursor; punto autodetectado (mayor
  variabilidad) u override. `animar_campo` (por-campo). Escritor MP4 (ffmpeg) con
  fallback GIF (Pillow). `progress_callback` para la GUI. Salida: 168 frames, 14 s
  a 12 fps. El nido NonSt es numéricamente inestable (sólo el paso 0 tiene oleaje;
  Tp/Dir ~99% NaN, Set-up 100% NaN): `_nido_util()` (Hs > umbral en ≥5% de los
  frames) lo detecta y el multipanel **omite el panel del nido**, dejando que la
  serie temporal de Hs ocupe todo el lado derecho. El robusto es el large.
- Datos: `Proyectos\Python\SWAN_Coronel\no_estacionario` (evento 28-jul→03-ago
  2024). Videos en `salidas\<fuente>\` (ver Salidas).

### GUI + lanzadores
- **Única interfaz de usuario:** `app_web.py` + carpeta `ui/` (pywebview).
- **Windows — lanzador del usuario:** `iniciar_windows.bat` o **`Tablero de Oleaje.lnk`**
  (regenerar con `crear_acceso_directo.ps1` / `Crear Tablero.bat`). El .bat crea
  `.venv`, instala `requirements.txt` y ejecuta `app_web.py --gui`. Guía: `GUIA DE USO WINDOWS.txt`.
- **macOS — lanzador del cliente:** `iniciar_mac.command` (doble clic; ver `GUIA DE USO MAC.txt`).
  Crea `.venv`, instala `requirements.txt` y ejecuta `app_web.py --gui`. Primera vez: `chmod +x`.
- **Desde terminal (con consola, para depurar):** `python app_web.py` (sin `--gui`).
- **Tkinter obsoleto:** `app_tablero.py`, `asistente.py`, `pasos_*.py`, `gui_swan.py`
  siguen en el repo **solo para tests**; no ampliar. Si se ejecuta `app_tablero.py`,
  redirige a la app web.
- Requiere `pywebview`. Windows: WebView2 (Edge); macOS: WebKit (backend `cocoa`).
  Tres caminos guiados + modo avanzado en HTML; motor en `motor_web.py` / `api_web.py`.
  Apertura de archivos/carpetas: `sistema.py` (multiplataforma). SWAN desde web;
  **no** se abre `gui_swan` desde la UI web.
- En `app_web.py`: log en `salidas/app_web.log` con `--gui`; stdout/stderr no van a `/devnull`.

### Modo guiado (asistente)
- **Web (único):** wizards en `ui/js/` (analizar / modelar / ver); validación en JS;
  llamadas a `api_web.Api`. Motor en `motor_web.py`.
- **Tkinter (obsoleto):** `pasos_*.py` + `asistente.Wizard` — conservados para
  `test_asistente.py`; la lógica de negocio vive en `motor_web.py`.
- **Nesting (anidado) implementado**: el camino Modelar arma un par grande+nido
  desde cero. `swan_builder.escribir_par_anidado` escribe los dos `.swn` enlazados
  (NGRID/NESTOUT en el grande ↔ BOU NEST en el nido) y `validar_caso_anidado`
  comprueba contención, misma zona UTM y celda más fina; `swan_runner.casos_ordenados`
  ordena por `BOU NEST` (el nido corre al final). El camino tiene 6 pasos: `PasoNido`
  (opcional, entre Borde y Correr) define la malla/batimetría fina y un punto de
  salida espectral opcional, y hace `append` a la lista `contexto["dominios"]` (helper
  `pasos_modelar._dominio_actual`); `PasoCorrer` arma 1 o 2 dominios según la lista.
  `PasoVer` no cambió (el tablero autodetecta los dominios).

### Salidas
- `rutas.py`: helper común. Todos los productos (tableros PNG, NetCDF, videos) se
  guardan en `salidas\<fuente>\` dentro de la herramienta, una subcarpeta por
  archivo/corrida (stem del archivo o nombre de la carpeta). El código queda
  limpio; los flujos llaman `rutas.carpeta_salida(nombre_fuente)`.

### D) Procesar SWAN (el paso previo: correr el modelo)
- `swan_runner.py`: corre `swanrun` (instalación SWAN en `%LOCALAPPDATA%\Programs\
  swan`, ver [[swan-instalacion]]) sobre una carpeta con caso(s) `.swn`. Orden grande→nido (el nido se detecta por `BOU NEST`/`BOUN NEST` y corre al final; el resto, antes); verifica inputs externos (READINP) justo
  antes de cada caso (no el nesting, que lo genera el grande); detecta `norm_end`;
  `log`/`progreso` callbacks. Verificado con SWAN real (50 iter, genera Hs/Tp/Dir).
- `swan_builder.py`: genera un `.swn` desde parámetros (malla CGRID, batimetría
  INPGRID/READINP, borde JONSWAP `BOUN SIDE`, física estándar OFF WINDGROWTH/OFF
  QUAD/BREAKING/FRICTION/SETUP, salidas BLOCK con `_QUANT`), estacionario o NONSTAT.
  Cantidades coinciden con `_QUANT_VAR` de io_swan (round-trip builder→runner→io_swan).
  `validar_caso()` chequea coherencia física antes de correr (errores vs avisos):
  INPGRID cubre CGRID, tamaño del `.bot` = (mxinp+1)(myinp+1), resolución vs L₀(Tp),
  Hs/dir/per del borde.
- `gui_swan.py`: ventana `VentanaSwan` (Toplevel) con 2 pestañas — «Correr caso
  existente» (carpeta + casos detectados) y «Armar y correr» (formulario: malla,
  batimetría .bot, borde Hs/Tp/Dir/dd + lados, salidas, estacionario; valida con
  `validar_caso`) — log en vivo, **barra indeterminada** (SWAN no anuncia el total
  de iteraciones, así que gira mientras trabaja) y **botón Cancelar** (mata el
  proceso `swan.exe`). Abierta desde «Procesar SWAN…» de `app_tablero.py`. El
  espectro 2D temporal lo lee `io_swan_nonst.leer_espectro_temporal` (SWAN ASCII,
  NO es .mat v7.3 — no se usó h5py) y `video_swan.animar_espectro` lo anima (o
  figura polar estática si <2 pasos con energía, como en Coronel: 1/168).

### E) Robustez y calidad
- `test_regresion.py` (pytest 9.1.1): 11 tests rápidos (~1 s, no corren SWAN ni
  generan figuras). Cargan las corridas conocidas y fijan valores clave (Hs de
  borde TR100/TR10/reinante, nt=168 y peak=118 del NonSt, espectro 168×35×180 con
  1 paso con energía, nido NonSt no-útil, helpers `_QUANT_VAR`/`casos_ordenados`,
  builder). **Detectaron un bug real**: el offset UTM del nido estacionario estaba
  mal en el módulo viejo (Norte 5893222; lo correcto, derivado del CGRID, es
  5908680 → el nido quedaba ~15 km desplazado en Y). Corre `pytest test_regresion.py`
  antes de dar por buena cualquier modificación.
- `config.py`: preferencias persistentes en `config.json` (últimas carpetas para
  los diálogos). `README.md`: doc de uso/flujo/módulos.

## Entorno
- Python 3.10+ recomendado (probado con 3.13). Usar `python` en PATH; en Windows,
  **`pythonw.exe` puede fallar** con `app_web.py` + pywebview — preferir `python.exe`.
- Instalados: `xarray` 2026.4.0, `netcdf4` 1.7.4, `scipy`, `matplotlib`, `windrose`,
  `cmocean`, `ffmpeg` (Gyan, vía winget), **`pywebview`** (UI principal), WebView2/Edge.

## Estado actual y lo que sigue
La herramienta está **completa y verificada** (A–E). Pendiente abierto al cerrar
esta sesión:

- **Corrida SWAN en progreso (del usuario)**: está re-corriendo SWAN sobre
  `SWAN_Coronel\no_estacionario` con el botón Procesar SWAN, **para ver si el nido
  no estacionario sale estable** esta vez. Al cerrar, el dominio grande se estaba
  regenerando (iba por el paso ~30/168); el nido aún no se re-corría.
  ⚠️ **Está corriendo sobre la carpeta ORIGINAL**, así que los `.mat` se
  sobreescriben. **Por eso `test_regresion.py` puede fallar mientras la corrida no
  termine** (lee `.mat` a medio escribir, p. ej. `nt=30`). Cuando termine:
  1. Generar el video con **Crear** y ver si el nido ahora tiene señal (si es
     estable, `_nido_util` lo detecta y el panel del nido reaparece).
  2. Si los valores del dominio grande cambian respecto a los de referencia
     (Hs.max=6.997, peak=118, nt=168), **actualizar `test_regresion.py`**.
- La barra indeterminada y `_nido_util` se añadieron en esta sesión; la corrida que
  el usuario tenía abierta usa el código viejo (debe reabrir la app para verlos).

Ideas futuras (del usuario, no comprometidas): nada concreto; la app "ya tiene todo".

## Docs en la carpeta
`README.md` (uso/flujo/módulos) · `DISEÑO.md` (diseño A y B) ·
`PLAN_video_no_estacionario.md` (plan ya implementado, histórico) ·
`test_regresion.py` (red de seguridad — correr antes de cerrar cualquier cambio).

## Forma de trabajar del usuario
Comentarios en español con tildes; `snake_case`; código limpio listo para entregar;
figuras con ejes/unidades/título; no sobre-preguntar. Estilo iterativo: cada módulo →
explicar 3-4 ideas clave de xarray → verificar corriéndolo → seguir.
