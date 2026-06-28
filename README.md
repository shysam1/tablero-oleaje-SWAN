# Tablero de Oleaje

Herramienta personal para analizar oleaje y modelos SWAN, de extremo a extremo:
**armar y correr el modelo → cargar los resultados → generar tableros y videos**.
Construida de forma iterativa como ejercicio de dirigir IA y verificar con criterio
de ingeniería (xarray + NetCDF, propagación de oleaje costero).

## Descarga (recomendado)

**Instalador Windows — descarga directa del `.exe`:**

👉 **[Releases → Tablero de Oleaje 1.0.0](https://github.com/shysam1/tablero-oleaje/releases/tag/v1.0.0)**

1. Descarga **`Tablero_Oleaje_Setup_1.0.0.exe`**
2. Ejecuta el instalador (si SmartScreen avisa: *Más información* → *Ejecutar de todas formas*)
3. Abre la app desde el acceso directo del Escritorio o menú Inicio

**Requisitos:** Windows 10/11 (64 bits), **Python 3.11+** en el PATH
([python.org](https://www.python.org/downloads/); marca *Add python.exe to PATH*),
internet la **primera vez** que abras la app (descarga librerías) y WebView2
(viene con Windows/Edge actualizado). SWAN y ffmpeg son opcionales.

Guía detallada dentro del instalador: `GUIAS DE USO\GUIA INSTALACION WINDOWS.txt`.

> **macOS:** instalador `.dmg` planificado; por ahora usa la carpeta del proyecto
> con `iniciar_mac.command` (ver guía Mac en `GUIAS DE USO/`).

## Uso rápido (desarrollo / carpeta .zip)

Doble clic en **`iniciar_windows.bat`** o en **`Tablero de Oleaje.lnk`**
(regenerar con `Crear Tablero.bat`), o desde consola:

```powershell
.\iniciar_windows.bat
```

La interfaz es **solo web** (pywebview + WebView2) en `ui/`. No uses
`app_tablero.py`: si lo ejecutas, redirige a la web.

El lanzador crea `.venv` e instala `requirements.txt` automáticamente la primera vez
(vía `scripts/bootstrap_windows.ps1` + `scripts/launch_windows.bat`).

**Windows:** lee `GUIAS DE USO\GUIA DE USO WINDOWS.txt` si falta Python, WebView2 o alguna librería.

**macOS:** lee `GUIAS DE USO\GUIA DE USO MAC.txt` y haz doble clic en `iniciar_mac.command`.

**Empaquetar para entregar:** `empaquetar_entrega.bat` → `.zip` en `dist\`.
**Compilar instalador Windows:** `empaquetar_instalador.bat` → `.exe` en `installer\windows\`.

Atajos en la UI web: **Enter** = Siguiente, **Esc** = Atrás, **Ctrl+L** = limpiar log.

## Modo guiado

La app arranca en una pantalla de inicio (**«¿Qué querés hacer?»**) con tres
caminos paso a paso, pensados para no tener que conocer el orden del flujo. Cada
camino es un asistente con barra de pasos y botones *Atrás / Siguiente*:

- **Analizar oleaje en un punto** — origen de datos (archivo `.mat/.csv/.nc` o
  descarga ERA5) → revisión (variables, validación física y qué productos se
  podrán generar) → **tablero de curvas**.
- **Modelar propagación con SWAN** — malla por lat/lon → batimetría (descarga
  automática o `.bot` propio) → borde (manual o derivado de ERA5/serie) → correr
  SWAN → **tablero de mapas**. Incluye un paso opcional para agregar un **dominio anidado (nido)** más fino:
  define su malla por lat/lon y su propia batimetría, y la app arma el par
  grande+nido (NGRID/NESTOUT ↔ BOU NEST) y lo corre en orden. Opcionalmente, un
  punto de salida espectral en el nido.
- **Ver una corrida SWAN ya hecha** — eliges la carpeta corrida y autodetecta si
  generar **mapas** (estacionaria) o **video** (no estacionaria).

Cada camino reutiliza el mismo motor que el modo avanzado; no hay lógica
duplicada. El enlace **«Herramientas sueltas (modo avanzado)»** abre la caja de
herramientas de siempre, descrita abajo.

## Modo avanzado

En modo avanzado, la ventana ofrece un selector y estas acciones:

- **Crear** — autodetecta el tipo de entrada y genera el producto:
  - archivo `.mat/.csv/.nc` (serie temporal) → **tablero de curvas** (PNG);
  - carpeta SWAN estacionaria → **tablero de mapas** (PNG);
  - carpeta SWAN no estacionaria (`*NonSt.swn` o `.mat` con sello de tiempo) →
    **video** del evento (MP4, o GIF si no hay ffmpeg).
- **Procesar SWAN…** — el paso previo: corre el modelo. Dos modos:
  - *Correr caso existente*: elige una carpeta con el/los `.swn` ya armados y los
    ejecuta (orden dominio grande → nido), con log en vivo y botón de cancelar;
  - *Armar y correr*: formulario (malla, batimetría, borde, salidas) que genera el
    `.swn` y lo corre. Valida coherencia física antes de lanzar. El botón
    **«Definir por lat/lon…»** calcula la malla UTM (origen, celdas y zona) desde
    un centro lat/lon + tamaño + resolución, así no hace falta saber el UTM. El
    botón **«Generar batimetría…»** crea el `.bot` desde la malla y la *Zona UTM*:
    descarga batimetría global (GEBCO/ETOPO) de la zona, o usa un raster local
    propio (SHOA u otro `.nc`); proyecta a UTM, interpola y rellena el campo de
    batimetría. Avisa el rango de profundidad y el % de nodos en tierra.

En *Armar y correr*, el botón **«Tomar borde de ERA5/serie…»** deriva la condición
de borde (Hs/Tp/Dir) desde una serie de oleaje (un `.nc` de ERA5 o tu `.mat/.csv`):
eliges la condición —periodo de retorno (Gumbel), máximo observado o reinante— y
rellena los campos. La misma acción está en la ventana *Descargar ERA5* como
**«Enviar a SWAN como borde»**. El lado de entrada, la dispersión, la malla y la
batimetría los completas tú. **Convención del campo Dir: náutica** (de dónde viene
el oleaje, grados desde el Norte); el `.swn` generado emite `SET NAUTICAL` para
interpretarlo igual.

El campo *Offset UTM grande (avanzado)* fija la georreferencia de los mapas; por
defecto es el Golfo de Arauco. Cámbialo sólo para una corrida de otro lugar (no
altera la forma de los mapas, sólo las etiquetas de los ejes).

Todas las salidas van a `salidas\<fuente>\`, una subcarpeta por archivo o corrida.

## Flujo completo

```
[Procesar SWAN]  archivos iniciales (.swn + .bot + bordes)
       │           → corre SWAN → salidas BLOCK en la carpeta
       ▼
[Crear]          carpeta de resultados → tablero / video en salidas\<fuente>\
```

## Módulos

| Archivo | Rol |
|---|---|
| `app_web.py` + `ui/` | **Interfaz principal** (pywebview): tres caminos guiados + modo avanzado. |
| `api_web.py` · `motor_web.py` | Puente JS ↔ motor Python (sin tkinter). |
| `app_tablero.py` · `asistente.py` · `pasos_*.py` · `gui_swan.py` | **Obsoletos** (tkinter); conservados para tests. `app_tablero.py` redirige a web si se ejecuta. |
| `io_oleaje.py` · `validacion.py` · `productos.py` · `tablero_oleaje.py` | Serie temporal en un punto → tablero de curvas. |
| `io_swan.py` · `productos_swan.py` · `tablero_swan.py` | Campos SWAN estacionarios → tablero de mapas. |
| `io_swan_nonst.py` · `video_swan.py` | Campos SWAN no estacionarios → videos (+ espectro). |
| `io_era5.py` | Descarga de oleaje por coordenada desde ERA5 (serie Hs/Tp/Dir + espectros 2D). |
| `particion_espectral.py` · `productos_particion.py` | Partición sea/swell por familias (watershed) → serie de Hs por familia, tabla y espectro polar. |
| `borde_oleaje.py` | Deriva la condición de borde SWAN (Hs/Tp/Dir) de una serie: periodo de retorno (Gumbel), máximo observado o reinante. |
| `io_batimetria.py` | Genera el `.bot` de la malla: descarga batimetría (GEBCO/ETOPO) por coordenadas o usa un raster local, proyecta a UTM e interpola. |
| `geo_malla.py` | Define la malla por lat/lon (centro + tamaño + celda) y calcula sola la zona UTM y los campos UTM. |
| `swan_runner.py` · `swan_builder.py` | Correr SWAN y armar el `.swn`. |
| `rutas.py` · `config.py` | Carpeta de salidas · preferencias entre sesiones. |
| `test_regresion.py` · `test_asistente.py` · `test_nesting.py` | Red de seguridad: valores conocidos del motor · navegación del wizard y composición de los caminos · motor de nesting (builder, validación y orden de corrida). |

## Decisiones de diseño

- **Registro adaptativo**: cada producto declara lo que necesita; el pipeline
  genera sólo lo que los datos permiten y reporta lo que falta. Por eso el nido no
  estacionario de Coronel (inestable, casi todo NaN) se omite sin romper nada.
- **Genérico, no atado a Coronel**: los dominios se detectan del `CGRID`; la
  variable de cada salida SWAN, del comando `BLOCK` del `.swn` (cantidad HS/TPS/
  DIR/SETUP), no del nombre del archivo. El offset UTM del dominio grande es un
  parámetro (`utm_large`); el del nido se deriva de su `CGRID`.
- **Orientación verificada contra MATLAB**: misma convención `flipud` y rellenos
  `−9/−999 → NaN`; el peak del evento cae en el mismo paso que el script del curso.

## Requisitos

Python **3.11+** con `numpy`, `pandas`, `xarray`, `netcdf4`, `scipy`, `matplotlib`,
`windrose`, `cmocean`, `scikit-image` (partición espectral) y `cdsapi` (descarga
ERA5). Opcionales: `ffmpeg` (MP4; si no, GIF), `pytest` (tests).
Para *Procesar SWAN*, SWAN instalado y `swanrun` en el PATH.

### Credenciales ERA5 (descarga por coordenada)

La descarga usa el Copernicus Climate Data Store. **Cada usuario debe usar su
propia cuenta** (gratis):

1. Crea una cuenta en <https://cds.climate.copernicus.eu> y acepta los términos
   del dataset ERA5.
2. En la app web: barra lateral → **Credenciales ERA5** → pega tu `UID:API-KEY`,
   guarda y opcionalmente prueba la conexión.

Alternativa manual: archivo `~/.cdsapirc` (en Windows,
`C:\Users\<tu-usuario>\.cdsapirc`):

   ```
   url: https://cds.climate.copernicus.eu/api
   key: <UID>:<API-KEY>
   ```

Sin credenciales válidas, el botón "Descargar ERA5…" avisa y no intenta descargar.

## Tests

```powershell
pytest test_regresion.py test_asistente.py -v
```

`test_regresion.py` carga las corridas conocidas y comprueba los valores clave (Hs
de borde, número de pasos, orientación); si los datos de prueba no están en disco,
esos tests se saltan solos. En tu máquina puedes apuntar a carpetas locales con:

```powershell
$env:TABLERO_DATOS_SWAN = "C:\ruta\a\SWAN_Coronel"
$env:TABLERO_DATOS_OLEAJE = "C:\ruta\a\serie.mat"
pytest test_regresion.py -v
```

`test_asistente.py` cubre la navegación del wizard
(avanzar/retroceder, validación, contexto compartido) y que cada camino tenga sus
pasos. Córrelos antes de dar por buena cualquier modificación.
