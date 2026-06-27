# Handoff — Herramienta "Tablero Oleaje" (contexto para nueva conversación)

## Qué es
Herramienta personal reutilizable de análisis de oleaje, construida iterativamente
para que el usuario (estudiante ing. civil hidráulica, UdeC) aprenda `xarray`
dirigiendo a la IA. Ubicación:
`C:\Users\123ja\OneDrive\Escritorio\Proyectos\Herramientas computacionales\Tablero Oleaje\`
(La carpeta "Herramientas computacionales" = herramientas reutilizables, distinta de
`Proyectos\Python` = tareas académicas.)

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
- `app_tablero.py`: GUI tkinter. Botón **Crear** autodetecta 3 modos: carpeta
  NonSt → video; carpeta SWAN → mapas; archivo `.mat/.csv/.nc` → curvas. Botón
  **Procesar SWAN…** abre `gui_swan.VentanaSwan`. Campo avanzado **Offset UTM
  grande** (default Coronel) que se pasa como `utm_large` a mapas/videos. Corre en
  hilo y abre el resultado al terminar.
- Doble-clic: `Tablero de Oleaje.lnk` y `Crear Tablero.bat` (usan `pythonw`).

### Modo guiado (asistente) — sub-proyecto C
- `app_tablero.py` ya **no** es una sola pantalla: `AppTablero` es un **contenedor de
  vistas** (`mostrar(nombre)` destruye la vista actual y crea una nueva). Vistas:
  `VistaInicio` (3 tarjetas: analizar / modelar / ver), `VistaAvanzado` (la GUI de
  siempre, movida tal cual — cero funcionalidad perdida) y un `asistente.Wizard` por
  cada camino. `mostrar` captura `ValueError` de un camino sin pasos y cae a inicio.
- `asistente.py`: `MaquinaWizard` (navegación pura, sin tkinter, 7 tests en
  `test_asistente.py`) + `Paso` (base: `entrar/validar/recoger`) + `Wizard` (barra de
  pasos, ← Inicio/Atrás/Siguiente, log/progreso comunes y `tarea(funcion, al_terminar)`
  que corre trabajo en hilo con guard de reentrada y de use-after-destroy
  `winfo_exists`). Los callbacks marshalan a la GUI con `self.after(0, …)`.
- `pasos_analizar.py` / `pasos_modelar.py` / `pasos_ver.py`: los pasos de cada camino,
  subclases de `Paso`, que **reutilizan el motor** (geo_malla, io_batimetria,
  borde_oleaje, io_era5, io_oleaje, validacion, productos, swan_builder/runner,
  tablero_*, video_swan). Mensajes de UI en español neutro (sin voseo).
- **Hueco del nesting (continuidad del 2.º proyecto)**: en el camino Modelar el
  contexto guarda los dominios como **lista** (`contexto["dominios"]`, helper
  `pasos_modelar._dominio_actual`); en v1 hay un solo dominio. El nido se agregará
  como un paso opcional entre Borde y Correr que reutilice malla/batimetría y haga
  `append`; `PasoCorrer`/`PasoVer` ya leen del dominio para no cambiar de firma.

### Salidas
- `rutas.py`: helper común. Todos los productos (tableros PNG, NetCDF, videos) se
  guardan en `salidas\<fuente>\` dentro de la herramienta, una subcarpeta por
  archivo/corrida (stem del archivo o nombre de la carpeta). El código queda
  limpio; los flujos llaman `rutas.carpeta_salida(nombre_fuente)`.

### D) Procesar SWAN (el paso previo: correr el modelo)
- `swan_runner.py`: corre `swanrun` (instalación SWAN en `%LOCALAPPDATA%\Programs\
  swan`, ver [[swan-instalacion]]) sobre una carpeta con caso(s) `.swn`. Orden
  grande→nido (padre = CGRID origen 0,0); verifica inputs externos (READINP) justo
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
- Python 3.13: `C:\Users\123ja\AppData\Local\Programs\Python\Python313\` (`pythonw.exe` ahí).
- Instalados: `xarray` 2026.4.0, `netcdf4` 1.7.4, `scipy`, `matplotlib`, `windrose`,
  `cmocean`, `ffmpeg` (Gyan, vía winget).

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
