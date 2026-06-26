# Plan — Auto-generación de videos para modelo SWAN no estacionario

Extiende la app para animar los campos espaciales de una corrida **no estacionaria**
(evento que evoluciona en el tiempo) y generar videos automáticamente.

## Objetivo

Donde el módulo SWAN estacionario produce un mapa por condición, aquí cada campo
tiene **168 pasos de tiempo**. El producto es un **video** (Hs, Tp, Dir, Set-up)
que muestra cómo evoluciona el oleaje en la bahía durante el temporal.

## Datos de entrada

Carpeta `SWAN_Coronel/no_estacionario/`:
- `.mat`: `Hs_Large`, `Dir_Large`, `Tp_Large`, `Hs_N1(c)`, `Dir_N1(c)`, `TP_N1(c)`,
  `SetUp_N1(c)`, `Espectro_Punto`.
- Cada `.mat` contiene **168 variables** nombradas `<Var>_YYYYMMDD_HHMMSS` (evento del
  2024-07-28, horario), campos **60×49** (large) / **51×46** (n1).
- Geometría: `Coronel1NonSt.swn` / `CoronelanidNonSt.swn` (mismo `CGRID` y offsets UTM
  que el módulo estacionario) + batimetría `batGC.bot` / `bataniGC.bot`.
- Forzantes de borde (para anotar): `Hs_Boya.txt`, `TPAR1.txt`, `TPAR2.txt`.

## Arquitectura (reutiliza lo ya construido)

1. **`io_swan_nonst.py`** (o ampliar `io_swan.py`)
   - `leer_mat_temporal(ruta, prefijo)`: apila las 168 variables timestamped en un
     `DataArray (time, y, x)`; arma la coord `time` parseando los nombres.
   - Reusa `_leer_cgrid` + los offsets UTM de `DOMINIOS` para las coordenadas.
   - Misma convención de relleno `−9/−999 → NaN`. **Verificar la orientación de los
     `.mat`** (si necesitan `flipud` como los `.txt` o ya vienen orientados).
   - `cargar_corrida_nonst(carpeta)` → `{large: ds(time,y,x), n1: ds(time,y,x), meta}`.

2. **`video_swan.py`**
   - Registro de animaciones (Hs large, Hs n1, Set-up, …) con **escala de color global
     fija** (vmin/vmax sobre todo el evento) para que los frames sean comparables.
   - `animar_campo(ds, var, salida, fps, formato)` con `matplotlib.animation.FuncAnimation`:
     cada frame hace `pcolormesh.set_array(...)` + título con el timestamp; opcional
     `quiver` de dirección actualizado por frame.
   - Escritor: **MP4** si hay `ffmpeg`; si no, **GIF** con Pillow (sin dependencia externa).
   - `generar_videos(carpeta, salida, campos, dominio, fps)` → uno o varios archivos.

3. **GUI (`app_tablero.py`)**
   - Autodetección: carpeta con `.mat` timestamped / `*NonSt.swn` → **modo video**.
   - Selector de campo, dominio (large/n1), fps y formato; **barra de progreso**
     (frame i/168) en el hilo de cálculo; abrir el video al terminar.

## Pasos de construcción (orden)

1. `io_swan_nonst` — cargar y **verificar**: `time` monótona, `Hs.max` coherente y
   orientación correcta contra una figura MATLAB conocida (1 frame estático de control).
2. `animar_campo` para **Hs (N1)** → primer video con escala fija + timestamp.
3. Resto de campos + dominio grande + vectores de dirección.
4. (Opcional) **multipanel sincronizado** (Hs large + Hs n1 + Set-up en un solo video).
5. Integración en la GUI (autodetección + progreso + abrir al terminar).

## Decisiones abiertas (definir antes de construir)

- **Formato:** MP4 (ffmpeg; liviano y de calidad) vs GIF (Pillow; sin instalar, pesa más).
  Recomendación: intentar MP4 con fallback a GIF.
- **Disparo:** autodetección automática vs botón/checkbox explícito "Generar video".
- **Salida:** un video por campo (varios archivos) vs un multipanel (un archivo).
  Recomendación: multipanel como principal + por-campo opcional.
- **Espectro temporal:** `Espectro_Punto.mat` (no estacionario) viene en MATLAB v7.3, que
  `scipy` no abre → requiere `h5py`. **Diferir** la animación del espectro.
- **FPS/duración:** 168 frames; recomendación 8–12 fps (≈14–21 s).

## Dependencias

- `Pillow` (ya instalado) → GIF.
- `ffmpeg` (opcional) → MP4: `winget install Gyan.FFmpeg`.
- `h5py` (solo si se anima el espectro v7.3): `pip install h5py`.

## Verificaciones clave

- Orientación de los campos `.mat` (¿`flipud` o no?) contra MATLAB.
- Escala de color global fija entre todos los frames.
- Timestamps correctos y monótonos en la coord `time`.
