# Diseño — Batimetría automática → `.bot` SWAN

Fecha: 2026-06-26
Herramienta: Tablero de Oleaje
Estado: aprobado, pendiente de plan de implementación

## Objetivo

Generar el archivo de batimetría `.bot` de un caso SWAN **automáticamente** a
partir de la malla de cómputo, sin que el usuario tenga que conseguir y convertir
la batimetría a mano. Por defecto descarga batimetría global (GEBCO/ETOPO) de la
zona de la malla; opcionalmente usa un raster propio (p. ej. SHOA para la tesis).
Es el insumo que hoy bloquea el flujo "Armar y correr" desde cero.

## Contexto y restricciones

- El `.bot` se lee en `io_swan._construir_dataset`: `bat` plano →
  `np.flipud(bat.reshape(ny, nx))`, con `nx = mxc+1`, `ny = myc+1` nodos, y coords
  `x = xpc + i·dx` (oeste→este), `y = ypc + j·dy` (sur→norte). Para **escribir** el
  `.bot` hay que invertir esa convención: `bat = np.flipud(D).ravel()`, donde
  `D[j,i]` es la profundidad en el nodo (x_i, y_j) con j sur→norte. Se valida por
  *round-trip* en los tests para no entregar un `.bot` espejado.
- La grilla de la batimetría (INPGRID) coincide por defecto con la malla de
  cómputo (CGRID): `swan_builder._completar` ya pone `xpinp=xpc, ypinp=ypc,
  mxinp=mxc, myinp=myc, dxinp=xlenc/mxc, dyinp=ylenc/myc`. El `.bot` generado usa
  esa misma grilla, así que el `.swn` lo consume sin cambios.
- La malla está en **UTM** (metros). El usuario indica la **zona UTM** (campo
  nuevo); con eso se proyecta a lat/lon para muestrear el raster.
- Disponibles: `pyproj` 3.7.2 (proyección), `scipy` 1.15.3 (interpolación),
  `xarray`/`netcdf4` (raster). Verificado que la **descarga por bbox vía ERDDAP
  HTTP funciona** (ETOPO recortado a Reñaca, NetCDF chico).

## Arquitectura

Un módulo motor nuevo (puro, testeable sin red) + integración delgada en la GUI.

```
io_batimetria.py            descarga/lee raster, proyecta, interpola, escribe .bot
gui_swan (Armar y correr)   campo "Zona UTM" + botón "Generar batimetría…"
```

### 1. `io_batimetria.py` — motor

- `epsg_utm(zona) -> int`: `"19S"`→32719, `"18S"`→32718, `"19N"`→32619. Parsea
  número + hemisferio.
- `descargar_raster(lat_min, lat_max, lon_min, lon_max, destino) -> xr.Dataset`:
  baja un recorte de batimetría global por *bounding box* vía ERDDAP HTTP
  (descarga el `.nc` y lo abre; no usa OPeNDAP, que falla con los corchetes de
  ERDDAP). Fuente configurable por constante del módulo; ETOPO1 (`etopo180`)
  confirmado como respaldo estable.
- **Normalización del raster** (clave para que las fuentes sean intercambiables):
  un helper `_normalizar_raster(ds)` renombra las dimensiones a `lat`/`lon` y la
  variable de elevación a `elevation` (acepta `altitude`/`z`/`elevation` y
  `latitude`/`longitude`/`y`/`x`), y ordena `lat`/`lon` ascendentes. ETOPO trae
  `altitude`+`latitude`/`longitude`; GEBCO trae `elevation`+`lat`/`lon`: tras
  normalizar, ambos quedan iguales (`elevation`, m, positivo hacia arriba).
  Tanto `descargar_raster` como `leer_raster_local` devuelven el Dataset ya
  normalizado.
- `leer_raster_local(ruta) -> xr.Dataset`: abre un `.nc` propio (batimetría de
  mayor resolución, SHOA u otra) y lo pasa por `_normalizar_raster`.
- `generar_bot(malla, zona_utm, carpeta, raster=None, nombre="bati.bot") -> (ruta, meta)`:
  1. Construye los nodos de la grilla `(myc+1)×(mxc+1)` en UTM desde
     `malla = {xpc, ypc, xlenc, ylenc, mxc, myc}`.
  2. Proyecta los nodos UTM → lat/lon con `pyproj` (EPSG de `zona_utm`).
  3. Si `raster is None`, calcula el bbox lat/lon de los nodos (+ margen ~0.05°) y
     `descargar_raster`; si se pasó `raster`, lo usa.
  4. Interpola `elevation` en los nodos con
     `scipy.interpolate.RegularGridInterpolator` (ejes lat/lon ascendentes;
     `bounds_error=False`, relleno por vecino más cercano en los bordes).
  5. `depth = −elevation` (convención SWAN: profundidad positiva hacia abajo;
     tierra con `elevation ≥ 0` queda con `depth ≤ 0`, seca).
  6. Escribe el `.bot` con `bat = np.flipud(D).ravel()` (D = grilla de profundidad
     `(ny, nx)`), valores en texto. Devuelve la ruta y `meta` (rango de
     profundidad, nº de nodos, fuente, % de nodos en tierra).

### 2. GUI — formulario "Armar y correr"

- Campo nuevo **"Zona UTM"** (StringVar, default `"19S"`) en la sección de malla.
- Botón **"Generar batimetría…"** junto al campo de batimetría →
  `_generar_batimetria()`:
  1. Lee la malla del formulario (`self.v["xpc"]`, etc.) y la zona; valida números.
  2. Pregunta (checkbox o diálogo) si usar un **archivo local** (`filedialog`) o
     descargar.
  3. Corre `io_batimetria.generar_bot` en un **hilo** (la descarga tarda), con
     avance/resultado en el log de la ventana.
  4. Al terminar, escribe `bati.bot` en la carpeta destino y **rellena el campo de
     batimetría** (`self.bat_archivo`). Reporta en el log el rango de profundidad y
     el % de nodos en tierra (señal de que la malla está bien ubicada).

## Flujo de datos

```
malla (UTM) + zona  → nodos UTM → (pyproj) → nodos lat/lon
                                                  │
   raster None → bbox → descargar_raster ─────────┤
   raster local ──────────────────────────────────┤
                                                  ▼
                       interpolar elevation → depth=−elev → flipud→.bot
                                                  │
                       rellena campo batimetría → construir_swn lo usa
```

## Manejo de errores

- **Sin internet y sin archivo local** → `RuntimeError` con mensaje claro (sugiere
  usar un raster local).
- **Zona UTM inválida** (no parsea) → `ValueError`.
- **Malla fuera de la cobertura del raster** → relleno por vecino más cercano en
  los bordes y aviso en el log (no aborta).
- **Demasiados nodos** (p. ej. > 1e6) → aviso antes de descargar (evita una
  descarga enorme).
- **Mayoría de nodos en tierra** (`depth ≤ 0` en > ~80%) → aviso: probablemente la
  malla o la zona UTM están mal ubicadas.

## Tests (sin red)

- `epsg_utm`: `"19S"→32719`, `"18S"→32718`, `"19N"→32619`; cadena inválida →
  `ValueError`.
- `generar_bot` con un **raster sintético** (Dataset lat/lon con `elevation` = un
  plano inclinado conocido) y una malla chica + zona UTM:
  - el `.bot` tiene exactamente `(mxc+1)·(myc+1)` valores;
  - **round-trip de orientación**: leer el `.bot` con la convención de `io_swan`
    (`flipud(reshape(ny,nx))`) reproduce la grilla `D` de profundidad esperada;
  - `depth = −elevation` en un nodo de prueba (signo correcto).
- La descarga real (`descargar_raster`) **no** se cubre con un test de red; queda
  como verificación manual.

## Fuera de alcance (YAGNI)

- Definir la malla por lat/lon (sigue siendo UTM + zona): otra iteración.
- Parsear cartas SHOA en PDF: el raster local se asume ya en NetCDF lat/lon.
- Suavizado/relleno avanzado de la batimetría (más allá del vecino más cercano en
  bordes).
- Generar el `.bot` de dominios anidados en una sola pasada: cada dominio se hace
  con su propia malla/zona.
