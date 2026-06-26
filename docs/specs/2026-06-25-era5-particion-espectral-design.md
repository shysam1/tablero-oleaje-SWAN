# Diseño — Descarga ERA5 por coordenada + Partición espectral sea/swell

Fecha: 2026-06-25
Herramienta: Tablero de Oleaje
Estado: aprobado, pendiente de plan de implementación

## Objetivo

Agregar dos capacidades nuevas a la herramienta, manteniendo su patrón de
**registro adaptativo** (cada producto declara lo que necesita; el pipeline
genera solo lo que los datos permiten):

1. **Descarga de oleaje por coordenada** desde el reanálisis ERA5 (Copernicus
   CDS): serie temporal de parámetros integrados (Hs/Tp/Dir) y espectros 2D
   direccionales, para un punto (lat, lon) y un rango de fechas.
2. **Partición espectral sea/swell por familias** (algoritmo watershed de Hanson
   & Phillips) sobre cualquier espectro `Efth(freq, dir)`, venga de SWAN o de
   ERA5. Separa el espectro en 1 windsea + N swells y reporta Hs/Tp/Dir por
   familia.

Ambas conectan con el trabajo de tesis (downscaling espectral por familias de
olas) y reutilizan las estructuras de datos que el pipeline ya maneja.

## Contexto y restricciones

- El espectro 2D ya se carga como `Dataset` con `Efth(time, freq, dir)` en
  `io_swan_nonst.leer_espectro_temporal`. La partición debe consumir **esa misma
  forma**, y la descarga ERA5 debe **producir esa misma forma**, para reutilizar
  todo el pipeline aguas abajo.
- Las series puntuales se cargan como `Dataset(time)` con variables `Hs/Tp/Dir`
  (ver `io_oleaje.construir_dataset`). La serie ERA5 debe ser compatible para
  entrar directo al tablero de curvas.
- Convención de dirección: SWAN guarda dirección **cartesiana** (`CDIR`); ERA5
  usa convención náutica ("coming from"). Cada módulo de entrada documenta su
  convención; la partición opera en la convención del Dataset que recibe.
- Se mantiene la separación de responsabilidades: `io_*` para entrada,
  `productos*` para análisis/figuras, `rutas.py` para salidas, registro
  adaptativo para decidir qué se genera.

## Arquitectura

Dos módulos nuevos, desacoplados, más integración mínima en GUI y registro.

```
io_era5.py              entrada  → descarga ERA5 (serie + espectro)
particion_espectral.py  análisis → watershed sea/swell sobre Efth
productos*.py            + producto(s) de partición (requiere Efth)
app_tablero.py          + botón "Descargar ERA5…"
test_regresion.py       + tests de partición y de parsing ERA5
```

### 1. `io_era5.py` — descarga por coordenada

Interfaz pública (dos funciones que devuelven Datasets compatibles con el
pipeline):

- `descargar_serie(lat, lon, inicio, fin, incluir_viento=False) -> xr.Dataset`
  - Vía `cdsapi`, dataset `reanalysis-era5-single-levels`.
  - Variables: `significant_height_of_combined_wind_waves_and_swell` (→ Hs),
    `peak_wave_period` (→ Tp), `mean_wave_direction` (→ Dir). Opcional
    `10m_u/v_component_of_wind` (→ viento, para clasificar sea/swell).
  - Devuelve `Dataset(time)` con `Hs/Tp/Dir` (+ `u10/v10` si se pidió),
    **compatible con el tablero de curvas**.
- `descargar_espectro(lat, lon, inicio, fin) -> xr.Dataset`
  - Espectro 2D direccional ERA5 (`2d_wave_spectra`, parámetro `d2fd`).
  - Decodifica el almacenamiento logarítmico (densidad = 10^valor, rellenos →
    NaN), arma la grilla ERA5 (30 frecuencias, 24 direcciones) y reordena a
    `Efth(time, freq, dir)` **idéntico en forma** al de `leer_espectro_temporal`.
- Credenciales: lee `~/.cdsapirc`. Si no existe o es inválido, lanza un error con
  instrucciones claras (crear cuenta CDS, aceptar términos del dataset, pegar la
  API key). No se intenta ninguna descarga sin credenciales válidas.
- Caché: el `.nc` crudo descargado se guarda en `salidas/<fuente>/` (nombre
  derivado de lat/lon/rango) para no re-descargar.

### 2. `particion_espectral.py` — watershed sea/swell

Agnóstico a la fuente. Interfaz pública:

- `particionar(efth, freqs, dirs, viento=None) -> list[dict]`
  - Entrada: un espectro de un paso `efth[freq, dir]` (2D), los vectores de
    frecuencia y dirección, y opcionalmente el viento `(u10, v10)` del paso.
  - Watershed (Hanson & Phillips) sobre `-efth` con marcadores en los máximos
    locales, **con wrap en la dirección** (θ periódica: se trata la grilla como
    cilíndrica en el eje direccional).
  - Por cada partición calcula: `Hs = 4·sqrt(m0)`, `Tp` (pico), `Tm`
    (momento), `Dir` (media direccional pesada por energía).
  - Clasificación `tipo ∈ {"sea", "swell"}`:
    - Con viento: por *wave age* (windsea si `U10·cos(Δθ)/c_p > 1.3` en la
      frecuencia de pico de la partición).
    - Sin viento (caso SWAN): *fallback* por frecuencia de pico / peralte
      (las particiones de período largo se marcan swell). Documentado como
      aproximación.
  - Devuelve la lista de familias ordenadas por energía (la más energética
    primero), cada una un `dict` con sus parámetros y su máscara.
- `particionar_serie(ds_efth, viento=None) -> xr.Dataset`
  - Aplica `particionar` a cada paso de `Efth(time, freq, dir)`.
  - Devuelve `Dataset(time, familia)` con `Hs/Tp/Dir/tipo` por familia (nº de
    familias = máximo observado; pasos con menos familias quedan NaN).

Dependencia: `scikit-image` (`skimage.segmentation.watershed` +
`skimage.feature.peak_local_max`), por robustez y por ser el método de
referencia.

### 3. Productos / figuras (registro adaptativo)

Productos nuevos con `requiere=["Efth"]` (se saltan solos si no hay espectro):

- **Serie de Hs por familia**: Hs de cada familia (sea vs swells) en el tiempo,
  apiladas, con la Hs total de referencia. Aplica a espectro temporal (SWAN
  NonSt o ERA5).
- **Espectro polar particionado** (un paso): `S(f, θ)` polar con cada familia en
  un color. Reutiliza el polar de `productos_swan._espectro_direccional`.
- **Tabla de familias**: Hs, Tp, Dir, tipo por familia, exportable.

### 4. GUI — `app_tablero.py`

- Botón nuevo **"Descargar ERA5…"** que abre un formulario: `lat`, `lon`, fecha
  inicio/fin, check *"incluir espectros 2D"*, check *"incluir viento"*.
- Corre la descarga en un hilo (como el resto), con log y manejo del error de
  credenciales. Guarda el `.nc` en `salidas/<fuente>/` y queda listo para
  **Crear**.
- La partición **no necesita botón**: aparece como producto cuando el input
  cargado trae `Efth`.

### 5. Tests — `test_regresion.py`

- **Partición sobre espectro sintético**: dos picos conocidos (un sea de período
  corto + un swell de período largo, bien separados en (f,θ)) →
  - nº de familias detectadas = 2,
  - Hs y Dir de cada familia dentro de tolerancia,
  - **conservación de energía**: Σ m0 de las familias ≈ m0 del espectro total.
- **Parsing/decodificación ERA5**: sobre un archivo `.nc` chico cacheado en
  disco (sin red), verifica que `descargar_espectro` reconstruye `Efth` con las
  dimensiones correctas (30 freq × 24 dir) y des-loguea bien un valor conocido.

## Flujo de datos

```
ERA5 (serie)    → io_era5.descargar_serie    → Dataset(time) Hs/Tp/Dir → tablero de curvas
ERA5 (espectro) → io_era5.descargar_espectro → Efth(time,freq,dir) ┐
SWAN (espectro) → leer_espectro_temporal     → Efth(time,freq,dir) ┴→ particion_espectral → productos
```

## Manejo de errores

- Sin `~/.cdsapirc` válido → error con instrucciones de configuración; no se
  intenta descargar.
- Espectro sin energía en un paso (ZERO/NODATA) → la partición devuelve lista
  vacía; la serie marca NaN ese paso (no rompe).
- Espectro casi todo NaN (caso del nido NonSt inestable de Coronel) → el producto
  de partición lo reporta como no útil y se omite, igual que hoy hace
  `_nido_util` con el video.

## Dependencias nuevas

- `cdsapi` — cliente del Copernicus CDS para descargar ERA5.
- `scikit-image` — watershed y detección de máximos locales para la partición.

## Fuera de alcance (YAGNI)

- Otras fuentes de descarga (Copernicus Marine, GOW2): no en esta iteración.
- Clasificación multi-swell por procedencia geográfica (tracking de trenes):
  solo se separan familias y se etiquetan sea/swell.
- Comparación modelo vs medición (validación): es otra feature, no entra aquí.
