# Tablero de Oleaje

Herramienta personal para analizar oleaje y modelos SWAN, de extremo a extremo:
**armar y correr el modelo → cargar los resultados → generar tableros y videos**.
Construida de forma iterativa como ejercicio de dirigir IA y verificar con criterio
de ingeniería (xarray + NetCDF, propagación de oleaje costero).

## Uso rápido

Doble clic en `Tablero de Oleaje.lnk` (o `Crear Tablero.bat`), o desde consola:

```powershell
python app_tablero.py
```

La ventana principal tiene un selector y dos acciones:

- **Crear** — autodetecta el tipo de entrada y genera el producto:
  - archivo `.mat/.csv/.nc` (serie temporal) → **tablero de curvas** (PNG);
  - carpeta SWAN estacionaria → **tablero de mapas** (PNG);
  - carpeta SWAN no estacionaria (`*NonSt.swn` o `.mat` con sello de tiempo) →
    **video** del evento (MP4, o GIF si no hay ffmpeg).
- **Procesar SWAN…** — el paso previo: corre el modelo. Dos modos:
  - *Correr caso existente*: elige una carpeta con el/los `.swn` ya armados y los
    ejecuta (orden dominio grande → nido), con log en vivo y botón de cancelar;
  - *Armar y correr*: formulario (malla, batimetría, borde, salidas) que genera el
    `.swn` y lo corre. Valida coherencia física antes de lanzar.

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
| `app_tablero.py` | Ventana principal (autodetección, botones Procesar SWAN y Descargar ERA5). |
| `io_oleaje.py` · `validacion.py` · `productos.py` · `tablero_oleaje.py` | Serie temporal en un punto → tablero de curvas. |
| `io_swan.py` · `productos_swan.py` · `tablero_swan.py` | Campos SWAN estacionarios → tablero de mapas. |
| `io_swan_nonst.py` · `video_swan.py` | Campos SWAN no estacionarios → videos (+ espectro). |
| `io_era5.py` | Descarga de oleaje por coordenada desde ERA5 (serie Hs/Tp/Dir + espectros 2D). |
| `particion_espectral.py` · `productos_particion.py` | Partición sea/swell por familias (watershed) → serie de Hs por familia, tabla y espectro polar. |
| `swan_runner.py` · `swan_builder.py` · `gui_swan.py` | Correr SWAN y armar el `.swn`. |
| `rutas.py` · `config.py` | Carpeta de salidas · preferencias entre sesiones. |
| `test_regresion.py` | Red de seguridad (valores conocidos). |

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

Python 3.13 con `numpy`, `pandas`, `xarray`, `netcdf4`, `scipy`, `matplotlib`,
`windrose`, `cmocean`, `scikit-image` (partición espectral) y `cdsapi` (descarga
ERA5). Opcionales: `ffmpeg` (MP4; si no, GIF), `pytest` (tests).
Para *Procesar SWAN*, SWAN instalado y `swanrun` en el PATH.

### Credenciales ERA5 (descarga por coordenada)

La descarga usa el Copernicus Climate Data Store. Una sola vez:

1. Crea una cuenta gratis en <https://cds.climate.copernicus.eu> y acepta los
   términos del dataset ERA5.
2. Crea el archivo `~/.cdsapirc` (en Windows, `C:\Users\<tu-usuario>\.cdsapirc`) con:

   ```
   url: https://cds.climate.copernicus.eu/api
   key: <UID>:<API-KEY>
   ```

Sin ese archivo, el botón "Descargar ERA5…" avisa con el paso a paso y no
descarga nada.

## Tests

```powershell
pytest test_regresion.py -v
```

Cargan las corridas conocidas y comprueban los valores clave (Hs de borde, número
de pasos, orientación). Córrelos antes de dar por buena cualquier modificación; si
los datos de prueba no están en disco, esos tests se saltan solos.
