# Tablero de Oleaje — Diseño

Herramienta reutilizable para análisis exploratorio de series de oleaje, construida
para aprender `xarray` + NetCDF y validación física automatizada.

## Objetivo

Cargar una serie de oleaje, llevarla a un `xarray.Dataset` con tiempo real, guardarla
en NetCDF, calcular **todos los productos que los datos permitan**, validarlos físicamente
y armar un tablero de figuras. El pipeline es **adaptativo**: lo que no puede calcular por
falta de datos lo reporta de forma explícita (qué falta y por qué) en vez de fallar o
saltárselo en silencio.

## Datos de entrada

**Caso base:** `Datos_Nodo10_37S_75W_Talcahuano.mat` (de Tarea 3 Costas).
- 105.191 registros, periodo 1980–2015, paso de 3 h.
- Nodo de oleaje frente a Talcahuano (37°S, 75°W).
- 7 columnas: `año, mes, día, hora, Hs [m], Tp [s], Dir [°]`.
- Rangos: Hs 0,38–7,90 m · Tp 5,2–24,0 s · Dir 7,5–352,5°.

**Formatos soportados:** `.mat`, `.csv`, `.nc`. El mapeo de columnas a variables es
configurable, de modo que el pipeline acepte fuentes con distinto contenido.

## Arquitectura (enfoque: registro de productos)

Flujo:

```
archivo (.mat/.csv/.nc)
   → io_oleaje: construir Dataset con coordenada time real → guardar NetCDF → recargar
   → inspeccionar capacidades (qué variables hay)
   → productos: calcular lo posible / reportar lo que falta
   → validacion: chequeos físicos (no borra, avisa)
   → tablero_oleaje: figura multipanel PNG + reporte por consola
```

### Módulos

- **`io_oleaje.py` — ingesta.** Lee el archivo, arma la coordenada `time` real desde
  `año/mes/día/hora`, crea el `xarray.Dataset` con `Hs/Tp/Dir` y sus atributos
  (unidades, nombre largo, convención CF) y lo guarda a NetCDF. Expone también la
  recarga (`open_dataset`).

- **`productos.py` — registro de cálculos.** Cada producto es una función que **declara
  las variables que requiere**. Un registro central permite inspeccionar el `Dataset` y
  decidir qué se puede calcular.

- **`validacion.py` — chequeos físicos automáticos.** Aplica reglas físicas y de
  consistencia temporal. No modifica los datos: reporta cuántos registros fallan cada regla.

- **`tablero_oleaje.py` — orquestador / punto de entrada.** Recibe un archivo, corre todo
  el flujo, imprime el reporte de capacidades (✓ calculado / ✗ omitido y por qué) y la
  validación, y guarda el tablero multipanel en PNG de alta resolución con ejes
  etiquetados, unidades y título.

## Productos y requisitos

| Producto                          | Requiere            | Con los datos base |
|-----------------------------------|---------------------|--------------------|
| Estadísticos de Hs/Tp/Dir         | la variable         | ✓                  |
| Serie temporal                    | Hs (+ time)         | ✓                  |
| Climatología mensual de Hs        | Hs + time           | ✓                  |
| Curva de excedencia de Hs         | Hs                  | ✓                  |
| Distribución de Hs (ajuste Rayleigh) | Hs               | ✓                  |
| Histograma conjunto Hs–Tp         | Hs, Tp              | ✓                  |
| Rosa de oleaje                    | Hs, Dir             | ✓                  |
| Espectro JONSWAP reconstruido     | Hs, Tp              | ✓ (marca: reconstruido) |
| Espectro medido S(f)              | densidad espectral  | ✗ (faltan datos espectrales) |

## Chequeos físicos automáticos

- `Hs ≥ 0` y `Hs < 20 m` (rango plausible).
- `Tp` en 2–30 s.
- `Dir` en [0, 360).
- Peralte en aguas profundas `Hs/L₀` por debajo del límite de rotura (~1/7),
  con `L₀ = g·Tp²/(2π)`.
- Continuidad temporal: detección de huecos y registros duplicados.

Cada chequeo informa el número de registros que lo incumplen (no se eliminan datos).

## Salidas

- `oleaje_<nodo>.nc` — Dataset en NetCDF.
- `tablero_<nodo>.png` — figura multipanel de alta resolución.
- Reporte por consola: capacidades (✓/✗ con motivo) + resumen de validación.

## Orden de construcción

1. `io_oleaje.py` — ingesta + NetCDF (la base; todo depende de esto).
2. `validacion.py` — chequeos físicos sobre el Dataset.
3. `productos.py` — registro y cálculos.
4. `tablero_oleaje.py` — orquestador + figura.
5. Prueba con el `.mat` real de Talcahuano.

## Interfaz gráfica (uso sin código)

- **`app_tablero.py`** — GUI en `tkinter` que reutiliza `generar_tablero`: elegir
  archivo → "Crear tablero" → genera y abre el PNG, mostrando el reporte.
- **`Tablero de Oleaje.lnk`** — acceso directo (doble-clic, sin consola) que abre
  la GUI con `pythonw`. Alternativa: **`Crear Tablero.bat`**.

## Módulo SWAN (campos espaciales 2D)

Familia paralela de productos para corridas SWAN estacionarias (p. ej. TR100):

- **`io_swan.py`** — lee una carpeta de corrida (`.swn` + salidas BLOCK `.txt` +
  batimetría `.bot`) y construye Datasets 2D UTM por dominio (`large`, `n1`) +
  el espectro 2D `S(f,θ)` del punto. Replica la convención MATLAB del usuario
  (reshape + flipud, rellenos `−9/−999 → NaN`, offsets UTM).
- **`productos_swan.py`** — mapas: Hs (grande y N1) con batimetría y vectores de
  dirección, set-up (N1, diverge en 0), y espectro direccional en polar.
- **`tablero_swan.py`** — orquestador del tablero de mapas.
- **GUI:** autodetección — carpeta de corrida SWAN → tablero de mapas; archivo
  `.mat/.csv/.nc` → tablero de curvas. Funciona con `extremo_Tr100`,
  `extremo_Tr10` y `reinante` (misma estructura).

## Qué se aprende

Construir `Dataset` de `xarray`, round-trip a NetCDF (`to_netcdf`/`open_dataset`),
agrupaciones temporales (`groupby('time.month')`, `resample`), inspección de datasets
para lógica adaptativa, y validación física automatizada.
